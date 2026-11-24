"""从有效声明与构造物派生公共 HTTP 挂载，不维护独立路由配置。"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from agent.core.slot_spec import HOST_OWNER

PREFIX = "app/shell/http/mounts/"


@dataclass(frozen=True)
class HttpMount:
    methods: frozenset[str]
    handlers: Mapping[str, Any]


def build_http_mounts(config: Any, built: Mapping[str, Any]) -> Mapping[str, HttpMount]:
    mounts = {}
    declared = {}
    for path in config.paths():
        spec = config.spec(path)
        if not path.startswith(PREFIX) or path.count("/") != PREFIX.count("/"):
            continue
        if config.origin_of(path) != HOST_OWNER or spec.kind != "container":
            raise ValueError(f"公共 HTTP 挂载须由宿主声明：{path}")
        url = str(spec.props.get("path", ""))
        methods = frozenset(spec.props.get("methods", ()))
        if not url.startswith("/api/") or url.startswith("/api/plugin/") or any(
                item in url for item in ("..", "?", "#", "\\")) or url.endswith("/"):
            raise ValueError(f"公共 HTTP 挂载路径非法：{path}")
        if not methods or not methods <= {"GET", "HEAD"} or url in mounts:
            raise ValueError(f"公共 HTTP 挂载重复或方法非法：{path}")
        mounts[url] = HttpMount(methods, {})
        declared[path] = url
    for path in config.paths():
        spec = config.spec(path)
        if spec.kind != "http-route":
            continue
        parent = path.rsplit("/", 1)[0]
        if parent not in declared or "path" in spec.props:
            raise ValueError(f"http-route 必须填充公共挂载且不得重复声明 URL：{path}")
        mount = mounts[declared[parent]]
        if spec.method not in mount.methods or spec.method in mount.handlers:
            raise ValueError(f"公共 HTTP 方法越界或重复：{path}")
        handler = built.get(path)
        if not callable(handler):
            raise ValueError(f"公共 HTTP 处理器不可调用：{path}")
        mount.handlers[spec.method] = handler
    return MappingProxyType({url: HttpMount(item.methods, MappingProxyType(item.handlers))
                             for url, item in mounts.items()})
