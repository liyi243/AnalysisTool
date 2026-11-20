"""组帧引擎测试：会话配对与流程归类（覆盖用户模拟序列）。"""
from pathlib import Path

from app_svc.pipeline import parse_text
from qgdw3762.flows import group_frames, msg_seq, first_fn

D1 = "68 10 00 41 01 00 FF 00 00 00 04 01 00 00 46 16"          # 链路检测下行
U_CONFIRM = "68 15 00 C1 01 00 FF 00 00 00 00 01 00 00 00 00 00 00 00 C2 16"  # 确认

PAIRS = [
    ("03-F10 查询", "68 0f 00 41 00 00 28 00 00 00 03 02 01 6f 16"),
    ("03-F10 应答", "68 38 00 81 00 00 40 00 00 00 03 02 01 71 2F 00 01 00 00 5A 0F 00 00 02 00 02 05 66 00 05 26 00 00 D0 07 76 02 31 31 32 31 31 32 5A 58 56 43 32 31 31 10 26 73 80 EA 16"),
    ("12-F2 暂停", "68 0f 00 41 00 00 28 73 80 02 12 02 00 72 16"),
    ("确认", "68 15 00 81 00 00 00 00 00 02 00 01 00 FF FF FF FF 00 00 80 16"),
    ("11-F1 添加", "68 17 00 41 00 00 28 73 80 10 11 01 00 01 11 00 00 91 11 12 00 44 16"),
    ("确认2", "68 15 00 81 00 00 00 00 00 10 00 01 00 FF FF FF FF 00 00 8E 16"),
]


def test_session_pairing():
    text = "\n".join(h for _, h in PAIRS)
    frames = parse_text(text).frames
    assert len(frames) == 6
    sessions, groups = group_frames(frames)
    assert len(sessions) == 3                      # 三组请求/应答
    assert [len(s.frame_idx) for s in sessions] == [2, 2, 2]
    assert sessions[0].flow == "模块识别"
    assert sessions[1].flow == "档案同步" and sessions[1].resp_ok is True
    assert sessions[2].flow == "档案同步" and sessions[2].resp_ok is True
    # 流程段聚合：模块识别 → 档案同步（两段被中间无间隔，第2、3会话同流程应合并）
    assert [g.name for g in groups] == ["模块识别", "档案同步"]


def test_sequence_numbers_matched():
    frames = parse_text("\n".join(h for _, h in PAIRS)).frames
    assert msg_seq(frames[0]) == 0 and msg_seq(frames[1]) == 0
    assert msg_seq(frames[2]) == 2 and msg_seq(frames[3]) == 2
    assert msg_seq(frames[4]) == 16 and msg_seq(frames[5]) == 16


def test_single_frame_flow():
    frames = parse_text(D1).frames
    sessions, groups = group_frames(frames)
    assert len(sessions) == 1
    assert sessions[0].flow == "链路检测"
    assert sessions[0].step == "发送测试"


def test_uplink_report_with_confirm():
    # 上行主动上报 + 下行确认（反向配对）
    up = "68 10 00 C1 01 00 FF 00 00 00 06 01 00 00 C8 16"
    ack = "68 0f 00 41 00 00 28 00 00 05 00 01 00 7a 16"
    frames = parse_text(f"{up}\n{ack}").frames
    sessions, _ = group_frames(frames)
    assert len(sessions) == 1
    assert sessions[0].frame_idx == [0, 1]
    assert sessions[0].resp_ok is True
    assert sessions[0].flow == "从节点注册"


def _flow_sample_path():
    return Path(__file__).resolve().parents[1] / "samples" / "流程模拟交互.txt"


def test_flow_sample_file():
    p = _flow_sample_path()
    if not p.exists():
        return
    frames = parse_text(p.read_text(encoding="utf-8")).frames
    assert len(frames) == 18
    sessions, groups = group_frames(frames)
    assert len(sessions) == 9
    names = [g.name for g in groups]
    assert "模块识别" in names and "白名单控制" in names
    assert names.count("档案同步") + names.count("主节点初始化/档案同步") >= 2


def test_fn_extraction():
    frames = parse_text(D1).frames
    assert first_fn(frames[0]) == 1
