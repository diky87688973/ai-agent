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
from agent.capabilities.registry import ToolPlugin, ToolRegistry
from agent.core.context import SERVICE_SUBAGENTS
from agent.core.error_report import report_error


def _safe_dir_name(name: str) -> str:
    """插件名 → 合法目录名：只留 `[A-Za-z0-9_-]`，其余换成 `_`。

    插件名会拼进文件路径，不净化就能用 `..` 或斜杠越出 `plugin/` 目录。
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(name or "")).strip("_")
    return cleaned or "plugin"


class PluginContext:
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
        prompt_tail: Any = None,
        prompt_sections: Any = None,
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
        self._prompt_tail = prompt_tail
        self._prompt_sections = prompt_sections
        #: 本插件在清单里的位次（宿主装载时写入；测试直构时为 None）
        self._rank: Optional[int] = None
        self._disposers: List[Disposer] = []

    def set_rank(self, rank: Optional[int]) -> None:
        """写入本插件在清单里的位次（组装顺序按它排）。"""
        self._rank = rank

    def owned_disposers(self) -> List[Disposer]:
        """本插件经 ctx 登记的贡献 disposer（登记顺序；撤销时逆序）。"""
        return list(self._disposers)

    def add_executor(self, name: str, fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Disposer:
        """登记写类工具的执行器（提交路径扩展点；需接入 ExecutorRegistry）。

        插件自己的写类工具走 `confirm_id` 制预览时，提交那一刻按工具名来这里取。
        """
        if self._executors is None:
            raise RuntimeError("插件未接入执行器注册表（PluginHost 未传 executors）")
        disposer = self._executors.add(name, fn, owner=self.name)
        self._disposers.append(disposer)
        return disposer

    def register_tool(self, plugin: ToolPlugin) -> Disposer:
        """向工具注册表注册插件；子 Agent 可见性由 set_subagent_tools 声明。"""
        disposer = self._registry.register(plugin, owner=self.name)
        self._disposers.append(disposer)
        return disposer

    def set_subagent_tools(self, tools: Any) -> Disposer:
        """声明本插件向子 Agent 暴露的工具清单；空清单表示全部不暴露。"""
        disposer = self._registry.set_subagent_tools(self.name, tools)
        self._disposers.append(disposer)
        return disposer

    def subscribe(self, event_type: str, handler: Callable[[Any], None]) -> Disposer:
        """订阅事件总线上的指定类型事件；返回幂等 disposer（需接入总线）。"""
        if self._event_bus is None:
            raise RuntimeError("插件未接入事件总线（PluginHost 未传 event_bus）")
        disposer = self._event_bus.subscribe(event_type, handler)
        self._disposers.append(disposer)
        return disposer

    def add_context_source(self, fn: Callable[[str], List[str]],
                           meta: Any = None) -> Disposer:
        """注册上下文注入源（上下文注入扩展点；需接入 sources）。

        `meta` 是这一段的描述（`SourceMeta` 或 `{"label": ...}` 这类映射）：
        段 key 一律以插件名为首（宿主不解释它的含义），段名由插件给。
        不给描述时用插件名当段名。
        """
        if self._context_sources is None:
            raise RuntimeError("插件未接入上下文注入源（PluginHost 未传 context_sources）")
        disposer = self._context_sources.add(fn, self._source_meta(meta))
        self._disposers.append(disposer)
        return disposer

    def add_mode_tail(self, fn: Callable[[str], Any], *,
                      subagent_visible: bool = True) -> Disposer:
        """注册请求尾部片段；可声明是否注入子 Agent 尾部。"""
        if self._prompt_tail is None:
            raise RuntimeError("插件未接入请求尾部（PluginHost 未传 prompt_tail）")
        disposer = self._prompt_tail.add(fn, subagent_visible=subagent_visible)
        self._disposers.append(disposer)
        return disposer

    def add_prompt_section(self, section: str, fn: Callable[[str], Any]) -> Disposer:
        """注册系统提示词章节来源；同一章节由多个插件合并。"""
        if self._prompt_sections is None:
            raise RuntimeError("插件未接入系统提示词章节（PluginHost 未传 prompt_sections）")
        disposer = self._prompt_sections.add(section, fn, rank=self._rank)
        self._disposers.append(disposer)
        return disposer

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

    def add_pre_gate(self, fn: Callable[[Any, Any], Any]) -> Disposer:
        """注册工具管道前置门控（工具管道扩展点；仅可加检查，不可减保证）。"""
        if self._pipeline is None:
            raise RuntimeError("插件未接入工具管道（PluginHost 未传 pipeline）")
        disposer = self._pipeline.add_pre(fn)
        self._disposers.append(disposer)
        return disposer

    def add_post_observer(self, fn: Callable[[Any, Any, Any], None]) -> Disposer:
        """注册工具管道后置观察者（工具管道扩展点）。"""
        if self._pipeline is None:
            raise RuntimeError("插件未接入工具管道（PluginHost 未传 pipeline）")
        disposer = self._pipeline.add_post(fn)
        self._disposers.append(disposer)
        return disposer

    def set_runtime(self, runtime: Any) -> None:
        """登记本插件的运行时对象，供壳层按插件名取用。

        插件被 `importlib` 以动态模块名加载，壳层没法 import 到同一个模块对象，
        所以插件自己持有的运行时必须经宿主登记出来 —— 否则壳层会另建一份，
        两边状态各写各的（勾选存进去却注入不出来）。
        """
        if self._host is not None:
            self._host.register_runtime(self.name, runtime)

    def is_subagent(self, conversation_id: str) -> bool:
        """当前会话是否为子 Agent；插件用它决定是否注入子 Agent 专属内容。"""
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

    def add_panel(
        self,
        panel_id: str,
        *,
        title: str,
        html: str = "",
        url: str = "",
        script: str = "",
        script_file: str = "",
        css_file: str = "",
        pinned: bool = False,
    ) -> Disposer:
        """声明右栏一个可开面板；壳层把它塞进面板容器，不解释内容。

        `html` 与 `url` 二选一：`html` 是同源 HTML 片段（按可信代码对待），
        `url` 交给壳层按需加载。
        `script_file` / `css_file` 是插件目录内的相对路径（如 `ui/panel.js`、
        `ui/panel.css`）：声明它们，壳层就按 `_asset` 路由送出，面板首次打开时注入。
        面板的脚本与样式都属于插件，不必自己挂路由、也不要写进壳层的公共资源。
        """
        disposer = self._contrib().add_panel(
            self.name, panel_id, title=title, html=html, url=url,
            script=script, script_file=script_file, css_file=css_file, pinned=pinned,
        )
        self._disposers.append(disposer)
        return disposer

    def add_route(
        self,
        method: str,
        path: str,
        handler: Callable[[Dict[str, Any]], Any],
    ) -> Disposer:
        """注册插件自己的 HTTP 端点：`/api/plugin/<插件名>/<path>`。

        `handler(query)` 返回 `(status, payload)`；payload 为 dict / list 时按 JSON 返回。
        路径只许是单段字面量（不许 `..`、通配或前导斜杠），命名空间不可越出。
        """
        disposer = self._contrib().add_route(self.name, method, path, handler)
        self._disposers.append(disposer)
        return disposer

    def add_action(
        self,
        action_id: str,
        *,
        label: str,
        title: str = "",
        panel: str = "",
    ) -> Disposer:
        """声明输入区的一个动作按钮（输入框下面）。

        默认点击打开本插件同 id 的面板；`panel` 可指向另一个面板。
        插件不声明就没有这个按钮 —— 界面里不该有内核写死的插件入口。
        """
        disposer = self._contrib().add_action(
            self.name, action_id, label=label, title=title, panel=panel)
        self._disposers.append(disposer)
        return disposer

    def add_ctx_segment_style(
        self,
        *,
        label: str = "",
        color: str = "",
    ) -> Disposer:
        """声明上下文分层里本插件段的外观（段名 / 色名）；壳层开屏按贡献表注册。"""
        disposer = self._contrib().add_ctx_segment_style(
            self.name, label=label, color=color)
        self._disposers.append(disposer)
        return disposer

    def add_boot_script(self, rel_path: str) -> Disposer:
        """声明开屏预载脚本（插件目录内相对路径）；无面板也能在经典 UI 启动时注入。

        壳层按 `/api/plugin/<插件>/_asset/<路径>` 送达，排在面板脚本预载之后。
        """
        disposer = self._contrib().add_boot_script(self.name, rel_path)
        self._disposers.append(disposer)
        return disposer

    def add_model_catalog(self, entries: Any) -> Disposer:
        """声明本插件的模型清单；`entries` 是条目序列或每次重读配置的回调。

        来源名固定是插件名：目录只认一个权威，冲突时保留先登记的来源并留痕，
        插件装载不因此失败（装载顺序不是契约，但结果必须确定且可审计）。
        """
        if self._model_catalog is None:
            raise RuntimeError("插件未接入模型目录（PluginHost 未传 model_catalog）")
        try:
            disposer = self._model_catalog.set_source(self.name, entries)
        except RuntimeError as exc:
            report_error("plugin.model_catalog", exc, plugin=self.name)
            return lambda: None
        self._disposers.append(disposer)
        return disposer
