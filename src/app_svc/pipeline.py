"""解析管线：统一入口（文本/文件 → 帧扫描 → 解析 → 汇总）。"""
from __future__ import annotations

from array import array
from pathlib import Path

from qgdw3762 import scanner
from qgdw3762.frame import parse_frame
from qgdw3762.model import ParsedFrame, ParseResult
from qgdw3762.textutil import extract_bytes, extract_bytes_streaming, is_probably_binary


def parse_stream(data: bytes, line_map: array | None = None, protocol_version: str = "2019") -> ParseResult:
    """对字节流分帧并逐帧解析。line_map 提供字节→源文本行号映射
    （textutil.extract_bytes 返回的 array("I")）。
    protocol_version: "2013" 或 "2019"。
    """
    result = ParseResult()
    candidates, scan_warnings = scanner.scan_frames(data)
    result.warnings.extend(scan_warnings)
    for cand in candidates:
        src_line = cand.source_line
        if line_map and 0 <= cand.start < len(line_map):
            src_line = line_map[cand.start]
        try:
            frame = parse_frame(data[cand.start:cand.start + cand.length],
                                start=cand.start, source_line=src_line,
                                protocol_version=protocol_version)
        except Exception as exc:
            # 单帧解析异常不得拖垮整批：降级为异常帧，保留原始字节
            from qgdw3762.model import ParsedFrame as _PF
            frame = _PF(raw=data[cand.start:cand.start + cand.length],
                        start=cand.start, source_line=src_line)
            frame.errors.append(f"帧解析内部异常（已降级为HEX展示）：{exc!r}")
        if cand.reason and not frame.errors:
            frame.errors.append(cand.reason)
        result.frames.append(frame)
    if not result.frames and data:
        result.warnings.append(
            "输入中未检测到结构完整的 376.2 帧（需 68…16 且校验通过；"
            "已自动归并注释与时间戳）")
    result.compute_stats(input_bytes=len(data))
    return result


def parse_text(text: str, protocol_version: str = "2019") -> ParseResult:
    data, line_map = extract_bytes(text)
    return parse_stream(data, line_map, protocol_version=protocol_version)


def parse_file(path: str | Path, protocol_version: str = "2019") -> ParseResult:
    path = Path(path)
    # 只读前 8KB 嗅探二进制/文本（is_probably_binary 本就只采样前 8KB），
    # 避免先把整个大文件读入内存再做判断
    with path.open("rb") as fh:
        head = fh.read(8192)
    if not head:
        result = ParseResult()
        result.warnings.append("文件为空")
        result.compute_stats(0)
        return result
    if is_probably_binary(head):
        # 二进制：扫描器需要完整缓冲，仍整体读入
        with path.open("rb") as fh:
            data = fh.read()
        return parse_stream(data, None, protocol_version=protocol_version)
    # 文本：逐行流式提取（不再整体 read_bytes + decode + splitlines，大日志峰值内存显著下降）
    with path.open("r", encoding="utf-8", errors="replace") as tf:
        data, line_map = extract_bytes_streaming(tf)
    return parse_stream(data, line_map, protocol_version=protocol_version)
