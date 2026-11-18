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
    # 行号映射使用 array("I") 存储（大文件内存优化）
    from array import array as _array
    assert isinstance(line_map, _array)


def test_colon_hex_not_eaten_by_timestamp():
    # 冒号分隔 hex 不得被时间戳正则吞掉（回归：旧 _TS_TIME_RE 不校验钟点合法性，
    # '68:25:00' 曾被整段删除、'AB:10:20' 只剩 AB）
    data, _ = extract_bytes("68:25:00")
    assert data == bytes.fromhex("682500")

    data, _ = extract_bytes("68:25:00:0B")
    assert data == bytes.fromhex("6825000B")

    data, _ = extract_bytes("AB:10:20")
    assert data == bytes.fromhex("AB1020")


def test_standalone_timestamps_still_removed():
    # 独立时间戳（日志主场景）仍应被剔除
    data, _ = extract_bytes("2026-11-16 10:00:00.123 [RX] 68 25 16")
    assert data == bytes.fromhex("682516")

    data, _ = extract_bytes("10:00 [RX] 68 25")
    assert data == bytes.fromhex("6825")

    data, _ = extract_bytes("23:59:59 68 16")
    assert data == bytes.fromhex("6816")


def test_date_followed_by_colon_hex_not_eaten():
    # 日期后跟冒号分隔 hex：日期本身剔除，但其时间部分不得吞掉合法 hex
    # （回归：旧 _TS_DATE_RE 时间部分不校验钟点，'2026-11-16 68:25:00' 的 68:25 曾被当作时间吞掉）
    data, _ = extract_bytes("2026-11-16 68:25:00")
    assert data == bytes.fromhex("682500")

    # 日期 + 合法钟点时间仍整体剔除
    data, _ = extract_bytes("2026-11-16 10:25 68 25")
    assert data == bytes.fromhex("6825")

    data, _ = extract_bytes("2026年11月16日 10:25:30 [TX] AB CD")
    assert data == bytes.fromhex("ABCD")


def test_streaming_extraction_matches_bulk():
    # 流式逐行提取与整段提取语义一致（parse_file 大文件路径依赖此等价性）
    import io
    from qgdw3762.textutil import extract_bytes_streaming
    text = (
        "2026-11-16 10:00:00.123 [RX] 68 0F 00 41 01 00 FF 00 00 00 03 01 00 45 16 // 注释\n"
        "噪声 AA 55 68:25:00\n"
        "# 纯注释行\n"
    )
    bulk = extract_bytes(text)
    streaming = extract_bytes_streaming(io.StringIO(text))
    assert bulk == streaming


def test_normalize_hex_format():
    out = normalize_hex("682500680B16")
    assert out == "68 25 00 68 0B 16"


def test_binary_detect():
    assert is_probably_binary(bytes(range(256)) * 8)
    assert not is_probably_binary(("68 25 00 68 " * 100 + "16\n").encode())
