"""输入规范化：从任意文本中提取候选 hex 字节流。

支持形态：
- ``68 25 00 68 ...``   空格分隔
- ``68-25-00`` / ``68,25,00`` / ``68:25`` 分隔符（注意边界：冒号形式中恰好构成
  合法钟点的纯数字对（如 ``10:20``）仍会被当作时间戳剔除，推荐改用空格分隔）
- ``68H 25H`` / ``0x68 0x25`` 前后缀
- ``68250068``          紧凑连续
- 含时间戳、行号、中文注释的抓包日志（时间戳与注释先被剔除；
  残余的伪 hex 字节位于帧外，由分帧扫描器的 68/长度/16/CS 校验自动排除）
"""
from __future__ import annotations

import re
from array import array
from typing import List, Tuple

# 日期时间戳：2026-11-16 10:00:00.123 / 2026/11/16 / 2026年11月16日 10:00:00
# （取舍：日期形态不会与 hex 令牌混淆——hex 令牌不含 -、/、年 等字符，且剔除
#   抓包日志里的时间戳是主场景，故日期部分保持宽松匹配；时间部分与 _TS_TIME_RE
#   同口径限定合法钟点，避免把日期后跟的冒号分隔 hex（如 "2026-11-16 68:25:00"）
#   误当作时间戳吞掉）
_TS_DATE_RE = re.compile(
    r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?"
    r"(?:\s+[Tt]?(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?(?![\dA-Fa-f:]))?"
)
# 纯时间戳：10:00:00.123 / 10:00。时/分/秒限定合法钟点取值，
# 前后向断言排除 hex/冒号上下文，避免误删 "68:25:00"、"AB:10:20" 这类冒号分隔 hex
_TS_TIME_RE = re.compile(
    r"(?<![\dA-Fa-f:])(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?(?![\dA-Fa-f:])"
)
# 0x 前缀；字节后缀 H（"68H"）
_HEX_PREFIX_RE = re.compile(r"(?i)0x")
_HEX_SUFFIX_H_RE = re.compile(r"(?<=[0-9A-Fa-f])[Hh](?![0-9A-Fa-f])")
# 非十六进制字符
_NON_HEX_RE = re.compile(r"[^0-9A-Fa-f]+")

# 注释起点：// # ; ；-- —— 及行首常见标记
_COMMENT_MARKS = ("//", "#", ";", "；", "--", "——")


def _cut_comment(line: str) -> str:
    """截掉行内注释（在所有注释标记中取**最早出现**的位置）。

    按最早位置而非固定顺序：如 ``68 16 -- 注释 // 说明`` 中 "--" 更靠前，
    固定顺序若先命中 "//" 会把 "-- 注释 " 留进提取流，注释中的 hex 词
    （"68 0F ..."）会被误收为报文字节。
    """
    cut = len(line)
    for mark in _COMMENT_MARKS:
        idx = line.find(mark)
        if 0 < idx < cut:   # 不裁剪行首（避免吞掉以 # 开头的行场景过窄）
            cut = idx
    return line[:cut] if cut < len(line) else line


def _token_to_pairs(token: str) -> List[str]:
    """一个 hex 令牌 → 2 字符对列表；奇数长度整块丢弃（避免错位）。"""
    if not token or len(token) % 2 != 0:
        return []
    return [token[i : i + 2] for i in range(0, len(token), 2)]


def _feed_line(raw_line: str, lineno: int, stream: bytearray, line_map: array) -> None:
    """规范化一行文本并把提取出的 hex 字节追加进 stream/line_map。"""
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


def extract_bytes(text: str) -> Tuple[bytes, array]:
    """从文本提取候选字节流。

    返回:
        (bytes, line_map)  line_map[i] 为第 i 个字节所在行号（1 基，0 表示未知）
    """
    stream = bytearray()
    # 行号映射用 array("I")（4 字节无符号）代替 list[int]，大文件内存占用约低一个数量级
    line_map = array("I")
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        _feed_line(raw_line, lineno, stream, line_map)
    return bytes(stream), line_map


def extract_bytes_streaming(lines) -> Tuple[bytes, array]:
    """逐行流式提取（lines 为可迭代文本行，如文本模式文件对象）。

    与 extract_bytes 语义一致，但无需把整个文件读入内存拼成大字符串，
    大日志文件峰值内存可显著下降。
    """
    stream = bytearray()
    line_map = array("I")
    for lineno, raw_line in enumerate(lines, start=1):
        _feed_line(raw_line, lineno, stream, line_map)
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
