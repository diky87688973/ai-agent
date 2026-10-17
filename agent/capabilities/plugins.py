# -*- coding: utf-8 -*-
"""插件加载器——能力层的插件装卸落点。

目录约定：`plugins/<name>/plugin.py`（工程根 plugins/；忽略 `_`/`.` 开头目录）。
装载清单：工程根 `plugins.ini` 的 `[plugin:<名字>]` 节（可声明 version 与 path）；
未列出的插件不装载。见 `docs/subsystems/plugins.md`。
插件契约：plugin.py 暴露 `register(ctx) -> None | disposer | list[disposer]`；
ctx（PluginContext）提供 name、register_tool（挂 ToolRegistry）、subscribe（挂事件总线）、add_context_source（挂上下文注入源）与 add_pre_gate / add_post_observer（挂工具管道门控与观察者）；均返回幂等 disposer。

纪律：
- 单插件装载失败降级为报告（不中断宿主与其余插件）；
- register 抛错时，经 ctx 完成的注册逆序回滚（原子性兜底）；
- 卸载 = 逆序调用 disposer（去重）+ 移除插件模块缓存。
"""
from __future__ import annotations

import configparser
import hashlib
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional

from agent.capabilities.registry import ToolPlugin, ToolRegistry
from agent.config import get_plugin_tree_only
from agent.core.error_report import report_error

Disposer = Callable[[], None]

_MODULE_PREFIX = "fan_agent_plugins"


def resolve_plugin_root(plugins_dir: Path, name: str, path_raw: str = "") -> Path:
    """清单里的 `path` → 插件目录。空值取 `<插件根>/<名字>`。

    相对路径**按插件根解析**，不是按工程根：插件根是可配置的，写死工程根会让
    换了目录的部署全解析错。清单里写 `plugins/knowledge` 这种带前缀的路径也认 ——
    前缀与插件根同名时先剥掉，否则会拼成 `<插件根>/plugins/knowledge`。
    """
    base = Path(plugins_dir)
    if not path_raw:
        return (base / name).resolve()
    raw = Path(path_raw)
    if raw.is_absolute():
        return raw.resolve()
    parts = list(raw.parts)
    if parts and parts[0] == base.name:
        parts = parts[1:]
    return (base.joinpath(*parts) if parts else base).resolve()


def plugin_config_fields(plugin_root: Path) -> Dict[str, str]:
    """读插件 `plugin-config.ini` 的 `[base]`：身份与开关。

    每个插件都有这一节：`id` / `name` / `desc` / `enable` / `icon` / `version`。
    `enable` 为 `0` 时不装载；没写时按 `1`。插件自己的键在 `[ext]`，这里不读。
    """
    root = Path(plugin_root)
    fields = {
        "id": root.name,
        "name": "",
        "desc": "",
        "enable": "1",
        "icon": "",
        "version": "",
    }
    path = root / "plugin-config.ini"
    if not path.is_file():
        return fields
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8-sig")
    except (OSError, configparser.Error):
        return fields
    if not parser.has_section("base"):
        return fields

    def _get(key: str) -> str:
        return str(parser.get("base", key, fallback="") or "").strip()

    if _get("id"):
        fields["id"] = _get("id")
    fields["name"] = _get("name")
    fields["desc"] = _get("desc")
    if _get("enable") == "0":
        fields["enable"] = "0"
    fields["icon"] = _get("icon")
    fields["version"] = _get("version")
    return fields


def _safe_dir_name(name: str) -> str:
    """插件名 → 合法目录名：只留 `[A-Za-z0-9_-]`，其余换成 `_`。

    插件名会拼进文件路径，不净化就能用 `..` 或斜杠越出 `plugin/` 目录。
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(name or "")).strip("_")
    return cleaned or "plugin"


def _valid_plugin_name(name: str) -> bool:
    """插件名合法性：字母数字下划线短横，不以 `.` / `_` 开头。

    名字要做模块名后缀（`fan_agent_plugins.<名字>`）与目录名，两处都受限。
    """
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", str(name or "")))


def _within_plugins_tree(plugins_dir: Path, root: Path) -> bool:
    """插件目录是否落在宿主 `plugins_dir` 之下（解析后比较）。"""
    try:
        Path(root).resolve().relative_to(Path(plugins_dir).resolve())
        return True
    except (ValueError, OSError):
        return False


def _entry_integrity(entry: Path) -> Dict[str, Any]:
    """入口文件来源与完整性摘要（路径 / sha256 前缀 / mtime / 字节数）。"""
    path = Path(entry)
    meta: Dict[str, Any] = {
        "path": str(path.resolve()) if path.exists() else str(path),
        "sha256": "",
        "mtime": 0,
        "bytes": 0,
    }
    try:
        st = path.stat()
        meta["mtime"] = int(st.st_mtime)
        meta["bytes"] = int(st.st_size)
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        meta["sha256"] = digest.hexdigest()[:16]
    except OSError:
        pass
    return meta


@dataclass(slots=True)
class PluginInfo:
    """发现到的插件（目录名 + 入口文件）。"""

    name: str
    path: Path


@dataclass(slots=True)
class LoadReport:
    """单插件装载报告（status：loaded / error）。"""

    name: str
    status: str
    message: str = ""


class PluginContext:
    """插件注册面：name + register_tool；经此产生的 disposer 由加载器记账（回滚/卸载用）。"""

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
    ) -> None:
        self.name = name
        self._registry = registry
        self._event_bus = event_bus
        self._context_sources = context_sources
        self._pipeline = pipeline
        self._host = host
        self._contributions = contributions
        self._executors = executors
        #: 本插件在清单里的位次（宿主装载时写入；测试直构时为 None）
        self._rank: Optional[int] = None
        self._disposers: List[Disposer] = []

    def set_rank(self, rank: Optional[int]) -> None:
        """写入本插件在清单里的位次（组装顺序按它排）。"""
        self._rank = rank

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
        """向工具注册表注册插件；返回幂等 disposer。"""
        disposer = self._registry.register(plugin)
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
        段 key 一律以**插件名**为首（宿主不解释它的含义），段名由插件给。
        不给描述时用插件名当段名。
        """
        if self._context_sources is None:
            raise RuntimeError("插件未接入上下文注入源（PluginHost 未传 context_sources）")
        disposer = self._context_sources.add(fn, self._source_meta(meta))
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

        **段 key 一律是插件名** —— 前端按这个名字找插件注册的渲染钩子。
        段名、注入前缀与主体数量的取数口由插件给：
        `{"label": ..., "prefix": ..., "count": fn(cid)}`。
        组装顺序不由插件声明：它取插件在清单里的位次。
        """
        from agent.mechanisms.context_pipeline import SourceMeta, slug

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
        # 组装顺序按**插件清单位次**：清单靠前的插件，它的段也排在前面。
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

    @property
    def app(self) -> Any:
        """内核 App；装配完成前为 None。

        插件要从内核取服务（如 `ctx.app.registry`）时用它 —— 只在**处理器内部**
        取而不是在 `register` 里取：插件在装配末尾加载，但处理器是后来才被调用的。
        """
        return getattr(self._host, "app", None) if self._host is not None else None

    @property
    def data_dir(self) -> Optional[Path]:
        """本插件的专属存储根（`<数据根>/plugin/<插件名>/`），首次访问时创建。

        插件**只看到自己这一层**，不需要知道外层目录在哪 —— 换个数据根、换个目录
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
            # **旁路，刻意吞掉**：建不出目录不该让插件加载失败；插件拿到路径后
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
        `script_file` / `css_file` 是**插件目录内**的相对路径（如 `ui/panel.js`、
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


class PluginHost:
    """插件宿主：发现 / 按清单装载 / 卸载 / 报告。"""

    def __init__(self, plugins_dir: Path, registry: ToolRegistry, event_bus: Any = None, context_sources: Any = None, pipeline: Any = None, contributions: Any = None, plugin_data_root: Any = None, executors: Any = None) -> None:
        self._dir = Path(plugins_dir)
        self._registry = registry
        self._event_bus = event_bus
        self._context_sources = context_sources
        self._pipeline = pipeline
        self._contributions = contributions
        self._executors = executors
        #: 插件专属存储的根（`<数据根>/plugin/`）。插件只拿到自己的子目录，见 `PluginContext.data_dir`。
        self.plugin_data_root: Optional[Path] = (
            Path(plugin_data_root) if plugin_data_root is not None else None
        )
        self._loaded: Dict[str, List[Disposer]] = {}
        self._modules: Dict[str, str] = {}
        self._runtimes: Dict[str, Any] = {}
        #: 已装载插件名 → 插件目录（清单 `path` 解析后的绝对路径）
        self._plugin_roots: Dict[str, Path] = {}
        #: 版本，来自 `[base] version`；没写时沿用模块里的 `PLUGIN_VERSION`。没声明就是空串。
        self._versions: Dict[str, str] = {}
        self._reports: List[LoadReport] = []
        #: 内核 App；`build_app` 装配完登记（插件取内核服务用，见 `PluginContext.app`）
        self.app: Any = None

    # ── 贡献 ──

    @property
    def plugins_dir(self) -> Path:
        """插件根目录（壳层送面板脚本资产时要按它校验路径）。"""
        return self._dir

    def plugin_root(self, name: str) -> Optional[Path]:
        """已装载插件的目录；未装载或未知名返回 None。"""
        return self._plugin_roots.get(str(name or "").strip())

    def resolve_plugin_root(self, name: str, path_raw: str = "") -> Path:
        """清单里的 `path` → 插件目录（与装载时同一套解析）。"""
        return resolve_plugin_root(self._dir, name, path_raw)

    @property
    def contributions(self) -> Any:
        """插件贡献注册表（面板 / 动作 / 端点）；未接入时返回 None。"""
        return self._contributions

    # ── 运行时登记 ──

    def register_runtime(self, name: str, runtime: Any) -> None:
        """登记某插件的运行时对象，供壳层按插件名取用。"""
        key = str(name or "").strip()
        if key:
            self._runtimes[key] = runtime

    def runtime(self, name: str, default: Any = None) -> Any:
        """取某插件的运行时对象；未加载或未登记返回 `default`。

        壳层用它拿到**插件自己那一份**运行时（`importlib` 以动态模块名加载，
        壳层 import 不到同一个模块对象，只能经宿主取）。
        """
        return self._runtimes.get(str(name or "").strip(), default)

    # ── 发现 ──

    def discover(self) -> List[PluginInfo]:
        """扫描插件根目录：`<name>/plugin.py` 为插件；忽略隐藏/私有目录与无入口项。

        这是**不依赖清单**的枚举，用于列出磁盘上有哪些插件。
        真正装载哪些由清单（`plugins.ini`）决定，装载入口是 `load_manifest`。
        """
        if not self._dir.is_dir():
            return []
        found: List[PluginInfo] = []
        for child in sorted(self._dir.iterdir()):
            if not child.is_dir() or child.name.startswith(("_", ".")):
                continue
            entry = child / "plugin.py"
            if entry.is_file():
                found.append(PluginInfo(name=child.name, path=entry))
        return found

    # ── 装载（按清单）──

    def load_manifest(self, entries: List[Any]) -> List[LoadReport]:
        """按清单装载。每项是 `{name, version, path}`；也接受纯名字（取默认目录）。

        插件 `plugin-config.ini` 的 `[base] enable = 0` 时卸下后跳过，不记错误。
        条目自己带 `enabled = 0` 时同样跳过。
        名字非法、目录缺失、缺 `plugin.py`、版本对不上都记下来。
        """
        fresh: List[LoadReport] = []
        for rank, entry in enumerate(entries):
            raw = entry if isinstance(entry, dict) else {"name": entry}
            name = str(raw.get("name") or "").strip()
            declared = str(raw.get("version") or "").strip()
            path_raw = str(raw.get("path") or "").strip()
            if isinstance(raw, dict) and str(raw.get("enabled", "1")).strip() == "0":
                if name in self._loaded:
                    self.unload(name)
                continue

            if not _valid_plugin_name(name):
                msg = "插件名非法：只许字母、数字、下划线与短横，且不以 . 或 _ 开头"
                report_error("plugin.load", msg, plugin=name or "(未命名)")
                fresh.append(LoadReport(
                    name=name or "(未命名)", status="error", message=msg))
                continue
            root = resolve_plugin_root(self._dir, name, path_raw)
            base = plugin_config_fields(root)
            if base["enable"] == "0":
                if name in self._loaded:
                    self.unload(name)
                continue
            if name in self._loaded:
                continue

            entry_file = root / "plugin.py"
            if not entry_file.is_file():
                msg = f"插件目录不存在或缺少 plugin.py：{entry_file}"
                report_error("plugin.load", msg, plugin=name)
                fresh.append(LoadReport(name=name, status="error", message=msg))
                continue

            report = self._load_one(
                PluginInfo(name=name, path=entry_file), rank=rank, root=root)
            if base["version"]:
                self._versions[name] = base["version"]
            if report.status == "loaded" and declared:
                actual = str(self._versions.get(name) or "")
                if actual and actual != declared:
                    report = LoadReport(
                        name=name, status="loaded",
                        message=f"清单声明版本 {declared}，插件自报 {actual}")
            fresh.append(report)
        self._reports.extend(fresh)
        return fresh

    def load_enabled(self, enabled: List[str]) -> List[LoadReport]:
        """按**名字白名单**装载（不写清单的场景：测试、脚本、临时装配）。

        正式装配走 `load_manifest`：清单里能声明版本与目录，白名单不能。
        """
        discovered = {info.name: info for info in self.discover()}
        fresh: List[LoadReport] = []
        for rank, raw in enumerate(enabled):
            name = str(raw or "").strip()
            if not name or name in self._loaded:
                continue
            info = discovered.get(name)
            if info is None:
                msg = "插件目录不存在或缺少 plugin.py"
                report_error("plugin.load", msg, plugin=name)
                fresh.append(LoadReport(name=name, status="error", message=msg))
                continue
            report = self._load_one(
                info, rank=rank, root=info.path.parent.resolve())
            fresh.append(report)
        self._reports.extend(fresh)
        return fresh

    def _load_one(
        self,
        info: PluginInfo,
        rank: Optional[int] = None,
        root: Optional[Path] = None,
    ) -> LoadReport:
        ctx = PluginContext(info.name, self._registry, self._event_bus,
                            self._context_sources, self._pipeline, self,
                            self._contributions, self._executors)
        ctx.set_rank(rank)
        mod_name = f"{_MODULE_PREFIX}.{info.name}"
        plugin_root = Path(root).resolve() if root is not None else info.path.parent.resolve()
        try:
            # 开关打开时拒绝对外置路径装载（见 docs/subsystems/plugins.md「信任模型」）
            if get_plugin_tree_only() and not _within_plugins_tree(self._dir, plugin_root):
                raise RuntimeError(
                    f"插件路径越出 plugins/ 树：{plugin_root}"
                    "（已开 plugin_tree_only / AI_AGENT_PLUGIN_TREE_ONLY）"
                )
            integrity = _entry_integrity(info.path)
            print(
                f"[plugin.load] {info.name} source={integrity['path']} "
                f"sha256={integrity['sha256'] or '?'} "
                f"mtime={integrity['mtime']} bytes={integrity['bytes']}",
                file=sys.stderr,
                flush=True,
            )
            # 把插件目录标成包搜索路径，使 `from .sibling import …` 在动态加载下可用
            spec = importlib.util.spec_from_file_location(
                mod_name,
                str(info.path),
                submodule_search_locations=[str(plugin_root)],
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载插件模块：{info.path}")
            module: ModuleType = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if not callable(register):
                raise AttributeError("plugin.py 未定义可调用的 register(ctx)")
            returned = register(ctx)
            self._loaded[info.name] = _collect_disposers(ctx, returned)
            self._modules[info.name] = mod_name
            self._plugin_roots[info.name] = plugin_root
            # 模块级 PLUGIN_VERSION。`[base] version` 有值时调用方改用那一份，再与清单核对。
            self._versions[info.name] = str(getattr(module, "PLUGIN_VERSION", "") or "")
            return LoadReport(name=info.name, status="loaded")
        except Exception as exc:
            _rollback(ctx)
            _drop_plugin_modules(mod_name)
            self._plugin_roots.pop(info.name, None)
            report_error("plugin.load", exc, plugin=info.name)
            return LoadReport(name=info.name, status="error", message=f"{type(exc).__name__}: {exc}")

    # ── 卸载 ──

    def unload(self, name: str) -> None:
        """卸载单个插件（未加载则忽略）；disposer 逆序执行、单个失败不阻断。"""
        key = str(name or "").strip()
        disposers = self._loaded.pop(key, None)
        if disposers is None:
            return
        for disposer in reversed(disposers):
            try:
                disposer()
            except Exception:
                pass
        mod_name = self._modules.pop(key, None)
        if mod_name:
            _drop_plugin_modules(mod_name)
        self._runtimes.pop(key, None)
        self._plugin_roots.pop(key, None)
        # 贡献兜底：disposer 正常时已撤过，这里防的是 disposer 漏挂或执行失败 ——
        # 残留的面板会变成打不开的死标签，残留的端点会指向已卸载的插件。
        if self._contributions is not None:
            self._contributions.drop_plugin(key)

    def unload_all(self) -> None:
        """卸载全部已加载插件。"""
        for name in list(self._loaded.keys()):
            self.unload(name)

    # ── 查询 ──

    def loaded_names(self) -> List[str]:
        """已加载插件名（排序）。"""
        return sorted(self._loaded.keys())

    def reports(self) -> List[LoadReport]:
        """全部装载报告（副本）。"""
        return list(self._reports)


def _drop_plugin_modules(mod_name: str) -> None:
    """卸掉插件入口模块及其子模块（相对 import 会挂上同前缀名）。"""
    prefix = mod_name + "."
    for key in list(sys.modules):
        if key == mod_name or key.startswith(prefix):
            sys.modules.pop(key, None)


def _collect_disposers(ctx: PluginContext, returned: Any) -> List[Disposer]:
    """合并 ctx 记账与 register 返回值，按对象去重（保序）。"""
    merged: List[Disposer] = list(ctx._disposers)
    merged.extend(_flatten(returned))
    seen = set()
    unique: List[Disposer] = []
    for disposer in merged:
        if callable(disposer) and id(disposer) not in seen:
            seen.add(id(disposer))
            unique.append(disposer)
    return unique


def _flatten(returned: Any) -> List[Disposer]:
    """把 None | 可调用 | 列表（可嵌套）拍平为 disposer 列表。"""
    if returned is None:
        return []
    if callable(returned):
        return [returned]
    if isinstance(returned, (list, tuple)):
        out: List[Disposer] = []
        for item in returned:
            out.extend(_flatten(item))
        return out
    return []


def _rollback(ctx: PluginContext) -> None:
    """register 抛错后的逆序回滚（容错执行）。"""
    for disposer in reversed(ctx._disposers):
        try:
            disposer()
        except Exception:
            pass
