"""GUI 冒烟测试（离屏）：模拟用户操作路径，排查闪退。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gui.main_window import MainWindow  # noqa: E402
from gui.theme import build_qss  # noqa: E402
import scripts.verify_user_frames as vf  # noqa: E402

USER_SEQ = "\n".join(h for _, _, h in vf.PAIRS)

EDGE_CASES = [
    ("空输入", ""),
    ("纯噪声", "AA BB CC DD EE FF " * 30),
    ("DT=0000", "68 0f 00 41 00 00 ff 00 00 00 10 00 00 51 16"),
    ("L=FFFF截断", "68 FF FF 41 00 00"),
    ("畸形DT1=0", "68 0f 00 41 00 00 ff 00 00 00 10 00 00 51 16 68 0f 00 41"),
    ("未知AFN=AB", "68 0f 00 41 00 00 ff 00 00 00 ab 01 00 05 16".replace("05", "E0")),
    ("超长噪声混合", USER_SEQ + " 00 " * 200 + USER_SEQ),
]


def wait_worker(win: MainWindow, timeout_ms: int = 60000) -> bool:
    """可靠等待后台解析线程结束（轮询 + 派发事件），返回是否在超时内完成。"""
    import time
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    t0 = time.monotonic()
    while win._worker is not None and win._worker.isRunning():
        app.processEvents()
        if (time.monotonic() - t0) * 1000 > timeout_ms:
            return False
        time.sleep(0.01)
    # 再泵一轮事件，确保 succeeded 信号（含 _apply_result）处理完毕
    for _ in range(10):
        app.processEvents()
    return True


def timed_parse(win: MainWindow, label: str) -> float:
    """触发解析并等待完成，返回耗时 ms。"""
    import time
    t0 = time.monotonic()
    win.on_parse()
    ok = wait_worker(win)
    ms = (time.monotonic() - t0) * 1000
    assert ok, f"{label}: 解析超时"
    print(f"[T] {label}: {ms:.0f} ms · 帧={win.table.rowCount()}")
    return ms


def main() -> int:
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss())
    win = MainWindow()
    win.resize(1440, 900)
    win.show()
    app.processEvents()
    print("[1] 启动+启动样例 OK")

    # 用户序列：多帧解析 + 组帧面板 + 会话点击
    win.input.set_mode(1)
    win.input.set_text(USER_SEQ)
    timed_parse(win, "用户18帧")
    flow_top = win.flow_panel.topLevelItemCount()
    print(f"[2] 用户18帧解析 OK · 流程段顶层 {flow_top} 项")
    assert flow_top >= 3, "组帧面板应有多个流程段"
    # 点击每个会话
    def visit(it):
        yield it
        for i in range(it.childCount()):
            yield from visit(it.child(i))
    clicked = 0
    for t in range(win.flow_panel.topLevelItemCount()):
        for item in visit(win.flow_panel.topLevelItem(t)):
            win.flow_panel._on_click(item, 0)
            app.processEvents()
            clicked += 1
    print(f"[3] 会话点击 {clicked} 次 OK")

    # 帧逐行切换
    for r in range(win.table.rowCount()):
        win.table.selectRow(r)
        app.processEvents()
    print(f"[4] 帧切换 {win.table.rowCount()} 行 OK")

    # 边界输入
    for name, text in EDGE_CASES:
        win.input.set_mode(1 if name != "空输入" else 0)
        win.input.set_text(text)
        win.on_parse()
        assert wait_worker(win), f"边界『{name}』解析超时"
        n = win.table.rowCount()
        print(f"[5] 边界『{name}』OK · 帧数={n}")

    # 版本切换（2013/2019）
    win.input.set_text(USER_SEQ)
    win._ver_combo.setCurrentIndex(1)
    assert wait_worker(win), "2013 重解析超时"
    win._ver_combo.setCurrentIndex(0)
    assert wait_worker(win), "2019 重解析超时"
    print("[6] 版本切换 2013↔2019 OK")

    # 导出
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        from app_svc import exporter
        p1 = exporter.export_json(win._result, str(Path(td) / "r.json"))
        p2 = exporter.export_text(win._result, str(Path(td) / "r.txt"))
        print(f"[7] 导出 OK · json={p1.stat().st_size}B txt={p2.stat().st_size}B")

    # 大文本（可靠等待 worker 完成，报告真实帧数与耗时）
    big = (USER_SEQ + "\n") * 300
    win.input.set_mode(1)
    win.input.set_text(big)
    ms = timed_parse(win, f"大输入({len(big)//1024}KB→预期5400帧)")
    assert win.table.rowCount() == 5400, f"期望 5400 帧，实际 {win.table.rowCount()}"
    print(f"[8] 大输入 OK · 5400 帧 · 总耗时 {ms:.0f} ms（含解析+表格填充+组帧）")

    # 引擎纯解析性能（不含 UI）
    import time as _t
    from app_svc.pipeline import parse_text as _pt
    t0 = _t.perf_counter()
    r = _pt(big)
    print(f"[T] 引擎纯解析 5400 帧: {(_t.perf_counter()-t0)*1000:.0f} ms")

    # 截图
    win.table.selectRow(1)
    app.processEvents()
    win.grab().save(str(ROOT / "docs" / "screenshots" / "flow.png"))
    print("[9] 流程面板截图 saved flow.png")
    print("SMOKE ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
