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

APP_VERSION = "1.0.0"
APP_TITLE = "376.2 协议解析工具"


def run_selftest() -> int:
    """内置样例自测：解析全部样例帧并输出结果。"""
    from qgdw3762.samples import SAMPLES, sample_report
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
    print(sample_report())
    print("SELFTEST", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def run_gui() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow
    from gui.theme import build_qss

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
