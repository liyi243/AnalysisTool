"""主窗口：整体布局与交互编排。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QMainWindow, QMenu, QMessageBox, QScrollArea,
    QSplitter, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout,
    QWidget,
)

from app_svc import APP_TITLE, APP_VERSION, exporter
from app_svc.pipeline import parse_file, parse_text
from gui.field_tree import FieldTreePanel
from gui.hex_viewer import HexByteMapViewer
from gui.input_panel import InputPanel
from gui.theme import (
    ACCENT_HOVER, ERROR, FIELD_COLORS, FIELD_LEGEND, SUCCESS, TXT2, TXT_MUTED,
    WARNING,
)

from qgdw3762.model import ParseResult, ParsedFrame

COLS = ["#", "方向", "长度", "控制码", "通信方式", "AFN", "摘要", "校验"]
DROP_SUFFIXES = {".txt", ".log", ".hex", ".csv", ".dat", ".bin"}


def _panel() -> QFrame:
    f = QFrame()
    f.setObjectName("panel")
    return f


class ParseWorker(QThread):
    """后台解析线程：run() 内调用纯 Python 解析引擎（无线程安全问题），
    结果 / 失败经信号-槽队列化送回 UI 线程，避免大文件解析冻结界面。"""

    succeeded = Signal(object, float)   # (ParseResult, 耗时 ms)
    failed = Signal(str)                # 失败消息（如文件读取 OSError）

    def __init__(self, task: Callable[[], ParseResult], generation: int = 0,
                 source: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._task = task
        self.generation = generation    # 触发本次解析时的代际号
        self.source = source            # 来源标签（文件名，文本输入为空）

    def run(self) -> None:
        t0 = time.perf_counter()
        try:
            result = self._task()
        except OSError as e:
            self.failed.emit(f"读取文件失败：{e}")
            return
        except Exception as e:          # 兜底：引擎异常不应拖垮线程
            self.failed.emit(f"解析失败：{e}")
            return
        ms = (time.perf_counter() - t0) * 1000
        self.succeeded.emit(result, ms)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._result: ParseResult | None = None
        self._frames: list[ParsedFrame] = []
        self._current: ParsedFrame | None = None
        self._worker: ParseWorker | None = None   # 当前后台解析线程
        self._generation = 0                      # 解析代际号：新解析/清空时递增
        self.setAcceptDrops(True)
        self._build_ui()
        self._wire()
        self._load_startup_sample()

    # ── 界面构建 ────────────────────────────────────────────────
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 6)
        root.setSpacing(10)

        root.addWidget(self._build_topbar())
        root.addWidget(self._build_body(), 1)
        self.statusBar().showMessage("就绪")
        ver = QLabel(f"v{APP_VERSION} · Q/GDW 376.2")
        ver.setObjectName("mutedText")
        self.statusBar().addPermanentWidget(ver)
        self._version_label = ver

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(2, 0, 2, 0)
        dot = QLabel("◆")
        dot.setObjectName("brandDot")
        title = QLabel("376.2 协议解析工具")
        title.setObjectName("brandTitle")
        chip = QLabel("协议：Q/GDW 376.2")
        chip.setObjectName("versionChip")
        lay.addWidget(dot)
        lay.addSpacing(6)
        lay.addWidget(title)
        lay.addSpacing(10)
        lay.addWidget(chip)
        lay.addSpacing(12)
        ver_label = QLabel("版本")
        ver_label.setObjectName("mutedText")
        self._ver_combo = QComboBox()
        self._ver_combo.addItem("2019（默认，含 HPLC）", "2019")
        self._ver_combo.addItem("2013（宽带载波）", "2013")
        self._ver_combo.setToolTip("选择协议版本。影响确认帧数据单元长度及通信方式命名等。")
        self._ver_combo.currentIndexChanged.connect(self._on_version_changed)
        lay.addWidget(ver_label)
        lay.addWidget(self._ver_combo)
        lay.addStretch(1)

        self._btn_export = QToolButton()
        self._btn_export.setText("导出 ▾")
        self._btn_export.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self._btn_export)
        menu.addAction("导出 JSON 报告…", self._export_json)
        menu.addAction("导出 TXT 报告…", self._export_txt)
        menu.addSeparator()
        menu.addAction("复制全部解析文本", self._copy_report)
        self._btn_export.setMenu(menu)
        lay.addWidget(self._btn_export)

        btn_about = QToolButton()
        btn_about.setText("关于")
        btn_about.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_about.clicked.connect(self._show_about)
        lay.addWidget(btn_about)
        return bar

    def _build_body(self) -> QWidget:
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)

        self.input = InputPanel(self._samples)
        body.addWidget(self.input)

        right = QSplitter(Qt.Orientation.Vertical)
        right.setChildrenCollapsible(False)

        # ── 帧列表 ──
        list_panel = _panel()
        lp = QVBoxLayout(list_panel)
        lp.setContentsMargins(12, 10, 12, 12)
        lp.setSpacing(8)
        lt_row = QHBoxLayout()
        lt = QLabel("◈ 帧列表")
        lt.setObjectName("panelTitle")
        self._list_hint = QLabel("—")
        self._list_hint.setObjectName("mutedText")
        lt_row.addWidget(lt)
        lt_row.addStretch(1)
        lt_row.addWidget(self._list_hint)
        lp.addLayout(lt_row)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        hh.highlightSections()
        lp.addWidget(self.table)
        right.addWidget(list_panel)

        # ── 字节映射 + 字段树 ──
        detail = QSplitter(Qt.Orientation.Horizontal)
        detail.setChildrenCollapsible(False)

        byte_panel = _panel()
        bp = QVBoxLayout(byte_panel)
        bp.setContentsMargins(12, 10, 12, 12)
        bp.setSpacing(8)
        bt_row = QHBoxLayout()
        bt = QLabel("◈ 字节映射")
        bt.setObjectName("panelTitle")
        self._byte_info = QLabel("—")
        self._byte_info.setObjectName("mutedText")
        self._btn_copy_hex = QToolButton()
        self._btn_copy_hex.setText("复制HEX")
        self._btn_copy_hex.setToolTip("复制当前帧的原始十六进制（空格分隔）")
        self._btn_copy_hex.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_copy_hex.clicked.connect(self._copy_current_hex)
        bt_row.addWidget(bt)
        bt_row.addSpacing(10)
        bt_row.addWidget(self._byte_info)
        bt_row.addStretch(1)
        bt_row.addWidget(self._btn_copy_hex)
        bp.addLayout(bt_row)
        self._legend_label = QLabel("")
        self._legend_label.setWordWrap(True)
        self._legend_label.setTextFormat(Qt.TextFormat.RichText)
        self._legend_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        bp.addWidget(self._legend_label)
        self.hex_viewer = HexByteMapViewer()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.hex_viewer)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        bp.addWidget(scroll, 1)
        detail.addWidget(byte_panel)

        field_panel = _panel()
        fp = QVBoxLayout(field_panel)
        fp.setContentsMargins(12, 10, 12, 12)
        fp.setSpacing(8)
        ft = QLabel("◈ 字段树")
        ft.setObjectName("panelTitle")
        fp.addWidget(ft)
        self.field_tree = FieldTreePanel()
        fp.addWidget(self.field_tree, 1)
        detail.addWidget(field_panel)
        detail.setSizes([720, 480])
        right.addWidget(detail)

        # ── 解析要点 ──
        sum_panel = _panel()
        sp = QVBoxLayout(sum_panel)
        sp.setContentsMargins(12, 10, 12, 12)
        sp.setSpacing(6)
        st_row = QHBoxLayout()
        st = QLabel("◈ 解析要点 / 诊断")
        st.setObjectName("panelTitle")
        self._sum_frame = QLabel("—")
        self._sum_frame.setObjectName("accentText")
        st_row.addWidget(st)
        st_row.addSpacing(10)
        st_row.addWidget(self._sum_frame)
        st_row.addStretch(1)
        sp.addLayout(st_row)
        self._summary = QLabel("解析后在此显示当前帧摘要。")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(f"color:{TXT2};")
        sp.addWidget(self._summary)
        self._diag = QLabel("")
        self._diag.setWordWrap(True)
        sp.addWidget(self._diag)
        right.addWidget(sum_panel)

        right.setSizes([230, 430, 120])
        body.addWidget(self.input)
        body.addWidget(right)
        body.setStretchFactor(1, 1)
        body.setSizes([360, 1050])
        return body

    # ── 信号接线 ────────────────────────────────────────────────
    def _wire(self) -> None:
        self.input.parseRequested.connect(self.on_parse)
        self.input.fileChosen.connect(self._on_file)
        self.input.clearRequested.connect(self._on_clear)
        self.table.currentCellChanged.connect(self._on_row_change)
        self.hex_viewer.byteClicked.connect(self._on_byte_clicked)
        self.field_tree.fieldSelected.connect(self._on_field_selected)

        QShortcut(QKeySequence("Ctrl+Return"), self, self.on_parse)
        QShortcut(QKeySequence("Ctrl+Enter"), self, self.on_parse)
        QShortcut(QKeySequence("Ctrl+L"), self, self.input._clear)
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self.input.set_mode(0))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self.input.set_mode(1))
        QShortcut(QKeySequence("Ctrl+3"), self, lambda: self.input.set_mode(2))

    # ── 样例 ────────────────────────────────────────────────────
    def _samples(self) -> list[tuple[str, str]]:
        try:
            from qgdw3762.samples import SAMPLES
            return SAMPLES
        except ImportError:
            return []

    def _load_startup_sample(self) -> None:
        samples = self._samples()
        if samples:
            self.input.set_text(samples[0][1])
            self.on_parse()

    # ── 解析（后台线程执行，结果经信号回到 UI 线程）─────────────
    def on_parse(self) -> None:
        mode = self.input.current_mode()
        if mode == 2:
            self.on_parse_file()
            return
        text = self.input.input_text()
        if not text.strip():
            self.input.flash_invalid()
            self.statusBar().showMessage("输入为空，请粘贴报文 hex 或选择样例", 4000)
            return
        version = self._current_version()

        def task() -> ParseResult:
            return parse_text(text, protocol_version=version)

        self._start_parse(task)

    def on_parse_file(self) -> None:
        path = getattr(self.input, "_file_path", "")
        if not path:
            self.statusBar().showMessage("请先选择报文文件", 4000)
            return
        version = self._current_version()

        def task() -> ParseResult:
            return parse_file(path, protocol_version=version)   # OSError 由 worker 兜底

        self._start_parse(task, source=Path(path).name)

    def _start_parse(self, task: Callable[[], ParseResult], source: str = "") -> None:
        """启动后台解析线程；运行中重复触发（按钮/Ctrl+Enter）直接忽略。"""
        if self._worker is not None and self._worker.isRunning():
            self.statusBar().showMessage("正在解析中，请稍候…", 3000)
            return
        self._generation += 1
        worker = ParseWorker(task, generation=self._generation, source=source)
        worker.succeeded.connect(self._on_parse_succeeded)
        worker.failed.connect(self._on_parse_failed)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        self.input.set_busy(True)
        worker.start()

    def _on_parse_succeeded(self, result: ParseResult, ms: float) -> None:
        worker = self.sender()
        if worker is not self._worker:
            return                          # 旧线程的迟到结果，已有新解析接替
        self._worker = None
        self.input.set_busy(False)
        if worker.generation != self._generation:
            return                          # 已过期（清空/更新解析），不回填界面
        self._apply_result(result, ms, source=worker.source)

    def _on_parse_failed(self, message: str) -> None:
        worker = self.sender()
        if worker is not self._worker:
            return
        self._worker = None
        self.input.set_busy(False)
        if worker.generation != self._generation:
            return
        self.statusBar().showMessage(message, 5000)

    def closeEvent(self, event) -> None:  # noqa: N802
        """窗口关闭前等待后台线程结束，避免 "QThread: Destroyed while running"。"""
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait()
        super().closeEvent(event)

    def _on_file(self, path: str) -> None:
        self.on_parse_file()

    def _apply_result(self, result: ParseResult, ms: float, source: str = "") -> None:
        self._result = result
        self._frames = result.frames
        st = result.stats
        self.table.setRowCount(len(self._frames))
        for i, fr in enumerate(self._frames):
            self._fill_row(i, fr)
        self._list_hint.setText(
            f"{st.get('total', 0)} 帧（上行 {st.get('up', 0)} / 下行 {st.get('down', 0)}）"
            + (f" · 异常 {st.get('invalid', 0)}" if st.get("invalid") else ""))
        if self._frames:
            self.table.selectRow(0)
            self._show_frame(self._frames[0])   # 行号未变化时信号不触发，显式刷新
        else:
            self._show_frame(None)
        if result.warnings:
            self._diag.setText("⚠ " + "；".join(result.warnings))
            self._diag.setStyleSheet(f"color:{WARNING};")
        else:
            self._diag.setText("")
        prefix = f"{source} · " if source else ""
        if st.get("total"):
            msg = f"{prefix}解析完成 · {st['total']} 帧 · 耗时 {ms:.0f} ms"
            if st.get("invalid"):
                self.statusBar().showMessage(msg + f" · 校验失败 {st['invalid']}", 8000)
            else:
                self.statusBar().showMessage(msg, 8000)
        else:
            self.statusBar().showMessage(f"{prefix}未检测到有效帧 · 耗时 {ms:.0f} ms", 8000)

    def _fill_row(self, row: int, fr: ParsedFrame) -> None:
        def item(text: str, color: str | None = None, mono: bool = False) -> QTableWidgetItem:
            it = QTableWidgetItem(text)
            if color:
                it.setForeground(QBrush(QColor(color)))
            return it

        if fr.direction.startswith("下行"):
            dir_it = item("↓ 下行", "#A78BFA")
        elif fr.direction.startswith("上行"):
            dir_it = item("↑ 上行", SUCCESS)
        else:
            dir_it = item("—", TXT_MUTED)
        ctrl = f"{fr.ctrl_byte:02X}" if fr.ctrl_byte is not None else "-"
        comm_name = (fr.ctrl_name or "").split("·")[-1] if fr.ctrl_byte is not None else "-"
        afn = f"{fr.afn_byte:02X} {fr.afn_name}" if fr.afn_byte is not None else "-"
        summary = fr.summary or ("；".join(fr.errors) if fr.errors else "")
        check = item("✓ 通过", SUCCESS) if fr.valid else item("✗ 失败", ERROR)
        values = [item(str(row + 1), TXT_MUTED), dir_it, item(str(fr.length)),
                  item(ctrl), item(comm_name), item(afn), item(summary), check]
        for c, v in enumerate(values):
            self.table.setItem(row, c, v)

    # ── 帧详情 ──────────────────────────────────────────────────
    def _on_row_change(self, row: int, _c1: int, _prev_row: int, _c2: int) -> None:
        if 0 <= row < len(self._frames):
            self._show_frame(self._frames[row])

    def _show_frame(self, fr: ParsedFrame | None) -> None:
        self._current = fr
        self.hex_viewer.setFrame(fr)
        self.field_tree.load_frame(fr)
        self._rebuild_legend(fr)
        if fr is None:
            self._byte_info.setText("—")
            self._sum_frame.setText("—")
            self._summary.setText("解析后在此显示当前帧摘要。")
            self._diag.setText("")
            return
        self._byte_info.setText(f"共 {fr.length} 字节")
        self._sum_frame.setText(fr.summary or "")
        if fr.errors:
            self._summary.setText(fr.summary or "")
            self._diag.setText("✗ " + "；".join(fr.errors))
            self._diag.setStyleSheet(f"color:{ERROR};")
        else:
            self._summary.setText(fr.summary or "")
            self._diag.setText("✓ 帧结构与校验和均正确")
            self._diag.setStyleSheet(f"color:{SUCCESS};")

    def _rebuild_legend(self, fr: ParsedFrame | None) -> None:
        """图例：单条富文本 QLabel，自动换行，避免溢出重叠。"""
        if fr is None:
            html = f"<span style='color:{TXT_MUTED};'>图例将在此显示</span>"
        else:
            kinds: list[str] = []
            for f in fr.iter_fields():
                k = "err" if f.error else f.kind
                if k not in kinds:
                    kinds.append(k)
            chips = []
            for k in kinds:
                color = FIELD_COLORS.get(k, "#94A3B8")
                chips.append(f"<span style='color:{color};'>● {FIELD_LEGEND.get(k, k)}</span>")
            html = "&nbsp;&nbsp;".join(chips) if chips else \
                f"<span style='color:{TXT_MUTED};'>图例将在此显示</span>"
        self._legend_label.setText(html)

    def _on_byte_clicked(self, idx: int) -> None:
        if self._current is None:
            return
        f = self._current.field_at(idx)
        if f is not None:
            self.field_tree.locate_field(f)
            self.hex_viewer.highlightField(f)

    def _on_field_selected(self, f) -> None:
        self.hex_viewer.highlightField(f)

    # ── 导出 ────────────────────────────────────────────────────
    def _require_result(self) -> ParseResult | None:
        if self._result is None or not self._result.frames:
            self.statusBar().showMessage("暂无解析结果，请先解析报文", 4000)
            return None
        return self._result

    def _export_json(self) -> None:
        result = self._require_result()
        if result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 JSON 报告",
                                              "376.2解析报告.json", "JSON (*.json)")
        if path:
            p = exporter.export_json(result, path)
            self.statusBar().showMessage(f"已导出：{p}", 6000)

    def _export_txt(self) -> None:
        result = self._require_result()
        if result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 TXT 报告",
                                              "376.2解析报告.txt", "Text (*.txt)")
        if path:
            p = exporter.export_text(result, path)
            self.statusBar().showMessage(f"已导出：{p}", 6000)

    def _copy_report(self) -> None:
        result = self._require_result()
        if result is None:
            return
        QApplication.clipboard().setText(exporter.render_text(result))
        self.statusBar().showMessage("解析文本已复制到剪贴板", 4000)


    def _current_version(self) -> str:
        if hasattr(self, "_ver_combo"):
            return self._ver_combo.currentData() or "2019"
        return "2019"

    def _on_version_changed(self, _idx: int = 0) -> None:
        ver = self._current_version()
        busy = self._worker is not None and self._worker.isRunning()
        if self._frames and not busy:
            # 已有解析结果时自动按新版本重解析，避免界面残留旧版本结果造成误读
            self.statusBar().showMessage(
                f"已切换协议版本：Q/GDW 376.2-{ver}，正在按新版本重新解析…", 4000)
            self.on_parse()
        elif self._frames:
            self.statusBar().showMessage(
                f"已切换协议版本：Q/GDW 376.2-{ver}，当前解析完成后请重新解析", 6000)
        else:
            self.statusBar().showMessage(
                f"已切换协议版本：Q/GDW 376.2-{ver}，下次解析生效", 4000)


    def _copy_current_hex(self) -> None:
        if self._current is None or not self._current.raw:
            self.statusBar().showMessage("无当前帧可复制", 3000)
            return
        hexs = " ".join(f"{b:02X}" for b in self._current.raw)
        QApplication.clipboard().setText(hexs)
        self.statusBar().showMessage(f"已复制当前帧 HEX（{len(self._current.raw)} 字节）", 4000)

    def _show_about(self) -> None:
        QMessageBox.information(
            self, "关于",
            f"<b>{APP_TITLE} v{APP_VERSION}</b><br><br>"
            "面向 Q/GDW 376.2《集中器本地通信模块接口协议》的报文解析工具。<br>"
            "支持 2013 / 2019 版本切换、单帧 / 多帧字节流 / 文本文件提取解析，"
            "链路层逐字段拆解、应用层 AFN 数据单元解析（已补充更多解码器）、"
            "内嵌 DL/T 645 报文解析、CS 校验诊断。<br><br>"
            "解析引擎与 GUI 解耦，预留 DLT645 / 376.1 / 698 协议扩展接口。")

    def _on_clear(self) -> None:
        self._generation += 1              # 使在途解析结果作废，不回填界面
        self._result = None
        self._frames = []
        self._current = None
        self.table.setRowCount(0)
        self._show_frame(None)
        self._list_hint.setText("—")
        self.statusBar().showMessage("已清空", 3000)

    # ── 拖拽文件 ────────────────────────────────────────────────
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls and Path(urls[0].toLocalFile()).suffix.lower() in DROP_SUFFIXES:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.input.load_file(path)  # fileChosen 信号会触发解析
