"""输入面板：单帧 / 多帧 / 文件 三种输入模式。"""
from __future__ import annotations

import os
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from gui.theme import TXT_MUTED, TXT2, BORDER

_MODES = [("单帧", 0), ("多帧", 1), ("文件", 2)]

PLACEHOLDER = (
    "粘贴 376.2 报文 hex，例如：\n\n"
    "68 10 00 41 01 00 FF 00 00 00 04 01 00 00 46 16\n\n"
    "自动忽略空格 / 换行 / 注释 / 时间戳"
)

FILE_FILTERS = "报文/文本文件 (*.txt *.log *.hex *.csv *.dat *.bin);;所有文件 (*)"


class InputPanel(QWidget):
    """左侧输入面板（含模式切换、hex 编辑器、文件选择、操作按钮）。"""

    parseRequested = Signal()                 # 点击解析
    fileChosen = Signal(str)                  # 选中文件路径
    modeChanged = Signal(int)                 # 0单帧 1多帧 2文件
    clearRequested = Signal()

    def __init__(self, sample_provider: Callable[[], list[tuple[str, str]]],
                 parent: Optional[QWidget] = None) -> None:
        """sample_provider 返回 [(名称, hex文本), ...] 供示例菜单。"""
        super().__init__(parent)
        self.setFixedWidth(360)
        self.setObjectName("panel")
        self._sample_provider = sample_provider
        self._file_path: str = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("◈ 输入")
        title.setObjectName("panelTitle")
        root.addWidget(title)

        # 模式分段控件
        seg_row = QHBoxLayout()
        seg_row.setSpacing(0)
        self._seg_group = QButtonGroup(self)
        self._seg_group.setExclusive(True)
        self._seg_buttons: list[QPushButton] = []
        for i, (name, _mid) in enumerate(_MODES):
            b = QPushButton(name)
            b.setObjectName("btnSegment")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if i == 0:
                b.setChecked(True)
            # 相邻圆角拼接成分段控件
            b.setProperty("segIndex", i)
            self._seg_group.addButton(b, i)
            self._seg_buttons.append(b)
            seg_row.addWidget(b)
        self._seg_group.idClicked.connect(
            lambda bid: (self._sync_seg_borders(bid), self.modeChanged.emit(bid)))
        root.addLayout(seg_row)

        # 页面：hex 编辑器 / 文件选择
        self._stack = QStackedWidget()
        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText(PLACEHOLDER)
        # 统计防抖：按键后 300ms 内只算一次，避免每次按键全文扫描
        self._stats_timer = QTimer(self)
        self._stats_timer.setSingleShot(True)
        self._stats_timer.setInterval(300)
        self._stats_timer.timeout.connect(self._update_stats)
        self._editor.textChanged.connect(self._stats_timer.start)   # start() 兼具重启语义
        self._stack.addWidget(self._editor)          # idx 0: hex（单帧/多帧共用）

        file_page = QWidget()
        fp_layout = QVBoxLayout(file_page)
        fp_layout.setContentsMargins(0, 4, 0, 0)
        fp_layout.setSpacing(10)
        self._drop_hint = QLabel(
            "将 .txt / .log / .hex / .csv / .bin\n拖拽到此处，或点击浏览")
        self._drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_hint.setStyleSheet(
            f"color:{TXT2}; border:1px dashed {BORDER}; border-radius:8px; padding:26px 10px;")
        self._drop_hint.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drop_hint.mousePressEvent = lambda _e: self._browse()
        self._file_info = QLabel("未选择文件")
        self._file_info.setObjectName("mutedText")
        self._file_info.setWordWrap(True)
        browse = QPushButton("浏览文件…")
        browse.clicked.connect(self._browse)
        fp_layout.addWidget(self._drop_hint)
        fp_layout.addWidget(self._file_info)
        fp_layout.addWidget(browse)
        fp_layout.addStretch(1)
        self._stack.addWidget(file_page)             # idx 1: 文件
        root.addWidget(self._stack, 1)

        # 统计胶囊
        self._stats = QLabel("0 字节")
        self._stats.setObjectName("mutedText")
        root.addWidget(self._stats)

        # 操作行
        btn_row1 = QHBoxLayout()
        self._btn_sample = QPushButton("示例 ▾")
        self._btn_sample.setToolTip("填充内置样例帧")
        self._btn_sample.clicked.connect(self._show_samples)
        btn_normalize = QPushButton("规范化")
        btn_normalize.setToolTip("去注释/时间戳，统一为大写空格分隔")
        btn_normalize.clicked.connect(self._normalize)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._clear)
        for b in (self._btn_sample, btn_normalize, btn_clear):
            btn_row1.addWidget(b)
        btn_row1.addStretch(1)
        root.addLayout(btn_row1)

        self._btn_parse = QPushButton("▶ 解析（Ctrl+Enter）")
        self._btn_parse.setObjectName("btnPrimary")
        self._btn_parse.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_parse.clicked.connect(self.parseRequested.emit)
        root.addWidget(self._btn_parse)

        root.addStretch(1)
        self._sync_seg_borders(0)

    # ── 模式 ────────────────────────────────────────────────────
    def current_mode(self) -> int:
        return self._seg_group.checkedId()

    def set_mode(self, mode_id: int) -> None:
        if 0 <= mode_id <= 2:
            btn = self._seg_group.button(mode_id)
            if btn:
                btn.setChecked(True)
                self._sync_seg_borders(mode_id)
                self.modeChanged.emit(mode_id)

    def _sync_seg_borders(self, checked_id: int) -> None:
        self._stack.setCurrentIndex(1 if checked_id == 2 else 0)

    # ── 输入内容 ────────────────────────────────────────────────
    def input_text(self) -> str:
        if self.current_mode() == 2:
            try:
                with open(self._file_path, "rb") as fh:
                    data = fh.read()
                try:
                    return data.decode("utf-8", errors="replace")
                except Exception:
                    return ""
            except OSError:
                return ""
        return self._editor.toPlainText()

    def set_text(self, text: str) -> None:
        self._editor.setPlainText(text)

    def _update_stats(self) -> None:
        # 与解析引擎同口径：复用 extract_bytes 提取的字节数（含紧凑 hex 如 "682500"）
        from qgdw3762.textutil import extract_bytes
        data, _ = extract_bytes(self._editor.toPlainText())
        self._stats.setText(f"{len(data)} 字节")

    # ── 文件 ────────────────────────────────────────────────────
    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择报文文件", "", FILE_FILTERS)
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> None:
        try:
            size = os.path.getsize(path)
        except OSError:
            # 拖入后文件被移动/删除：给出提示且不触发解析
            self._file_path = ""
            self._file_info.setText("⚠ 无法读取文件，可能已被移动或删除")
            return
        self._file_path = path
        self._file_info.setText(f"📄 {os.path.basename(path)}\n{size:,} 字节")
        self.fileChosen.emit(path)

    # ── 操作 ────────────────────────────────────────────────────
    def _normalize(self) -> None:
        from qgdw3762.textutil import normalize_hex
        self._editor.setPlainText(normalize_hex(self._editor.toPlainText()))

    def _clear(self) -> None:
        self._file_path = ""
        self._file_info.setText("未选择文件")
        self._editor.clear()
        self.clearRequested.emit()

    def _show_samples(self) -> None:
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        for name, hexs in self._sample_provider():
            act = menu.addAction(name)
            act.setData(hexs)
        act = menu.exec(self._btn_sample.mapToGlobal(
            self._btn_sample.rect().bottomLeft()))
        if act is not None and act.data():
            self._editor.setPlainText(str(act.data()))

    def set_busy(self, busy: bool) -> None:
        self._btn_parse.setEnabled(not busy)
        self._btn_parse.setText("解析中…" if busy else "▶ 解析（Ctrl+Enter）")

    def flash_invalid(self) -> None:
        """输入无效时的视觉反馈。"""
        self._editor.setProperty("invalid", True)
        self._editor.style().unpolish(self._editor)
        self._editor.style().polish(self._editor)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(900, self._unflash)

    def _unflash(self) -> None:
        self._editor.setProperty("invalid", False)
        self._editor.style().unpolish(self._editor)
        self._editor.style().polish(self._editor)
