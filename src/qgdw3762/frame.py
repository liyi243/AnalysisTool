"""单帧解析器：逐字段拆解 376.2 帧并构建字段树。

帧结构：68H | L(2B小端) | C | 信息域R(6B) | 地址域A(条件) | AFN | DT(2B) | 数据单元 | CS | 16H
"""
from __future__ import annotations

from . import consts, applayer
from .model import (
    Field, ParsedFrame,
    KIND_ADDR, KIND_AFN, KIND_CS, KIND_CTRL, KIND_DATA, KIND_END, KIND_LENGTH,
    KIND_SEQ, KIND_START,
)


def _bcd_str(raw: bytes) -> str:
    """BCD 地址显示：正常 BCD 按帧内字节序拼数字；含非 BCD 半字节则回退 hex。"""
    chars = []
    for b in raw:
        hi, lo = b >> 4, b & 0x0F
        if hi > 9 or lo > 9:
            return raw.hex(" ").upper()
        chars.append(f"{hi}{lo}")
    return "".join(chars)


def _bs_bits(value: int, names: list[str]) -> str:
    parts = []
    for idx, name in enumerate(names):
        parts.append(f"{name}={'1' if value >> idx & 1 else '0'}")
    return "；".join(parts)


def parse_frame(raw: bytes, start: int = 0, source_line: int = 0, protocol_version: str = "2019") -> ParsedFrame:
    fr = ParsedFrame(raw=bytes(raw), start=start, source_line=source_line, protocol_version=protocol_version)
    n = len(raw)
    errors: list[str] = []
    if n < 15:
        errors.append(f"帧长 {n} 字节，小于最小帧长 15 字节，无法完整解析")
        fr.errors = errors
        fr.valid = False
        return fr

    # ── 起始符 / 长度域 ──────────────────────────────────────
    L = raw[1] | (raw[2] << 8)
    # L1 = L - 6（用户数据长度）；L<6 时差值为负无意义，做显示保护
    l1_text = f"L1={L - 6} 字节" if L >= 6 else "无效（L<6）"
    fields: list[Field] = [
        Field("起始符", 0, 1, f"{raw[0]:02X}", "68H", "", KIND_START,
              error=raw[0] != 0x68),
        Field("长度域L", 1, 2, raw[1:3].hex(" ").upper(),
              f"L={L}（整帧总长）", "L = L1+6；L1=用户数据(R+A+AFN+DT+数据)长度",
              KIND_LENGTH,
              children=[Field("用户数据长度L1", 1, 2, "", l1_text, "",
                              KIND_LENGTH)]),
    ]
    if raw[0] != 0x68:
        errors.append("起始符不是 68H")
    if L != n:
        errors.append(f"长度域 L={L} 与实际帧长 {n} 不符")

    # ── 控制域 C ────────────────────────────────────────────
    c = raw[3]
    dir_up = bool(c & 0x80)
    prm = bool(c & 0x40)
    comm = c & 0x3F
    direction = "上行(模块→集中器)" if dir_up else "下行(集中器→模块)"
    fr.direction = direction
    fr.ctrl_byte = c
    fr.ctrl_name = f"{'上行' if dir_up else '下行'}·{'启动站' if prm else '从动站'}·{consts.comm_type_name(comm, protocol_version)}"
    fields.append(Field(
        "控制域C", 3, 1, f"{c:02X}", fr.ctrl_name,
        f"DIR={int(dir_up)}({'上行' if dir_up else '下行'})，PRM={int(prm)}({'启动站' if prm else '从动站'})",
        KIND_CTRL,
        children=[
            Field("DIR 传输方向位", 3, 1, f"{c:02X}",
                  "1=模块上行" if dir_up else "0=集中器下行", "D7", KIND_CTRL),
            Field("PRM 启动标志位", 3, 1, f"{c:02X}",
                  "1=启动站" if prm else "0=从动站", "D6", KIND_CTRL),
            Field("通信方式", 3, 1, f"{c:02X}", consts.comm_type_name(comm, protocol_version),
                  "D5~D0", KIND_CTRL),
        ]))

    # ── 信息域 R（6 字节） ───────────────────────────────────
    r = raw[4:10]
    relay_level = (r[0] >> 4) & 0x0F
    module_flag = bool(r[0] & 0x04)
    r_children = [
        Field("中继级别", 4, 1, f"{r[0]:02X}", f"{relay_level}（0=无中继）",
              "R1.D7~D4", KIND_SEQ),
        Field("通信模块标识", 4, 1, f"{r[0]:02X}",
              "1=对从节点操作(有地址域)" if module_flag else "0=对主节点操作(无地址域)",
              "R1.D2", KIND_SEQ),
        Field("路由标识", 4, 1, f"{r[0]:02X}",
              "1=不带路由/旁路模式" if r[0] & 0x01 else "0=带路由/路由模式",
              "R1.D0", KIND_SEQ),
        Field("信道标识", 5, 1, f"{r[1]:02X}", f"{r[1] & 0x0F}（0=不分信道）",
              "R2.D3~D0", KIND_SEQ),
        Field("报文序列号", 9, 1, f"{r[5]:02X}", f"{r[5]}",
              "R6，匹配上下行请求/应答", KIND_SEQ),
    ]
    if dir_up:
        r_children.insert(2, Field("实测相线标识", 6, 1, f"{r[2]:02X}",
                                   f"{(r[2] & 0x0F) or '不确定'}",
                                   "R3.D3~D0（0=不确定，1~3=第1~3相）", KIND_SEQ))
        r_children.insert(3, Field("电能表通道特征", 6, 1, f"{r[2]:02X}",
                                   f"{(r[2] >> 4) & 0x0F}", "R3.D7~D4", KIND_SEQ))
        r_children.insert(4, Field("末级应答信号品质", 7, 1, f"{r[3]:02X}",
                                   f"{(r[3] >> 4) & 0x0F}（15级，0=无）",
                                   "R4.D7~D4", KIND_SEQ))
        r_children.insert(5, Field("末级命令信号品质", 7, 1, f"{r[3]:02X}",
                                   f"{r[3] & 0x0F}（15级，0=无）",
                                   "R4.D3~D0", KIND_SEQ))
        r_children.insert(6, Field("事件标志", 8, 1, f"{r[4]:02X}",
                                   "有上报事件" if r[4] & 0x01 else "无上报事件",
                                   "R5.D0", KIND_SEQ))
    else:
        r_children.insert(2, Field("冲突检测", 4, 1, f"{r[0]:02X}",
                                   "要进行冲突检测" if r[0] & 0x08 else "不进行冲突检测",
                                   "R1.D3", KIND_SEQ))
        r_children.insert(3, Field("附属节点标识", 4, 1, f"{r[0]:02X}",
                                   "有附加节点" if r[0] & 0x02 else "无附加节点",
                                   "R1.D1", KIND_SEQ))
        r_children.insert(4, Field("纠错编码标识", 5, 1, f"{r[1]:02X}",
                                   "RS编码" if (r[1] >> 4) == 1 else f"{(r[1] >> 4) & 0x0F}（0=未编码）",
                                   "R2.D7~D4", KIND_SEQ))
        r_children.insert(5, Field("预计应答字节数", 6, 1, f"{r[2]:02X}",
                                   f"{r[2]}（0=默认延时）", "R3", KIND_SEQ))
        rate_raw = r[3] | (r[4] << 8)
        rate_val = rate_raw & 0x7FFF
        rate_unit = "kbit/s" if rate_raw & 0x8000 else "bit/s"
        rate_txt = "默认速率" if rate_val == 0 else f"{rate_val} {rate_unit}"
        r_children.insert(6, Field("通信速率", 7, 2, raw[7:9].hex(" ").upper(),
                                   rate_txt, "R4~R5：D14~D0 速率 + D15 单位标识", KIND_SEQ))
    fields.append(Field("信息域R", 4, 6, r.hex(" ").upper(), "", "", KIND_SEQ,
                        children=r_children))

    # ── 地址域 A（条件出现） ─────────────────────────────────
    pos = 10
    if module_flag:
        if dir_up:
            addr_len = 12
        else:
            addr_len = 12 + 6 * relay_level
        if pos + addr_len > n - 2:
            errors.append("地址域长度超出帧范围（信息域声明有地址域）")
            addr_len = max(0, n - 2 - pos)
        if addr_len > 0:
            a_raw = raw[pos:pos + addr_len]
            a_children = [Field("A1 源地址", pos, 6, raw[pos:pos + 6].hex(" ").upper(),
                                _bcd_str(raw[pos:pos + 6]), "BCD，帧内字节序", KIND_ADDR)]
            p = pos + 6
            if not dir_up:
                for k in range(relay_level):
                    a_children.append(Field(
                        f"A2-{k + 1} 中继地址", p, 6,
                        raw[p:p + 6].hex(" ").upper(), _bcd_str(raw[p:p + 6]),
                        "BCD，个数=中继级别", KIND_ADDR))
                    p += 6
            a_children.append(Field("A3 目的地址", p, 6, raw[p:p + 6].hex(" ").upper(),
                                    _bcd_str(raw[p:p + 6]), "BCD；广播=999999999999H",
                                    KIND_ADDR))
            fields.append(Field("地址域A", pos, addr_len, a_raw.hex(" ").upper(),
                                "", "通信模块标识=1 时存在", KIND_ADDR, children=a_children))
            pos += addr_len
    else:
        fields.append(Field("地址域A", pos, 0, "", "无（通信模块标识=0）", "", KIND_ADDR))

    # ── AFN + DT ────────────────────────────────────────────
    if pos + 3 > n - 2:
        errors.append("帧中缺少 AFN/DT 域")
        fr.errors = errors
        fr.cs_ok = _cs_check(raw) is not False
        fr.fields = fields
        fr.valid = False
        return fr
    afn = raw[pos]
    dt1 = raw[pos + 1]
    dt2 = raw[pos + 2]
    fr.afn_byte = afn
    fr.afn_name = consts.afn_name(afn)
    fns = consts.dt_to_fns(dt1, dt2)
    fr.fns = [fn for fn, _mask in fns]
    fr.r6_seq = raw[9] if n >= 10 else None       # 信息域R第6字节（偏移9）
    if not fns:
        errors.append("数据单元标识 DT1=0（未指明信息类 Fn）")
    dt_children = []
    for fn, _mask in fns:
        dt_children.append(Field(
            f"F{fn}", pos + 1, 2, raw[pos + 1:pos + 3].hex(" ").upper(),
            consts.fn_name(afn, fn), f"Fn=DT2×8+位序号（DT2={dt2}）", KIND_AFN))
    fields.append(Field(
        "应用功能码AFN", pos, 1, f"{afn:02X}", fr.afn_name, "", KIND_AFN,
        children=dt_children))
    fields.append(Field("数据单元标识DT", pos + 1, 2,
                        raw[pos + 1:pos + 3].hex(" ").upper(),
                        "、".join(f"F{fn}" for fn, _ in fns) or "无有效Fn",
                        "DT1(位掩码)+DT2(组号)", KIND_AFN, children=[]))
    pos += 3

    # ── 数据单元 ────────────────────────────────────────────
    du = raw[pos:n - 2]
    du_fields, du_errors = applayer.decode_data_units(afn, dir_up, fns, du, pos, protocol_version=protocol_version)
    errors.extend(du_errors)
    if du or fns:
        fields.append(Field(
            "数据单元", pos, len(du), du.hex(" ").upper(),
            "、".join(f.display_value() for f in du_fields if f.display_value()) or "",
            "", KIND_DATA, children=du_fields))
    pos += len(du)

    # ── CS / 结束符 ─────────────────────────────────────────
    calc_cs = sum(raw[3:n - 2]) & 0xFF
    real_cs = raw[n - 2]
    cs_ok = calc_cs == real_cs
    fr.cs_ok = cs_ok
    fields.append(Field("校验和CS", n - 2, 1, f"{real_cs:02X}",
                        f"计算 0x{calc_cs:02X} {'=' if cs_ok else '≠'} 帧内",
                        "C起至数据末字节累加和 mod 256", KIND_CS, error=not cs_ok))
    if not cs_ok:
        errors.append(f"CS 校验失败：计算 0x{calc_cs:02X} ≠ 帧内 0x{real_cs:02X}")
    fields.append(Field("结束符", n - 1, 1, f"{raw[n - 1]:02X}", "16H", "", KIND_END,
                        error=raw[n - 1] != 0x16))
    if raw[n - 1] != 0x16:
        errors.append("结束符不是 16H")

    # ── 摘要 ────────────────────────────────────────────────
    fn_txt = ""
    if fns:
        fn = fns[0][0]
        fname = consts.fn_name(afn, fn)
        fn_txt = fname if fname == f"F{fn}" else f"F{fn} {fname}"
        if len(fns) > 1:
            fn_txt += f" 等{len(fns)}个Fn"
    comm_short = consts.comm_type_name(comm, protocol_version).split("（")[0]
    fr.summary = (f"{('↑' if dir_up else '↓')}{comm_short} · {fr.afn_name}"
                  + (f" {fn_txt}" if fn_txt else ""))
    fr.errors = errors
    fr.fields = fields
    fr.valid = (not errors) and cs_ok
    return fr


def _cs_check(raw: bytes) -> bool | None:
    if len(raw) < 5:
        return None
    return sum(raw[3:-2]) & 0xFF == raw[-2]
