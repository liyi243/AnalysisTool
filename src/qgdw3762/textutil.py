"""输入规范化：从任意文本中提取候选 hex 字节流。

支持形态：
- ``68 25 00 68 ...``   空格分隔
- ``68-25-00`` / ``68,25,00`` / ``68:25`` 分隔符
- ``68H 25H`` / ``0x68 0x25`` 前后缀
- ``68250068``          紧凑连续
- 含时间戳、行号、中文注释的抓包日志（时间戳与注释先被剔除；
  残余的伪 hex 字节位于帧外，由分帧扫描器的 68/长度/16/CS 校验自动排除）
"""
from __future__ import annotations

import re
from typing import List, Tuple

# 日期时间戳：2026-11-16 10:00:00.123 / 2026/11/16 / 2026年11月16日 10:00:00
_TS_DATE_RE = re.compile(
    r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?(?:\s+[Tt]?\d{1,2}:\d{1,2}(?::\d{1,2})?(?:\.\d+)?)?"
)
# 纯时间戳：10:00:00.123 / 10:00
_TS_TIME_RE = re.compile(r"\b\d{1,2}:\d{1,2}(?::\d{1,2})?(?:\.\d+)?\b")
# 0x 前缀；字节后缀 H（"68H"）
_HEX_PREFIX_RE = re.compile(r"(?i)0x")
_HEX_SUFFIX_H_RE = re.compile(r"(?<=[0-9A-Fa-f])[Hh](?![0-9A-Fa-f])")
# 非十六进制字符
_NON_HEX_RE = re.compile(r"[^0-9A-Fa-f]+")

# 注释起点：// # ; ；-- —— 及行首常见标记
_COMMENT_MARKS = ("//", "#", ";", "；", "--", "——")


def _cut_comment(line: str) -> str:
    for mark in _COMMENT_MARKS:
        idx = line.find(mark)
        if idx > 0:  # 不裁剪行首（避免吞掉以 # 开头的有效 hex 行场景过窄，>0 更稳）
            line = line[:idx]
    return line


def _token_to_pairs(token: str) -> List[str]:
    """一个 hex 令牌 → 2 字符对列表；奇数长度整块丢弃（避免错位）。"""
    if not token or len(token) % 2 != 0:
        return []
    return [token[i : i + 2] for i in range(0, len(token), 2)]


def extract_bytes(text: str) -> Tuple[bytes, List[int]]:
    """从文本提取候选字节流。

    返回:
        (bytes, line_map)  line_map[i] 为第 i 个字节所在行号（1 基，0 表示未知）
    """
    stream = bytearray()
    line_map: List[int] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = _cut_comment(raw_line)
        line = _TS_DATE_RE.sub(" ", line)
        line = _TS_TIME_RE.sub(" ", line)
        line = _HEX_PREFIX_RE.sub(" ", line)
        line = _HEX_SUFFIX_H_RE.sub(" ", line)
        line = _NON_HEX_RE.sub(" ", line)
        for token in line.split():
            pairs = _token_to_pairs(token)
            for p in pairs:
                stream.extend(bytes.fromhex(p))
                line_map.append(lineno)
    return bytes(stream), line_map


def normalize_hex(text: str) -> str:
    """规范化为『大写、两位一组、空格分隔』的显示形式（每 16 字节换行）。"""
    data, _ = extract_bytes(text)
    pairs = [f"{b:02X}" for b in data]
    lines = [" ".join(pairs[i : i + 16]) for i in range(0, len(pairs), 16)]
    return "\n".join(lines)


def is_probably_binary(data: bytes) -> bool:
    """粗判二进制文件：不可打印字节占比高且无 16 结束特征时按裸流处理。"""
    if not data:
        return False
    sample = data[:8192]
    printable = sum(1 for b in sample if 0x20 <= b < 0x7F or b in (0x09, 0x0A, 0x0D))
    ratio = printable / len(sample)
    return ratio < 0.60
