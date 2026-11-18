"""内嵌 DL/T 645-2007 解析（six45.parse_645）回归测试。"""
from conftest import build_645
from qgdw3762.six45 import parse_645

# 表号 123456789012，BCD 低位在前
ADDR = bytes([0x12, 0x90, 0x78, 0x56, 0x34, 0x12])


def _children(f):
    return {c.name: c for c in f.children}


def test_abnormal_response_d6_without_d5():
    """异常应答 = 请求码|C0H（D6=1、D5=0）：不得再误按数据标识解析。

    回归：旧判定额外要求 D5=1，最常见的异常应答帧（D6=1, D5=0）全部漏判，
    ERR 错误信息字被当成数据标识 DI 解析。
    """
    f = parse_645(build_645(ADDR, 0xD1, bytes([0x02, 0x00, 0x00, 0x00]), b""))
    assert f is not None
    assert "异常应答" in f.value
    ch = _children(f)
    assert "错误信息字ERR" in ch
    assert "无请求数据" in ch["错误信息字ERR"].value   # ERR=0x02
    assert "数据标识DI" not in ch


def test_normal_response_naming_unaffected():
    """正常应答（请求码|80H，D6=0）的解析不受异常判定修复影响。

    注：正常应答 D6=0，func_name 保持原样（如『读数据』）；
    关键是不得被误判为异常、DI 命名保持不变。
    """
    f = parse_645(build_645(ADDR, 0x91, bytes([0x10, 0x90, 0x00, 0x00]),
                            bytes([0x78, 0x56])))
    assert f is not None
    assert "读数据" in f.value
    assert "异常应答" not in f.value
    ch = _children(f)
    di = ch["数据标识DI"]
    assert "正向有功总电能" in di.value
    assert "错误信息字ERR" not in ch


def test_min_13_byte_abnormal_frame_parseable():
    """标准异常应答帧 68 L 68 C A(6) ERR CS 16 共 13 字节，必须可解析。

    回归：旧下限 n<14 把最短合法异常应答帧整体拒收（返回 None）。
    """
    body = bytes([0xD1]) + ADDR + bytes([0x02])          # C + A + ERR
    L = len(body) + 1
    cs = sum(body) & 0xFF
    frame = b"\x68" + bytes([L]) + b"\x68" + body + bytes([cs, 0x16])
    assert len(frame) == 13
    f = parse_645(frame)
    assert f is not None
    assert "异常应答" in f.value
    ch = _children(f)
    assert "错误信息字ERR" in ch
    assert "无请求数据" in ch["错误信息字ERR"].value


def test_min_12_byte_frame_without_userdata():
    """结构下限 12 字节（68 L 68 C A(6) CS 16，无用户数据）可解析；11 字节拒收。"""
    body = bytes([0x91]) + ADDR
    L = len(body) + 1
    cs = sum(body) & 0xFF
    frame = b"\x68" + bytes([L]) + b"\x68" + body + bytes([cs, 0x16])
    assert len(frame) == 12
    f = parse_645(frame)
    assert f is not None
    assert "数据标识DI" not in _children(f)              # 无用户数据 → 无 DI 字段
    assert parse_645(frame[:-1]) is None                  # 11 字节：低于结构下限


def test_length_field_mismatch_returns_none():
    """L 与总字节数不符（合法帧总长 = L+4）应返回 None，防止误解析。"""
    frame = bytearray(build_645(ADDR, 0x91, bytes([0x10, 0x90, 0x00, 0x00]),
                                bytes([0x78, 0x56])))
    frame[1] = frame[1] + 1                              # 破坏 L，其余不动
    assert parse_645(bytes(frame)) is None
    frame[1] = frame[1] - 3                              # 反向偏差同样拒收
    assert parse_645(bytes(frame)) is None


def test_cs_failure_flagged():
    """CS 校验失败：标记 error=True 且值含『校验失败』，但帧仍解析。"""
    frame = bytearray(build_645(ADDR, 0xD1, bytes([0x02, 0x00, 0x00, 0x00]), b""))
    frame[-2] ^= 0xFF                                     # 破坏校验码
    f = parse_645(bytes(frame))
    assert f is not None
    assert f.error is True
    assert "校验失败" in f.note
    cs_field = _children(f)["校验码CS"]
    assert cs_field.error is True
    assert "校验失败" in cs_field.value
