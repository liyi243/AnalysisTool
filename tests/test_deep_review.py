"""深度评审回归测试：组帧配对 / 注释截断 / 告警上限 / 导出流程段。"""
from qgdw3762.scanner import scan_frames
from qgdw3762.textutil import extract_bytes


def _frames(hex_lines):
    from app_svc.pipeline import parse_text
    return parse_text("\n".join(hex_lines)).frames


# ── 组帧：单应答配对 ──────────────────────────────────────────

REQ = "68 0f 00 41 00 00 28 73 80 03 10 01 00 70 16"        # 下行 10-F1 seq=3
RESP = "68 13 00 81 00 00 00 00 00 03 10 01 00 76 02 D0 07 E4 16"  # 上行应答 seq=3
REPORT_SAME_SEQ = "68 10 00 C1 01 00 FF 00 00 03 06 01 00 00 C6 16"  # 上行主动上报 seq=3


def test_pairing_takes_only_one_response():
    """同序列号的相邻第二个上行帧（另一上报）不得被吞进会话。"""
    from qgdw3762.flows import group_frames
    frames = _frames([REQ, RESP, REPORT_SAME_SEQ])
    sessions, _ = group_frames(frames)
    # REQ+RESP 一会话；REPORT_SAME_SEQ 独立成会话（此前误吞）
    assert len(sessions) == 2
    assert sessions[0].frame_idx == [0, 1]
    assert sessions[1].frame_idx == [2]
    assert sessions[1].flow == "从节点注册"


def test_unanswered_request_is_own_session():
    from qgdw3762.flows import group_frames
    frames = _frames([REQ])                    # 无应答
    sessions, _ = group_frames(frames)
    assert len(sessions) == 1
    assert sessions[0].frame_idx == [0]
    assert sessions[0].resp_ok is None


def test_structured_fn_and_seq_fields():
    frames = _frames([REQ, RESP])
    assert frames[0].fns == [1] and frames[0].r6_seq == 3
    assert frames[1].fns == [1] and frames[1].r6_seq == 3


def test_unclassified_label_contains_afn_name():
    from qgdw3762.flows import group_frames
    frames = _frames(["68 11 00 41 01 00 FF 00 00 00 F0 01 00 11 22 65 16"])  # F0 F1 无规则
    sessions, _ = group_frames(frames)
    assert "内部调试" in sessions[0].label      # label 含 AFN 名称（此前丢失）


# ── textutil：注释按最早位置截断 ──────────────────────────────

def test_comment_cut_earliest_marker():
    # "--" 在 "//" 之前出现：必须从 "--" 截断，否则注释中 hex 词会漏进流
    line = "68 16 -- 备注 0F 00 // 附注"
    data, _ = extract_bytes(line)
    assert data == bytes.fromhex("6816")


def test_comment_cut_earliest_hash():
    line = "68 16 # 备注 0F 00 // 附注"
    data, _ = extract_bytes(line)
    assert data == bytes.fromhex("6816")


# ── scanner：告警上限 ─────────────────────────────────────────

def test_incomplete_warning_capped():
    # 构造噪声：大量 0x68 + 大 L 值（帧体必然不完整）
    noise = bytes([0x68, 0xFF, 0x7F, 0x41, 0x00]) * 200
    _, warnings = scan_frames(noise)
    incomplete = [w for w in warnings if "不完整" in w]
    assert len(incomplete) <= 5
    assert any("仅展示" in w for w in warnings)   # 有汇总条目


def test_cs_failed_candidates_still_capped():
    # 大量伪帧（68 开头、L=16 与帧长一致、尾 16H、CS 必错 → 每帧一个失败候选）
    blob = b"".join(bytes([0x68, 0x10, 0x00, 0x41, 0x00, 0x00, 0x28, 0x00,
                           0x00, 0x00, 0x03, 0x01, 0x00, 0x00, 0x99, 0x16])
                    for _ in range(1500))
    cands, warnings = scan_frames(blob)
    assert 1000 >= len(cands) >= 1
    assert any("过多" in w for w in warnings)


# ── exporter：流程会话导出 ────────────────────────────────────

def test_export_contains_flows():
    import json
    from app_svc import exporter
    from app_svc.pipeline import parse_text
    # 两组请求/应答 → 2 个会话（导出流程段需 >1 会话）
    result = parse_text("\n".join([REQ, RESP, REQ, RESP]))
    payload = json.loads(json.dumps({
        "flows": [
            {"name": g.name,
             "sessions": [{"index": s.index,
                           "frame_numbers": [k + 1 for k in s.frame_idx],
                           "label": s.label} for s in g.sessions]}
            for g in exporter.group_frames(result.frames)[1]
        ]}))
    assert payload["flows"]
    assert payload["flows"][0]["sessions"][0]["frame_numbers"] == [1, 2]

    text = exporter.render_text(result)
    assert "流程会话" in text and "档案同步" in text


def test_json_export_has_flows_section(tmp_path):
    import json
    from app_svc import exporter
    from app_svc.pipeline import parse_text
    result = parse_text("\n".join([REQ, RESP, REQ, RESP]))
    p = exporter.export_json(result, tmp_path / "r.json")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "flows" in data and data["flows"][0]["name"] == "档案同步"
    assert data["flows"][0]["sessions"][0]["frame_numbers"] == [1, 2]


# ── GUI warnings 截断（纯逻辑等价校验） ───────────────────────

def test_warning_join_capped_shape():
    warnings = [f"偏移 0x{i:X} 处存在起始符但帧体不完整" for i in range(3000)]
    shown = warnings[:5]
    more = len(warnings) - len(shown)
    text = "；".join(shown) + (f"；…另有 {more} 条告警" if more else "")
    assert len(text) < 500     # 截断后远小于全量 join（数万字符）


# ── 噪声含大量 0x68 的整体管线（防告警爆炸传导 UI） ──────────

def test_pipeline_with_heavy_68_noise():
    from app_svc.pipeline import parse_text
    noise = ("68 FF 41 00 " * 500) + REQ
    result = parse_text(noise)
    assert len(result.warnings) <= 8            # 上限 + 汇总，不再逐条爆炸
    valid = [f for f in result.frames if f.valid]
    assert len(valid) == 1                      # 真帧仍被解析
