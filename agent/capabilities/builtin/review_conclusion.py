# -*- coding: utf-8 -*-
"""review_conclusion：写盘后 review 提交 / 预览解锁 / 预览取消。

写盘链路只有预览 → review → 提交（仅 `confirm_id`）。
调用本工具即"提交结论"（带 `confirm_id` 时并解锁预览）。
提交结论 → 门控 review_done()（清 pending_review、解除跨文件写限制）；
confirm_id → gate.confirm 解锁；cancel_preview → gate.discard 释放预览。
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


class ReviewConclusionTool(ToolPlugin):
    """review 结论提交与预览解锁。"""

    name = "review_conclusion"
    label = "提交 review 结论"
    icon = "🔍"
    description = (
        "写盘前必做：提交 review 结论并解锁预览。"
        "结论须基于本次改动的实际审阅、给出验证证据（≥30 字）；"
        "带 confirm_id 时解锁，之后用该 confirm_id 调 commit_write 落盘。"
        "cancel_preview 取消预览。"
    )
    parameters = {
        "conclusion": {"type": "string", "description": "review 结论文本（至少 30 字，须含验证证据；取消预览时可省略）"},
        "file_name": {"type": "string", "description": "本次 review 涉及的文件名，多个用逗号分隔（必填）"},
        "review_type": {"type": "string", "description": "review 类型（默认 file）"},
        "confirm_id": {"type": "string", "description": "要解锁的预览快照 ID（可选）"},
        "cancel_preview": {"type": "boolean", "description": "true 时取消该 confirm_id 预览（释放锁）"},
    }

    def __init__(self, gate: GateRef) -> None:
        self._gate = gate

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        text = str(arguments.get("conclusion") or "").strip()
        fn = str(arguments.get("file_name") or "").strip()
        if not fn:
            raise ValueError("file_name 必填：请填写本次 review 涉及的一个或多个文件名，多个用逗号分隔。")
        cancel = bool(arguments.get("cancel_preview", False))
        if not cancel and len(text) < 30:
            raise ValueError(
                "结论至少 30 字，必须给出真实验证结果与证据，不能只写「验证通过」。"
                "示例：'review结论：xxx 修复了空指针异常并加 None 判断，用 py_compile 确认语法通过，跑测试全部 PASS。'"
                f"（当前 {len(text)} 字）"
            )
        review_type = str(arguments.get("review_type") or "file")
        cid = str(arguments.get("confirm_id") or "").strip()

        # 调用即"提交结论"，并按需解锁预览；写盘链路只有：预览 → review → 提交（仅 confirm_id）。
        # 解锁必须由显式调用触发：靠对模型不可见的参数默认值，漏传就会静默解锁失败。
        # ⚠️ 下面 `cancel` 分支必须在 `confirm` **之前**：取消不能变成解锁。

        if cid and cancel:
            ok = _resolve_gate(self._gate).discard(cid)
            if not ok:
                raise ValueError(f"confirm_id 无效或已被消耗: {cid}")
            return {
                "reviewed": True,
                "review_type": review_type,
                "file_name": fn,
                "confirm_id": cid,
                "message": "预览已取消。",
            }

        if cid:
            ok = _resolve_gate(self._gate).confirm(cid)
            if not ok:
                raise ValueError(f"confirm_id 无效或已被消耗: {cid}")

        _resolve_gate(self._gate).review_done()
        return {
            "reviewed": True,
            "review_type": review_type,
            "file_name": fn,
            "confirm_id": cid,
            "message": "review 结论已记录，confirm_id 已解锁。" if cid else "review 结论已记录。",
        }


def build(gate: GateRef = None) -> ReviewConclusionTool:
    """构造 review_conclusion 插件（需门控引用）。

    gate 可传门控实例（直调场景）或"按当前会话解析门控"的可调用（装配态）。
    """
    return ReviewConclusionTool(gate)
