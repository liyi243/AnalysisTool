"""组帧引擎：将连续交互帧组织为"请求/应答会话"，并归类到业务流程。

流程规则依据：
- Q/GDW 1376.2—2013 附录 A（识别流程 A.2 / 档案同步 A.3 / 点抄 A.4 / 从节点注册 A.5 /
  定时抄表 A.6 / 广播 A.7）
- 华立《1376.2-2013 应用接口协议 V2.3》第 2 章（主节点初始化 / 模块识别 /
  白名单控制 / 档案同步 / 从节点注册 / 节点事件上报）

配对依据：信息域 R6"报文序列号"（标准 5.2.1 k)：匹配上下行报文的请求应答对应关系）。
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from .model import ParsedFrame

# ── 流程规则表：(AFN, Fn) → (流程名, 步骤说明) ────────────────
FLOW_RULES: dict[tuple[int, int], tuple[str, str]] = {
    # 主节点初始化（华立 2.2 / 标准 5.5.2）
    (0x01, 1): ("主节点初始化", "硬件初始化(复位)"),
    (0x01, 2): ("主节点初始化/档案同步", "参数区初始化(清空档案并全网复位)"),
    (0x01, 3): ("主节点初始化", "数据区初始化"),
    # 模块识别（附录 A.2 / 华立 2.3）
    (0x03, 10): ("模块识别", "本地通信模块运行模式信息(上报/查询)"),
    (0x03, 4): ("模块识别", "查询主节点地址"),
    (0x05, 1): ("模块识别", "设置主节点地址"),
    # 白名单控制（华立 2.4）
    (0xF0, 5): ("白名单控制", "查询白名单状态"),
    (0xF0, 4): ("白名单控制", "设置白名单开关"),
    # 档案同步（附录 A.3 / 华立 2.5）
    (0x12, 2): ("档案同步", "暂停路由"),
    (0x12, 3): ("档案同步/点抄", "恢复路由"),
    (0x12, 1): ("档案同步/点抄", "重启路由"),
    (0x10, 1): ("档案同步", "查询从节点数量"),
    (0x10, 2): ("档案同步", "读取从节点信息(逐条比对档案)"),
    (0x10, 3): ("档案同步", "指定从节点的上一级中继路由信息"),
    (0x11, 1): ("档案同步", "添加从节点"),
    (0x11, 2): ("档案同步", "删除从节点"),
    (0x11, 3): ("档案同步", "设置从节点固定中继路径"),
    # 从节点注册（附录 A.5 / 华立 2.6）
    (0x11, 5): ("从节点注册", "激活从节点主动注册"),
    (0x11, 6): ("从节点注册", "终止从节点主动注册"),
    (0x06, 1): ("从节点注册", "上报从节点信息"),
    (0x06, 4): ("从节点注册", "上报从节点信息及设备类型"),
    (0x06, 10): ("从节点注册", "上报从节点离线信息(华立)"),
    (0x06, 14): ("从节点注册", "上报485从节点注册(华立)"),
    (0x06, 3): ("从节点注册", "上报路由工况变动(搜表/抄表任务结束)"),
    # 节点事件上报（华立 2.7）
    (0x06, 5): ("节点事件上报", "上报从节点事件"),
    (0x06, 249): ("节点事件上报", "主节点事件上报(华立)"),
    # 点抄/监控（附录 A.4 / A.6）
    (0x13, 1): ("点抄/监控", "监控从节点"),
    (0x14, 1): ("点抄/监控", "路由请求抄读内容"),
    (0x14, 2): ("点抄/监控", "路由请求集中器时钟"),
    (0x14, 3): ("点抄/监控", "请求依通信延时修正通信数据"),
    (0x06, 2): ("点抄/监控", "上报抄读数据"),
    # 广播（附录 A.7）
    (0x03, 9): ("广播流程", "广播通信时长查询"),
    (0x05, 3): ("广播流程", "启动广播"),
    # 网络维护/查询
    (0x10, 21): ("网络维护", "查询网络拓扑信息"),
    (0x10, 4): ("网络维护", "查询路由运行状态"),
    (0x10, 9): ("网络维护", "查询网络规模"),
    (0x10, 31): ("网络维护", "查询相位信息"),
    # 数据转发/抄表
    (0x02, 1): ("数据转发/抄表", "转发通信协议数据帧(内嵌645)"),
    (0xF1, 1): ("数据转发/抄表", "集中器主动并发抄表"),
    # 链路检测
    (0x04, 1): ("链路检测", "发送测试"),
    (0x04, 2): ("链路检测", "从节点点名"),
    (0x04, 3): ("链路检测", "报文通信测试"),
}


def msg_seq(fr: ParsedFrame) -> int | None:
    """提取信息域 R6 报文序列号；解析失败返回 None。"""
    for f in fr.fields:
        if f.name == "信息域R":
            for c in f.children:
                if c.name == "报文序列号":
                    try:
                        return int(c.display_value())
                    except ValueError:
                        return None
    return None


def first_fn(fr: ParsedFrame) -> int | None:
    """提取 DT 解出的首个 Fn。"""
    for f in fr.fields:
        if f.name == "数据单元标识DT":
            v = f.display_value()
            if v.startswith("F") and "无有效" not in v:
                try:
                    return int(v.split("、")[0][1:])
                except ValueError:
                    return None
    return None


def is_up(fr: ParsedFrame) -> bool:
    return fr.direction.startswith("上行")


@dataclass
class Session:
    """一次请求/应答交互（或孤立帧）。"""

    index: int                      # 会话序号（1 基）
    frame_idx: list[int] = dc_field(default_factory=list)   # 帧索引（0 基）
    afn: int | None = None
    fn: int | None = None
    label: str = ""                 # 如 "AFN=10H F1 从节点数量"
    flow: str = "其他/未归类"
    step: str = ""
    resp_ok: bool | None = None     # 应答结果：True 确认 / False 否认 / None 无应答或数据应答

    @property
    def is_query_resp(self) -> bool:
        """应答是否为数据应答（非确认/否认）。"""
        return self.resp_ok is None


@dataclass
class FlowGroup:
    """同类流程的连续会话段。"""

    name: str
    sessions: list[Session] = dc_field(default_factory=list)


def group_frames(frames: list[ParsedFrame]) -> tuple[list[Session], list[FlowGroup]]:
    """组帧：配对会话并归类流程。返回（会话列表, 流程分组列表）。"""
    sessions: list[Session] = []
    n = len(frames)
    i = 0
    while i < n:
        fr = frames[i]
        afn = fr.afn_byte
        fn = first_fn(fr)
        sess = Session(index=len(sessions) + 1, frame_idx=[i], afn=afn, fn=fn)
        if afn is not None and fn is not None and (afn, fn) in FLOW_RULES:
            sess.flow, sess.step = FLOW_RULES[(afn, fn)]
        elif afn is not None:
            from .consts import afn_name
            sess.label = f"AFN={afn:02X}H"
            sess.step = afn_name(afn)
        if afn == 0x00 and fn in (1, 2):
            # 孤立确认/否认（前面未并入任何会话时才会走到这里）
            sess.flow = "确认应答"
            sess.step = "确认" if fn == 1 else "否认"
            sess.resp_ok = fn == 1

        # ── 配对应答 ──
        seq = msg_seq(fr)
        j = i + 1
        if not is_up(fr):
            # 下行请求 → 吞掉紧随的上行应答（R6 相同或 AFN=00H 确认/否认）
            while j < n and is_up(frames[j]):
                nxt = frames[j]
                nxt_afn = nxt.afn_byte
                if nxt_afn == 0x00 or (seq is not None and msg_seq(nxt) == seq):
                    sess.frame_idx.append(j)
                    if nxt_afn == 0x00:
                        nf = first_fn(nxt)
                        sess.resp_ok = (nf == 1) if nf in (1, 2) else None
                    j += 1
                else:
                    break
        else:
            # 上行主动上报 → 吞掉紧随的下行确认
            while j < n and not is_up(frames[j]):
                nxt = frames[j]
                if nxt.afn_byte == 0x00:
                    sess.frame_idx.append(j)
                    nf = first_fn(nxt)
                    sess.resp_ok = (nf == 1) if nf in (1, 2) else None
                    j += 1
                else:
                    break
        # 会话标签
        if not sess.label:
            fn_txt = f"F{fn}" if fn is not None else "?"
            resp_txt = {True: "→ 确认", False: "→ 否认", None: ""}[sess.resp_ok]
            sess.label = f"AFN={afn:02X}H {fn_txt} {sess.step} {resp_txt}".strip()
        else:
            sess.label += {True: " → 确认", False: " → 否认", None: ""}[sess.resp_ok]
        sessions.append(sess)
        i = j

    # ── 聚合流程段（连续同流程会话） ──
    groups: list[FlowGroup] = []
    for s in sessions:
        if groups and groups[-1].name == s.flow:
            groups[-1].sessions.append(s)
        else:
            groups.append(FlowGroup(name=s.flow, sessions=[s]))
    # 相邻同流程段合并（如 档案同步 → 确认应答 → 档案同步）
    merged: list[FlowGroup] = []
    for g in groups:
        if merged and merged[-1].name == g.name:
            merged[-1].sessions.extend(g.sessions)
        else:
            merged.append(g)
    return sessions, merged
