# -*- coding: utf-8 -*-
"""会话协作网格：会话注册表 + inbox 队列 + 忙闲原子投递。

- 线程安全：实例级 RLock（submit → activator → try_begin 可重入）；
- 持久化：agents.json（注册表）+ inbox/<cid>.jsonl（队列）；目录由装配注入（缺省纯内存）；
- 加载容错：坏文件 / 坏行忽略；
- 活跃集：由运行器经 try_begin_run / end_run 登记与释放。
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.mechanisms.run_registry import RunRegistry, build_run_registry

_CID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


class MeshState:
    """会话协作网格：注册表 / inbox / 活跃运行集 / 原子投递（装配时单例注入）。"""

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        *,
        run_registry: Optional[RunRegistry] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._inboxes: Dict[str, List[Dict[str, Any]]] = {}
        # 运行态不在本对象内保存：进程内存做权威判断，多实例部署下必然给错答案
        # （实例 A 跑的回合，实例 B 看不见）。收敛到 `RunRegistry` 接口后面 ——
        # 换共享存储只需换实现，调用方不变。
        self._runs: RunRegistry = run_registry if run_registry is not None else build_run_registry(
            (Path(storage_dir) / "runs") if storage_dir else None
        )
        self._activator: Optional[Callable[[str, Dict[str, Any]], str]] = None
        self._session_exists: Optional[Callable[[str], bool]] = None
        self._storage_dir = Path(storage_dir) if storage_dir else None
        if self._storage_dir is not None:
            self._load()

    # ── 装配─────────────────────────────

    def set_activator(self, activator: Optional[Callable[[str, Dict[str, Any]], str]]) -> None:
        """装配激活器（会话运行器入口）：返回 run_id；空串表示未能启动。"""
        with self._lock:
            self._activator = activator

    def set_session_exists(self, fn: Optional[Callable[[str], bool]]) -> None:
        """装配会话存在性回调（缺省仅注册表命中视为存在）。"""
        with self._lock:
            self._session_exists = fn

    def session_exists(self, cid: str) -> bool:
        """目标存在性：注册表命中 → 真；否则经注入回调判定。"""
        key = str(cid or "").strip()
        if not key:
            return False
        with self._lock:
            if key in self._agents:
                return True
            fn = self._session_exists
        if fn is None:
            return False
        return bool(fn(key))

    # ── 注册表───────────────────────────────────

    def upsert_agent(self, cid: str, **fields: Any) -> Dict[str, Any]:
        """写入 / 更新 agent meta（None 值不覆盖；返回副本并落盘）。"""
        key = str(cid or "").strip()
        if not key:
            return {}
        now = int(time.time())
        with self._lock:
            item = dict(self._agents.get(key) or {})
            item.setdefault("cid", key)
            item.setdefault("created_at", now)
            item["updated_at"] = now
            for k, v in fields.items():
                if v is not None:
                    item[k] = v
            self._agents[key] = item
            self._save_agents_locked()
            return dict(item)

    def get_agent(self, cid: str) -> Dict[str, Any]:
        """读取 agent meta 副本；无则空 dict。"""
        with self._lock:
            return dict(self._agents.get(str(cid or "").strip()) or {})

    def list_agents(self) -> Dict[str, Dict[str, Any]]:
        """全部 agent meta 副本（浅拷贝字典）。"""
        with self._lock:
            return {k: dict(v) for k, v in self._agents.items()}

    # ── inbox────────────────────────────────────

    def _enqueue_locked(self, key: str, message: Dict[str, Any]) -> int:
        q = self._inboxes.setdefault(key, [])
        q.append(dict(message))
        n = len(q)
        self._persist_inbox_locked(key)
        return n

    def enqueue(self, cid: str, message: Dict[str, Any]) -> int:
        """入队并返回队长。"""
        key = str(cid or "").strip()
        if not key:
            return 0
        with self._lock:
            return self._enqueue_locked(key, message)

    def pop(self, cid: str) -> Optional[Dict[str, Any]]:
        """出队首；空则 None。"""
        key = str(cid or "").strip()
        with self._lock:
            q = self._inboxes.get(key) or []
            if not q:
                self._inboxes.pop(key, None)
                return None
            msg = q.pop(0)
            if not q:
                self._inboxes.pop(key, None)
            self._persist_inbox_locked(key)
            return msg

    def inbox_size(self, cid: str) -> int:
        """队列长度。"""
        with self._lock:
            return len(self._inboxes.get(str(cid or "").strip()) or [])

    # ── 活跃集与投递─────────────────────

    def is_running(self, cid: str) -> bool:
        """该会话是否正在跑（转调 `RunRegistry`，自身不存运行态）。"""
        return self._runs.running(str(cid or "").strip())

    def running_cids(self) -> List[str]:
        """当前正在跑的会话 id（快照）。

        `is_running` 只回答单个会话；本方法一次给出全部在跑的会话 id ——
        前端不知道有哪些会话在跑（尤其是中途接入的页面：它没收到 `run_started`，
        只能靠服务端告诉它）。`/api/chat/ui-state` 用这个列出在跑的会话，
        页面据此回填"忙"状态，停止键才不会永不出现。

        ⚠️ 返回值来自 `RunRegistry`（读落盘登记：心跳 + TTL），不取自本对象的注册表：
        读落盘登记（心跳 + TTL）；换成共享存储实现，调用方不用改。
        """
        return self._runs.running_cids()

    def active_run_id(self, cid: str) -> str:
        """该会话当前占位的 run_id；未在跑返回空串。"""
        return self._runs.active_run_id(str(cid or "").strip())

    def touch_run(self, cid: str) -> None:
        """续一次运行态心跳（幂等）。

        `RunRegistry` 用"心跳 + 存活期"判定在跑，
        而一次长工具调用（`run_command` 跑 `ping -n 120` ≈ 120 秒）
        期间运行器不会与登记表交互 —— 只靠占位/释放两次心跳的话，
        长任务中途就会被误判成"已结束"，用户那边的停止键会消失。
        运行器因此起一个旁路线程周期性调用本方法。
        """
        self._runs.touch(str(cid or "").strip())

    def try_begin_run(self, cid: str) -> str:
        """原子占位（供激活器 / 运行器）：忙则返回空串。"""
        key = str(cid or "").strip()
        if not key:
            return ""
        with self._lock:
            rid = uuid.uuid4().hex[:12]
            return rid if self._runs.claim(key, rid) else ""

    def end_run(self, cid: str) -> Optional[Dict[str, Any]]:
        """回合结束：原子释放 + 队列非空则取队首并续占位（返回该消息，同线程抽干）。

        ⚠️ 顺序是硬要求：先为下一条占位，再释放当前占位 ——
        中间不能出现"空闲窗口"。若按 `release → pop → claim` 执行，第二个
        `session_send` 会正好落进那个窗口、看到"空闲"就又激活一趟：
        同一个回合被执行两遍（`provider.stream` 被调两次、队列也算抽干，
        但 `seen` 只有 1）。
        """
        key = str(cid or "").strip()
        with self._lock:
            q = self._inboxes.get(key) or []
            if not q:
                self._runs.release(key)
                return None
            # 先换 id、全程不释放：`renew` 在已占位时就地换 run_id，
            # 于是外界始终看到"在跑"，不存在能被别人抢走的空闲窗口。
            new_rid = uuid.uuid4().hex[:12]
            if not self._runs.renew(key, new_rid):
                # 理论上到不了（此刻必然是自己占着位）；真到不了就当异常兜底，
                # 释放后由队列/投递路径重新激活，行为退化成"没续占"。
                self._runs.release(key)
            msg = q.pop(0)
            if not q:
                self._inboxes.pop(key, None)
            self._persist_inbox_locked(key)
            return msg

    def abort_run(self, cid: str) -> None:
        """异常兜底：释放占位（不续跑）。"""
        with self._lock:
            self._runs.release(str(cid or "").strip())

    def submit(self, cid: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """原子投递：忙 / 无激活器 → 入队；闲 → 激活启动；失败 → 回退入队。"""
        key = str(cid or "").strip()
        with self._lock:
            if self._runs.running(key) or self._activator is None:
                n = self._enqueue_locked(key, message)
                return {"queued": True, "queued_count": n, "run_id": ""}
            try:
                rid = str(self._activator(key, dict(message)) or "")
            except Exception as exc:
                print(
                    f"[mesh] activator 失败 cid={key}: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr, flush=True,
                )
                n = self._enqueue_locked(key, message)
                return {"queued": True, "queued_count": n, "run_id": ""}
            if rid:
                return {"queued": False, "queued_count": 0, "run_id": rid}
            n = self._enqueue_locked(key, message)
            return {"queued": True, "queued_count": n, "run_id": ""}

    # ── 持久化───────────────────────────

    def _agents_file(self) -> Optional[Path]:
        return (self._storage_dir / "agents.json") if self._storage_dir else None

    def _inbox_file(self, cid: str) -> Optional[Path]:
        if self._storage_dir is None or not _CID_RE.match(cid):
            return None
        return self._storage_dir / "inbox" / f"{cid}.jsonl"

    def _save_agents_locked(self) -> None:
        fp = self._agents_file()
        if fp is None:
            return
        try:
            fp.parent.mkdir(parents=True, exist_ok=True)
            data = {"agents": {k: dict(v) for k, v in self._agents.items()}}
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _persist_inbox_locked(self, cid: str) -> None:
        fp = self._inbox_file(cid)
        if fp is None:
            return
        try:
            rows = self._inboxes.get(cid) or []
            if not rows:
                if fp.is_file():
                    fp.unlink()
                return
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
        except Exception:
            pass

    def _load(self) -> None:
        """加载持久化状态；坏文件 / 坏行忽略（分节隔离：单节故障不影响其余）。"""
        try:
            fp = self._agents_file()
            if fp is not None and fp.is_file():
                data = json.loads(fp.read_text(encoding="utf-8"))
                agents = data.get("agents") if isinstance(data, dict) else None
                if isinstance(agents, dict):
                    self._agents.update({str(k): dict(v) for k, v in agents.items() if isinstance(v, dict)})
        except Exception:
            pass
        try:
            inbox_dir = (self._storage_dir / "inbox") if self._storage_dir else None
            if inbox_dir is not None and inbox_dir.is_dir():
                for p in inbox_dir.glob("*.jsonl"):
                    rows: List[Dict[str, Any]] = []
                    try:
                        for line in p.read_text(encoding="utf-8").splitlines():
                            if not line.strip():
                                continue
                            try:
                                obj = json.loads(line)
                            except Exception:
                                continue  # 坏行跳过
                            if isinstance(obj, dict):
                                rows.append(obj)
                    except Exception as exc:
                        print(
                            f"[mesh] 读 inbox 失败 path={p}: "
                            f"{type(exc).__name__}: {exc}",
                            file=sys.stderr, flush=True,
                        )
                        continue
                    if rows:
                        self._inboxes[p.stem] = rows
        except Exception:
            pass
