"""解析报告导出：JSON（结构化）与 TXT（人读）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from app_svc import APP_TITLE, APP_VERSION
from qgdw3762.flows import group_frames
from qgdw3762.model import Field, ParsedFrame, ParseResult


def _field_to_dict(f: Field) -> dict:
    d = {
        "name": f.name,
        "offset": f.offset,
        "length": f.length,
        "raw": f.raw,
        "value": f.display_value(),
    }
    if f.note:
        d["note"] = f.note
    if f.error:
        d["error"] = True
    if f.children:
        d["children"] = [_field_to_dict(c) for c in f.children]
    return d


def _frame_to_dict(fr: ParsedFrame) -> dict:
    return {
        "start_in_source": fr.start,
        "source_line": fr.source_line,
        "length": fr.length,
        "raw_hex": fr.raw.hex(" ").upper(),
        "direction": fr.direction,
        "summary": fr.summary,
        "valid": fr.valid,
        "cs_ok": fr.cs_ok,
        "errors": fr.errors,
        "fields": [_field_to_dict(f) for f in fr.fields],
    }


def export_json(result: ParseResult, path: str | Path) -> Path:
    sessions, groups = group_frames(result.frames)
    payload = {
        "protocol": "Q/GDW 376.2",
        "tool": f"{APP_TITLE} v{APP_VERSION}",
        "stats": result.stats,
        "warnings": result.warnings,
        "flows": [
            {
                "name": g.name,
                "sessions": [
                    {
                        "index": s.index,
                        "frame_numbers": [k + 1 for k in s.frame_idx],  # 1 基帧号
                        "afn": s.afn,
                        "fn": s.fn,
                        "label": s.label,
                        "resp": {True: "确认", False: "否认", None: None}[s.resp_ok],
                    }
                    for s in g.sessions
                ],
            }
            for g in groups
        ],
        "frames": [_frame_to_dict(f) for f in result.frames],
    }
    p = Path(path)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _render_field_lines(fields: Iterable[Field], depth: int, out: list[str]) -> None:
    for f in fields:
        flag = "  [✗]" if f.error else ""
        out.append("    " * depth + f"├─ {f.name}  偏移0x{f.offset:02X}  "
                   f"[{f.raw}]  {f.display_value()}{flag}")
        if f.note:
            out.append("    " * (depth + 1) + f"· {f.note}")
        _render_field_lines(f.children, depth + 1, out)


def render_text(result: ParseResult) -> str:
    lines: list[str] = [
        "=" * 72,
        "376.2 协议解析报告（Q/GDW 376.2 集中器本地通信模块接口协议）",
        "=" * 72,
        f"帧总数: {result.stats.get('total', 0)}  "
        f"上行: {result.stats.get('up', 0)}  下行: {result.stats.get('down', 0)}  "
        f"校验失败: {result.stats.get('invalid', 0)}",
        "",
    ]
    if result.warnings:
        lines.append("⚠ 告警:")
        lines.extend(f"  - {w}" for w in result.warnings)
        lines.append("")
    # 流程会话概览（组帧）
    sessions, groups = group_frames(result.frames)
    if len(sessions) > 1:
        lines.append("◈ 流程会话（组帧）")
        for g in groups:
            lines.append(f"  ▶ {g.name}（{len(g.sessions)} 步）")
            for s in g.sessions:
                frs = "↔".join(f"#{k + 1}" for k in s.frame_idx)
                mark = {True: "✓", False: "✗", None: ""}[s.resp_ok]
                lines.append(f"      {frs}  {s.label} {mark}")
        lines.append("")
    for i, fr in enumerate(result.frames, 1):
        src = f"（来源行 {fr.source_line}）" if fr.source_line else ""
        lines.append("-" * 72)
        lines.append(f"帧 #{i}  {fr.direction}  长度 {fr.length} 字节  "
                     f"{'✓ 校验通过' if fr.valid else '✗ 校验失败'}{src}")
        lines.append(f"原始: {fr.raw.hex(' ').upper()}")
        if fr.summary:
            lines.append(f"摘要: {fr.summary}")
        if fr.errors:
            lines.append("诊断:")
            lines.extend(f"  ! {e}" for e in fr.errors)
        _render_field_lines(fr.fields, 0, lines)
        lines.append("")
    return "\n".join(lines)


def export_text(result: ParseResult, path: str | Path) -> Path:
    p = Path(path)
    p.write_text(render_text(result), encoding="utf-8")
    return p
