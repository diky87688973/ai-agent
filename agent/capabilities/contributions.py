# -*- coding: utf-8 -*-
"""插件贡献注册表——插件向壳层暴露「界面」与「HTTP 端点」的落点。

插件可以贡献的不只是工具：右侧面板（界面）与自己的数据端点（HTTP）同样是一等贡献。
本模块只管记账与查找，不关心具体是什么语义：

- `Panel`：右栏一个可开面板的声明（id / 标题 / HTML 片段或 url / 是否常驻）。
  HTML 由插件给，壳层只负责塞进面板容器，不解释内容。
- `BootScript`：开屏预载脚本（插件目录内相对路径）；无面板也能注入工具卡等 JS。
- `Route`：插件自己的 HTTP 端点，挂在 `/api/plugin/<plugin>/<path>` 命名空间下。

命名空间是硬约束：插件不许注册到内核路由上，也不许用 `..` 或前导 `/` 越出命名空间。
这样"插件挂了哪些端点"永远是可枚举、可审计的，内核路由表也不必为每个插件加分支。

纪律：注册返回幂等 disposer；卸载时必须撤干净（面板与端点都是贡献，撤不掉的贡献
会让界面出现打不开的标签、或指向已经卸载插件的死端点）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

Disposer = Callable[[], None]

#: 插件端点的公共前缀。壳层只在这一段之下做转发。
PLUGIN_ROUTE_PREFIX = "/api/plugin/"

#: 面板脚本用的资产段：`<前缀><插件>/_asset/<插件目录内的相对路径>`。
#: 用下划线开头避免与插件自己的端点路径撞名。
ASSET_SEGMENT = "_asset"


class ContributionError(ValueError):
    """贡献声明不合规（命名空间越界 / 重名 / 字段缺失）。"""


@dataclass(slots=True)
class Panel:
    """右栏面板声明。

    - `html`：一段 HTML 片段，由壳层注入面板容器（与页面同源，按可信代码对待）。
    - `url`：面板内容的地址；与 `html` 二选一。给 `url` 时壳层按需加载。
    - `pinned`：常驻面板不显示关闭按钮（步骤栏就是这种）。
    - `script`：可选的脚本 URL，面板首次打开时加载一次，供面板自行渲染与取数。
      壳层不为它挂路由，插件应自己用 `add_route` 提供（返回 JS 文本即可）。
    - `script_file`：脚本在插件目录内的相对路径（如 `ui/panel.js`）。声明它就不必
      自己挂路由 —— 壳层按 `/api/plugin/<插件>/_asset/<路径>` 直接读出并送 JS。
    - `css_file`：样式表在插件目录内的相对路径（如 `ui/panel.css`），面板首次打开时
      注入。插件的样式属于插件，不该写进壳层的公共样式表 —— 那样插件的类名会
      和页面样式混在一个文件里，且插件没被加载时也白带一份。
      路径不许越出插件目录。
    """

    plugin: str
    panel_id: str
    title: str
    html: str = ""
    url: str = ""
    script: str = ""
    script_file: str = ""
    css_file: str = ""
    pinned: bool = False

    def as_dict(self) -> Dict[str, Any]:
        #: 面板脚本 / 样式地址：显式 URL 优先，否则由 `*_file` 推出来
        script = self.script
        if not script and self.script_file:
            script = f"{PLUGIN_ROUTE_PREFIX}{self.plugin}/{ASSET_SEGMENT}/{self.script_file}"
        style = ""
        if self.css_file:
            style = f"{PLUGIN_ROUTE_PREFIX}{self.plugin}/{ASSET_SEGMENT}/{self.css_file}"
        return {
            "plugin": self.plugin,
            "id": self.panel_id,
            "title": self.title,
            "html": self.html,
            "url": self.url,
            "script": script,
            "style": style,
            "pinned": self.pinned,
        }


@dataclass(slots=True)
class Action:
    """输入区动作声明：输入框下面的一个按钮。

    点它做什么由前端定（默认打开本插件同 id 的面板）—— 插件只声明"有这个动作"，
    不注入脚本。要在点击时执行逻辑，插件应端点化（`/api/plugin/<插件>/…`）并由
    前端按 `panel` 打开的面板去调。
    """

    plugin: str
    action_id: str
    label: str
    title: str = ""
    panel: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "plugin": self.plugin,
            "id": self.action_id,
            "label": self.label,
            "title": self.title,
            "panel": self.panel or self.action_id,
        }


@dataclass(slots=True)
class CtxSegmentStyle:
    """上下文分层里某插件段的外观（段名 / 色名）。"""

    plugin: str
    label: str = ""
    color: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "plugin": self.plugin,
            "label": self.label,
            "color": self.color,
        }


@dataclass(slots=True)
class BootScript:
    """开屏预载脚本：插件目录内相对路径，无面板也能在经典 UI 启动时注入。"""

    plugin: str
    rel_path: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "plugin": self.plugin,
            "rel_path": self.rel_path,
            "script": (
                f"{PLUGIN_ROUTE_PREFIX}{self.plugin}/"
                f"{ASSET_SEGMENT}/{self.rel_path}"
            ),
        }


@dataclass(slots=True)
class Route:
    """插件 HTTP 端点声明；实际路径是 `<前缀><plugin>/<path>`。

    路径里可以有 `:名字` 段（如 `tasks/:sid`），匹配到的内容按名字交给 handler。
    除 `:名字` 外不做通配 —— "某插件挂了哪些端点形状"始终可枚举、可审计。
    """

    plugin: str
    method: str
    path: str
    handler: Callable[..., Any]

    @property
    def full_path(self) -> str:
        return f"{PLUGIN_ROUTE_PREFIX}{self.plugin}/{self.path}"

    @property
    def segments(self) -> List[str]:
        """`full_path` 按 `/` 切分（去掉空段）。"""
        return [s for s in self.full_path.split("/") if s]

    def match_segments(self, segments: List[str]) -> Optional[Dict[str, str]]:
        """段对段匹配；命中返回 `:名字` 段取到的值（无参数则为空 dict），否则 None。

        段数必须完全相等：`tasks` 不等于 `tasks/t-1`。
        """
        want = self.segments
        if len(want) != len(segments):
            return None
        params: Dict[str, str] = {}
        for expected, actual in zip(want, segments):
            if expected.startswith(":"):
                name = expected[1:]
                if not name:
                    return None
                params[name] = actual
                continue
            if expected != actual:
                return None
        return params

    def as_dict(self) -> Dict[str, Any]:
        return {"plugin": self.plugin, "method": self.method, "path": self.full_path}


def _reject_absolute(raw: Any, what: str) -> str:
    """拒绝绝对路径写法（前导 `/`、`\\`、盘符），返回原串。

    绝对路径要报错而不是被悄悄剥成相对路径 —— 静默纠正会把
    `/etc/x.js` 当成 `etc/x.js`，写的人和读的人对最终位置的理解不一致。
    """
    s = str(raw or "").strip()
    if not s:
        raise ContributionError(f"{what} 不能为空")
    if s[0] in ("/", "\\") or re.match(r"^[A-Za-z]:", s):
        raise ContributionError(f"{what} 非法：{s!r}（不许绝对路径）")
    return s


def _clean_segment(raw: Any, what: str) -> str:
    """校验命名空间段：非空、相对、无 `..`、无空白。

    这一段会拼进 URL 路径，不校验就能用 `..` 越出插件命名空间挂到别处。
    """
    s = _reject_absolute(raw, what).strip("/")
    if not s:
        raise ContributionError(f"{what} 不能为空")
    if ".." in s or "\\" in s or any(c.isspace() for c in s):
        raise ContributionError(f"{what} 非法：{s!r}（不许含 `..` / 反斜杠 / 空白）")
    return s


def _clean_asset_rel(raw: Any) -> str:
    """校验面板脚本在插件目录内的相对路径：不许绝对路径、不许 `..`。

    它会被拼成 `<插件目录>/<相对路径>` 后读文件；不校验就能读到插件目录之外。
    """
    rel = _reject_absolute(raw, "面板脚本路径").replace("\\", "/").strip("/")
    if not rel:
        raise ContributionError("面板脚本路径 不能为空")
    parts = [p for p in rel.split("/") if p]
    if any(p == ".." for p in parts):
        raise ContributionError(f"面板脚本路径 非法：{raw!r}（不许含 `..`）")
    return "/".join(parts)


def _clean_path_segments(raw: Any) -> List[str]:
    """校验端点路径：逐段净化，允许 `:名字` 形式的参数段。

    `:名字` 段的值由请求提供而不是声明，所以必须防止它被当成通配 ——
    参数段名只留字面量，且整条路径不许出现 `..`（那会越出命名空间）。
    """
    path = _reject_absolute(raw, "端点路径").strip("/")
    if not path:
        raise ContributionError("端点路径 不能为空")
    if ".." in path or "\\" in path:
        raise ContributionError(f"端点路径 非法：{path!r}（不许含 `..` / 反斜杠）")
    out: List[str] = []
    for seg in path.split("/"):
        if seg.startswith(":"):
            name = seg[1:]
            if not name:
                raise ContributionError(f"端点路径 参数段缺名字：{path!r}")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ContributionError(f"端点路径 参数名非法：{name!r}")
            out.append(":" + name)
            continue
        if not seg:
            continue
        out.append(_clean_segment(seg, "端点路径"))
    if not out:
        raise ContributionError("端点路径 不能为空")
    return out


@dataclass
class ContributionRegistry:
    """面板与端点的注册表；键都带插件名，避免不同插件撞名。"""

    panels: Dict[str, Panel] = field(default_factory=dict)
    routes: Dict[str, Route] = field(default_factory=dict)
    actions: Dict[str, Action] = field(default_factory=dict)
    ctx_segment_styles: Dict[str, CtxSegmentStyle] = field(default_factory=dict)
    boot_scripts: Dict[str, BootScript] = field(default_factory=dict)

    # ── 上下文段外观 ──

    def add_ctx_segment_style(
        self,
        plugin: str,
        *,
        label: str = "",
        color: str = "",
    ) -> Disposer:
        key = _clean_segment(plugin, "插件名")
        if key in self.ctx_segment_styles:
            raise ContributionError(f"上下文段外观已注册：{key}")
        self.ctx_segment_styles[key] = CtxSegmentStyle(
            plugin=plugin,
            label=str(label or ""),
            color=str(color or ""),
        )
        return lambda: self.ctx_segment_styles.pop(key, None)

    def all_ctx_segment_styles(self) -> List[CtxSegmentStyle]:
        """全部上下文段外观，按插件名排序。"""
        return sorted(self.ctx_segment_styles.values(), key=lambda s: s.plugin)

    # ── 开屏脚本（无面板也可预载）──

    def add_boot_script(self, plugin: str, rel_path: str) -> Disposer:
        """登记开屏预载脚本（插件目录内相对路径，如 `ui/tool-view.js`）。"""
        name = _clean_segment(plugin, "插件名")
        rel = _clean_asset_rel(rel_path)
        key = f"{name}:{rel}"
        if key in self.boot_scripts:
            raise ContributionError(f"开屏脚本已注册：{key}")
        self.boot_scripts[key] = BootScript(plugin=plugin, rel_path=rel)
        return lambda: self.boot_scripts.pop(key, None)

    def all_boot_scripts(self) -> List[BootScript]:
        """全部开屏脚本，按插件名与相对路径排序。"""
        return sorted(
            self.boot_scripts.values(),
            key=lambda s: (s.plugin, s.rel_path),
        )

    # ── 动作（输入区按钮）──

    def add_action(
        self,
        plugin: str,
        action_id: str,
        *,
        label: str,
        title: str = "",
        panel: str = "",
    ) -> Disposer:
        key = f"{_clean_segment(plugin, '插件名')}:{_clean_segment(action_id, '动作 id')}"
        if key in self.actions:
            raise ContributionError(f"动作已注册：{key}")
        self.actions[key] = Action(
            plugin=plugin, action_id=action_id, label=str(label or action_id),
            title=str(title or label or ""),
            # 未指定面板即"开同名面板"：在这里落定，而不是留给消费方各自补默认
            panel=str(panel or action_id),
        )
        return lambda: self.actions.pop(key, None)

    def actions_of(self, plugin: str) -> List[Action]:
        return [a for a in self.actions.values() if a.plugin == plugin]

    def all_actions(self) -> List[Action]:
        """全部动作，按插件名与动作 id 排序（供界面稳定渲染）。"""
        return sorted(self.actions.values(), key=lambda a: (a.plugin, a.action_id))

    # ── 面板 ──

    def add_panel(
        self,
        plugin: str,
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
        key = f"{_clean_segment(plugin, '插件名')}:{_clean_segment(panel_id, '面板 id')}"
        if key in self.panels:
            raise ContributionError(f"面板已注册：{key}")
        for rel in (script_file, css_file):
            if rel:
                _clean_asset_rel(rel)
        self.panels[key] = Panel(
            plugin=plugin, panel_id=panel_id, title=str(title or panel_id),
            html=str(html or ""), url=str(url or ""), script=str(script or ""),
            script_file=str(script_file or ""), css_file=str(css_file or ""),
            pinned=bool(pinned),
        )
        return lambda: self.panels.pop(key, None)

    def panel(self, plugin: str, panel_id: str) -> Optional[Panel]:
        return self.panels.get(f"{plugin}:{panel_id}")

    def panels_of(self, plugin: str) -> List[Panel]:
        return [p for p in self.panels.values() if p.plugin == plugin]

    def all_panels(self) -> List[Panel]:
        """全部面板，按插件名与面板 id 排序（供界面稳定渲染）。"""
        return sorted(self.panels.values(), key=lambda p: (p.plugin, p.panel_id))

    # ── 端点 ──

    def add_route(
        self,
        plugin: str,
        method: str,
        path: str,
        handler: Callable[..., Any],
    ) -> Disposer:
        if not callable(handler):
            raise ContributionError("handler 必须可调用")
        m = str(method or "GET").strip().upper()
        if m not in ("GET", "POST", "PUT", "DELETE"):
            raise ContributionError(f"method 不支持：{method!r}")
        seg = _clean_path_segments(path)
        key = f"{m} {_clean_segment(plugin, '插件名')}/{'/'.join(seg)}"
        if key in self.routes:
            raise ContributionError(f"端点已注册：{key}")
        self.routes[key] = Route(plugin=plugin, method=m, path="/".join(seg), handler=handler)
        return lambda: self.routes.pop(key, None)

    def match(self, method: str, url_path: str) -> Optional[Tuple[Route, Dict[str, str]]]:
        """按 `方法 + 路径` 找端点；返回 `(Route, 路径参数)` 或 None。

        `:名字` 段按位置取值（如 `tasks/:sid` 对上 `tasks/t-1` → `{"sid": "t-1"}`）。
        优先精确匹配，再退到带参数的路由 —— 声明了 `tasks` 又声明 `tasks/:sid` 时
        `tasks` 不会被参数路由抢走。
        """
        m = str(method or "GET").strip().upper()
        segments = [s for s in str(url_path or "").split("/") if s]
        candidates = [r for r in self.routes.values() if r.method == m]
        # 精确（无 `:名字` 段）优先
        for route in candidates:
            if ":" in route.full_path:
                continue
            if route.match_segments(segments) is not None:
                return route, {}
        for route in candidates:
            params = route.match_segments(segments)
            if params is not None:
                return route, params
        return None

    def routes_of(self, plugin: str) -> List[Route]:
        return [r for r in self.routes.values() if r.plugin == plugin]

    def all_routes(self) -> List[Route]:
        return sorted(self.routes.values(), key=lambda r: (r.plugin, r.method, r.path))

    # ── 卸载 ──

    def drop_plugin(self, plugin: str) -> int:
        """撤掉某插件的全部贡献；返回撤掉条数（卸载兜底，防残留死标签 / 死端点）。"""
        name = str(plugin or "")
        total = 0
        for store in (
            self.panels, self.routes, self.actions,
            self.ctx_segment_styles, self.boot_scripts,
        ):
            keys = [k for k, v in store.items() if getattr(v, "plugin", None) == name]
            for k in keys:
                store.pop(k, None)
            total += len(keys)
        return total
