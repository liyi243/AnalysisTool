"""内嵌 DL/T 645-2007 报文解析（376.2 中继类报文承载 645 数据）。

645-2007 帧结构：
    68H | L(1字节) | 68H | C | A(6字节BCD, 低位在前) | [DI(低位在前)+DATA] | CS | 16H
- L：控制码、地址域、用户数据、校验码的字节总数（不含起始/长度/结束符）；
- CS：从控制码C起至校验码前所有字节累加和 mod 256；
- 多字节字段（地址/DI/数据）均低位字节在前；
- 正常应答控制码 = 请求码|80H，异常应答 = 请求码|C0H。
"""
from __future__ import annotations

from typing import Optional

from .model import Field, KIND_ADDR, KIND_CTRL, KIND_CS, KIND_DATA, KIND_END

C645_FUNC = {
    0x01: "广播校时", 0x02: "读通信地址", 0x03: "重读通信地址",
    0x04: "写数据", 0x05: "写通信地址", 0x08: "广播校时",
    0x0A: "更改通信速率", 0x0C: "修改密码", 0x0F: "最大需量清零",
    0x11: "读数据", 0x12: "读后续数据", 0x15: "写数据",
    0x17: "跳合闸/输出控制", 0x18: "安全认证",
}
# 645 异常应答 ERR 错误信息字
ERR645 = [
    (0x01, "其他错误"), (0x02, "无请求数据"), (0x04, "密码错/未授权"),
    (0x08, "通信速率不能更改"), (0x10, "年时区数超"), (0x20, "日时段数超"),
    (0x40, "费率数超"),
]

# 常用数据标识（645-2007，低位在前后按 16 位解读）
DI645 = {
    0x9010: "正向有功总电能", 0x9110: "反向有功总电能",
    0x901F: "正向有功总电能(组合)",
    0x2020: "电压数据块", 0x2021: "A相电压", 0x2022: "B相电压", 0x2023: "C相电压",
    0x2030: "电流数据块", 0x2031: "A相电流", 0x2032: "B相电流", 0x2033: "C相电流",
    0x2001: "当前正向有功总功率", 0x2003: "当前正向有功功率(块)",
    0x0400: "日期时间", 0x0401: "日期", 0x0402: "时间",
    0x0600: "电表运行状态字", 0x0601: "电表状态字(块)",
    0x0901: "当前需量", 0x0101: "最大需量及发生时间(块)",
}


def _fmt_bcd_addr(raw: bytes) -> str:
    """BCD 地址：低位在前的字节序 → 正序表号（按半字节）。"""
    out = []
    for b in reversed(raw):
        hi, lo = b >> 4, b & 0x0F
        if hi > 9 or lo > 9:
            return raw.hex(" ").upper()
        out.append(f"{hi}{lo}")
    return "".join(out)


def _di_name(di_bytes: bytes) -> str:
    if len(di_bytes) < 2:
        return ""
    di_le = int.from_bytes(di_bytes[:2], "little")
    return DI645.get(di_le, f"数据标识 0x{di_bytes[:2][::-1].hex().upper()}")


def locate_645(data: bytes) -> Optional[int]:
    """在 data 中定位一帧 CS 通过的 645 报文，返回其起始偏移；找不到返回 None。"""
    n = len(data)
    for i in range(0, max(1, n - 11)):
        if data[i] != 0x68 or i + 2 >= n or data[i + 2] != 0x68:
            continue
        L = data[i + 1]
        total = 6 + L
        end = i + total - 1
        if L < 12 or end >= n or data[end] != 0x16:
            continue
        cs_idx = end - 1
        if sum(data[i + 3 : cs_idx]) & 0xFF == data[cs_idx]:
            return i
    return None


def parse_645(data: bytes, offset: int = 0) -> Optional[Field]:
    """解析一帧 645 报文（默认 data 就是完整帧，offset 为其在宿主帧中的偏移）。"""
    n = len(data)
    if n < 14 or data[0] != 0x68 or data[2] != 0x68 or data[n - 1] != 0x16:
        return None
    L = data[1]
    cs_ok = sum(data[3 : n - 2]) & 0xFF == data[n - 2]
    c = data[3]
    up = bool(c & 0x80)
    from_station = bool(c & 0x40)
    more = bool(c & 0x20)
    abnormal = (c & 0xC0) == 0xC0 and bool(c & 0x20)
    func = c & 0x1F
    func_name = C645_FUNC.get(func, f"保留(0x{func:02X})")
    if from_station:
        if abnormal:
            func_name = f"异常应答(请求功能 0x{func:02X})"
        elif up and (c & 0x60) == 0x00:
            func_name = f"{func_name}正常应答"
    addr = _fmt_bcd_addr(data[4:10])
    di_part = data[10 : n - 2]

    children = [
        Field("传输方向", offset + 3, 1, f"{c:02X}",
              "上行(表→集中器)" if up else "下行(集中器→表)",
              "D7 传输方向位", KIND_CTRL),
        Field("从站标志", offset + 3, 1, f"{c:02X}",
              "从站应答帧" if from_station else "主站请求帧",
              "D6 从站标志位", KIND_CTRL),
        Field("功能码", offset + 3, 1, f"{c:02X}", func_name,
              f"D4~D0 功能码=0x{func:02X}" + ("；有后续帧" if more else ""), KIND_CTRL),
        Field("地址域A", offset + 4, 6, data[4:10].hex(" ").upper(),
              f"表通信地址 {addr}", "BCD 低位在前", KIND_ADDR),
    ]
    if di_part:
        if abnormal:
            err = di_part[0]
            errs = [name for bit, name in ERR645 if err & bit]
            di_val = "；".join(errs) if errs else f"错误信息字 0x{err:02X}"
            di_name = "错误信息字ERR"
        else:
            di_val = _di_name(di_part[:4])
            di_name = "数据标识DI"
        children.append(Field(di_name, offset + 10, len(di_part),
                              di_part.hex(" ").upper(), di_val, "低位在前", KIND_DATA))
    children.append(Field("校验码CS", offset + n - 2, 1, f"{data[n - 2]:02X}",
                          "校验通过" if cs_ok else "校验失败",
                          "C起至CS前累加和 mod 256", KIND_CS, error=not cs_ok))
    children.append(Field("结束符", offset + n - 1, 1, f"{data[n - 1]:02X}", "16H", "", KIND_END))
    return Field(
        "内嵌 DL/T 645-2007 报文", offset, n, data.hex(" ").upper(),
        f"{func_name} · 表号 {addr}", "CS 校验通过" if cs_ok else "CS 校验失败",
        KIND_DATA, children, error=not cs_ok,
    )
