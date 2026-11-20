"""帧扫描器：从任意字节流中定位 376.2 帧。

帧结构（Q/GDW 10376.2-2019）：68H | L(2B 小端=整帧总长) | C | ... | CS | 16H
- L == 帧总字节数（含 68H/L/C/CS/16H 共 6 字节固定部分）
- CS = sum(帧内偏移3 .. 倒数第3字节) mod 256，CS 位于倒数第 2 字节
- 最小合法帧 15 字节（无地址域）
"""
from __future__ import annotations

from array import array
from itertools import accumulate

from .model import FrameCandidate

MIN_FRAME_LEN = 15
# L 为 16 位小端，天然 ≤65535，无需再与上限比较（原 MAX_FRAME_LEN 判定为恒假死条件，已移除）
# CS 校验失败的帧候选保留上限：失败后仅逐字节重同步（i+=1），噪声/损坏流
# 会产生大量重叠失败候选，全部保留将造成内存与时间放大（拷贝 L 字节切片）。
# 超出上限后照常扫描，但不再保留失败候选，仅追加一条汇总告警；成功候选不受限。
MAX_FAILED_CANDIDATES = 1000
# "帧体不完整"（流末尾截断帧）告警保留上限：噪声/损坏流中大量 0x68 都会触发
# 该告警，无上限时告警列表可被刷至数万条（GUI 会整体拼接展示）。
MAX_INCOMPLETE_WARNINGS = 5
# 直接对源缓冲逐候选求和的累计字节数一旦超过 输入长度×该系数（说明存在大量
# 重叠失败候选被反复重扫），就一次性构建前缀和，把每次 CS 校验降为 O(1) 查表。
# 正常单遍流量各帧窗口基本不重叠，不会触发，也就不产生额外内存分配。
CS_PREFIX_TRIGGER_FACTOR = 2


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
    """滑窗扫描字节流，返回（帧候选列表, 告警列表）。

    候选仅记录 start/length（不复制帧字节）；CS 校验默认直接对源缓冲求和
    sum(data[i+3:end-2]) & 0xFF（与原 frame[3:-2] 完全等价：帧内偏移 3 ..
    倒数第 3 字节，不含结尾 CS 与 16H）。若重叠失败候选导致重复求和的开销
    超过阈值，则构建前缀和改为 O(1) 差分查表，二者结果精确相等。
    """
    n = len(data)
    out: list[FrameCandidate] = []
    warnings: list[str] = []
    failed_kept = 0                       # 已保留的 CS 失败候选数
    failed_dropped = 0                    # 超限被丢弃的 CS 失败候选数
    incomplete_kept = 0                   # 已保留的"帧体不完整"告警数
    incomplete_dropped = 0                # 超限被丢弃的告警数
    cs_prefix: array | None = None        # 前缀和缓存（惰性构建），[k]=sum(data[:k])
    sum_work = 0                          # 直接求和路径累计累加的字节数
    i = 0
    while i < n:
        if data[i] != 0x68:
            i += 1
            continue
        if n - i < 5:
            break
        L = data[i + 1] | (data[i + 2] << 8)
        if L < MIN_FRAME_LEN:
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
            if incomplete_kept < MAX_INCOMPLETE_WARNINGS:
                warnings.append(
                    f"偏移 0x{i:X} 处存在起始符但帧体不完整（L={L}，仅剩 {n - i} 字节）")
                incomplete_kept += 1
            else:
                incomplete_dropped += 1
            i += 1
            continue
        if data[end - 1] != 0x16:
            i += 1
            continue
        if cs_prefix is not None:         # O(1) 差分：sum(data[i+3:end-2]) 的精确值
            calc_cs = (cs_prefix[end - 2] - cs_prefix[i + 3]) & 0xFF
        else:
            calc_cs = sum(data[i + 3:end - 2]) & 0xFF
            sum_work += end - 2 - (i + 3)
            if sum_work > CS_PREFIX_TRIGGER_FACTOR * n:
                cs_prefix = array("q", accumulate(data, initial=0))
        real_cs = data[end - 2]
        if calc_cs == real_cs:
            out.append(FrameCandidate(start=i, length=L))
            i = end
            continue
        # CS 失败：照常逐字节重同步，但失败候选仅保留前 MAX_FAILED_CANDIDATES 个
        if failed_kept < MAX_FAILED_CANDIDATES:
            out.append(FrameCandidate(
                start=i, length=L,
                reason=f"CS 校验失败：计算 0x{calc_cs:02X} ≠ 帧内 0x{real_cs:02X}"))
            failed_kept += 1
        else:
            failed_dropped += 1
        i += 1                            # 重同步：逐字节推进
    if incomplete_dropped:
        warnings.append(
            f"流末尾存在 {incomplete_kept + incomplete_dropped} 处疑似截断的起始符，"
            f"仅展示前 {incomplete_kept} 处（多为噪声字节，可忽略）")
    if failed_dropped:
        warnings.append(
            f"CS 校验失败的帧候选过多，仅保留前 {MAX_FAILED_CANDIDATES} 个"
            f"（丢弃 {failed_dropped} 个）；输入可能包含大量噪声或损坏数据")
    return out, warnings
