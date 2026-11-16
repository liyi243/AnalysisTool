"""帧扫描器：从任意字节流中定位 376.2 帧。

帧结构（Q/GDW 10376.2-2019）：68H | L(2B 小端=整帧总长) | C | ... | CS | 16H
- L == 帧总字节数（含 68H/L/C/CS/16H 共 6 字节固定部分）
- CS = sum(帧内偏移3 .. 倒数第3字节) mod 256，CS 位于倒数第 2 字节
- 最小合法帧 15 字节（无地址域）
"""
from __future__ import annotations

from .model import FrameCandidate

MIN_FRAME_LEN = 15
MAX_FRAME_LEN = 65535


def _check_3761_shape(data: bytes, i: int, n: int) -> str | None:
    """识别 376.1 形态帧（68 L L 68 ...），提示用户而非误解析。

    376.1 帧结构：68 | L(2B) | L(2B重复) | 68 | C..数据末(U字节) | CS | 16H；
    L 低 2 位为规约标志（=10B），U = L>>2。
    """
    if i + 5 < n and data[i + 5] == 0x68 \
            and data[i + 3] == data[i + 1] and data[i + 4] == data[i + 2]:
        L = data[i + 1] | (data[i + 2] << 8)
        if (L & 0x03) == 0x02:
            U = L >> 2
            total = U + 8
            if U >= 8 and i + total <= n and data[i + total - 1] == 0x16:
                cs_calc = sum(data[i + 6:i + 6 + U]) & 0xFF
                if cs_calc == data[i + 6 + U]:
                    return "疑似 376.1 帧（双起始符 68 L L 68），本工具面向 376.2，未解析"
    return None


def scan_frames(data: bytes) -> tuple[list[FrameCandidate], list[str]]:
    """滑窗扫描字节流，返回（帧候选列表, 告警列表）。"""
    n = len(data)
    out: list[FrameCandidate] = []
    warnings: list[str] = []
    i = 0
    while i < n:
        if data[i] != 0x68:
            i += 1
            continue
        if n - i < 5:
            break
        L = data[i + 1] | (data[i + 2] << 8)
        if L < MIN_FRAME_LEN or L > MAX_FRAME_LEN:
            i += 1
            continue
        # 376.1 形态优先识别（长度域重复且低 2 位=10B）
        if data[i + 3] == data[i + 1] and data[i + 4] == data[i + 2] \
                and (L & 0x03) == 0x02:
            reason3761 = _check_3761_shape(data, i, n)
            if reason3761:
                warnings.append(reason3761)
                i += 1
                continue
        end = i + L                       # 帧结束位置（不含）
        if end > n:
            warnings.append(
                f"偏移 0x{i:X} 处存在起始符但帧体不完整（L={L}，仅剩 {n - i} 字节）")
            i += 1
            continue
        if data[end - 1] != 0x16:
            i += 1
            continue
        frame = data[i:end]
        calc_cs = sum(frame[3:-2]) & 0xFF
        real_cs = frame[-2]
        if calc_cs == real_cs:
            out.append(FrameCandidate(data=frame, start=i))
            i = end
            continue
        out.append(FrameCandidate(
            data=frame, start=i,
            reason=f"CS 校验失败：计算 0x{calc_cs:02X} ≠ 帧内 0x{real_cs:02X}"))
        i += 1                            # 重同步：逐字节推进
    return out, warnings
