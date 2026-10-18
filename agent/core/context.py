# -*- coding: utf-8 -*-
"""上下文数据结构：进程级 `AppContext` + 工具轮次 `ToolTurnContext`。

装配点（app.py）在启动时注册各层服务，使用方经 get 解析；
所有注册返回 disposer——插件热装卸的地基。

这些是数据结构（"模块间传输的数据长什么样"的约定），不是机制实现：
使用方直接 import；`scripts/check_imports.py` 约束的是行为依赖方向
（谁调用谁），不是"谁能使用同一份数据形状"。

设计纪律：
- 容器不知道装的是"什么机制"（core 对机制零感知）；
- 注册名唯一：重复注册即报错（先注销再替换，防装配错误）；
- dispose_all 按注册逆序清理（后注册先清理）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

Disposer = Callable[[], None]

# 进程级服务登记名（装配点 register / 使用方 get 的唯一词汇表）。
# 集中定义防拼写漂移：装配点与解析方引用同一常量。
SERVICE_REGISTRY = "registry"                    # 工具注册表
SERVICE_PIPELINE = "pipeline"                    # 工具执行管道（唯一入口）
SERVICE_PROVIDER = "provider"                    # 模型提供者（ProviderRouter）
SERVICE_MODEL_CATALOG = "model_catalog"          # 模型描述目录（唯一权威来源）
SERVICE_STORE = "store"                          # 会话存储（事实源）
SERVICE_EVENT_BUS = "event_bus"                  # 事件总线（旁路）
SERVICE_PLUGIN_HOST = "plugin_host"              # 插件宿主
SERVICE_CONTEXT_SOURCES = "context_sources"      # 上下文注入源
SERVICE_SESSION_CONTEXTS = "session_contexts"    # 会话注册表（cid → SessionContext）
SERVICE_LIVE_STATE = "live_state"                # 实时状态容器（按 cid 分键）
SERVICE_MESH = "mesh"                            # 协作网格 / 收件队列（按 cid 分键）
SERVICE_SESSION_FACTORY = "session_factory"      # 上下文管线工厂（cid → ContextPipeline）
SERVICE_COMPACTOR_FACTORY = "compactor_factory"  # 压缩器工厂（cid → ContextCompactor）
SERVICE_ERROR_LOG = "error_log"                  # 错误日志（mechanisms.ErrorLog）


class AppContext:
    """应用级服务容器：注册 → 解析 → 注销。"""

    def __init__(self) -> None:
        self._services: Dict[str, Any] = {}
        self._disposers: List[Tuple[str, Disposer]] = []

    def register(self, name: str, service: Any) -> Disposer:
        """注册服务；名称为空或重复时抛 ValueError；返回幂等 disposer。"""
        key = str(name or "").strip()
        if not key:
            raise ValueError("服务名不能为空")
        if key in self._services:
            raise ValueError(f"服务已注册：{key}（请先注销旧服务再替换）")
        self._services[key] = service

        def _dispose() -> None:
            if key not in self._services:
                return  # 幂等：已注销
            del self._services[key]
            for i, (k, _d) in enumerate(self._disposers):
                if k == key:
                    del self._disposers[i]
                    break

        self._disposers.append((key, _dispose))
        return _dispose

    def get(self, name: str) -> Any:
        """解析服务；未注册时抛 KeyError（附已注册名单）。"""
        key = str(name or "").strip()
        if key not in self._services:
            raise KeyError(f"服务未注册：{key}（已注册：{sorted(self._services)}）")
        return self._services[key]

    def has(self, name: str) -> bool:
        """是否已注册该服务（可选服务的存在性查询，不抛错）。"""
        return str(name or "").strip() in self._services

    def names(self) -> List[str]:
        """已注册的服务名（排序后；诊断用）。"""
        return sorted(self._services)

    def dispose_all(self) -> None:
        """按注册逆序注销全部服务（后注册先清理）。"""
        while self._disposers:
            _key, disposer = self._disposers.pop()
            disposer()


@dataclass(slots=True)
class ToolTurnContext:
    """工具轮次上下文：一次工具调用的窄视图（三级状态里的回合级）。

    它把该轮次需要的东西显式摆在一起，工具不必再靠 contextvar 猜、也不必在
    构造期注入"能摸到会话态的函数"：

    - `app`：进程级 `AppContext`（服务注册表）——需要全局能力时经 `app.get(NAME)` 解析，
      或先 `has(NAME)` 判存在（可选服务不得假设存在）；
    - `session`：会话级 `SessionContext`——写盘门控 `session.gate`、实时状态
      `session.live`、收件队列 `session.inbox`、待确认 `session.pending_confirm`；
    - `turn`：回合级原对象——只在确实要看回合内部状态时才用；
    - `call`：本轮次的工具调用（`call_id` / 工具名 / 入参）；
    - `progress`：进度上报器（`report(payload)`；`None` 表示本场合不上报）。

    窄视图的取舍：
    ① 工具按构造拿到的是"这一次调用"，不是"整个回合"——`step_index` / `await_user` /
    停止检查这些回合内部状态不该出现在工具的视野里（现在它们确实看不到，因为只给了
    派生量）；② 它是一处审计面：将来工具在别的进程 / 沙箱里跑，要跨过去的正是
    这个对象携带的数据，而不是整棵上下文。
    """

    app: Any = None
    session: Any = None
    turn: Any = None
    call: Any = None
    progress: Optional[Callable[[dict], None]] = None

    # ── 便捷读取（避免每处都写 getattr 链；缺省一律给安全值）──

    @property
    def conversation_id(self) -> str:
        """本会话 id。"""
        return str(getattr(self.session, "conversation_id", "") or "")

    @property
    def call_id(self) -> str:
        """本次工具调用的 id（`tool_end` 配对的唯一键）。"""
        return str(getattr(self.call, "call_id", "") or "")

    @property
    def tool_name(self) -> str:
        """本次调用的工具名。"""
        return str(getattr(self.call, "name", "") or "")

    @property
    def arguments(self) -> Dict[str, Any]:
        """本次调用的入参（无则空字典）。"""
        args = getattr(self.call, "arguments", None)
        return dict(args) if isinstance(args, dict) else {}

    def service(self, name: str) -> Any:
        """解析全局服务；未注册返回 None（与 `AppContext.get` 的抛错口径区分开）。"""
        app = self.app
        if app is None or not hasattr(app, "has"):
            return None
        return app.get(name) if app.has(name) else None

    def report(self, payload: dict) -> None:
        """上报工具进度（未接进度通道时静默丢弃——工具不必自己判空）。"""
        if self.progress is None:
            return
        try:
            self.progress(payload)
        except Exception:
            # 旁路，刻意吞掉：进度上报是观察面，一个坏掉的观察者
            # （或已断开的 SSE 连接）不该让整个回合失败。
            # 判据：这里失败不影响回合结果，只影响"过程显示得全不全"。
            pass
