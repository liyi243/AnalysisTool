"""管线测试：单帧/多帧/文件/日志提取。"""
from conftest import build_frame, build_645
from app_svc.pipeline import parse_file, parse_text
from qgdw3762.samples import SAMPLE_LOG, SAMPLE_MULTI, SAMPLES


def test_single_sample():
    name, hexs = SAMPLES[0]
    result = parse_text(hexs)
    assert len(result.frames) == 1
    assert result.frames[0].valid
    assert result.stats["total"] == 1 and result.stats["down"] == 1


def test_multi_with_noise():
    result = parse_text(SAMPLE_MULTI)
    valid = [f for f in result.frames if f.valid]
    assert len(valid) == 2
    assert result.stats["total"] >= 2


def test_log_with_timestamps():
    result = parse_text(SAMPLE_LOG)
    valid = [f for f in result.frames if f.valid]
    assert len(valid) == 3
    lines = {f.source_line for f in valid}
    assert lines == {1, 2, 3}


def test_all_samples_parse_valid():
    for name, hexs in SAMPLES:
        result = parse_text(hexs)
        assert result.frames, name
        for fr in result.frames:
            assert fr.valid, f"{name}: {fr.errors}"


def test_embedded_645_uplink_f1h():
    # 并发抄表上行携带 645 应答（R1=04H → 有地址域：A1=从节点MAC，A3=主节点MAC）
    meter = bytes([0x12, 0x90, 0x78, 0x56, 0x34, 0x12])
    f645 = build_645(meter, 0x91, bytes([0x10, 0x90, 0x00, 0x00]),
                     bytes([0x12, 0x34, 0x56, 0x78]))   # 4 字节电能量
    du = bytes([0x02]) + len(f645).to_bytes(2, "little") + f645
    addr = bytes([0x12, 0x90, 0x78, 0x56, 0x34, 0x12]) + b"\x00" * 6
    frame = build_frame(0x83, b"\x04\x00\x00\x00\x00\x32", 0xF1, 0x01, 0x00, du,
                        addr=addr)
    result = parse_text(frame.hex(" ").upper())
    assert len(result.frames) == 1
    fr = result.frames[0]
    assert fr.valid, fr.errors
    du_f = next(f for f in fr.fields if f.name == "数据单元")
    embed = du_f.children[0].children[0]          # 抄表报文包装字段
    assert embed.children and "645" in embed.children[0].name
    f45 = embed.children[0]
    assert "123456789012" in f45.display_value()
    assert any("正向有功总电能" in c.display_value() for c in f45.children)


def test_parse_file_text(tmp_path):
    p = tmp_path / "frames.log"
    p.write_text(SAMPLE_LOG, encoding="utf-8")
    result = parse_file(p)
    assert len([f for f in result.frames if f.valid]) == 3


def test_parse_file_binary(tmp_path):
    from qgdw3762.samples import SAMPLES
    data = b"\x00\x01\x02" + bytes.fromhex(
        SAMPLES[0][1].replace(" ", "")) + b"\xff\xee"
    p = tmp_path / "frames.bin"
    p.write_bytes(data)
    result = parse_file(p)
    assert len([f for f in result.frames if f.valid]) == 1


def test_empty_input():
    result = parse_text("")
    assert result.frames == []
    result = parse_text("没有任何报文的内容")
    assert result.frames == []
    assert result.warnings or result.stats["total"] == 0
