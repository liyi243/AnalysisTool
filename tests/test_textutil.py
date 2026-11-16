"""输入规范化（textutil.extract_bytes）单元测试。"""
from qgdw3762.textutil import extract_bytes, normalize_hex, is_probably_binary


def test_plain_hex_with_spaces():
    data, _ = extract_bytes("68 25 00 68 0B 16")
    assert data == bytes.fromhex("682500680B16")


def test_compact_hex():
    data, _ = extract_bytes("68250068")
    assert data == bytes.fromhex("68250068")


def test_dash_and_comma_separators():
    data, _ = extract_bytes("68-25-00,68:0B")
    assert data == bytes.fromhex("682500680B")


def test_0x_prefix_and_h_suffix():
    data, _ = extract_bytes("0x68 0x25 68H 0Bh")
    assert data == bytes.fromhex("6825680B")


def test_timestamps_and_comments_removed():
    text = (
        "2026-11-16 10:00:00.123 [RX] 68 25 00 68 0B 16   // 下行读表帧\n"
        "# 注释行\n"
        "2026/11/16 10:00:01 上行: 68 0B 00 68 -- 结束\n"
    )
    data, _ = extract_bytes(text)
    assert data == bytes.fromhex("682500680B16" + "680B0068")


def test_odd_tokens_dropped():
    data, _ = extract_bytes("123 68 25")
    assert data == bytes.fromhex("6825")


def test_lowercase_and_newlines():
    data, _ = extract_bytes("68\n25\n00\n68\n0b\n16\n")
    assert data == bytes.fromhex("682500680B16")


def test_line_map():
    text = "68 25 00\n0B 16\n"
    data, line_map = extract_bytes(text)
    assert len(line_map) == len(data) == 5
    assert line_map[0] == 1 and line_map[4] == 2


def test_normalize_hex_format():
    out = normalize_hex("682500680B16")
    assert out == "68 25 00 68 0B 16"


def test_binary_detect():
    assert is_probably_binary(bytes(range(256)) * 8)
    assert not is_probably_binary(("68 25 00 68 " * 100 + "16\n").encode())
