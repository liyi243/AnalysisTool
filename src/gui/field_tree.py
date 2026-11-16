"""字段树面板：以树形展示协议字段（字段/偏移/原始值/解析值）。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QAbstractItemView

from qgdw3762.model import Field, ParsedFrame
from .theme import FIELD_COLORS, TXT_MUTED, ERROR

_KIND_TO_ICON = {
    "start": "▣", "length": "L", "ctrl": "C", "addr": "A", "afn": "F",
    "seq": "S", "data": "◇", "six45": "◆", "cs": "✓", "end": "▣", "err": "!",
}


class FieldTreePanel(QTreeWidget):
    fieldSelected = Signal(object)  # Field

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setColumnCount(4)
        self.setHeaderLabels(["字段", "偏移", "原始值", "解析值"])
        self.setRootIsDecorated(True)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setExpandsOnDoubleClick(True)
        header = self.header()
        header.resizeSection(0, 150)
        header.resizeSection(1, 52)
        header.resizeSection(2, 76)
        self.itemClicked.connect(self._on_item_clicked)
        self._field_map: dict[int, Field] = {}

    def load_frame(self, frame: Optional[ParsedFrame]) -> None:
        self.clear()
        self._field_map.clear()
        if frame is None:
            return
        for top in frame.fields:
            item = self._make_item(top)
            self.addTopLevelItem(item)
        self.expandToDepth(1)

    def _make_item(self, f: Field) -> QTreeWidgetItem:
        color = QColor(FIELD_COLORS.get("err" if f.error else f.kind, FIELD_COLORS["data"]))
        item = QTreeWidgetItem([
            f"{_KIND_TO_ICON.get(f.kind, '·')} {f.name}",
            f"0x{f.offset:02X}",
            f.raw,
            f.display_value(),
        ])
        item.setForeground(0, QBrush(color))
        item.setForeground(2, QBrush(QColor("#A8B8D0")))
        if f.error:
            for c in range(4):
                item.setBackground(c, QBrush(QColor(239, 68, 68, 36)))
        if f.note:
            item.setToolTip(3, f.note)
        self._field_map[id(item)] = f
        for child in f.children:
            item.addChild(self._make_item(child))
        return item

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        f = self._field_map.get(id(item))
        if f is not None:
            self.fieldSelected.emit(f)

    def locate_field(self, target: Optional[Field]) -> None:
        """与字节图联动：展开并高亮目标字段所在行。"""
        found: Optional[QTreeWidgetItem] = None

        def visit(it: QTreeWidgetItem) -> None:
            nonlocal found
            f = self._field_map.get(id(it))
            if f is target:
                found = it
            for i in range(it.childCount()):
                visit(it.child(i))

        for i in range(self.topLevelItemCount()):
            visit(self.topLevelItem(i))
            if found is not None:
                break
        if found is not None:
            self.scrollToItem(found, QAbstractItemView.ScrollHint.PositionAtCenter)
            self.setCurrentItem(found)
