"""流程会话面板：按业务流程分组展示组帧结果，点击会话定位帧列表。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from qgdw3762.flows import Session, group_frames
from qgdw3762.model import ParsedFrame
from .theme import ACCENT_HOVER, SUCCESS, TXT_MUTED, WARNING

FLOW_ACCENT = {  # 流程名 → 显示色（未列出的用默认）
    "模块识别": "#38BDF8",
    "白名单控制": "#C084FC",
    "档案同步": "#4ADE80",
    "从节点注册": "#FBBF24",
    "节点事件上报": "#F472B6",
    "主节点初始化": "#60A5FA",
    "主节点初始化/档案同步": "#60A5FA",
    "点抄/监控": "#2DD4BF",
    "广播流程": "#F59E0B",
}


class FlowTreePanel(QTreeWidget):
    sessionClicked = Signal(object)   # Session

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.itemClicked.connect(self._on_click)
        self._session_map: dict[int, Session] = {}

    def load_frames(self, frames: list[ParsedFrame]) -> None:
        self.clear()
        self._session_map.clear()
        if not frames:
            hint = QTreeWidgetItem(["组帧：多帧交互报文解析后，此处按流程（识别/档案同步/注册等）分组展示"])
            hint.setForeground(0, QBrush(QColor(TXT_MUTED)))
            self.addTopLevelItem(hint)
            return
        sessions, groups = group_frames(frames)
        if len(sessions) <= 1 and len(groups) <= 1:
            hint = QTreeWidgetItem([f"共 {len(frames)} 帧，未形成多帧交互流程"])
            hint.setForeground(0, QBrush(QColor(TXT_MUTED)))
            self.addTopLevelItem(hint)
            return
        for g in groups:
            color = FLOW_ACCENT.get(g.name, ACCENT_HOVER)
            top = QTreeWidgetItem([f"▶ {g.name}（{len(g.sessions)} 步）"])
            top.setForeground(0, QBrush(QColor(color)))
            for s in g.sessions:
                frs = "↔".join(f"#{k + 1}" for k in s.frame_idx)
                mark = ""
                if s.resp_ok is True:
                    mark = "  ✓"
                elif s.resp_ok is False:
                    mark = "  ✗"
                it = QTreeWidgetItem([f"{frs}  {s.label}{mark}"])
                it.setForeground(0, QBrush(QColor("#E6EDF7")))
                if s.resp_ok is False:
                    it.setForeground(0, QBrush(QColor(WARNING)))
                self._session_map[id(it)] = s
                top.addChild(it)
            top.setExpanded(True)
            self.addTopLevelItem(top)

    def _on_click(self, item: QTreeWidgetItem, _col: int) -> None:
        s = self._session_map.get(id(item))
        if s is not None:
            self.sessionClicked.emit(s)
