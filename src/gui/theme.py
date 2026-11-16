"""GUI 主题：调色板常量 + 全局 QSS 样式表。

所有颜色/字号/圆角遵循《docs/04-UI设计说明书.md》的设计 Token。
"""
from __future__ import annotations

# ── 设计 Token（与 04-UI设计说明书.md 2.1 节一致） ─────────────────────────
BG_BASE = "#0B1220"          # 窗口底色
BG_PANEL = "#111A2C"         # 面板底色
BG_PANEL2 = "#16213A"        # 输入框/悬浮层
BG_HEX = "#0D1526"           # 字节网格底
BORDER = "#23304A"           # 描边/分隔线
TXT = "#E6EDF7"              # 主文本
TXT2 = "#94A3B8"             # 次要文本
TXT_MUTED = "#64748B"        # 弱化文本
ACCENT = "#3B82F6"           # 主色
ACCENT_HOVER = "#60A5FA"
SUCCESS = "#22C55E"
WARNING = "#F59E0B"
ERROR = "#EF4444"
VIOLET = "#A78BFA"

# 字节映射图字段配色（04-UI设计说明书.md 2.2 节）
FIELD_COLORS = {
    "start": "#64748B",   # 起始符
    "length": "#C084FC",  # 长度域
    "ctrl": "#FBBF24",    # 控制码
    "addr": "#38BDF8",    # 地址域
    "afn": "#4ADE80",     # AFN
    "seq": "#2DD4BF",     # 帧序域
    "data": "#60A5FA",    # 数据单元
    "six45": "#F472B6",   # 内嵌 645
    "cs": "#FB7185",      # 校验码
    "end": "#64748B",     # 结束符
    "err": "#EF4444",     # 异常
}
FIELD_LEGEND = {
    "start": "起始符",
    "length": "长度域L",
    "ctrl": "控制域C",
    "addr": "地址域A",
    "afn": "AFN/DT",
    "seq": "信息域R",
    "data": "数据单元",
    "six45": "内嵌645报文",
    "cs": "校验码CS",
    "end": "结束符",
    "err": "异常",
}

FONT_UI = '"Microsoft YaHei UI"'
FONT_MONO = '"Cascadia Mono", "Consolas", "Courier New"'


def build_qss() -> str:
    return f"""
/* ===== 全局 ===== */
QMainWindow, QDialog {{ background: {BG_BASE}; }}
QWidget {{
    background: transparent;
    color: {TXT};
    font-family: {FONT_UI};
    font-size: 12.5px;
}}
QToolTip {{
    background: {BG_PANEL2}; color: {TXT};
    border: 1px solid {ACCENT}; border-radius: 6px; padding: 6px 8px;
    font-size: 12px;
}}

/* ===== 面板（objectName=panel） ===== */
QFrame#panel {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#panelTitle {{
    color: {TXT}; font-size: 13px; font-weight: 600;
    letter-spacing: 0.5px;
}}
QLabel#mutedText {{ color: {TXT_MUTED}; font-size: 12px; }}
QLabel#accentText {{ color: {ACCENT_HOVER}; font-weight: 600; }}
QLabel#successText {{ color: {SUCCESS}; font-weight: 600; }}
QLabel#warningText {{ color: {WARNING}; font-weight: 600; }}
QLabel#errorText {{ color: {ERROR}; font-weight: 600; }}
QLabel#brandTitle {{
    color: {TXT}; font-size: 15px; font-weight: 700;
}}
QLabel#brandDot {{
    color: {ACCENT}; font-size: 16px; font-weight: 700;
}}
QLabel#versionChip {{
    color: {TXT2}; background: {BG_PANEL2};
    border: 1px solid {BORDER}; border-radius: 9px; padding: 2px 10px;
    font-size: 11px;
}}

/* ===== 按钮 ===== */
QPushButton {{
    background: {BG_PANEL2}; color: {TXT};
    border: 1px solid {BORDER}; border-radius: 8px;
    padding: 7px 14px;
}}
QPushButton:hover {{ background: #1D2B47; border-color: #2F4066; }}
QPushButton:pressed {{ padding-top: 8px; padding-bottom: 6px; }}
QPushButton:disabled {{ color: {TXT_MUTED}; background: {BG_PANEL}; }}
QPushButton#btnPrimary {{
    background: {ACCENT}; border: none; color: white; font-weight: 600;
    padding: 9px 16px;
}}
QPushButton#btnPrimary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#btnPrimary:pressed {{ background: #2563EB; }}
QPushButton#btnPrimary:disabled {{ background: #1E3A6E; color: #6B8CC7; }}
QPushButton#btnSegment {{
    background: transparent; border: 1px solid {BORDER};
    color: {TXT2}; border-radius: 8px; padding: 6px 14px;
}}
QPushButton#btnSegment:checked {{
    background: {ACCENT}; border-color: {ACCENT}; color: white; font-weight: 600;
}}
QPushButton#btnSegment:hover:!checked {{ background: {BG_PANEL2}; color: {TXT}; }}

/* ===== 输入 ===== */
QPlainTextEdit, QLineEdit, QSpinBox {{
    background: {BG_PANEL2}; color: {TXT};
    border: 1px solid {BORDER}; border-radius: 8px;
    padding: 6px 8px;
    selection-background-color: {ACCENT};
}}
QPlainTextEdit:focus, QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QPlainTextEdit[invalid="true"] {{ border: 1px solid {ERROR}; }}
QPlainTextEdit {{ font-family: {FONT_MONO}; font-size: 12.5px; }}

QComboBox {{
    background: {BG_PANEL2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 5px 10px; color: {TXT};
}}
QComboBox:hover {{ border-color: #2F4066; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{
    image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {TXT2}; margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {BG_PANEL2}; border: 1px solid {BORDER};
    selection-background-color: rgba(59,130,246,60); outline: none;
}}

/* ===== 表格 ===== */
QTableWidget, QTreeView, QTreeWidget {{
    background: {BG_PANEL};
    border: 1px solid {BORDER}; border-radius: 8px;
    gridline-color: {BORDER};
    outline: none;
    alternate-background-color: #0F1830;
}}
QTableWidget {{
    font-family: {FONT_MONO}; font-size: 12px;
}}
QHeaderView::section {{
    background: {BG_PANEL}; color: {TXT2};
    border: none; border-bottom: 1px solid {BORDER};
    padding: 7px 8px; font-weight: 600; font-family: {FONT_UI}; font-size: 12px;
}}
QTableWidget::item, QTreeWidget::item {{
    padding: 4px 6px; border: none;
}}
QTableWidget::item:selected, QTreeWidget::item:selected {{
    background: rgba(59,130,246,70); color: {TXT};
}}
QTableWidget::item:hover, QTreeWidget::item:hover {{ background: rgba(59,130,246,30); }}
QTreeWidget::branch {{ background: transparent; }}

/* ===== 滚动条 ===== */
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: #334155; border-radius: 4px; min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{ background: #475569; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #334155; border-radius: 4px; min-width: 40px; }}
QScrollBar::handle:horizontal:hover {{ background: #475569; }}

/* ===== 分割条 ===== */
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

/* ===== 菜单 ===== */
QMenu {{
    background: {BG_PANEL2}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 5px;
}}
QMenu::item {{ padding: 6px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: rgba(59,130,246,60); }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

/* ===== 状态栏 ===== */
QStatusBar {{
    background: {BG_PANEL}; border-top: 1px solid {BORDER};
    color: {TXT2}; font-size: 12px;
}}
QStatusBar::item {{ border: none; }}

/* ===== 徽章胶囊 ===== */
QLabel#badgeDown {{
    color: {VIOLET}; background: rgba(167,139,250,28);
    border: 1px solid rgba(167,139,250,90); border-radius: 9px;
    padding: 1px 8px; font-size: 11px; font-weight: 600;
}}
QLabel#badgeUp {{
    color: {SUCCESS}; background: rgba(34,197,94,28);
    border: 1px solid rgba(34,197,94,90); border-radius: 9px;
    padding: 1px 8px; font-size: 11px; font-weight: 600;
}}
QLabel#badgeWarn {{
    color: {WARNING}; background: rgba(245,158,11,24);
    border: 1px solid rgba(245,158,11,80); border-radius: 9px;
    padding: 1px 8px; font-size: 11px; font-weight: 600;
}}
"""
