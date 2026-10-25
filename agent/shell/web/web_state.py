# -*- coding: utf-8 -*-
"""会话设置与 UI 状态：推理档位、自主模式、状态快照。"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from agent.config import get_reasoning_effort
from agent.shell.web.web_static import MODE_VALUES


class UiStateActions:
    """读写按会话落点的模式、模型、推理档位、自主模式与 todo 状态。"""

    def reasoning_effort_get(self, cid: str) -> Tuple[int, Dict[str, Any]]:
        """读会话级推理档位；同时给出全局默认。"""
        state = self.app.live_state
        if state is None:
            fallback = get_reasoning_effort()
            return 200, {"ok": True, "reasoning_effort": fallback, "global_default": fallback}
        cid = str(cid or "").strip()
        return 200, {
            "ok": True,
            "reasoning_effort": state.get_reasoning_effort(cid),
            "global_default": state.default_effort,
        }

    def reasoning_effort_set(self, cid: str, effort: str) -> Tuple[int, Dict[str, Any]]:
        """设置会话级推理档位。缺 cid 或非法值 → `ok:False`。"""
        state = self.app.live_state
        cid = str(cid or "").strip()
        if not cid:
            return 200, {"ok": False, "error": "conversation_id required"}
        if state is None:
            return 200, {"ok": False, "error": "live_state 不可用"}
        ok = state.set_reasoning_effort(cid, effort)
        return 200, {
            "ok": bool(ok),
            "reasoning_effort": state.get_reasoning_effort(cid),
        }

    def autonomous(self, cid: str, enabled: Any) -> Tuple[int, Dict[str, Any]]:
        """开关会话自主模式：开启后回合结束会自动续跑（`SessionRunner.auto_continue`）。"""
        state = self.app.live_state
        cid = str(cid or "").strip()
        if not cid:
            return 200, {"ok": False, "error": "conversation_id required"}
        if state is None:
            return 200, {"ok": False, "error": "live_state 不可用"}
        state.set_autonomy(cid, bool(enabled))
        return 200, {"ok": True, "autonomy": state.get_autonomy(cid)}

    def ui_state(self, cid: str) -> Tuple[int, Dict[str, Any]]:
        """UI 状态快照（模式 / todo / 自主 / 模型；落点 = live_state 按 cid）。"""
        cid = str(cid or "").strip()
        live = self.app.live_state
        model_for = getattr(self.app, "model_for", None)
        current = (
            model_for(cid) if callable(model_for)
            else str(live.get_model(cid) or "")
        )
        return 200, {
            "conversation_id": cid,
            "mode": live.get_mode(cid),
            "todo": live.get_todo(cid),
            "autonomy": live.get_autonomy(cid),
            # 目标（Goal）：前端"目标"按钮据此回填状态；无目标时为 None。
            "goal": live.get_goal(cid),
            # 模型选择与可选清单：前端据此回填下拉（刷新后不丢）。
            # 只给 id —— 凭据（key / url）始终留在服务端。
            "model": current,
            "available_models": self.available_models(),
            # 会话级设置同源回填：模式 / 推理档位都属于会话，不属于某个标签页。
            "reasoning_effort": live.get_reasoning_effort(cid),
            "running": self.app.mesh.is_running(cid),
            # 也在跑的全部会话（供中途接入的页面拉 `/api/chat/ui-state` 回填忙闲）。
            "running_cids": self.app.mesh.running_cids(),
        }

    def ui_state_put(self, cid: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        cid = str(cid or "").strip()
        mode = str(payload.get("mode") or "").strip().lower()
        if mode:
            if mode not in MODE_VALUES:
                return 400, {"error": "invalid mode"}
            self.app.live_state.set_mode(cid, mode)
        if "model" in payload:
            want = str(payload.get("model") or "").strip()
            allowed = self.available_models()
            if want and allowed and want not in allowed:
                return 400, {"error": f"unknown model: {want}"}
            before = str(self.app.live_state.get_model(cid) or "")
            self.app.live_state.set_model(cid, want)
            if want and before != want:
                self._announce_model(cid, want)
        return self.ui_state(cid)
