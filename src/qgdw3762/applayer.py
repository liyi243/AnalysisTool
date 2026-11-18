"""应用层数据单元解析：按 AFN/Fn 分派，已知格式逐字段解码，未知格式 HEX 兜底。

格式依据 Q/GDW 10376.2—2019 第 6.5 节（详见 docs/03-协议解析设计说明书.md 与调研笔记）。
内嵌 DL/T 645 报文（协议类型 01H/02H）调用 six45 模块做结构级解析。
"""
from __future__ import annotations

from . import consts, six45
from .model import Field, KIND_DATA, KIND_ERR, KIND_SEQ


def _raw_field(name: str, data: bytes, offset: int, note: str = "") -> Field:
    return Field(name, offset, len(data), data.hex(" ").upper(),
                 data.hex(" ").upper() if data else "（无数据）", note, KIND_DATA)


def _int_le(data: bytes) -> int:
    return int.from_bytes(data, "little")


def _embed_proto_field(name: str, proto: int, content: bytes, offset: int) -> Field:
    """内嵌规约报文字段：645 → 结构解析；其他 → HEX。"""
    proto_txt = consts.PROTO_TYPE.get(proto, f"保留(0x{proto:02X})")
    if proto in (0x01, 0x02) and content:
        f45 = six45.parse_645(content, offset)
        if f45 is not None:
            return Field(name, offset, len(content), content.hex(" ").upper(),
                         f"{proto_txt} · {f45.value}", "内嵌规约报文", "six45",
                         children=[f45])
        return Field(name, offset, len(content), content.hex(" ").upper(),
                     f"{proto_txt} · 未识别出 645 帧结构（HEX 原文）", "", "six45")
    tag = "（698.45 结构解析暂未内置，HEX 原文）" if proto == 0x03 else ""
    return Field(name, offset, len(content), content.hex(" ").upper(),
                 (content.hex(" ").upper() if content else "（空）") + tag,
                 f"{proto_txt}", "six45")


# ── 各 Fn 解码器：输入 (data剩余, 绝对偏移) → (Field, 消耗字节数) ──

def _dec_afn00_f1(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    """确认(F1)。2013 版：2B 信道状态 BS + 2B 等待时间（共 4B）；
    2019 版及项目样例：4B 信道状态 + 2B 等待时间（共 6B）。"""
    status_len = 2 if version == "2013" else 4
    total = status_len + 2
    if len(data) < total:
        return _raw_field("确认数据单元", data, off), len(data)
    status = data[:status_len]
    wait = _int_le(data[status_len:status_len + 2])
    note = f"{status_len}B信道状态BS + 2B等待时间"
    if version == "2013":
        note += "（2013版）"
    return Field("确认(F1)", off, total, data[:total].hex(" ").upper(),
                 f"信道状态字 0x{status[::-1].hex().upper()}（0=忙/1=闲）；等待时间 {wait} s",
                 note, KIND_DATA), total


def _dec_afn00_f2(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    if not data:
        return Field("否认(F2)", off, 0, "", "（无数据）", "", KIND_ERR), 0
    v = data[0]
    return Field("否认(F2) 错误状态字", off, 1, f"{v:02X}",
                 consts.deny_error_text(v), "1字节", KIND_DATA), 1


def _dec_afn02_f1(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    if len(data) < 2:
        return _raw_field("转发通信协议数据帧(F1)", data, off), len(data)
    proto = data[0]
    L = data[1]
    if 2 + L > len(data):
        return Field("转发报文(F1)", off, len(data), data.hex(" ").upper(),
                     f"声明长度 {L} 超出剩余 {len(data) - 2} 字节", "", KIND_ERR), len(data)
    content = data[2:2 + L]
    child = _embed_proto_field("内嵌规约报文", proto, content, off + 2)
    f = Field("转发通信协议数据帧(F1)", off, 2 + L, data[:2 + L].hex(" ").upper(),
              f"{consts.PROTO_TYPE.get(proto, '保留')} · {L} 字节",
              "1B协议类型 + 1B报文长度 + 内容", KIND_DATA, children=[child])
    return f, 2 + L


def _dec_afn03_f1_up(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    n = len(data)
    if n < 8:
        return _raw_field("厂商代码和版本信息(F1)", data, off), n
    def _ascii(bs: bytes) -> str:
        return bs.decode("ascii", errors="replace")
    try:
        txt = (f"厂商 {_ascii(data[0:2])}，芯片 {_ascii(data[2:4])}，"
               f"版本 20{data[7]:02X}-{data[6]:02X}-{data[5]:02X}（V{data[4]:02X}）")
        note = "2B厂商ASCII+2B芯片ASCII+3B版本日期BCD+1B版本号（常见布局）"
    except Exception:
        txt, note = data.hex(" ").upper(), ""
    return Field("厂商代码和版本信息(F1)", off, n, data.hex(" ").upper(), txt,
                 note, KIND_DATA), n


def _dec_afn03_f2(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    if not data:
        return _raw_field("噪声值(F2)", data, off), 0
    v = data[0] & 0x0F
    return Field("噪声值(F2)", off, 1, f"{data[0]:02X}",
                 f"噪声强度 {v}（0~15）", "D3~D0", KIND_DATA), 1


def _dec_addr6(name: str, fn: str, data: bytes, off: int) -> tuple[Field, int] | None:
    if len(data) < 6:
        return None
    from .frame import _bcd_str
    return Field(f"{name}({fn})", off, 6, data[:6].hex(" ").upper(),
                 _bcd_str(data[:6]), "BCD 6字节", KIND_DATA), 6


def _dec_afn04_f1_down(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    if not data:
        return _raw_field("发送测试(F1)", data, off), 0
    v = data[0]
    return Field("发送测试(F1)", off, 1, f"{v:02X}",
                 f"持续时间 {v} s" + ("（停止发送）" if v == 0 else ""), "1B", KIND_DATA), 1


def _dec_afn04_f3_down(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    if len(data) < 10:
        return _raw_field("报文通信测试(F3)", data, off), len(data)
    L = data[9]
    if 10 + L > len(data):
        return _raw_field("报文通信测试(F3)", data, off), len(data)
    from .frame import _bcd_str
    proto = data[8]
    child = _embed_proto_field("测试报文", proto, data[10:10 + L], off + 10) if L else None
    children = [
        Field("本地信道标识", off, 1, f"{data[0]:02X}", f"{data[0]}（0=默认信道）", "", KIND_DATA),
        Field("测试通信速率", off + 1, 1, f"{data[1]:02X}", f"{data[1]}（0=默认）", "", KIND_DATA),
        Field("目标地址", off + 2, 6, data[2:8].hex(" ").upper(), _bcd_str(data[2:8]), "BCD", KIND_DATA),
        Field("通信协议类型", off + 8, 1, f"{proto:02X}", consts.PROTO_TYPE.get(proto, "保留"), "", KIND_DATA),
        Field("报文长度", off + 9, 1, f"{L:02X}", str(L), "", KIND_DATA),
    ]
    if child:
        children.append(child)
    return Field("报文通信测试(F3)", off, 10 + L, data[:10 + L].hex(" ").upper(),
                 f"测试 {L} 字节 · {consts.PROTO_TYPE.get(proto, '保留')}", "", KIND_DATA,
                 children=children), 10 + L


def _dec_afn06_f1_up(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    if not data:
        return _raw_field("上报从节点信息(F1)", data, off), 0
    n = data[0]
    need = 1 + 9 * n
    if len(data) < need:
        return _raw_field("上报从节点信息(F1)", data, off), len(data)
    from .frame import _bcd_str
    children = []
    for k in range(n):
        base = off + 1 + 9 * k
        node = data[1 + 9 * k:1 + 9 * k + 9]
        proto = node[6]
        seq = _int_le(node[7:9])
        children.append(Field(
            f"从节点{k + 1}", base, 9, node.hex(" ").upper(),
            f"地址 {_bcd_str(node[0:6])} · {consts.PROTO_TYPE.get(proto, '保留')} · 序号 {seq}",
            "6B地址BCD+1B协议+2B序号", KIND_DATA))
    return Field("上报从节点信息(F1)", off, need, data[:need].hex(" ").upper(),
                 f"上报 {n} 个从节点", "", KIND_DATA, children=children), need


def _dec_afn06_f2_up(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    if len(data) < 6:
        return _raw_field("上报抄读数据(F2)", data, off), len(data)
    seq = _int_le(data[0:2])
    proto = data[2]
    delay = _int_le(data[3:5])
    L = data[5]
    if 6 + L > len(data):
        return _raw_field("上报抄读数据(F2)", data, off), len(data)
    content = data[6:6 + L]
    child = _embed_proto_field("抄读报文内容", proto, content, off + 6)
    return Field("上报抄读数据(F2)", off, 6 + L, data[:6 + L].hex(" ").upper(),
                 f"从节点序号 {seq} · {consts.PROTO_TYPE.get(proto, '保留')} · 上行时长 {delay}s",
                 "2B序号+1B协议+2B时长+1B长度+内容", KIND_DATA, children=[child]), 6 + L


def _dec_afn06_f3_up(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    if not data:
        return _raw_field("路由工况变动(F3)", data, off), 0
    v = data[0]
    return Field("路由工况变动(F3)", off, 1, f"{v:02X}",
                 consts.ROUTE_WORK_CHANGE.get(v, f"保留({v})"), "1B", KIND_DATA), 1


def _dec_afn14_f1_up(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    if len(data) < 9:
        return _raw_field("路由请求抄读内容(F1)", data, off), len(data)
    from .frame import _bcd_str
    return Field("路由请求抄读内容(F1)", off, 9, data[:9].hex(" ").upper(),
                 f"相位 {data[0] or '未知'} · 从节点 {_bcd_str(data[1:7])} · 序号 {_int_le(data[7:9])}",
                 "1B相位+6B地址BCD+2B序号", KIND_DATA), 9


def _dec_afn14_f3_up(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    if len(data) < 9:
        return _raw_field("请求依通信延时修正通信数据(F3)", data, off), len(data)
    from .frame import _bcd_str
    L = data[8]
    if 9 + L > len(data):
        return _raw_field("请求依通信延时修正通信数据(F3)", data, off), len(data)
    content = data[9:9 + L]
    child = six45.parse_645(content, off + 9) if content else None
    children = [
        Field("从节点地址", off, 6, data[0:6].hex(" ").upper(), _bcd_str(data[0:6]), "BCD", KIND_DATA),
        Field("预计延迟时间", off + 6, 2, data[6:8].hex(" ").upper(), f"{_int_le(data[6:8])} s", "", KIND_DATA),
        Field("抄读信息长度", off + 8, 1, f"{L:02X}", str(L), "", KIND_DATA),
    ]
    if child:
        children.append(child)
    return Field("请求依通信延时修正通信数据(F3)", off, 9 + L,
                 data[:9 + L].hex(" ").upper(), f"延迟 {_int_le(data[6:8])}s · {L} 字节",
                 "", KIND_DATA, children=children), 9 + L


def _dec_afn14_f4(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    if len(data) < 5:
        return _raw_field("路由请求交采信息(F4)", data, off), len(data)
    t = data[0]
    tname = {1: "645-2007", 2: "698.45"}.get(t, f"保留({t})")
    di = data[1:5][::-1].hex().upper()
    return Field("路由请求交采信息(F4)", off, 5, data[:5].hex(" ").upper(),
                 f"数据项类型 {tname} · 交采标识 0x{di}", "1B类型+4B标识(低位在前)", KIND_DATA), 5


def _dec_afnf1_f1_down(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    if len(data) < 5:
        return _raw_field("并发抄表(F1)", data, off), len(data)
    proto = data[0]
    L = _int_le(data[3:5])
    if 5 + L > len(data):
        return _raw_field("并发抄表(F1)", data, off), len(data)
    content = data[5:5 + L]
    child = _embed_proto_field("抄表报文", proto, content, off + 5)
    return Field("并发抄表(F1) 下行", off, 5 + L, data[:5 + L].hex(" ").upper(),
                 f"{consts.PROTO_TYPE.get(proto, '保留')} · {L} 字节",
                 "1B规约+2B保留+2B长度+内容", KIND_DATA, children=[child]), 5 + L


def _dec_afnf1_f1_up(data: bytes, off: int, version: str = "2019") -> tuple[Field, int]:
    if len(data) < 3:
        return _raw_field("并发抄表(F1)", data, off), len(data)
    proto = data[0]
    L = _int_le(data[1:3])
    if 3 + L > len(data):
        return _raw_field("并发抄表(F1)", data, off), len(data)
    content = data[3:3 + L]
    child = _embed_proto_field("抄表报文", proto, content, off + 3)
    if L == 0:
        val = "抄表失败（报文长度域=0，源地址A1为失败电表地址）"
    else:
        val = f"{consts.PROTO_TYPE.get(proto, '保留')} · {L} 字节"
    return Field("并发抄表(F1) 上行", off, 3 + L, data[:3 + L].hex(" ").upper(),
                 val, "1B规约+2B长度+内容；长度0=抄表失败", KIND_DATA,
                 children=[child]), 3 + L



# ── 补充解码器（覆盖 2013/2019 常见查询、控制、路由类） ──

def _dec_addr6_simple(name: str, data: bytes, off: int, note: str = "6B BCD") -> tuple[Field, int]:
    if len(data) < 6:
        return _raw_field(name, data, off), len(data)
    from .frame import _bcd_str
    return Field(name, off, 6, data[:6].hex(" ").upper(), _bcd_str(data[:6]), note, KIND_DATA), 6


def _dec_afn03_f4_up(data: bytes, off: int, *_a) -> tuple[Field, int]:
    return _dec_addr6_simple("主节点地址(F4)", data, off)


def _dec_afn03_f6_up(data: bytes, off: int, *_a) -> tuple[Field, int]:
    if not data:
        return _raw_field("主节点干扰状态(F6)", data, off), 0
    v = data[0]
    txt = "没有干扰" if v == 0 else ("有干扰" if v == 1 else f"保留({v})")
    return Field("主节点干扰状态(F6)", off, 1, f"{v:02X}", txt, "1B", KIND_DATA), 1


def _dec_afn03_f7_up(data: bytes, off: int, *_a) -> tuple[Field, int]:
    if len(data) < 2:
        return _raw_field("从节点监控最大超时时间(F7)", data, off), len(data)
    t = _int_le(data[:2])
    return Field("从节点监控最大超时时间(F7)", off, 2, data[:2].hex(" ").upper(),
                 f"{t} s", "BIN 2B", KIND_DATA), 2


def _dec_afn03_f8_up(data: bytes, off: int, *_a) -> tuple[Field, int]:
    if len(data) < 2:
        return _raw_field("无线通信参数(F8)", data, off), len(data)
    ch, pwr = data[0], data[1]
    pwr_txt = {0: "最高", 1: "次高", 2: "次低", 3: "最低"}.get(pwr, f"保留({pwr})")
    return Field("无线通信参数(F8)", off, 2, data[:2].hex(" ").upper(),
                 f"信道组 {ch} · 发射功率 {pwr_txt}", "1B信道组+1B功率", KIND_DATA), 2


def _dec_afn05_f1_down(data: bytes, off: int, *_a) -> tuple[Field, int]:
    return _dec_addr6_simple("设置主节点地址(F1)", data, off)


def _dec_afn05_f2(data: bytes, off: int, *_a) -> tuple[Field, int]:
    if not data:
        return Field("允许/禁止从节点上报(F2)", off, 0, "", "无数据", "", KIND_DATA), 0
    v = data[0]
    txt = "允许上报" if v == 1 else ("禁止上报" if v == 0 else f"值={v}")
    return Field("允许/禁止从节点上报(F2)", off, 1, f"{v:02X}", txt, "1B", KIND_DATA), 1


def _dec_afn10_f1_up(data: bytes, off: int, *_a) -> tuple[Field, int]:
    if len(data) < 2:
        return _raw_field("从节点数量(F1)", data, off), len(data)
    n = _int_le(data[:2])
    return Field("从节点数量(F1)", off, 2, data[:2].hex(" ").upper(), f"{n} 个", "BIN 2B", KIND_DATA), 2


def _dec_afn10_f2_up(data: bytes, off: int, *_a) -> tuple[Field, int]:
    """从节点信息：总数量 + 本帧数量 + 每节点(6B地址 + 1B协议? 或按标准变长)。简化展示。"""
    if len(data) < 2:
        return _raw_field("从节点信息(F2)", data, off), len(data)
    # 常见格式：2B总数量 + 1B本帧数 + 节点列表（每节点 6B地址+附加）
    total = _int_le(data[:2]) if len(data) >= 2 else 0
    return Field("从节点信息(F2)", off, len(data), data.hex(" ").upper(),
                 f"总数量约 {total} · 共 {len(data)} 字节（详细结构按标准/HEX）",
                 "建议对照标准表查看", KIND_DATA), len(data)


def _dec_afn12_simple(data: bytes, off: int, name: str) -> tuple[Field, int]:
    # 重启/暂停/恢复通常无数据单元或仅确认
    if not data:
        return Field(name, off, 0, "", "无数据单元", "", KIND_DATA), 0
    return _raw_field(name, data, off), len(data)


def _dec_afn12_f1(data: bytes, off: int, *_a) -> tuple[Field, int]:
    return _dec_afn12_simple(data, off, "路由控制·重启(F1)")


def _dec_afn12_f2(data: bytes, off: int, *_a) -> tuple[Field, int]:
    return _dec_afn12_simple(data, off, "路由控制·暂停(F2)")


def _dec_afn12_f3(data: bytes, off: int, *_a) -> tuple[Field, int]:
    return _dec_afn12_simple(data, off, "路由控制·恢复(F3)")


def _dec_afn13_f1(data: bytes, off: int, *_a) -> tuple[Field, int]:
    """监控从节点：通常含协议类型 + 长度 + 报文，类似转发。"""
    if len(data) < 2:
        return _raw_field("监控从节点(F1)", data, off), len(data)
    proto = data[0]
    L = data[1]
    if 2 + L > len(data):
        return _raw_field("监控从节点(F1)", data, off), len(data)
    content = data[2:2 + L]
    child = _embed_proto_field("监控报文", proto, content, off + 2)
    return Field("监控从节点(F1)", off, 2 + L, data[:2 + L].hex(" ").upper(),
                 f"{consts.PROTO_TYPE.get(proto, '保留')} · {L} 字节",
                 "1B协议+1B长度+内容", KIND_DATA, children=[child]), 2 + L


def _dec_afn15_f1(data: bytes, off: int, *_a) -> tuple[Field, int]:
    """文件传输方式1：简化展示总长与前几字节。"""
    if len(data) < 4:
        return _raw_field("文件传输方式1(F1)", data, off), len(data)
    # 常见：段号/总段/数据等，按 HEX + 长度提示
    return Field("文件传输方式1(F1)", off, len(data), data.hex(" ").upper(),
                 f"文件传输数据 {len(data)} 字节（段号等字段请对照标准）",
                 "详细分包结构见标准 AFN=15H", KIND_DATA), len(data)


def _dec_afn06_f5_up(data: bytes, off: int, *_a) -> tuple[Field, int]:
    if len(data) < 2:
        return _raw_field("上报从节点事件(F5)", data, off), len(data)
    # 常见含地址 + 事件内容
    return Field("上报从节点事件(F5)", off, len(data), data.hex(" ").upper(),
                 f"事件上报 {len(data)} 字节", "含从节点地址与事件数据", KIND_DATA), len(data)

# (AFN, Fn, 上行?) → 解码器；up=None 表示上下行同构
_DECODERS: dict[tuple[int, int, int | None], object] = {
    (0x00, 1, None): _dec_afn00_f1,
    (0x00, 2, None): _dec_afn00_f2,
    (0x02, 1, None): _dec_afn02_f1,
    (0x03, 1, 1): _dec_afn03_f1_up,
    (0x03, 2, None): _dec_afn03_f2,
    (0x04, 1, 0): _dec_afn04_f1_down,
    (0x04, 3, 0): _dec_afn04_f3_down,
    (0x06, 1, 1): _dec_afn06_f1_up,
    (0x06, 2, 1): _dec_afn06_f2_up,
    (0x06, 3, 1): _dec_afn06_f3_up,
    (0x14, 1, 1): _dec_afn14_f1_up,
    (0x14, 3, 1): _dec_afn14_f3_up,
    (0x14, 4, None): _dec_afn14_f4,
    (0xF1, 1, 0): _dec_afnf1_f1_down,
    (0xF1, 1, 1): _dec_afnf1_f1_up,
    # 补充
    (0x03, 4, 1): _dec_afn03_f4_up,
    (0x03, 6, 1): _dec_afn03_f6_up,
    (0x03, 7, 1): _dec_afn03_f7_up,
    (0x03, 8, 1): _dec_afn03_f8_up,
    (0x05, 1, 0): _dec_afn05_f1_down,
    (0x05, 2, None): _dec_afn05_f2,
    (0x06, 5, 1): _dec_afn06_f5_up,
    (0x10, 1, 1): _dec_afn10_f1_up,
    (0x10, 2, 1): _dec_afn10_f2_up,
    (0x12, 1, 0): _dec_afn12_f1,
    (0x12, 2, 0): _dec_afn12_f2,
    (0x12, 3, 0): _dec_afn12_f3,
    (0x13, 1, None): _dec_afn13_f1,
    (0x15, 1, None): _dec_afn15_f1,
}

# 无数据单元的 Fn（请求类常见）
_NO_DATA_FN = {(0x04, 2), (0x05, 3), (0x14, 1)}


def decode_data_units(afn: int, up: bool, fns: list[tuple[int, int]],
                      data: bytes, base_off: int, protocol_version: str = "2019") -> tuple[list[Field], list[str]]:
    """按 Fn 顺序解析数据单元。返回 (字段列表, 错误列表)。"""
    errors: list[str] = []
    fields: list[Field] = []
    upi = 1 if up else 0
    pos = 0
    n = len(data)
    for fn, _mask in fns:
        decoder = _DECODERS.get((afn, fn, upi)) or _DECODERS.get((afn, fn, None))
        rest = data[pos:]
        if decoder is None:
            if (afn, fn) in _NO_DATA_FN:
                if rest:
                    fields.append(Field(
                        f"F{fn} 数据单元", base_off + pos, len(rest),
                        rest.hex(" ").upper(), rest.hex(" ").upper(),
                        "标准定义该 Fn 无数据单元，此字节按 HEX 展示", KIND_SEQ))
                else:
                    fields.append(Field(f"F{fn} 数据单元", base_off + pos, 0, "",
                                        "无数据单元", "", KIND_SEQ))
                pos = n
                continue
            if len(fns) == 1 or pos == 0:
                f = _raw_field(f"F{fn} 数据单元（未内置解析，HEX）", rest, base_off + pos,
                               "该 AFN/Fn 的数据单元格式暂未内置，可对照标准查阅")
                fields.append(f)
                pos = n
                continue
            f = _raw_field(f"F{fn} 数据单元（HEX）", rest, base_off + pos,
                           "多Fn组合中位于后续位置，按 HEX 展示")
            fields.append(f)
            pos = n
            continue
        try:
            # _DECODERS 表中所有解码器均接收第三参数 protocol_version（未使用者忽略之），
            # 直接统一传参，避免用 except TypeError 探测签名而掩盖解码器内部真实 TypeError
            field, consumed = decoder(rest, base_off + pos, protocol_version)
        except Exception as exc:  # 防御：任何解码异常都不得中断整体解析
            errors.append(f"F{fn} 数据单元解码异常：{exc}")
            field = _raw_field(f"F{fn} 数据单元", rest, base_off + pos)
            consumed = len(rest)
        fields.append(field)
        pos += consumed if consumed is not None else len(rest)
        if pos >= n:
            break
    if pos < n and pos > 0:
        tail = data[pos:]
        fields.append(_raw_field("剩余数据", tail, base_off + pos,
                                 "按 Fn 逐个解析后的剩余字节（HEX）"))
    return fields, errors
