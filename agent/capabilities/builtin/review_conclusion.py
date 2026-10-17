# -*- coding: utf-8 -*-
"""review_conclusion：写盘后 review 提交 / 预览解锁 / 预览取消。

写盘链路只有预览 → review → 提交（仅 `confirm_id`）。
调用本工具即"提交结论"（带 `confirm_id` 时并解锁预览）。
会话门控只经 `current_context().session.gate`。
"""
from __future__ import annotations

from typing import Any, Dict

from agent.capabilities.registry import ToolPlugin
from agent.mechanisms.quality import QualityGate


def _session_gate() -> QualityGate:
    """取当前工具轮次的会话门控。"""
    from agent.core.session_scope import current_context

    ctx = current_context()
    session = getattr(ctx, "session", None) if ctx is not None else None
    resolved = getattr(session, "gate", None)
    if resolved is None:
        raise ValueError(
            "取不到会话门控：须经 ToolPort.execute（管道上下文填入 session）调用"
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
    needs_preview = False
    write_path_keys: tuple[str, ...] = ()

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
        gate = _session_gate()

        # cancel 分支在 confirm 之前：取消不能变成解锁。

        if cid and cancel:
            ok = gate.discard(cid)
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
            ok = gate.confirm(cid)
            if not ok:
                raise ValueError(f"confirm_id 无效或已被消耗: {cid}")

        gate.review_done()
        return {
            "reviewed": True,
            "review_type": review_type,
            "file_name": fn,
            "confirm_id": cid,
            "message": "review 结论已记录，confirm_id 已解锁。" if cid else "review 结论已记录。",
        }


def build() -> ReviewConclusionTool:
    """构造 review_conclusion；门控由管道上下文提供。"""
    return ReviewConclusionTool()
