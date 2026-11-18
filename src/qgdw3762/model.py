"""376.2 协议解析引擎 — 数据模型。

本模块定义解析结果的核心数据结构，供引擎、测试与 GUI 共同使用。
协议引擎层不依赖任何 GUI 模块。
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Iterator, Optional

# 字段语义分组（字节映射图着色 / 字段树着色依据）
KIND_START = "start"      # 起始符
KIND_LENGTH = "length"    # 长度域
KIND_CTRL = "ctrl"        # 控制码
KIND_ADDR = "addr"        # 地址域
KIND_AFN = "afn"          # 应用层功能码
KIND_SEQ = "seq"          # 帧序域
KIND_DATA = "data"        # 数据单元
KIND_CS = "cs"            # 校验码
KIND_END = "end"          # 结束符
KIND_ERR = "err"          # 异常/无法解析


@dataclass
class Field:
    """一个协议字段（含子字段，构成字段树）。"""

    name: str                 # 字段名，如 "控制码C"
    offset: int               # 相对帧首字节偏移
    length: int               # 字节数
    raw: str                  # 原始 hex，如 "0B"
    value: str = ""           # 解析值；留空则显示 raw
    note: str = ""            # 备注（bit 解释、编码说明等）
    kind: str = KIND_DATA     # 语义分组（着色）
    children: list["Field"] = dc_field(default_factory=list)
    error: bool = False       # 校验失败/异常标记

    def display_value(self) -> str:
        return self.value if self.value else self.raw

    def walk(self) -> Iterator["Field"]:
        """深度优先遍历自身及全部子孙节点。"""
        yield self
        for c in self.children:
            yield from c.walk()

    def find_at(self, byte_index: int) -> Optional["Field"]:
        """返回覆盖指定字节偏移的最深层字段（同级取先出现者）。"""
        best: Optional[Field] = None
        best_depth = -1
        # 广度优先遍历；用头指针前移代替 pop(0)，避免列表头部弹出 O(n) 开销
        queue: list[tuple["Field", int]] = [(self, 0)]
        head = 0
        while head < len(queue):
            f, depth = queue[head]
            head += 1
            if f.offset <= byte_index < f.offset + f.length:
                if depth > best_depth:
                    best, best_depth = f, depth
            for c in f.children:
                queue.append((c, depth + 1))
        return best


@dataclass
class ParsedFrame:
    """一帧报文的完整解析结果。"""

    raw: bytes
    start: int = 0                    # 在源数据流中的起始偏移（多帧场景）
    source_line: int = 0              # 来源文本行号（文件解析场景，0=未知）
    fields: list[Field] = dc_field(default_factory=list)   # 链路层字段树
    direction: str = "未知"           # "下行(集中器→模块)" / "上行(模块→集中器)"
    summary: str = ""                 # 一句话摘要（帧列表展示）
    errors: list[str] = dc_field(default_factory=list)      # 诊断信息
    cs_ok: bool = False
    valid: bool = False               # 结构完整且 CS 通过
    # 便捷信息（引擎解析时填充，供帧列表直接展示）
    ctrl_byte: int | None = None      # 控制码原始值
    ctrl_name: str = ""               # 控制码功能码名称
    afn_byte: int | None = None       # 应用层功能码原始值
    afn_name: str = ""                # AFN 名称
    protocol_version: str = "2019"    # "2013" | "2019"，影响部分字段长度与命名

    @property
    def length(self) -> int:
        return len(self.raw)

    def iter_fields(self) -> Iterator[Field]:
        for f in self.fields:
            yield from f.walk()

    def field_at(self, byte_index: int) -> Optional[Field]:
        for top in self.fields:
            if top.offset <= byte_index < top.offset + top.length:
                return top.find_at(byte_index)
        return None


@dataclass
class FrameCandidate:
    """扫描器定位出的帧候选（解析前的中间产物）。

    为避免噪声/损坏流下的内存放大，不复制帧字节，仅记录位置与长度；
    需要帧字节时由调用方按 source[start:start+length] 切片。
    """

    start: int           # 在源流中的偏移
    length: int          # 候选帧字节长度
    source_line: int = 0
    reason: str = ""     # 无效原因（仅当校验失败）


@dataclass
class ParseResult:
    """一次解析任务的汇总结果（GUI/导出使用）。"""

    frames: list[ParsedFrame] = dc_field(default_factory=list)
    stats: dict = dc_field(default_factory=dict)
    warnings: list[str] = dc_field(default_factory=list)

    def compute_stats(self, input_bytes: int = 0) -> dict:
        up = sum(1 for f in self.frames if f.direction.startswith("上行"))
        down = sum(1 for f in self.frames if f.direction.startswith("下行"))
        bad = sum(1 for f in self.frames if not f.valid)
        self.stats = {
            "total": len(self.frames),
            "up": up,
            "down": down,
            "invalid": bad,
            "input_bytes": input_bytes,
        }
        return self.stats
