"""程序入口。

用法：
    python src/main.py            # 启动 GUI
    python src/main.py --selftest # 运行内置样例自测（打包后验证用）
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# 将 src 目录加入 sys.path，保证包导入（qgdw3762/gui/app_svc）
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# 版本号与产品名统一定义在 app_svc 包（GUI 状态栏 / 关于 / 导出共用）
from app_svc import APP_TITLE, APP_VERSION


def _install_crash_hook() -> None:
    """全局异常钩子：未捕获异常写入 logs/crash-*.log 并弹窗提示。

    背景：PyInstaller --windowed 模式下 stdout/stderr 为 None，未捕获异常
    被直接吞掉导致"闪退"且无任何痕迹。此钩子保证每次异常都留有日志，
    便于用户回报问题后精确定位。
    """
    import datetime
    import traceback

    def _log_dir() -> Path:
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).resolve().parent      # exe 旁边
        else:
            base = Path(__file__).resolve().parent.parent      # 项目根
        d = base / "logs"
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            d = Path(".")                                     # 兜底当前目录
        return d

    def _hook(etype, value, tb) -> None:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = "".join(traceback.format_exception(etype, value, tb))
        entry = f"\n==== {stamp} · {APP_TITLE} v{APP_VERSION} ====\n{text}"
        try:
            log = _log_dir() / f"crash-{datetime.date.today():%Y%m%d}.log"
            with open(log, "a", encoding="utf-8") as f:
                f.write(entry)
        except OSError:
            pass
        sys.__stderr__ and sys.__stderr__.write(entry)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                box = QMessageBox()
                box.setIcon(QMessageBox.Icon.Critical)
                box.setWindowTitle("程序异常")
                box.setText(f"发生未处理异常：{value}")
                box.setDetailedText(text)
                box.exec()
        except Exception:
            pass

    sys.excepthook = _hook


def run_selftest() -> int:
    """内置样例自测：解析全部样例帧并输出结果。"""
    import os
    import sys
    # windowed 打包（console=False）下 sys.stdout 为 None，print 会抛异常；
    # 重定向到空设备，保证打包后的 exe --selftest 仍可用退出码验证
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    from qgdw3762.samples import SAMPLES, SAMPLE_LOG, sample_report
    ok = True
    for name, hexs in SAMPLES:
        from app_svc.pipeline import parse_text
        result = parse_text(hexs)
        n = len(result.frames)
        bad = sum(1 for f in result.frames if not f.valid)
        print(f"[{name}] 帧={n} 校验失败={bad}")
        for fr in result.frames:
            print(f"   {fr.direction} len={fr.length} {fr.summary}")
        if bad:
            ok = False
    # 组帧（流程会话）自检：日志样例 3 帧应组出 ≥2 会话
    from app_svc.pipeline import parse_text as _pt
    from qgdw3762.flows import group_frames
    _frames = _pt(SAMPLE_LOG).frames
    _sessions, _groups = group_frames(_frames)
    print(f"[组帧自检] {len(_frames)} 帧 → {len(_sessions)} 会话 / {len(_groups)} 流程段")
    if len(_sessions) < 2:
        print("组帧自检失败：日志样例应至少形成 2 个会话")
        ok = False
    print(sample_report())
    print("SELFTEST", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def run_gui() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow
    from gui.theme import build_qss

    _install_crash_hook()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss())
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)

    win = MainWindow()
    win.setWindowTitle(f"{APP_TITLE} v{APP_VERSION}")
    win.resize(1440, 900)
    win.show()
    return app.exec()


def main() -> int:
    args = sys.argv[1:]
    if "--selftest" in args:
        return run_selftest()
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
