# -*- coding: utf-8 -*-
"""插件贡献注册表：插件向壳层暴露 HTTP 端点的落点。

只记录端点与所属插件；命名空间固定为 `/api/plugin/<plugin>/<path>`。
注册返回幂等 disposer，卸载时撤销。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

Disposer = Callable[[], None]

#: 插件端点的公共前缀。壳层只在这一段之下做转发。
PLUGIN_ROUTE_PREFIX = "/api/plugin/"
ASSET_SEGMENT = "_asset"

class ContributionError(ValueError):
    """贡献声明不合规（命名空间越界 / 重名 / 字段缺失）。"""


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
    """插件 HTTP 端点注册表；键都带插件名，避免不同插件撞名。"""

    routes: Dict[str, Route] = field(default_factory=dict)

    # ── 上下文段外观 ──

    # ── 开屏脚本（无面板也可预载）──

    # ── 宿主设置字段 ──

    # ── 动作（输入区按钮）──

    # ── 面板 ──

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
            self.routes,
        ):
            keys = [k for k, v in store.items() if getattr(v, "plugin", None) == name]
            for k in keys:
                store.pop(k, None)
            total += len(keys)
        return total
