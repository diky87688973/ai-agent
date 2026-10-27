# -*- coding: utf-8 -*-
"""经典 UI 会话级状态。"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional


class ClassicState:
    """按会话的内存态（进程重启即丢，符合"UI 偏好"的语义）。

    - `usage`：用量累计（经典界面的 `/api/usage-accumulator`）
    - `command_input`：命令确认时的回灌通道（只存不注入，内核暂不消费）
    - `attachments`：本回合附件（供 `/api/chat/attachment` 内联返回）

    知识库勾选由 knowledge 插件的运行时持有（带落盘与注入），
    界面经插件自己的端点 `/api/plugin/knowledge/checked` 读写。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.usage: Dict[str, Dict[str, int]] = {}
        self.command_input: Dict[str, Dict[str, Any]] = {}
        self.attachments: Dict[str, List[Dict[str, Any]]] = {}

    # 用量 ──
    def add_usage(self, cid: str, data: Dict[str, Any]) -> None:
        """按 SSE 那套字段名累加，输出时再翻成 accumulator 那套。"""
        if not cid:
            return
        with self._lock:
            acc = self.usage.setdefault(cid, {
                "total_prompt_tokens": 0, "total_completion_tokens": 0,
                "total_cache_hit_tokens": 0, "total_cache_miss_tokens": 0,
                "total_tokens": 0,
            })
            prompt = int(data.get("prompt_tokens") or 0)
            completion = int(data.get("completion_tokens") or 0)
            hit = int(data.get("prompt_cache_hit_tokens") or 0)
            miss = int(data.get("prompt_cache_miss_tokens") or max(0, prompt - hit))
            acc["total_prompt_tokens"] += prompt
            acc["total_completion_tokens"] += completion
            acc["total_cache_hit_tokens"] += hit
            acc["total_cache_miss_tokens"] += miss
            acc["total_tokens"] += int(data.get("total_tokens") or (prompt + completion))

    def set_usage(self, cid: str, data: Dict[str, Any]) -> None:
        """覆盖该会话的累计用量（`accumulator` 那套字段名）。

        与 `add_usage` 的区别就是这个方法的全部意义：`/api/usage-accumulator` 的
        PUT 上报的是会话累计值，不是本回合增量 —— 用累加就等于每上报一次翻一倍。
        """
        if not cid:
            return
        prompt = int(data.get("prompt_tokens") or 0)
        completion = int(data.get("completion_tokens") or 0)
        hit = int(data.get("prompt_cache_hit_tokens") or 0)
        miss = int(data.get("prompt_cache_miss_tokens") or max(0, prompt - hit))
        with self._lock:
            self.usage[cid] = {
                "total_prompt_tokens": prompt,
                "total_completion_tokens": completion,
                "total_cache_hit_tokens": hit,
                "total_cache_miss_tokens": miss,
                "total_tokens": int(data.get("total_tokens") or (prompt + completion)),
            }

    def get_usage(self, cid: str) -> Dict[str, int]:
        """返回累计量（`accumulator` 那套字段名）。

        `session_token_used` 是派生值（输入 + 输出），不是独立计数器：
        经典界面的圆环用它显示「已用」，而 PUT 上来的字段里就有它 ——
        不从 `total_*` 推导就会出现"圆环显示 0、同一提示里却写着
        `输入: 18,631 输出: 8`"这种自相矛盾。由 `total_*` 推导，只有一个权威。
        """
        with self._lock:
            acc = dict(self.usage.get(cid) or {
                "total_prompt_tokens": 0, "total_completion_tokens": 0,
                "total_cache_hit_tokens": 0, "total_cache_miss_tokens": 0,
                "total_tokens": 0,
            })
        acc["session_token_used"] = (
            int(acc.get("total_prompt_tokens") or 0)
            + int(acc.get("total_completion_tokens") or 0)
        )
        return acc

    def has_usage(self, cid: str) -> bool:
        with self._lock:
            return cid in self.usage

    def reset_usage(self, cid: str) -> None:
        with self._lock:
            self.usage.pop(cid, None)

    # 命令输入回灌（预留）──
    def set_command_input(self, cid: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            self.command_input[cid] = {"payload": dict(payload or {}), "at": time.time()}

    def take_command_input(self, cid: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self.command_input.pop(cid, None)
        return item["payload"] if item else None

    # 附件（内联）──
    def put_attachments(self, cid: str, items: List[Dict[str, Any]]) -> None:
        with self._lock:
            self.attachments[cid] = list(items or [])

    def get_attachment(self, cid: str, ident: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for item in self.attachments.get(cid) or []:
                if str(item.get("id")) == str(ident):
                    return dict(item)
        return None

    def clear_attachments(self, cid: str) -> None:
        with self._lock:
            self.attachments.pop(cid, None)


# ── 端点实现 ────────────────────────────────────────────────
