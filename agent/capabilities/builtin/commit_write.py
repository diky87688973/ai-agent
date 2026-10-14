# -*- coding: utf-8 -*-
"""commit_write：统一提交入口——凭 confirm_id 从预览快照分派执行。

- 预览与提交是两个独立工具入口：提交仅传 confirm_id；写参数（含内容）由
  QualityGate 从预览快照恢复，模型不重传（省 token、防漂移）；快照一次性消费防重放；
- 分派：快照记录 tool → executors 表（由装配点 app.py 注入，覆盖全部写类工具）。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Union

from agent.capabilities.registry import ToolPlugin
from agent.mechanisms.quality_gate import QualityGate

GateRef = Union[QualityGate, Callable[[], QualityGate], None]


def _resolve_gate(gate: GateRef) -> QualityGate:
    """解析本次调用的会话门控。

    优先用构造期给的引用（门控对象或取门控的回调）；没有给就**从会话上下文取**
    ——门控本来就住在 `SessionContext.gate` 里，而工具轮次的上下文是共享数据结构，
    直接读即可，不必让装配层专门造一个"能摸到门控的函数"传进来。
    """
    if gate is not None:
        return gate() if callable(gate) else gate
    from agent.core.session_scope import current_context

    ctx = current_context()
    session = getattr(ctx, "session", None) if ctx is not None else None
    resolved = getattr(session, "gate", None)
    if resolved is None:
        raise ValueError(
            "取不到会话门控：既未注入，也不在工具轮次上下文内（须经 ToolPipeline.execute 调用）"
        )
    return resolved


class CommitWriteTool(ToolPlugin):
    """提交：仅凭 confirm_id；写参数由门控从预览快照恢复后分派执行。"""

    name = "commit_write"
    label = "提交写盘"
    icon = "💾"
    description = (
        "凭 confirm_id 提交写预览并落盘。"
        "前置：必须先通过 review_conclusion 的 review。"
        "写参数由门控从预览快照恢复并分派执行。"
    )
    parameters = {
        "confirm_id": {"type": "string", "description": "预览快照 ID（提交唯一凭据）"},
    }

    def __init__(
        self,
        gate: GateRef,
        executors: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]],
        dynamic: Any = None,
    ) -> None:
        self._gate = gate
        # 内置执行器是静态表；插件贡献的执行器走 `dynamic`（提交那一刻才查），
        # 所以插件装配顺序不影响提交能不能解析到。
        self._executors = dict(executors)
        self._dynamic = dynamic

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        cid = str(arguments.get("confirm_id") or "").strip()
        if not cid:
            raise ValueError("缺少 confirm_id")
        record = _resolve_gate(self._gate).take_record(cid)
        if record is None:
            raise ValueError("confirm_id 无效或已使用：请重新预览")
        tool = str(record.get("tool") or "")
        executor = self._executors.get(tool)
        if executor is None and self._dynamic is not None:
            executor = self._dynamic.get(tool)
        if executor is None:
            raise ValueError(f"该预览类型不支持提交：{tool or '（空）'}")
        return executor(dict(record.get("arguments") or {}))


def build(
    gate: GateRef,
    executors: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]],
    dynamic: Any = None,
) -> CommitWriteTool:
    """构造 commit_write 插件（提交入口；需门控与执行器表）。

    gate 可传门控实例（直调场景）或"按当前会话解析门控"的可调用（装配态）。
    `dynamic` 是插件贡献的执行器注册表（`ExecutorRegistry`），可为 None。
    """
    return CommitWriteTool(gate, executors, dynamic)
