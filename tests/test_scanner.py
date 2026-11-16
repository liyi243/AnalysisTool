"""帧扫描器测试。"""
from conftest import build_frame
from qgdw3762.scanner import scan_frames

D1 = "68 10 00 41 01 00 FF 00 00 00 04 01 00 00 46 16"
U2 = "68 10 00 C1 01 00 FF 00 00 00 00 02 00 00 C3 16"


def _hex(s: str) -> bytes:
    return bytes.fromhex(s.replace(" ", ""))


def test_single_frame():
    cands, warns = scan_frames(_hex(D1))
    assert len(cands) == 1
    assert cands[0].reason == ""
    assert len(cands[0].data) == 16


def test_multi_with_noise():
    data = b"\x55\xAA" + _hex(D1) + b"\x00\x99" + _hex(U2)
    cands, warns = scan_frames(data)
    assert len(cands) == 2
    assert all(c.reason == "" for c in cands)
    assert cands[0].start == 2
    assert cands[1].start == 2 + 16 + 2


def test_bad_cs_flagged():
    frame = bytearray(_hex(D1))
    frame[-2] ^= 0x01            # 破坏 CS
    cands, warns = scan_frames(bytes(frame))
    assert len(cands) == 1
    assert "CS 校验失败" in cands[0].reason


def test_truncated_tail():
    data = _hex(D1)[:-3]         # 末尾截断
    cands, warns = scan_frames(data)
    assert cands == []
    assert any("不完整" in w for w in warns)


def test_3761_shape_warning():
    # 376.1 形态：68 L L 68 C ... CS 16（L 低 2 位=10B，L 重复两次）
    payload = bytes([0x0B, 0x03, 0x44, 0x04, 0x00, 0x00, 0x02, 0x71, 0x00,
                     0x00, 0x01, 0x00])
    L1 = len(payload)
    Lfield = (L1 << 2) | 0x02
    cs = sum(payload) & 0xFF
    frame = (b"\x68" + Lfield.to_bytes(2, "little") + Lfield.to_bytes(2, "little")
             + b"\x68" + payload + bytes([cs, 0x16]))
    cands, warns = scan_frames(frame)
    assert cands == []
    assert any("376.1" in w for w in warns)


def test_adhesive_frames():
    # 粘包：两帧紧连
    data = _hex(D1) + _hex(U2)
    cands, _ = scan_frames(data)
    assert len(cands) == 2


def test_no_frame():
    cands, warns = scan_frames(b"\x01\x02\x03\x04" * 10)
    assert cands == []
