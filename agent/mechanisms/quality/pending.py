# -*- coding: utf-8 -*-
"""未提交预览快照仓库（confirm_id → tool / arguments / confirmed / path）。

同路径只留最新；满 `MAX_PENDING_PREVIEWS` 时按登记顺序挤掉最旧的。
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Iterable, Optional, Tuple
from uuid import uuid4

from agent.mechanisms.quality.path_keys import resolve_write_path

# 未提交预览快照上限：同路径只留最新；满额时按登记顺序挤掉最旧的。
MAX_PENDING_PREVIEWS = 100


class PendingStore:
    """预览快照字典封装：登记 / 窥视 / 取出 / 丢弃 / 确认。"""

    def __init__(self) -> None:
        # confirm_id → {"tool": str, "arguments": dict, "confirmed": bool, "path": str, ...}
        self._pending: Dict[str, Dict[str, Any]] = {}
        # 线程安全：Web 壳的多个会话可能并发预览/提交，登记、挤出、消费必须是原子的。
        # 没有锁时 `while len >= MAX` 与插入之间可被另一线程插入，导致上限失效；
        # `peek` + 改写 `confirmed` 也会丢更新。
        self._lock = threading.RLock()

    @property
    def records(self) -> Dict[str, Dict[str, Any]]:
        """底层字典的快照（测试与兼容层读长度 / 键，不能借此改动真表）。"""
        with self._lock:
            return dict(self._pending)

    def register_preview(
        self,
        tool: str,
        arguments: Dict[str, Any],
        *,
        path_keys: Iterable[str] = (),
    ) -> str:
        """登记一次预览快照（写参数入库），返回 confirm_id（提交唯一凭据）。

        `path_keys` 为工具声明的写路径参数键序；空则 path 为空（不做默认真猜）。
        同一写目标路径只保留最新一条；条数达到上限时按登记顺序挤掉最旧的。
        """
        tool_name = str(tool or "")
        args = dict(arguments or {})
        keys: Tuple[str, ...] = tuple(str(k).strip() for k in path_keys if str(k).strip())
        path = resolve_write_path(args, keys)
        with self._lock:
            if path:
                stale = [
                    key
                    for key, rec in self._pending.items()
                    if str(rec.get("path") or "") == path
                ]
                for key in stale:
                    del self._pending[key]
            while len(self._pending) >= MAX_PENDING_PREVIEWS:
                oldest = next(iter(self._pending))
                del self._pending[oldest]
            cid = uuid4().hex
            self._pending[cid] = {
                "tool": tool_name,
                "arguments": args,
                "confirmed": False,
                "path": path,
                "path_keys": keys,
            }
        return cid

    def peek(self, confirm_id: str) -> Optional[Dict[str, Any]]:
        """查看确认 ID 关联的预览快照（不消费）；无效返回 None。"""
        with self._lock:
            return self._pending.get(str(confirm_id or "").strip())

    def take_record(self, confirm_id: str) -> Optional[Dict[str, Any]]:
        """取出并消费预览快照（完整记录）；无效/已使用返回 None。"""
        key = str(confirm_id or "").strip()
        with self._lock:
            return self._pending.pop(key, None)

    def take(self, confirm_id: str) -> Optional[Dict[str, Any]]:
        """取出并消费预览快照的写参数（一次性）；无效/已使用返回 None。"""
        rec = self.take_record(confirm_id)
        if rec is None:
            return None
        return dict(rec.get("arguments") or {})

    def discard(self, confirm_id: str) -> bool:
        """丢弃一个未提交的预览快照；返回是否命中。"""
        key = str(confirm_id or "").strip()
        with self._lock:
            if key not in self._pending:
                return False
            del self._pending[key]
            return True

    def confirm(self, confirm_id: str, *, write_generation: int = 0) -> bool:
        """确认（review 通过）某次预览可提交；返回是否找到该快照。"""
        with self._lock:
            rec = self.peek(confirm_id)
            if rec is None:
                return False
            rec["confirmed"] = True
            rec["confirmed_generation"] = int(write_generation)
            return True
