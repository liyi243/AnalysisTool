"""现场模拟帧（华立模块交互序列）解析审核测试。

背景：2026-11-20 用户提供的模拟交互帧（识别/白名单/档案同步流程），
18 帧 CS 全部验证通过；本测试固化字段级解析结论。
"""
from conftest import build_frame
from qgdw3762.frame import parse_frame
from qgdw3762.flows import group_frames


def _p(hexs: str):
    return parse_frame(bytes.fromhex(hexs.replace(" ", "")))


def test_afn03_f10_up_layout():
    fr = _p("68 38 00 81 00 00 40 00 00 00 03 02 01 71 2F 00 01 00 00 5A 0F 00 00 02 00 02 05 66 00 05 26 00 00 D0 07 76 02 31 31 32 31 31 32 5A 58 56 43 32 31 31 10 26 73 80 EA 16")
    assert fr.valid and fr.cs_ok
    du = next(f for f in fr.fields if f.name == "数据单元")
    f10 = du.children[0]
    all_names = " | ".join(c.name for c in f10.children)
    all_vals = " | ".join(c.display_value() for c in f10.children)
    # 布局探测：华立固件（无升级等待字段），39B 固定段
    assert "主节点地址" in all_names
    assert "支持的最大从节点数量" in all_names
    assert "2000" in all_vals and "630" in all_vals
    assert "115 kbit/s" in all_vals


def test_afn11_f1_add_meter():
    fr = _p("68 17 00 41 00 00 28 73 80 10 11 01 00 01 11 00 00 91 11 12 00 44 16")
    assert fr.valid
    du = next(f for f in fr.fields if f.name == "数据单元")
    node = du.children[0].children[0]
    # BCD 低位在前 → 正序表号（帧内 11 00 00 91 11 12 → 121191000011）
    assert node.display_value() == "地址 121191000011 · 透明传输"


def test_afn10_f2_up_nodes():
    fr = _p("68 3A 00 81 00 00 00 00 00 04 10 02 00 76 02 05 01 00 00 91 11 12 00 00 12 01 26 20 00 10 00 00 03 00 00 91 11 12 00 00 04 00 00 91 11 12 00 00 05 00 00 91 11 12 00 00 5A 16")
    assert fr.valid
    du = next(f for f in fr.fields if f.name == "数据单元")
    nodes = du.children[0].children
    assert len(nodes) == 5
    # 表号正序：121191000001（帧内 01 00 00 91 11 12）
    assert "121191000001" in nodes[0].display_value()
    assert "121191000005" in nodes[4].display_value()


def test_f0_f5_whitelist():
    down = _p("68 0f 00 41 00 00 28 73 80 01 f0 10 00 5d 16")
    assert down.valid and "查询白名单状态" in down.summary
    up = _p("68 10 00 81 00 00 00 00 00 01 F0 10 00 01 83 16")
    assert up.valid
    du = next(f for f in up.fields if f.name == "数据单元")
    assert du.children[0].display_value() == "白名单开启 · 黑名单关闭"


def test_confirm_6byte_du():
    # 确认帧 DU=6B：4B 信道状态(全闲 FFFFFFFF) + 2B 等待时间
    fr = _p("68 15 00 81 00 00 00 00 00 02 00 01 00 FF FF FF FF 00 00 80 16")
    assert fr.valid and fr.cs_ok
    du = next(f for f in fr.fields if f.name == "数据单元")
    v = du.children[0].display_value()
    assert "FFFFFFFF" in v and "等待时间 0 s" in v


def test_flow_sequence_e2e():
    seq = [
        "68 0f 00 41 00 00 28 00 00 00 03 02 01 6f 16",
        "68 38 00 81 00 00 40 00 00 00 03 02 01 71 2F 00 01 00 00 5A 0F 00 00 02 00 02 05 66 00 05 26 00 00 D0 07 76 02 31 31 32 31 31 32 5A 58 56 43 32 31 31 10 26 73 80 EA 16",
        "68 0f 00 41 00 00 28 73 80 01 f0 10 00 5d 16",
        "68 10 00 81 00 00 00 00 00 01 F0 10 00 01 83 16",
        "68 0f 00 41 00 00 28 73 80 02 12 02 00 72 16",
        "68 15 00 81 00 00 00 00 00 02 00 01 00 FF FF FF FF 00 00 80 16",
    ]
    frames = parse_frame(build_frame(0x41, b"\x00\x00\x28\x00\x00\x00", 0x03, 0x02, 0x01)) and None  # noqa: F841
    from app_svc.pipeline import parse_text
    result = parse_text("\n".join(seq))
    sessions, groups = group_frames(result.frames)
    assert len(sessions) == 3
    assert groups[0].name == "模块识别"
    assert groups[1].name == "白名单控制"
    assert groups[2].name == "档案同步"
