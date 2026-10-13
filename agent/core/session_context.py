# -*- coding: utf-8 -*-
"""会话上下文（SessionContext / SessionContexts）——会话级状态的载体。

三级上下文的中间一级：进程级（AppContext）/ 会话级（本模块）/ 回合级。
一切可变状态按生命周期分三级存放，禁止混放、禁止跨级占用。

它是**数据结构**（"会话态长什么样"的约定），不是机制实现。把它放进 mechanisms
会造成隔断——`core` 引用不了它，于是各处只好用回调/解析器绕过去
（如 `app._gate_resolver` 这类解析器）。上下文类是**模块间传输数据
的约定**，所有用到的地方都该直接 import 它；`scripts/check_imports.py` 约束的是
**行为依赖方向**（谁调用谁），不是"谁能使用同一份数据形状"。

本模块承担两件事：

1. `SessionContext` —— 单会话局部状态的载体：
   - `gate`：写盘门控（确认 ID 与预览 kv / 待重读 / 待 review / 红灯 / 意图证据），
     **每会话独占一个实例**：一个会话的预览快照不得被另一个会话看到或提交；
   - `live`：实时状态（模式 / todo / 自主 / 休眠）；实例由装配共享，内部按 cid 分键；
   - `inbox`：收件队列；实例由装配共享，内部按 cid 分键；
   - `pending_confirm`：待用户确认（两段式首段留下的挂起调用）。

2. `SessionContexts` —— 会话注册表（cid → SessionContext）：懒创建、线程安全、同 cid 复用；
   空 cid 归默认会话桶（无会话作用域直调场景）。

解析路径（唯一）：工具与管道钩子执行期内经 `core.session_scope.current_session_id()`
取当前会话 id，再经注册表解析——会话态不进全局单例、不跨会话直读。
（回合期的组件另有**显式**引用：回合级原对象上的 `.session` / `.app`——
显式引用优先，contextvar 只服务"没有显式引用可用"的场合。）

不在本模块驻留之物：会话记录 / 上下文管线 / 压缩器——属"可由事实源
重建的会话运行态"，由回合引擎按会话构建（App.session）。

回收：注册表提供**显式释放**——`release(cid)` 丢单会话、`close_all()` 丢全部、
`active_count()` 诊断驻留量。释放只丢进程内运行态，不动已落盘的会话记录（事实源不变，
重新解析会话即从记录重建运行态）。不引入自动淘汰（TTL / LRU）：静默丢弃不活跃会话的
门控状态会让用户回来时"待 review / 红灯"凭空消失，属正确性风险；何时回收由壳层按
会话生命周期显式调用。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from agent.core.session_scope import current_session_id

DEFAULT_BUCKET = ""  # 空 cid 归默认会话桶（无会话作用域直调场景）

GateFactory = Callable[[str], Any]


@dataclass
class SessionContext:
    """单会话局部状态（gate 独占；live / inbox 为装配共享的按 cid 分键容器）。"""

    conversation_id: str = DEFAULT_BUCKET
    gate: Any = None
    live: Any = None
    inbox: Any = None
    extras: Dict[str, Any] = field(default_factory=dict)
    # 待用户确认（两段式 / 挂起）：`user_confirm` 类工具首段返回信封后，
    # 回合把它置为 `{call_id, title, confirms, multi}`，然后**放行结束**（不阻塞、不再调模型）；
    # 用户在宿主界面作答后，宿主查这里、把选择写成那次调用的 `tool_result`，再起新回合。
    #
    # 放在会话级：它要**跨回合**存活（暂停发生在上一回合，作答在下一回合），
    # 而回合级上下文随回合消亡。放这里也符合分级纪律——
    # 会话态归 SessionContext，不塞全局单例、也不跨会话直读。
    pending_confirm: Optional[Dict[str, Any]] = None


class SessionContexts:
    """会话注册表：按 cid 懒创建、线程安全、同 cid 复用。

    - `gate_factory(cid)`：门控工厂——每会话调用一次，产出该会话独占的写盘门控；
    - `live` / `inbox`：装配级共享容器（内部按 cid 分键，同为按 cid 字典）；
    - `resolve_sync(cid)`：显式取某会话上下文（脚本 / 测试 / 无 contextvar 场景）；
    - `resolve()`：取当前会话上下文（经 core.session_scope 的 contextvar）；
    - `get(cid)` / `buckets()`：只读查询，**不创建**会话上下文。
    """

    def __init__(
        self,
        gate_factory: Optional[GateFactory] = None,
        *,
        live: Any = None,
        inbox: Any = None,
    ) -> None:
        if gate_factory is None:
            raise ValueError("SessionContexts 需要 gate_factory（每会话产出独占门控）")
        self._gate_factory: GateFactory = gate_factory
        self._live = live
        self._inbox = inbox
        self._buckets: Dict[str, SessionContext] = {}
        self._lock = threading.Lock()

    # ── 元信息 ──────────────────────────────────────────────

    @property
    def live(self) -> Any:
        """装配级共享的实时状态容器（内部按 cid 分键）。"""
        return self._live

    @property
    def inbox(self) -> Any:
        """装配级共享的收件队列容器（内部按 cid 分键）。"""
        return self._inbox

    # ── 解析 ────────────────────────────────────────────────

    def resolve_sync(self, conversation_id: str) -> SessionContext:
        """按 cid 取会话上下文；无则创建（同 cid 复用，线程安全）。

        `gate_factory` 在持锁期间**之外**调用——避免工厂重入注册表导致死锁。
        """
        bucket = _bucket(conversation_id)
        with self._lock:
            ctx = self._buckets.get(bucket)
            if ctx is not None:
                return ctx
        gate = self._gate_factory(bucket)
        with self._lock:
            existing = self._buckets.get(bucket)
            if existing is not None:
                return existing  # 竞态：他线程已建，复用先到者
            ctx = SessionContext(
                conversation_id=bucket,
                gate=gate,
                live=self._live,
                inbox=self._inbox,
            )
            self._buckets[bucket] = ctx
            return ctx

    def resolve(self) -> SessionContext:
        """取当前会话上下文（解析路径唯一：core.session_scope）。"""
        return self.resolve_sync(current_session_id())

    def get(self, conversation_id: str) -> Optional[SessionContext]:
        """只读查询某会话上下文；未创建返回 None（不产生副作用）。"""
        with self._lock:
            return self._buckets.get(_bucket(conversation_id))

    def buckets(self) -> Dict[str, SessionContext]:
        """已创建的会话上下文快照（cid → SessionContext）。"""
        with self._lock:
            return dict(self._buckets)

    def release(self, conversation_id: str) -> bool:
        """显式释放某会话的上下文（丢弃门控状态）；返回是否命中。

        语义边界：只丢**进程内会话运行态**（门控 kv / 预览快照 / 红灯 / 意图证据 /
        待重读 / 待 review、以及 SessionContext 对共享容器的引用），**不动**已落盘的
        会话记录（事实源仍在，重新解析会话即从记录重建运行态）。
        """
        with self._lock:
            return self._buckets.pop(_bucket(conversation_id), None) is not None

    def close_all(self) -> int:
        """释放全部会话上下文（壳层停机 / 测试收尾）；返回释放数量。"""
        with self._lock:
            count = len(self._buckets)
            self._buckets.clear()
            return count

    def active_count(self) -> int:
        """当前驻留的会话上下文数量（诊断用）。"""
        with self._lock:
            return len(self._buckets)


def _bucket(conversation_id: str) -> str:
    """归一化会话键：空 cid 归默认桶，其余保留原值（cid 即为字典键）。"""
    return str(conversation_id or "").strip() or DEFAULT_BUCKET
