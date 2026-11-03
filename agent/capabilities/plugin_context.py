# -*- coding: utf-8 -*-
"""插件注册面——插件 `register(ctx)` 拿到的那个对象。

`PluginContext` 把插件的能力声明落到内核各处扩展点（工具注册表、事件总线、
上下文注入源、请求尾部、系统提示词章节、模型目录、工具管道、界面与端点贡献）。
每个 `add_*` 返回幂等 disposer，同时记入本插件的贡献账本；加载器在 `register`
返回后把账本与返回值合并，卸载或回滚时逆序撤销（见 `plugin_ledger`）。

上下文段 key 一律以插件名为首，贡献注册一律带插件名命名空间 —— 插件不能注册到
别人的命名空间，内核也不必为单个插件加分支。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.capabilities.plugin_ledger import Disposer
from agent.capabilities.plugin_ui_context import PluginUiContextMixin
from agent.capabilities.registry import ToolRegistry
from agent.capabilities.slot_registry import canonical_slot_path
from agent.core.app_path import app_path
from agent.core.context import SERVICE_PLUGIN_EVENTS, SERVICE_SUBAGENTS
from agent.core.error_report import report_error
from agent.core.slot import SlotContribution


def _safe_dir_name(name: str) -> str:
    """插件名 → 合法目录名：只留 `[A-Za-z0-9_-]`，其余换成 `_`。

    插件名会拼进文件路径，不净化就能用 `..` 或斜杠越出 `plugin/` 目录。
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(name or "")).strip("_")
    return cleaned or "plugin"


class PluginContext(PluginUiContextMixin):
    """插件注册面：name + 各扩展点的 `add_*`；经此产生的 disposer 由加载器记账。"""

    def __init__(
        self,
        name: str,
        registry: ToolRegistry,
        event_bus: Any = None,
        context_sources: Any = None,
        pipeline: Any = None,
        host: Any = None,
        contributions: Any = None,
        executors: Any = None,
        model_catalog: Any = None,
        settings: Any = None,
        ui: Any = None,
        backend: Any = None,
        prompt_tail: Any = None,
        prompt_sections: Any = None,
        context_hooks: Any = None,
        tree: Any = None,
    ) -> None:
        self.name = name
        self._registry = registry
        self._event_bus = event_bus
        self._context_sources = context_sources
        self._pipeline = pipeline
        self._host = host
        self._contributions = contributions
        self._executors = executors
        self._model_catalog = model_catalog
        self._settings = settings
        self._ui = ui
        self._backend = backend
        self._prompt_tail = prompt_tail
        self._prompt_sections = prompt_sections
        self._context_hooks = context_hooks
        self._tree = tree
        #: 本插件在清单里的位次（宿主装载时写入；测试直构时为 None）
        self._rank: Optional[int] = None
        self._disposers: List[Disposer] = []

    def set_rank(self, rank: Optional[int]) -> None:
        """写入本插件在清单里的位次（组装顺序按它排）。"""
        self._rank = rank

    def owned_disposers(self) -> List[Disposer]:
        """本插件经 ctx 登记的贡献 disposer（登记顺序；撤销时逆序）。"""
        return list(self._disposers)

    def own_disposer(self, disposer: Any) -> None:
        """登记一个由本插件持有的清理器，随插件卸载逆序释放。"""
        if callable(disposer):
            self._disposers.append(disposer)

    def _contribute(self, path: str, register: Callable[[], Any],
                    *, master: bool = False, replace: bool = False,
                    kind: str = "") -> Disposer:
        """把插件贡献落成插口；运行期贡献失败时默认只丢弃这一条。"""
        try:
            path = canonical_slot_path(str(path or "").strip())
        except Exception as exc:
            report_error("agent.capabilities.plugin_context.contribute", exc,
                         plugin=self.name, path=str(path or ""), master=master)
            if master:
                raise ValueError(f"必须显式提供合法 path：{path}") from exc
            return lambda: None
        if self._tree is None:
            try:
                disposer = register()
            except Exception as exc:
                report_error("agent.capabilities.plugin_context.contribute", exc,
                             plugin=self.name, path=path, master=master)
                if master:
                    raise ValueError(f"必须显式提供合法 path：{path}") from exc
                return lambda: None
            self._disposers.append(disposer)
            return disposer
        try:
            if kind and self._backend is not None:
                if not (replace and path in self._backend.entries):
                    self._backend.validate(path, kind=kind, owner=self.name)
            disposer = self._tree.add_dynamic(
                path, lambda _ctx: SlotContribution(path, register, master=master),
                replace=replace)
        except Exception as exc:
            report_error("agent.capabilities.plugin_context.contribute", exc,
                         plugin=self.name, path=path, master=master)
            if master:
                raise ValueError(f"必须显式提供合法 path：{path}") from exc
            return lambda: None
        self._disposers.append(disposer)
        return disposer

    def _backend_path(self, path: str, kind: str, handler: Any = None,
                      metadata: Any = None) -> Disposer:
        path = canonical_slot_path(path)
        if self._backend is None:
            return lambda: None
        disposer = self._backend.register(
            path, kind=kind, owner=self.name, handler=handler,
            metadata=dict(metadata or {}))
        self._disposers.append(disposer)
        return disposer



    def set_subagent_tools(self, tools: Any) -> Disposer:
        """声明本插件向子智能体暴露的工具清单；空清单表示全部不暴露。"""
        path = app_path("backend", "tools", "subagents", "visibility", self.name)

        def register() -> Disposer:
            backend = self._backend_path(path, "visibility", None, {"tools": tools})
            try:
                return self._registry.set_subagent_tools(self.name, tools)
            except Exception:
                backend()
                raise

        return self._contribute(path, register)

    def subscribe(self, event_type: str, handler: Callable[[Any], None], *,
                  path: str, master: bool = False) -> Disposer:
        """订阅事件总线上的指定类型事件；path 必须显式声明。"""
        if self._event_bus is None:
            raise RuntimeError("插件未接入事件总线（PluginHost 未传 event_bus）")
        event_path = canonical_slot_path(str(path or "").strip())

        def register() -> Disposer:
            backend = self._backend_path(event_path, "event-subscription", handler)
            try:
                return self._event_bus.subscribe(event_type, handler)
            except Exception:
                backend()
                raise

        return self._contribute(event_path, register, master=master,
                                kind="event-subscription")

    def add_context_source(self, fn: Callable[[str], List[str]],
                           meta: Any = None, *, path: str,
                           master: bool = False,
                           replace: bool = False) -> Disposer:
        """注册上下文注入源；path 是必选契约，不再自动拼序号。"""
        if self._context_sources is None:
            raise RuntimeError("插件未接入上下文注入源（PluginHost 未传 context_sources）")
        source_path = canonical_slot_path(str(path or "").strip())

        def register() -> Disposer:
            backend = None
            if not replace:
                backend = self._backend_path(
                    source_path, "context-source", fn, {"meta": meta})
            try:
                return self._context_sources.add(
                    fn, self._source_meta(meta), path=source_path,
                    owner=self.name, replace=replace)
            except Exception:
                if backend is not None:
                    backend()
                raise

        return self._contribute(source_path, register, master=master, replace=replace, kind="context-source")

    def add_mode_tail(self, fn: Callable[[str], Any], *,
                      path: str, master: bool = False,
                      subagent_visible: bool = True) -> Disposer:
        """注册请求尾部片段；path 是必选契约。"""
        if self._prompt_tail is None:
            raise RuntimeError("插件未接入请求尾部（PluginHost 未传 prompt_tail）")
        tail_path = canonical_slot_path(str(path or "").strip())

        def register() -> Disposer:
            backend = self._backend_path(tail_path, "mode-tail", fn)
            try:
                return self._prompt_tail.add(
                    fn, subagent_visible=subagent_visible)
            except Exception:
                backend()
                raise

        return self._contribute(tail_path, register, master=master, kind="mode-tail")

    def add_prompt_section(self, section: str, fn: Callable[[str], Any], *,
                           path: str, master: bool = False,
                           after_tools: bool = False) -> Disposer:
        """注册系统提示词章节来源；path 是必选契约。"""
        if self._prompt_sections is None:
            raise RuntimeError("插件未接入系统提示词章节（PluginHost 未传 prompt_sections）")
        section_path = canonical_slot_path(str(path or "").strip())

        def register() -> Disposer:
            backend = self._backend_path(
                section_path, "prompt-section", fn, {"section": section})
            try:
                return self._prompt_sections.add(
                    section, fn, rank=self._rank, after_tools=after_tools)
            except Exception:
                backend()
                raise

        return self._contribute(section_path, register, master=master, kind="prompt-section")

    def bump_context_sources(self) -> None:
        """声明"本插件注入的内容变了"（勾选集合、磁盘文件等）。

        装配侧会把收集结果缓存一趟（压缩与模型请求共用同一份），缓存看不到插件内部
        的数据变化 —— 改完数据不打招呼，那一段就要等下一趟装配才更新。
        """
        if self._context_sources is None:
            return
        bump = getattr(self._context_sources, "bump", None)
        if callable(bump):
            bump()

    def _source_meta(self, meta: Any) -> Any:
        """把插件给的描述补上插件名，成为内核认的 `SourceMeta`。

        段 key 一律是插件名 —— 前端按这个名字找插件注册的渲染钩子。
        段名、注入前缀与主体数量的取数口由插件给：
        `{"label": ..., "prefix": ..., "count": fn(cid)}`。
        组装顺序不由插件声明：它取插件在清单里的位次。
        """
        from agent.mechanisms.context import SourceMeta, slug

        label = ""
        prefix = ""
        count = None
        if isinstance(meta, str):
            label = meta
        elif isinstance(meta, dict):
            label = str(meta.get("label") or "")
            prefix = str(meta.get("prefix") or "")
            count = meta.get("count") if callable(meta.get("count")) else None
        elif meta is not None:
            label = str(getattr(meta, "label", "") or "")
            prefix = str(getattr(meta, "prefix", "") or "")
            count = getattr(meta, "count", None)
        name = slug(self.name)
        # 组装顺序按插件清单位次：清单靠前的插件，它的段也排在前面。
        return SourceMeta(key=name, label=label or name, plugin=self.name,
                          prefix=prefix, count=count,
                          plugin_rank=self._rank)

    def add_pre_gate(self, fn: Callable[[Any, Any], Any], *,
                     path: str, master: bool = False) -> Disposer:
        """注册工具管道前置门控；path 必须显式声明。"""
        if self._pipeline is None:
            raise RuntimeError("插件未接入工具管道（PluginHost 未传 pipeline）")
        gate_path = canonical_slot_path(str(path or "").strip())

        def register() -> Disposer:
            backend = self._backend_path(gate_path, "gate", fn)
            try:
                return self._pipeline.add_pre(fn)
            except Exception:
                backend()
                raise

        return self._contribute(gate_path, register, master=master, kind="gate")

    def add_post_observer(self, fn: Callable[[Any, Any, Any], None], *,
                          path: str, master: bool = False) -> Disposer:
        """注册工具管道后置观察者；path 必须显式声明。"""
        if self._pipeline is None:
            raise RuntimeError("插件未接入工具管道（PluginHost 未传 pipeline）")
        observer_path = canonical_slot_path(str(path or "").strip())

        def register() -> Disposer:
            backend = self._backend_path(observer_path, "observer", fn)
            try:
                return self._pipeline.add_post(fn)
            except Exception:
                backend()
                raise

        return self._contribute(observer_path, register, master=master,
                                kind="observer")


    def is_subagent(self, conversation_id: str) -> bool:
        """当前会话是否为子智能体；插件用它决定是否注入子智能体专属内容。"""
        app = self.app
        context = getattr(app, "context", None)
        if context is None or not context.has(SERVICE_SUBAGENTS):
            return False
        manager = context.get(SERVICE_SUBAGENTS)
        check = getattr(manager, "is_child", None)
        return bool(check(str(conversation_id or ""))) if callable(check) else False

    @property
    def app(self) -> Any:
        """内核 App；装配完成前为 None。

        插件要从内核取服务（如 `ctx.app.registry`）时用它 —— 只在处理器内部
        取而不是在 `register` 里取：插件在装配末尾加载，但处理器是后来才被调用的。
        """
        return getattr(self._host, "app", None) if self._host is not None else None

    @property
    def data_dir(self) -> Optional[Path]:
        """本插件的专属存储根（`<数据根>/plugin/<插件名>/`），首次访问时创建。

        插件只看到自己这一层，不需要知道外层目录在哪 —— 换个数据根、换个目录
        层级都不影响插件。各插件的目录互相隔离，同名文件也不会撞。
        未接入宿主时返回 None（插件应自己判空或只在有值时落盘）。
        """
        base = getattr(self._host, "plugin_data_root", None) if self._host is not None else None
        if base is None:
            return None
        target = Path(base) / _safe_dir_name(self.name)
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            # 旁路，刻意吞掉：建不出目录不该让插件加载失败；插件拿到路径后
            # 自己写文件时会再次遇到并处理（写失败是它的事），这里只保证不在这里炸。
            return target
        return target

    # ── 界面与端点贡献 ──

    def _contrib(self) -> Any:
        if self._contributions is None:
            raise RuntimeError("插件未接入贡献注册表（PluginHost 未传 contributions）")
        return self._contributions



    def publish_event(self, event: str, payload: Any = None) -> int:
        """推送插件 SSE 事件（非事实帧）；未接入 SSE 时返回 0。"""
        app = self.app
        context = getattr(app, "context", None) if app is not None else None
        if context is None or not context.has(SERVICE_PLUGIN_EVENTS):
            return 0
        publisher = context.get(SERVICE_PLUGIN_EVENTS)
        try:
            return int(publisher(self.name, str(event or ""), payload or {}))
        except Exception as exc:
            report_error("agent.capabilities.plugin_context.publish_event", exc)
            return 0

    def resume_suspended(
        self,
        conversation_id: str,
        call_id: str,
        data: Any,
        *,
        ok: bool = True,
        name: str = "",
        error: str = "",
    ) -> Dict[str, Any]:
        """把确认结果交回内核；由内核写回挂起调用并恢复回合。"""
        app = self.app
        resume = getattr(app, "resume_suspended", None) if app is not None else None
        if not callable(resume):
            return {"ok": False, "error": "内核未接入挂起调用恢复入口"}
        return resume(
            conversation_id, call_id, data, ok=ok, name=name, error=error)
