"""GUI 无头冒烟测试（QT_QPA_PLATFORM=offscreen）。

覆盖：
- MainWindow 启动样例经后台线程解析、手动 on_parse 结果回填（B1）；
- 状态栏版本标签使用统一常量 APP_VERSION（B3）；
- 输入面板统计 300ms 防抖后与 extract_bytes 同口径（B2）。
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
# 必须在导入 QtWidgets 之前设置 offscreen 平台
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from app_svc import APP_VERSION
from qgdw3762.samples import SAMPLES
from qgdw3762.textutil import extract_bytes

# 模块级唯一 QApplication：真实尝试在 offscreen 平台创建（含控件探测），
# 仅在本机确实不可用时才跳过。
try:
    _app = QApplication.instance() or QApplication(["gui-smoke-test"])
    _probe = QWidget()
    _probe.setWindowTitle("offscreen-probe")
except Exception as e:  # pragma: no cover
    pytest.skip(f"本机 QT_QPA_PLATFORM=offscreen 实测不可用：{e!r}",
                allow_module_level=True)


def _wait_until(cond, timeout_ms: int = 5000) -> bool:
    """在事件循环中轮询等待条件成立（QEventLoop+QTimer），超时返回 False。"""
    loop = QEventLoop()
    ok = [False]

    def check() -> None:
        if cond():
            ok[0] = True
            loop.quit()

    poll = QTimer()
    poll.setInterval(25)
    poll.timeout.connect(check)
    poll.start()
    QTimer.singleShot(timeout_ms, loop.quit)   # 超时兜底（≤5s）
    loop.exec()
    poll.stop()
    return ok[0]


def test_main_window_background_parse_and_stats():
    from gui.main_window import MainWindow

    win = MainWindow()   # __init__ 自动加载启动样例并触发后台解析
    # 等待启动样例后台解析完成：表格出现帧且 worker 已归空
    assert _wait_until(lambda: win.table.rowCount() > 0 and win._worker is None), \
        "启动样例后台解析超时"
    assert len(win._frames) == 1
    assert win._frames[0].valid

    # 填入 SAMPLES[0] 并手动触发解析（与 Ctrl+Enter 同路径）
    win.input.set_text(SAMPLES[0][1])
    win.on_parse()
    assert _wait_until(lambda: win._worker is None and win.table.rowCount() > 0), \
        "解析线程未在超时内完成"
    assert win.table.rowCount() == 1
    assert len(win._frames) == 1
    assert win._frames[0].valid

    # 状态栏版本标签包含统一常量 APP_VERSION
    assert APP_VERSION in win._version_label.text()

    # 统计防抖（300ms）后与 extract_bytes 同口径：SAMPLES[0] 为 16 字节
    data, _ = extract_bytes(SAMPLES[0][1])
    assert len(data) == 16
    assert _wait_until(lambda: win.input._stats.text() == f"{len(data)} 字节"), \
        "统计防抖超时未刷新"

    win.close()   # 触发 closeEvent（worker 已结束，wait() 立即返回）
