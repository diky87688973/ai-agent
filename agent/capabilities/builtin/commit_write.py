# -*- coding: utf-8 -*-
"""commit_write：统一提交入口——凭 confirm_id 从预览快照分派执行。

- 预览与提交是两个独立工具入口：提交仅传 confirm_id；写参数（含内容）由
  QualityGate 从预览快照恢复，模型不重传（省 token、防漂移）；快照一次性消费防重放；
- 分派：快照记录 tool → executors 表（由装配点 app.py 注入，覆盖全部写类工具）。
- 会话门控只经 `current_context().session.gate`（ToolPort 在管道执行期填齐 session）。
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from agent.capabilities.registry import ToolPlugin
from agent.mechanisms.quality import QualityGate


def _session_gate() -> QualityGate:
    """取当前工具调用的会话门控。"""
    from agent.core.session_scope import current_context

    ctx = current_context()
    session = getattr(ctx, "session", None) if ctx is not None else None
    resolved = getattr(session, "gate", None)
    if resolved is None:
        raise ValueError(
            "取不到会话门控：须经 ToolPort.execute（管道上下文填入 session）调用"
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
        "同一文件刚提交后又要改：若门控要求先 read_file，只是复核落盘后的内容与行号；"
        "已解锁的 confirm_id 仍有效，确认无误后用原 confirm_id 继续提交，不必重新预览。"
    )
    parameters = {
        "confirm_id": {"type": "string", "description": "预览快照 ID（提交唯一凭据）"},
    }
    needs_preview = False
    write_path_keys: tuple[str, ...] = ()

    def __init__(
        self,
        executors: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]],
        dynamic: Any = None,
    ) -> None:
        # 内置执行器是静态表；插件贡献的执行器走 `dynamic`（提交那一刻才查）。
        self._executors = dict(executors)
        self._dynamic = dynamic

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        cid = str(arguments.get("confirm_id") or "").strip()
        if not cid:
            raise ValueError("缺少 confirm_id")
        record = _session_gate().take_record(cid)
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
    executors: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]],
    dynamic: Any = None,
) -> CommitWriteTool:
    """构造 commit_write；门控由管道上下文提供。"""
    return CommitWriteTool(executors, dynamic)
