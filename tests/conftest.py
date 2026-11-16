"""测试工具：按协议规则合成 376.2 帧（自动计算 CS）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def build_frame(c: int, r: bytes, afn: int, dt1: int, dt2: int,
                du: bytes = b"", addr: bytes = b"") -> bytes:
    """addr 为完整地址域（A1[+A2..]+A3）。返回完整帧字节。"""
    user = bytes(r) + bytes(addr) + bytes([afn, dt1, dt2]) + bytes(du)
    L = len(user) + 6
    body = bytes([c]) + user
    cs = sum(body) & 0xFF
    return b"\x68" + L.to_bytes(2, "little") + body + bytes([cs, 0x16])


def build_645(addr_bcd_le: bytes, c: int, di_le: bytes, data: bytes) -> bytes:
    """合成 645-2007 帧：addr 6B BCD 低位在前，di 4B 低位在前。"""
    body = bytes([c]) + bytes(addr_bcd_le) + bytes(di_le) + bytes(data)
    L = len(body) + 1
    cs = sum(body) & 0xFF
    return b"\x68" + bytes([L]) + b"\x68" + body + bytes([cs, 0x16])
