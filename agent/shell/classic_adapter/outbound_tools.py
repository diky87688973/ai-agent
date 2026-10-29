# -*- coding: utf-8 -*-
"""出站适配的工具事件族：`tool_*` 内核事实 → 经典界面的工具卡帧。

覆盖起卡、进度、暂停确认与收卡；每张卡的终态只发一帧。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import agent.shell.classic_adapter.contract as C


@dataclass
class PendingToolCall:
    """一次工具调用的进站记录（供 tool_end 组装 preview 用）。"""

    tool_call_id: str
    script: str
    args: Dict[str, Any] = field(default_factory=dict)


class ToolFrames:
    """工具事件的翻译（挂在 `ClassicStream` 上）。"""

    def _on_tool_call(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        call_id = str(d.get("call_id") or "")
        if not call_id:
            return []          # 没有 id 就配不上 tool_end，不如不发
        name = str(d.get("name") or "")
        args = d.get("arguments") if isinstance(d.get("arguments"), dict) else {}
        script = C.tool_script(name)
        self.pending[call_id] = PendingToolCall(call_id, script, dict(args))
        self._tools_in_step += 1
        # 待确认卡由内核事实 `turn_awaiting_user` 转成：
        # `turn_awaiting_user`（带 `call_id`/标题/选项），由 `_on_turn_awaiting_user`
        # 转成卡片。那样选项以工具声明的为准，不比这里的模型原始入参更差。
        return [self._ev(C.EV_TOOL_START, tool_call_id=call_id, script=script, args=dict(args))]

    def _on_tool_progress(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        call_id = str(d.get("call_id") or "")
        text = str(d.get("text") or "")
        if not call_id or not text:
            return []
        frame = self._ev(
            C.EV_TOOL_PROGRESS,
            tool_call_id=call_id,
            stream=str(d.get("stream") or "stdout"),
            text=text,
            done=bool(d.get("done")),
        )
        # 命令在问人（winget / npm init 之类）时把提示透传给经典界面：
        # 它据此在工具卡里挂一条输入条（对照经典界面的 `renderRunCommandInputBar`）。
        awaiting = d.get("awaiting_input")
        if isinstance(awaiting, dict) and awaiting:
            frame["awaiting_input"] = awaiting
        return [frame]

    def _on_tool_suspended(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """工具声明"需要外部输入" → 经典界面的待确认卡（当前事实名）。

        与 `_on_turn_awaiting_user` 是同一件事的两种事实名：
        - `turn_awaiting_user`：回合级暂停事实，载荷扁平带 title/confirms；
        - `tool_suspended`：工具级挂起事实，选项在 `envelope` 里（当前）；

        适配层两个都认，吸收词汇差异。

        卡片挂在专用事实上：按两段式设计，首段不产生结果事实
        （那次调用还没返回），所以没有结果事件可以挂载。
        """
        call_id = str(d.get("call_id") or "")
        if not call_id:
            return []
        envelope = d.get("envelope") if isinstance(d.get("envelope"), dict) else {}
        if str(envelope.get("kind") or "") == "vision_consent":
            title = str(envelope.get("title") or "").strip()
            confirms = envelope.get("confirms")
            endpoint = str(envelope.get("confirm_path") or "").strip()
            request_id = str(envelope.get("request_id") or "").strip()
            if not title or not isinstance(confirms, list) or not confirms or not endpoint or not request_id:
                self._awaiting_confirm = True
                self.pending.pop(call_id, None)
                return [self._ev(
                    C.EV_TOOL_END, tool_call_id=call_id, ok=False, preview="",
                    user_confirm_required=False,
                )]
            self._awaiting_confirm = True
            self.pending.pop(call_id, None)
            return [self._ev(
                C.EV_TOOL_END,
                tool_call_id=call_id,
                ok=True,
                preview="",
                user_confirm_required=True,
                user_confirm_title=title,
                user_confirm_options=[str(x) for x in confirms],
                user_confirm_multi=False,
                user_confirm_endpoint=endpoint,
                user_confirm_endpoint_method=str(envelope.get("confirm_method") or "POST"),
                user_confirm_request_id=request_id,
            )]
        if str(envelope.get("kind") or "") == "approval":
            # 审批帧带描述，按钮是同意和驳回，不带选项列表。
            desc = str(envelope.get("option_desc") or "").strip()
            self._awaiting_confirm = True
            self.pending.pop(call_id, None)
            return [self._ev(
                C.EV_TOOL_END,
                tool_call_id=call_id,
                ok=True,
                preview="",
                approval_required=True,
                approval_title="审批",
                approval_desc=desc,
            )]
        title = str(envelope.get("title") or "").strip()
        confirms = envelope.get("confirms")
        if not title or not isinstance(confirms, list) or not confirms:
            # 工具没给可渲染的选项（例如它要自由文本）：仍弹卡片，只留自定义输入
            title = title or f"{d.get('name') or '工具'}需要你的输入"
            confirms = []
        self._awaiting_confirm = True
        # 待确认卡已发：把这张卡从 `pending` 摘掉。内核紧接着还会发
        # `tool_ended{status:"suspended"}`，那会走 `_on_tool_ended` 的兜底分支
        # 再收一次同一张卡 —— 契约上就是重复帧：
        # 按 id 幂等渲染的客户端会出现重复条目。
        # 摘除动作在 return 之前执行。
        self.pending.pop(call_id, None)
        return [self._ev(
            C.EV_TOOL_END,
            tool_call_id=call_id,
            ok=True,                 # 停下来等用户是协议的一环
            preview="",
            user_confirm_required=True,
            user_confirm_title=title,
            user_confirm_options=[str(x) for x in confirms],
            user_confirm_multi=bool(envelope.get("multi")),
        )]

    def _on_turn_awaiting_user(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """回合停在"等用户作答" → 把内核事实变成经典界面的待确认卡。

        卡片挂在专用事实上的原因：按两段式设计，首段不产生结果事实
        （那次调用还没返回），所以没有结果事件可以挂载。内核为此产出这条专用事实，
        携带 `call_id` / `title` / `confirms`，选项以工具声明的为准
        （选项以工具声明的为准）。

        经典界面的卡片靠 `tool_end` 上的 `user_confirm_required` 渲染，所以这里发一个
        `tool_end`：卡片就是这次调用的界面呈现，而这次调用确实"停在了等人这一步"。

        发完同样把它从 `pending` 摘掉：
        否则内核随后补的终态会再收一次同一张卡，产生重复帧。
        """
        call_id = str(d.get("call_id") or "")
        title = str(d.get("title") or "").strip()
        confirms = d.get("confirms")
        if not call_id or not title or not isinstance(confirms, list) or not confirms:
            return []
        self._awaiting_confirm = True
        # 与 `_on_tool_suspended` 同理：摘掉，避免随后的终态事实重复收卡。
        # 必须在 `return` 之前。
        self.pending.pop(call_id, None)
        return [self._ev(
            C.EV_TOOL_END,
            tool_call_id=call_id,
            ok=True,                 # 停下来等用户是协议的一环
            preview="",
            user_confirm_required=True,
            user_confirm_title=title,
            user_confirm_options=[str(x) for x in confirms],
            user_confirm_multi=bool(d.get("multi")),
        )]

    def _on_tool_started(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """工具开始调用：起工具卡，标签「进行中」。

        监听者也可以在这里起 RT、修剪参数——事件本身带 `arguments`。
        """
        call_id = str(d.get("call_id") or "")
        if not call_id:
            return []
        name = str(d.get("name") or "")
        args = d.get("arguments") if isinstance(d.get("arguments"), dict) else {}
        script = C.tool_script(name)
        self.pending[call_id] = PendingToolCall(call_id, script, dict(args))
        self._tools_in_step += 1
        return [self._ev(C.EV_TOOL_START, tool_call_id=call_id, script=script,
                         args=dict(args))]

    def _on_tool_done(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """工具成功完成 → 卡片标签绿色 `Done`。"""
        return self._finish_tool(d, ok=True)

    def _on_tool_failed(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """工具失败 → 卡片标签红色 `Fail`。"""
        return self._finish_tool(d, ok=False)

    def _on_tool_canceled(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """工具被取消 → 卡片标签 `Stoped`（预留：取消能力尚未接线，先让映射就位）。"""
        call_id = str(d.get("call_id") or "")
        pend = self.pending.pop(call_id, None)
        if pend is None:
            return []
        return [self._ev(C.EV_TOOL_END, tool_call_id=call_id,
                         ok=False, canceled=True, preview="",
                         elapsed_s=d.get("elapsed_s"))]

    def _on_tool_result(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """历史结果事实（`tool_result{ok, data, error}`）→ 收卡。

        当前用 `tool_done` / `tool_failed` / `tool_ended`；保留这一支是为了让
        以 `tool_result` 落盘的结果事实仍能被翻译。
        """
        return self._finish_tool(d, ok=bool(d.get("ok")))

    def _on_tool_ended(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """工具终态（与 `tool_started` 配对）。

        它在结果事实之后紧随发出（`tool_done` / `tool_failed` / `tool_suspended`
        已经各自把卡片收过尾了），所以到这里只做兜底：若还有没被收尾的卡片
        （例如出现了没预料到的终止路径），在这里收掉——保证每张卡都有终态，
        不会永远停在「进行中」。卡片已被收过就走空（`pending` 里没有了）。
        """
        call_id = str(d.get("call_id") or "")
        if not call_id or call_id not in self.pending:
            return []
        return self._finish_tool(d, ok=(str(d.get("status") or "") != "failed"))

    def _finish_tool(self, d: Dict[str, Any], *, ok: bool) -> List[Dict[str, Any]]:
        """工具结果 → 经典界面的 `tool_end`（含卡片标签与结果预览）。"""
        call_id = str(d.get("call_id") or "")
        pend = self.pending.pop(call_id, None)
        if pend is None:
            return []          # 经典界面找不到 tool_call_id 就整个忽略
        data = d.get("data")
        envelope = data if isinstance(data, dict) else {}
        error = str(d.get("error") or "")

        out: List[Dict[str, Any]] = []
        frame: Dict[str, Any] = {
            "tool_call_id": call_id,
            "ok": ok,
            "preview": _preview_json(pend.script, data, error, ok,
                                     elapsed_s=d.get("elapsed_s")),
        }
        if d.get("elapsed_s") is not None:
            frame["elapsed_s"] = d.get("elapsed_s")
        images = C.public_tool_images(d.get("attachments"))
        if images:
            frame["images"] = images
        # ⚠️ `script` 是经典界面判别"这是哪类工具"的唯一依据，原样带上。
        #
        # 经典界面的 `fillToolPreview(o,ev)` 第 2 行就是
        # `const sc=(ev.script||"").toLowerCase();`，之后所有预览分支
        # （`run_command` 的实时输出、`write_file`/`replace_in_file` 的 diff …）
        # 都以 `sc` 为条件。漏发它 → `sc=""` → 一个分支都不进 → 预览槽永远空白。
        #
        # 帧带 `api_name` + `script`（`agent_runtime.py`
        # 三处 yield 都是 `{"type":"tool_end","api_name":…,"script":…,"tool_call_id":…,
        # "ok":…,"preview":…}`）。经典界面的 `onToolEnd` 直接把这个帧当事件用，
        # 所以 `ev.script` 一定有值 —— 漏发它就是漏了经典界面契约的一半。
        frame["script"] = pend.script
        frame["api_name"] = pend.script
        # ⚠️ `data.confirm_id` 不映射为 `user_confirm_required`。
        #
        # `confirm_id` 是写盘门控的二阶提交锁，不是"等用户点卡片"：
        # 写盘门控给预览类工具的成功结果挂上它，意思是
        # "锁已建好，模型接着调提交工具并把 `confirm_id` 传回来"。
        # 用户交互不发生在这一步。
        #
        # 契约里没有"写盘需要确认 / 允许提交 / 拒绝"这段卡片文案：
        # 那段文案在契约里根本不存在，而且 `user_confirm_required`
        # 在经典界面里是 100% 走弹窗的（`openUserConfirmModalFromToolEnd`，
        # 会 `userConfirmBlocking=true` + `goBtn.disabled=true`）。虚构它有双重害处：
        #   ① 用户看到一张没人触发的内嵌卡，还得手动点 ✅；
        #   ② 模型完全不知道发生了这个交互（`tool_done` 已正常返回，模型以为流程在跑）。
        #
        # 真正的挂起只有一条路：工具自己 `Outcome.suspend` / `await_user=True`
        # （由 `_on_tool_suspended` 处理）——只有那时才弹模态。
        #
        # 清单：经典界面从 `todo_list_data` 读（`todo_list` 为真才继续读）
        if pend.script == "todo_list" and (
            envelope.get("items") is not None or envelope.get("close")
        ):
            frame["todo_list"] = True
            frame["todo_list_data"] = {
                "items": envelope.get("items") or [],
                "collapsed": bool(envelope.get("collapsed")),
                "close": bool(envelope.get("close")),
            }
        out.append(self._ev(C.EV_TOOL_END, **frame))

        # `run_type` 切模式 → 补一帧 `mode_changed`。
        #
        # 该工具直接写 `live_state.set_mode()`，但不发 `mode_changed`；
        # 而经典界面的模式按钮只在 `mode_changed`（与 `conversation`）时刷新，
        # 所以模型用工具切换模式后必须由这里补一帧，否则按钮停在旧值。
        # 对照：`goal` 不需要在这里补——经典界面自己在 `onToolEnd` 里读工具结果
        # 刷新「目标」按钮（实现在 agent-ui.js 的 goal 分支）。
        if ok and pend.script == "run_type":
            switched = str(envelope.get("action") or "") == "switch"
            mode = envelope.get("run_type")
            if switched and mode:
                out.append(self._ev(C.EV_MODE_CHANGED, mode=C.normalize_mode(mode)))
        return out


def _preview_json(script: str, data: Any, error: str, ok: bool,
                  elapsed_s: Any = None) -> str:
    """`tool_end.preview` 是 JSON 字符串（经典界面会 `JSON.parse`，失败回落原文）。

    与回灌模型的信封同形（见 `session_log._tool_envelope`）：
      - 成功：`{"ok": true, "data": <工具结果>}`
      - 失败：`{"ok": false, "error": "…"}`（可选附带 `data`）

    内层字段仍各工具不同（经典界面读 `data.stdout` / `data.diffText` /
    `data.diff_text` / `data.confirm_id` / `data.restored_path`）。
    """
    import json

    if not ok:
        payload: Dict[str, Any] = {"ok": False, "error": error}
        if data is not None:
            payload["data"] = data
    elif isinstance(data, dict):
        payload = {"ok": True, "data": data}
    else:
        payload = {"ok": True, "data": {"value": data}}
    if elapsed_s is not None:
        payload["elapsed_s"] = elapsed_s
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "error": "结果无法序列化"}, ensure_ascii=False)
