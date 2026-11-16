"""单帧解析器测试：覆盖调研笔记中的已验证帧。"""
from conftest import build_645, build_frame
from qgdw3762.frame import parse_frame
from qgdw3762.model import ParsedFrame


def _p(hexs: str) -> ParsedFrame:
    return parse_frame(bytes.fromhex(hexs.replace(" ", "")))


def test_d1_link_detect_down():
    fr = _p("68 10 00 41 01 00 FF 00 00 00 04 01 00 00 46 16")
    assert fr.valid and fr.cs_ok
    assert fr.direction.startswith("下行")
    assert fr.ctrl_byte == 0x41
    assert "集中式路由载波" in fr.ctrl_name and "启动站" in fr.ctrl_name
    assert fr.afn_byte == 0x04 and "链路接口检测" in fr.afn_name
    assert "F1" in fr.summary and "发送测试" in fr.summary
    # 字段树完整性
    names = [f.name for f in fr.fields]
    for expect in ("起始符", "长度域L", "控制域C", "信息域R", "应用功能码AFN",
                   "数据单元标识DT", "数据单元", "校验和CS", "结束符"):
        assert expect in names, expect
    # 信息域R：预计应答字节数=255
    r_field = next(f for f in fr.fields if f.name == "信息域R")
    vals = {c.name: c.display_value() for c in r_field.children}
    assert vals["预计应答字节数"] == "255（0=默认延时）"
    assert vals["报文序列号"] == "0"
    # 数据单元：1 字节 持续时间=0
    du = next(f for f in fr.fields if f.name == "数据单元")
    assert "发送测试" in du.children[0].name


def test_u1_confirm_up():
    fr = _p("68 15 00 C1 01 00 FF 00 00 00 00 01 00 00 00 00 00 00 00 C2 16")
    assert fr.valid
    assert fr.direction.startswith("上行")
    assert fr.afn_byte == 0x00
    du = next(f for f in fr.fields if f.name == "数据单元")
    assert "确认" in du.children[0].name
    assert "等待时间" in du.children[0].display_value()


def test_u2_deny_error_text():
    fr = _p("68 10 00 C1 01 00 FF 00 00 00 00 02 00 00 C3 16")
    assert fr.valid
    du = next(f for f in fr.fields if f.name == "数据单元")
    assert du.children[0].display_value() == "通信超时"


def test_d20_with_address():
    fr = _p("68 1B 00 41 04 00 FF 00 00 01 12 01 00 00 00 01 00 00 00 00 00 01 04 01 00 5F 16")
    assert fr.valid
    a = next(f for f in fr.fields if f.name == "地址域A")
    assert a.length == 12
    child_names = [c.name for c in a.children]
    assert child_names == ["A1 源地址", "A3 目的地址"]
    a3 = a.children[1]
    assert a3.display_value() == "000000000001"


def test_d22_relay_with_a2():
    fr = _p("68 21 00 41 14 00 FF 00 00 03 12 01 00 00 00 01 00 00 00 00 00 02 00 00 00 00 00 03 10 02 00 82 16")
    assert fr.valid
    a = next(f for f in fr.fields if f.name == "地址域A")
    assert a.length == 18
    assert [c.name for c in a.children] == ["A1 源地址", "A2-1 中继地址", "A3 目的地址"]
    assert "路由查询" in fr.summary and "从节点信息" in fr.summary


def test_d21_broadcast_addr():
    fr = _p("68 1C 00 41 04 00 00 00 00 02 12 01 00 00 00 01 99 99 99 99 99 99 05 04 00 01 FB 16")
    assert fr.valid
    a = next(f for f in fr.fields if f.name == "地址域A")
    a3 = a.children[-1]
    assert a3.display_value() == "999999999999"
    assert "广播" in a3.note


def test_u5_field_capture():
    fr = _p("68 1E 00 83 04 00 00 00 00 32 72 57 28 09 00 00 00 00 00 00 00 00 F1 01 00 02 00 00 A7 16")
    assert fr.valid
    assert fr.direction.startswith("上行")
    assert "从动站" in fr.ctrl_name and "HPLC" in fr.ctrl_name
    assert fr.afn_byte == 0xF1
    r = next(f for f in fr.fields if f.name == "信息域R")
    seq = next(c for c in r.children if c.name == "报文序列号")
    assert seq.display_value() == "50"        # 0x32=50
    du = next(f for f in fr.fields if f.name == "数据单元")
    assert "抄表失败" in du.children[0].display_value()


def test_d12_multi_fn_f200():
    fr = _p("68 10 00 41 01 00 FF 00 00 00 05 80 18 01 DF 16")
    assert fr.valid
    assert "F200" in fr.summary


def test_d8_f21():
    fr = _p("68 12 00 41 01 00 FF 00 00 00 10 10 02 00 00 00 63 16")
    assert fr.valid
    assert "F21" in fr.summary and "网络拓扑" in fr.summary


def test_bad_cs_and_l():
    # CS 破坏
    raw = bytearray(build_frame(0x41, b"\x01\x00\xff\x00\x00\x00", 0x04, 0x01, 0x00))
    raw[-2] ^= 0x01
    fr = parse_frame(bytes(raw))
    assert not fr.valid and not fr.cs_ok
    assert any("CS" in e for e in fr.errors)
    # L 与实际不符
    raw = bytearray(build_frame(0x41, b"\x01\x00\xff\x00\x00\x00", 0x04, 0x01, 0x00))
    raw[1] = 0x30
    fr = parse_frame(bytes(raw))
    assert any("长度域" in e for e in fr.errors)


def test_embedded_645_in_afn02():
    meter = bytes([0x12, 0x90, 0x78, 0x56, 0x34, 0x12])   # 表号 123456789012，BCD 低位在前
    f645 = build_645(meter, 0x91, bytes([0x10, 0x90, 0x00, 0x00]),
                     bytes([0x78, 0x56]))       # 读正向有功总电能应答
    du = bytes([0x02, len(f645)]) + f645        # 协议类型=02 (645-2007)
    frame = build_frame(0xC1, b"\x01\x00\xff\x00\x00\x00", 0x02, 0x01, 0x00, du)
    fr = parse_frame(frame)
    assert fr.valid, fr.errors
    du_f = next(f for f in fr.fields if f.name == "数据单元")
    embed = du_f.children[0].children[0]
    assert "645" in embed.name or "645" in embed.display_value()
    assert "123456789012" in embed.display_value()      # 表号 BCD 正序


def test_field_at_click():
    fr = _p("68 10 00 41 01 00 FF 00 00 00 04 01 00 00 46 16")
    f = fr.field_at(3)
    assert f is not None and f.name == "DIR 传输方向位"
    f2 = fr.field_at(1)
    assert f2 is not None and f2.name == "用户数据长度L1"
