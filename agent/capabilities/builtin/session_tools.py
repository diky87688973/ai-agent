# -*- coding: utf-8 -*-
"""会话协作工具组：Agent 间互发消息、群发、创建与列表。

- send / multisend / broadcast：投向 MeshState（忙闲原子判定 → 直启或排队）；
- create / list：自由 Agent 的创建与列举（注册表）；
- 发送方身份经 core.session_scope 取 conversation_id；消息包装与 thread 自动生成见 `_build_peer_message`；
- 未实现：限流、哨兵、wait 体系、SSE 发布。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from agent.capabilities.registry import ToolPlugin
from agent.core.session_scope import current_session_id
from agent.mechanisms.mesh import MeshState
from agent.mechanisms.session_store import new_conversation_id

_DEFAULT_SYSTEM_PROMPT = (
    "你是 agent 多 Agent 协作网络中的一员。"
    "收到其他 Agent 的消息时，应通过 session_send 回复对方；"
    "需要群体协作时使用 session_multisend 或 session_broadcast。"
    "涉及写盘时遵循四步协议：预览 → 确认 → 凭 confirm_id 提交 → 重读。"
)

_ROLE_ALIASES = {
    "worker": "全栈开发",
    "dev": "全栈开发",
    "developer": "全栈开发",
    "全栈": "全栈开发",
    "全栈工程师": "全栈开发",
    "后端": "全栈开发",
    "前端": "全栈开发",
    "qa": "QA",
    "测试": "QA",
    "测试工程师": "QA",
    "quality": "QA",
}


def _parse_bool(value: Any) -> Optional[bool]:
    """宽松布尔解析：None → None；字符串按 1/true/yes/on。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _normalize_role(role: str) -> str:
    """角色别名映射：worker / dev / qa 等 → 规范名。"""
    r = str(role or "").strip()
    if not r:
        return r
    low = r.lower()
    for k, v in _ROLE_ALIASES.items():
        if k.lower() == low:
            return v
    return r


def _normalize_target_ids(raw: Any) -> List[str]:
    """target_ids 归一：列表或逗号分隔（含中文逗号）。"""
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    s = str(raw or "").strip()
    if not s:
        return []
    return [x.strip() for x in s.replace("，", ",").split(",") if x.strip()]


def _normalize_tags(raw: Any) -> List[str]:
    """tags 归一：列表或逗号分隔（含中文逗号）。"""
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        return [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]
    return []


def _sender_fields(mesh: MeshState, src_cid: str) -> Dict[str, str]:
    """发送方身份：注册表 meta 优先；缺省 name=cid 前 12 位、role=agent。"""
    meta = mesh.get_agent(src_cid)
    if meta:
        return {
            "_sender": src_cid,
            "_sender_role": str(meta.get("role") or ""),
            "_sender_name": str(meta.get("name") or ""),
        }
    return {"_sender": src_cid, "_sender_role": "agent", "_sender_name": src_cid[:12]}


def _build_peer_message(
    mesh: MeshState,
    src_cid: str,
    message: str,
    *,
    thread_id: str,
    channel: str,
    priority: str,
    requires_reply: bool,
) -> Any:
    """构造 peer 消息：包装头 + 结构化字段；返回 (user_msg, sender)。"""
    sender = _sender_fields(mesh, src_cid)
    thread = str(thread_id or "").strip()
    if not thread:
        prefix = src_cid[:8] if len(src_cid) >= 8 else src_cid
        thread = f"auto-{prefix}-{int(time.time())}"
    channel_s = str(channel or "direct").strip() or "direct"
    parts = [
        f"from={sender['_sender_name'] or sender['_sender']}",
        f"sender_cid={src_cid}",
        f"thread_id={thread}",
        f"channel={channel_s}",
    ]
    if requires_reply:
        parts.append("requires_reply=true")
    tag = "[" + " | ".join(parts) + "]\n"
    user_msg: Dict[str, Any] = {
        "role": "user",
        "content": f"{tag}{message}",
        "_priority": str(priority or "normal"),
        "_agent_peer_message": True,
        "_message_kind": "peer",
        "_channel": channel_s,
        "_thread_id": thread,
        "_requires_reply": bool(requires_reply),
    }
    user_msg.update(sender)
    return user_msg, sender


def _deliver(
    mesh: MeshState,
    src_cid: str,
    target_id: Any,
    message: str,
    *,
    thread_id: str,
    channel: str,
    priority: str,
    requires_reply: Optional[bool],
) -> Dict[str, Any]:
    """单目标投递：校验 → 目标存在性 → 包装 → 原子投递 → 信封。"""
    tid = str(target_id or "").strip()
    if not tid:
        raise ValueError("missing_target：缺少 target_id")
    msg = str(message or "").strip()
    if not msg:
        raise ValueError("missing_message：缺少 message")
    if requires_reply is None:
        raise ValueError(
            "missing_requires_reply：requires_reply 是必填参数。收到消息后，"
            "根据对方消息中的 requires_reply 元数据决定传 true（需回复）或 false（纯通知）。"
        )
    if not src_cid:
        raise ValueError("missing_conversation：缺少 conversation_id（发送方会话 id），无法标识 Agent 身份。")
    if not mesh.session_exists(tid):
        raise ValueError(f"target_not_found：目标会话 {tid} 不存在")
    user_msg, sender = _build_peer_message(
        mesh,
        src_cid,
        msg,
        thread_id=thread_id,
        channel=channel,
        priority=priority,
        requires_reply=bool(requires_reply),
    )
    res = mesh.submit(tid, user_msg)
    base: Dict[str, Any] = {"target_id": tid, "message_sent": msg[:200], "_sender": sender}
    if res.get("queued"):
        base.update({"queued": True, "queued_count": int(res.get("queued_count") or 0)})
    else:
        base.update({"queued": False, "run_id": str(res.get("run_id") or "")})
    return base


class SessionSendTool(ToolPlugin):
    """点对点发送：触发接收方执行或排队。"""

    name = "session_send"
    label = "发送到会话"
    icon = "💬"
    description = "向目标 Agent 发送消息并触发其执行；目标忙时进入 inbox 队列（requires_reply 必填）。"
    parameters = {
        "target_id": {"type": "string", "description": "目标会话 id"},
        "message": {"type": "string", "description": "消息内容"},
        "priority": {"type": "string", "description": "优先级（默认 normal）"},
        "thread_id": {"type": "string", "description": "协作线程 id（缺省自动生成）"},
        "requires_reply": {"type": "boolean", "description": "是否要求回复（必填）"},
        "channel": {"type": "string", "description": "通道名（默认 direct）"},
    }

    def __init__(self, mesh: MeshState) -> None:
        self._mesh = mesh

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return _deliver(
            self._mesh,
            current_session_id(),
            arguments.get("target_id"),
            str(arguments.get("message") or ""),
            thread_id=str(arguments.get("thread_id") or ""),
            channel=str(arguments.get("channel") or "direct"),
            priority=str(arguments.get("priority") or "normal"),
            requires_reply=_parse_bool(arguments.get("requires_reply")),
        )


class SessionMultisendTool(ToolPlugin):
    """多目标同文发送：逐目标走 send 通道。"""

    name = "session_multisend"
    label = "多会话分发"
    icon = "💬"
    description = "向多个目标 Agent 发送同一条消息（target_ids 列表或逗号分隔）；返回 sent / skipped / partial。"
    parameters = {
        "target_ids": {"type": "array", "description": "目标会话 id 列表（或逗号分隔字符串）"},
        "message": {"type": "string", "description": "消息内容"},
        "channel": {"type": "string", "description": "通道名（默认 group）"},
        "thread_id": {"type": "string", "description": "协作线程 id（缺省自动生成）"},
        "priority": {"type": "string", "description": "优先级（默认 normal）"},
        "requires_reply": {"type": "boolean", "description": "是否要求回复（必填）"},
    }

    def __init__(self, mesh: MeshState) -> None:
        self._mesh = mesh

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ids = _normalize_target_ids(arguments.get("target_ids"))
        if not ids:
            raise ValueError("missing_targets：缺少 target_ids")
        msg = str(arguments.get("message") or "").strip()
        if not msg:
            raise ValueError("missing_message：缺少 message")
        rr = _parse_bool(arguments.get("requires_reply"))
        if rr is None:
            raise ValueError("missing_requires_reply：requires_reply 是必填参数，必须显式设置 true 或 false。")
        src = current_session_id()
        thread = str(arguments.get("thread_id") or "")
        sent: List[Dict[str, Any]] = []
        skipped: List[Dict[str, str]] = []
        for tid in ids:
            try:
                data = _deliver(
                    self._mesh,
                    src,
                    tid,
                    msg,
                    thread_id=thread,
                    channel=str(arguments.get("channel") or "group"),
                    priority=str(arguments.get("priority") or "normal"),
                    requires_reply=rr,
                )
                sent.append({"target_id": tid, "queued": bool(data.get("queued"))})
            except Exception as exc:
                skipped.append({"target_id": tid, "error": str(exc)})
        if not sent:
            failure = ValueError("all_targets_failed：所有目标发送均失败，请检查 target_ids 与网络状态。")
            failure.data = {
                "sent": sent,
                "skipped": skipped,
                "count": 0,
                "thread_id": thread,
                "partial": False,
                "all_sent": False,
            }
            raise failure
        return {
            "sent": sent,
            "skipped": skipped,
            "count": len(sent),
            "thread_id": thread,
            "partial": bool(skipped),
            "all_sent": not skipped,
        }


class SessionBroadcastTool(ToolPlugin):
    """按 tag（可叠加 role）广播：禁止全员广播。"""

    name = "session_broadcast"
    label = "广播到多会话"
    icon = "💬"
    description = "按 tag 向目标群组广播消息（tag 必填；可叠加 role 过滤与 exclude_self）。"
    parameters = {
        "role": {"type": "string", "description": "按角色过滤（可选）"},
        "tag": {"type": "string", "description": "目标群组标签（必填）"},
        "exclude_self": {"type": "boolean", "description": "是否排除发送者自己（默认 true）"},
        "message": {"type": "string", "description": "消息内容"},
        "requires_reply": {"type": "boolean", "description": "是否要求回复（必填）"},
        "thread_id": {"type": "string", "description": "协作线程 id（缺省自动生成）"},
        "priority": {"type": "string", "description": "优先级（默认 normal）"},
    }

    def __init__(self, mesh: MeshState) -> None:
        self._mesh = mesh

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        msg = str(arguments.get("message") or "").strip()
        if not msg:
            raise ValueError("missing_message：缺少 message")
        rr = _parse_bool(arguments.get("requires_reply"))
        if rr is None:
            raise ValueError("missing_requires_reply：requires_reply 是必填参数，必须显式设置 true 或 false。")
        tag = str(arguments.get("tag") or "").strip()
        if not tag:
            raise ValueError('missing_tag：session_broadcast 必须传 tag 指定目标群组（如 tag="spy-game"），禁止全员广播。')
        src = current_session_id()
        role = str(arguments.get("role") or "").strip()
        ex = _parse_bool(arguments.get("exclude_self"))
        exclude_self = True if ex is None else ex
        thread = str(arguments.get("thread_id") or "")
        sent: List[str] = []
        skipped: List[Dict[str, str]] = []
        for mid, info in self._mesh.list_agents().items():
            if exclude_self and mid == src:
                continue
            if role and str(info.get("role") or "") != role:
                continue
            tags = info.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            if tag not in tags:
                continue
            try:
                _deliver(
                    self._mesh,
                    src,
                    mid,
                    msg,
                    thread_id=thread,
                    channel="broadcast",
                    priority=str(arguments.get("priority") or "normal"),
                    requires_reply=rr,
                )
                sent.append(mid)
            except Exception as exc:
                skipped.append({"target_id": mid, "error": str(exc)})
        if not sent:
            failure = ValueError("all_targets_failed：广播未送达任何目标，请检查 tag/role 筛选条件。")
            failure.data = {"sent": sent, "skipped": skipped, "count": 0, "partial": bool(skipped), "all_sent": False}
            raise failure
        return {"sent": sent, "skipped": skipped, "count": len(sent), "partial": bool(skipped), "all_sent": not skipped}


class SessionCreateTool(ToolPlugin):
    """创建自由 Agent：注册表登记 + 身份注入通道。"""

    name = "session_create"
    label = "新建会话"
    icon = "💬"
    description = "创建自由 Agent 会话（count 1-50 批量；role / persona / tags / skill；名称规则与别名映射）。"
    parameters = {
        "role": {"type": "string", "description": "角色（别名映射：worker / qa 等）"},
        "name": {"type": "string", "description": "名称（单条创建时使用）"},
        "name_prefix": {"type": "string", "description": "名称前缀（批量创建时拼接序号）"},
        "persona": {"type": "string", "description": "人设文本（缺省含协作指引）"},
        "count": {"type": "integer", "description": "创建数量（1-50，默认 1）"},
        "tags": {"type": "array", "description": "标签（列表或逗号分隔字符串）"},
        "skill": {"type": "string", "description": "Skills 名（记录于 meta；Skills 库未接入）"},
    }

    def __init__(self, mesh: MeshState) -> None:
        self._mesh = mesh

    def _pick_name(self, scope_tags: List[str]) -> str:
        """命名规则：占用集内递增（池未配置时 base+序号）。"""
        taken = set()
        for meta in self._mesh.list_agents().values():
            nm = str(meta.get("name") or "").strip()
            if not nm:
                continue
            if scope_tags:
                m_tags = meta.get("tags") or []
                if isinstance(m_tags, str):
                    m_tags = [m_tags]
                if not any(t in m_tags for t in scope_tags):
                    continue
            taken.add(nm)
        base = "Agent"
        if base not in taken:
            return base
        i = 2
        while f"{base}{i}" in taken:
            i += 1
        return f"{base}{i}"

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            n = max(1, min(50, int(arguments.get("count") or 1)))
        except (TypeError, ValueError):
            n = 1
        base_role = _normalize_role(str(arguments.get("role") or "")) or "Agent"
        base_persona = str(arguments.get("persona") or "").strip()
        tags = _normalize_tags(arguments.get("tags"))
        skill = str(arguments.get("skill") or "").strip()
        created_by = current_session_id()
        agents: List[Dict[str, Any]] = []
        for i in range(n):
            sid = new_conversation_id()
            if n == 1:
                requested = str(arguments.get("name") or arguments.get("name_prefix") or "").strip()
                agent_name = requested or self._pick_name(tags)
            else:
                prefix = str(arguments.get("name_prefix") or arguments.get("name") or "").strip()
                agent_name = f"{prefix}{i + 1}" if prefix else self._pick_name(tags)
            persona_text = base_persona or (
                f"你是多 Agent 协作网络中的 {agent_name}，角色是 {base_role}。"
                "收到其他 Agent 的消息时，应通过 session_send 回复对方；"
                "需要群体协作时使用 session_multisend 或 session_broadcast。"
            )
            system_text = (
                f"{_DEFAULT_SYSTEM_PROMPT}\n\n"
                f"【Agent 身份】\n名称：{agent_name}\n角色：{base_role}\n\n{persona_text}"
            )
            meta = self._mesh.upsert_agent(
                sid,
                name=agent_name,
                role=base_role,
                persona=persona_text,
                system=system_text,
                tags=tags,
                status="idle",
                skill=skill or None,
                created_by=created_by or None,
            )
            agents.append(
                {
                    "cid": sid,
                    "session_id": sid,
                    "name": agent_name,
                    "role": base_role,
                    "tags": tags,
                    "url": f"/?cid={sid}",
                    "meta": meta,
                }
            )
        data: Dict[str, Any] = {"agents": agents, "count": len(agents)}
        if agents:
            data.update(agents[0])
        return data


class SessionListTool(ToolPlugin):
    """列出 Session Mesh 自由 Agent。"""

    name = "session_list"
    label = "列出会话"
    icon = "💬"
    description = "列出协作网络中的自由 Agent（状态派生：running / queued / meta.status；含 queueSize）。"
    parameters: Dict[str, Any] = {}

    def __init__(self, mesh: MeshState) -> None:
        self._mesh = mesh

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        agents: List[Dict[str, Any]] = []
        items = sorted(self._mesh.list_agents().items(), key=lambda kv: str(kv[1].get("name") or kv[0]))
        for cid, meta in items:
            qn = self._mesh.inbox_size(cid)
            if self._mesh.is_running(cid):
                status = "running"
            elif qn:
                status = "queued"
            else:
                status = str(meta.get("status") or "idle")
            row = dict(meta)
            row.update({"cid": cid, "session_id": cid, "status": status, "queueSize": qn})
            agents.append(row)
        return {"agents": agents, "count": len(agents)}


def build_plugins(mesh: MeshState) -> List[ToolPlugin]:
    """构造本组工具（session_send / session_multisend / session_broadcast / session_create / session_list）。"""
    return [
        SessionSendTool(mesh),
        SessionMultisendTool(mesh),
        SessionBroadcastTool(mesh),
        SessionCreateTool(mesh),
        SessionListTool(mesh),
    ]
