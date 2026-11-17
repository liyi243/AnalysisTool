"""解析管线：统一入口（文本/文件 → 帧扫描 → 解析 → 汇总）。"""
from __future__ import annotations

from pathlib import Path

from qgdw3762 import scanner
from qgdw3762.frame import parse_frame
from qgdw3762.model import ParsedFrame, ParseResult
from qgdw3762.textutil import extract_bytes, is_probably_binary


def parse_stream(data: bytes, line_map: list[int] | None = None, protocol_version: str = "2019") -> ParseResult:
    """对字节流分帧并逐帧解析。line_map 提供字节→源文本行号映射。
    protocol_version: "2013" 或 "2019"。
    """
    result = ParseResult()
    candidates, scan_warnings = scanner.scan_frames(data)
    result.warnings.extend(scan_warnings)
    for cand in candidates:
        src_line = cand.source_line
        if line_map and 0 <= cand.start < len(line_map):
            src_line = line_map[cand.start]
        frame = parse_frame(cand.data, start=cand.start, source_line=src_line,
                            protocol_version=protocol_version)
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
    raw = path.read_bytes()
    if not raw:
        result = ParseResult()
        result.warnings.append("文件为空")
        result.compute_stats(0)
        return result
    if is_probably_binary(raw):
        return parse_stream(raw, None, protocol_version=protocol_version)
    text = raw.decode("utf-8", errors="replace")
    return parse_text(text, protocol_version=protocol_version)
