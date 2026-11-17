"""字节映射图控件：按字段着色的 hex 网格（自绘 QWidget）。

- 每行 16 字节，行首 4 位偏移，行尾 ASCII 列；
- 字节颜色按所属协议字段语义着色（FIELD_COLORS）；
- 悬停显示字段 tooltip，点击发射 byteClicked 供字段树联动；
- 高亮指定字段区间（与字段树选中联动）。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from qgdw3762.model import Field, ParsedFrame, KIND_ERR
from gui.theme import BG_HEX, BORDER, FIELD_COLORS, TXT_MUTED, ACCENT, ERROR

_HEX = "0123456789ABCDEF"


class HexByteMapViewer(QWidget):
    """单帧字节网格视图（放在 QScrollArea 内使用）。"""

    byteClicked = Signal(int)  # 参数：帧内字节偏移

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._frame: Optional[ParsedFrame] = None
        self._kinds: list[str] = []          # 每字节语义分组
        self._highlight: Optional[tuple[int, int]] = None  # (offset, length)
        self._hover_idx: int = -1
        self._mono = QFont("Cascadia Mono")
        self._mono.setStyleHint(QFont.StyleHint.Monospace)
        self._mono.setPixelSize(13)
        fm = QFontMetrics(self._mono)
        self._cw = fm.horizontalAdvance("00") + 10   # 字节单元格宽
        self._rh = 26                                 # 行高
        self._margin = 14
        self._offset_w = fm.horizontalAdvance("0000") + 14
        self._ascii_gap = 18
        self.setMouseTracking(True)
        self.setMinimumSize(420, 120)

    # ── 数据装载 ────────────────────────────────────────────────
    def setFrame(self, frame: Optional[ParsedFrame]) -> None:
        self._frame = frame
        self._kinds = []
        self._highlight = None
        self._hover_idx = -1
        if frame is not None and frame.raw:
            self._kinds = ["data"] * len(frame.raw)
            for f in frame.iter_fields():
                kind = "err" if (f.error or f.kind == KIND_ERR) else f.kind
                for i in range(f.offset, min(f.offset + f.length, len(self._kinds))):
                    self._kinds[i] = kind
        self._update_rect()
        self.update()

    def highlightField(self, field: Optional[Field]) -> None:
        self._highlight = None
        if field is not None:
            self._highlight = (field.offset, field.length)
        self.update()

    def _update_rect(self) -> None:
        if self._frame is None or not self._frame.raw:
            self.setMinimumSize(420, 120)
        else:
            rows = (len(self._frame.raw) + 15) // 16
            self.setMinimumSize(420, self._margin * 2 + (rows + 1) * self._rh + 34)
        self.resize(self.sizeHint())

    def sizeHint(self) -> QSize:  # noqa: D102
        if self._frame is None or not self._frame.raw:
            return QSize(420, 120)
        rows = (len(self._frame.raw) + 15) // 16
        w = self._margin * 2 + self._offset_w + 16 * self._cw + self._ascii_gap + 16 * 8 + 20
        return QSize(w, self._margin * 2 + (rows + 1) * self._rh + 30)

    # ── 坐标换算 ────────────────────────────────────────────────
    def _cell_at(self, pos_x: float, pos_y: float) -> int:
        """返回鼠标处字节序号，-1 表示不在字节区。"""
        if self._frame is None or not self._frame.raw:
            return -1
        x0 = self._margin + self._offset_w
        y0 = self._margin + self._rh
        col = int((pos_x - x0 - 2) // self._cw)
        if col < 0 or col > 15:
            return -1
        row = int((pos_y - y0 - 2) // self._rh)
        if row < 0:
            return -1
        idx = row * 16 + col
        return idx if idx < len(self._frame.raw) else -1

    # ── 绘制 ────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(BG_HEX))
        if self._frame is None or not self._frame.raw:
            p.setPen(QColor(TXT_MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "解析后此处将显示按字段着色的字节映射图")
            return

        raw = self._frame.raw
        rows = (len(raw) + 15) // 16
        x0, y0 = self._margin, self._margin
        p.setFont(self._mono)

        # 列号标尺
        p.setPen(QColor(TXT_MUTED))
        ruler_font = QFont(self._mono)
        ruler_font.setPixelSize(10)
        p.setFont(ruler_font)
        for c in range(16):
            cx = x0 + self._offset_w + c * self._cw + 2
            p.drawText(QRect(cx, y0, self._cw - 4, self._rh - 6),
                       Qt.AlignmentFlag.AlignCenter, f"{c:X}".rjust(2))
        y0 += self._rh
        p.setFont(self._mono)

        for r in range(rows):
            y = y0 + r * self._rh
            # 行偏移
            p.setPen(QColor(TXT_MUTED))
            p.drawText(QRect(x0, y + 3, self._offset_w - 10, self._rh - 6),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{r * 16:04X}")
            # 字节
            for c in range(16):
                idx = r * 16 + c
                if idx >= len(raw):
                    break
                cx = x0 + self._offset_w + c * self._cw + 2
                cell = QRect(cx + 1, y + 3, self._cw - 6, self._rh - 6)
                kind = self._kinds[idx] if idx < len(self._kinds) else "data"
                color = QColor(FIELD_COLORS.get(kind, FIELD_COLORS["data"]))
                base = QColor(color)
                base.setAlpha(30)
                if self._highlight:
                    ho, hl = self._highlight
                    if ho <= idx < ho + hl:
                        base = QColor(color)
                        base.setAlpha(72)
                if idx == self._hover_idx:
                    base = QColor(color)
                    base.setAlpha(95)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(base)
                p.drawRoundedRect(cell, 4, 4)
                if kind == "err":
                    pen = QPen(QColor(ERROR))
                    pen.setWidth(1)
                    p.setPen(pen)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(cell, 4, 4)
                p.setPen(color)
                p.drawText(cell, Qt.AlignmentFlag.AlignCenter, f"{raw[idx]:02X}")
            # ASCII 列（提高对比度）
            p.setPen(QColor("#CBD5E1"))
            ax = x0 + self._offset_w + 16 * self._cw + self._ascii_gap
            chars = []
            for c in range(16):
                idx = r * 16 + c
                if idx >= len(raw):
                    break
                b = raw[idx]
                chars.append(chr(b) if 0x20 <= b < 0x7F else "·")
            p.drawText(QRect(ax, y + 3, self.width() - ax - 8, self._rh - 6),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       "".join(chars))

        # 底部提示
        p.setPen(QColor(TXT_MUTED))
        hint_font = QFont(self.font())
        hint_font.setPixelSize(11)
        p.setFont(hint_font)
        p.drawText(QRect(x0, self.height() - 26, self.width() - x0 * 2, 20),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   "悬停查看字段含义 · 点击定位字段树")

    # ── 交互 ────────────────────────────────────────────────────
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        idx = self._cell_at(event.position().x(), event.position().y())
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
        if idx >= 0 and self._frame is not None:
            f = self._frame.field_at(idx)
            if f is not None:
                b = self._frame.raw[idx]
                tip = (f"<b>{f.name}</b><br>偏移 0x{idx:02X} · 原始 0x{b:02X}"
                       + (f"<br>{f.display_value()}" if f.display_value() else ""))
                if f.note:
                    tip += f"<br><span style='color:#94A3B8'>{f.note}</span>"
                from PySide6.QtWidgets import QToolTip
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        else:
            from PySide6.QtWidgets import QToolTip
            QToolTip.hideText()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_idx = -1
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        idx = self._cell_at(event.position().x(), event.position().y())
        if idx >= 0:
            self.byteClicked.emit(idx)
