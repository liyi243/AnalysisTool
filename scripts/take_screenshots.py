"""批量截图验收脚本（离屏渲染）。

产出 docs/screenshots/：main.png / multi.png / invalid.png / six45.png / file.png
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app_svc.pipeline import parse_text  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from gui.theme import build_qss  # noqa: E402

SHOTS = ROOT / "docs" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)

# 程序化构造演示帧（自动算 CS，保证合法）
def build_frame(c: int, r: bytes, afn: int, dt1: int, dt2: int,
                du: bytes = b"", addr: bytes = b"") -> bytes:
    user = bytes(r) + bytes(addr) + bytes([afn, dt1, dt2]) + bytes(du)
    L = len(user) + 6
    body = bytes([c]) + user
    return (b"\x68" + L.to_bytes(2, "little") + body
            + bytes([sum(body) & 0xFF, 0x16]))


def build_645(addr: bytes, c: int, di: bytes, data: bytes) -> bytes:
    body = bytes([c]) + bytes(addr) + bytes(di) + bytes(data)
    return (b"\x68" + bytes([len(body) + 1]) + b"\x68" + body
            + bytes([sum(body) & 0xFF, 0x16]))


def _fmt(data: bytes) -> str:
    return data.hex(" ").upper()


METER = bytes([0x12, 0x90, 0x78, 0x56, 0x34, 0x12])          # 表号 123456789012
F645 = build_645(METER, 0x91, bytes([0x10, 0x90, 0x00, 0x00]),
                 bytes([0x78, 0x56]))                        # 读正向有功总电能应答
SIX45_FRAME = _fmt(build_frame(
    0x83, b"\x04\x00\x00\x00\x00\x32", 0xF1, 0x01, 0x00,
    du=bytes([0x02]) + len(F645).to_bytes(2, "little") + F645,
    addr=METER + b"\x00" * 6))
# CS 错误帧（D1 校验位翻转）
BAD_CS = _fmt(bytes.fromhex("68100041010" + "0FF000000040100004616")[:-2]
              + bytes([0x46 ^ 0x01]) + b"\x16")


def snap(win: MainWindow, name: str, row: int | None = None) -> None:
    app.processEvents()
    if row is not None:
        win.table.selectRow(row)
        app.processEvents()
    win.grab().save(str(SHOTS / name))
    print("saved", name)


def main() -> None:
    global app
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss())
    win = MainWindow()
    win.resize(1440, 900)
    win.show()
    snap(win, "main.png")

    # 多帧混流
    win.input.set_mode(1)
    win.input.set_text(
        "55 AA 68 0F 00 41 01 00 FF 00 00 00 03 01 00 45 16 00 68 10 00 C1 "
        "01 00 FF 00 00 00 00 02 00 00 C3 16 68 15 00 C1 01 00 FF 00 00 00 "
        "00 01 00 00 00 00 00 00 00 C2 16")
    win.on_parse()
    snap(win, "multi.png", row=1)

    # 异常帧诊断
    win.input.set_mode(0)
    win.input.set_text(BAD_CS)
    win.on_parse()
    snap(win, "invalid.png")

    # 内嵌 645
    win.input.set_text(SIX45_FRAME)
    win.on_parse()
    snap(win, "six45.png")

    # 文件解析
    log = ROOT / "samples" / "示例日志.txt"
    log.write_text(
        "2026-11-17 09:12:01.102 [下行] 68 0F 00 41 01 00 FF 00 00 00 03 01 00 45 16   // 查询厂商代码\n"
        "2026-11-17 09:12:01.350 [上行] 68 15 00 C1 01 00 FF 00 00 00 00 01 00 00 00 00 00 00 00 C2 16  // 确认\n"
        "2026-11-17 09:12:05.220 [下行] 68 10 00 41 01 00 FF 00 00 00 04 01 00 00 46 16   // 链路检测\n",
        encoding="utf-8")
    win.input.set_mode(2)
    win.input.load_file(str(log))
    app.processEvents()
    snap(win, "file.png")

    print("ALL SHOTS DONE")


if __name__ == "__main__":
    main()
