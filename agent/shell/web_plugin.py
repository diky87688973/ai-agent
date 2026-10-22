# -*- coding: utf-8 -*-
"""插件 HTTP 路由。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from agent.core.error_report import report_error
from agent.shell.web_static import plugin_asset_rel


class PluginRoutes:
    server_version = "ai-agent-web/1.0"
    shell: Any
    assets_dir: Any

    def _plugin_route(self, method: str, body: Optional[Dict[str, Any]] = None) -> None:
        """把 `/api/plugin/<插件>/<段>` 转发给插件注册的端点。

        路径与查询串自己从请求行取（三个动词共用这一条，调用点不必各传一份）。
        路径里声明的 `:名字` 段由壳层按位置取值后交给 handler；除参数段外不做通配，
        「某插件挂了哪些端点形状」始终可枚举。无匹配时 404 并列出全部已注册端点。

        handler 收到的 dict：查询串 + 路径参数 + （有请求体时）`body`。
        """
        path = self._path()
        query = self._query()
        host = getattr(self.shell.app, "plugin_host", None) if self.shell.app else None
        contribs = getattr(host, "contributions", None) if host is not None else None
        if contribs is None:
            self._json(404, {"error": "插件系统未接入"})
            return
        # 面板脚本资产：`/api/plugin/<插件>/_asset/<插件目录内相对路径>`
        asset = plugin_asset_rel(path)
        if asset is not None and method == "GET":
            self._plugin_asset(asset[0], asset[1])
            return
        hit = contribs.match(method, path)
        if hit is None:
            self._json(404, {"error": "插件端点不存在", "method": method, "path": path,
                             "available": [r.as_dict() for r in contribs.all_routes()]})
            return
        route, params = hit
        args: Dict[str, Any] = dict(query or {})
        if params:
            args.update(params)
        if body:
            args["body"] = body
        try:
            result = route.handler(args)
        except Exception as exc:  # 插件端点异常不该打挂壳层
            report_error("plugin.route", exc, plugin=str(route.plugin or ""))
            self._json(500, {"error": f"{type(exc).__name__}: {exc}",
                             "plugin": route.plugin})
            return
        if isinstance(result, tuple) and len(result) == 2:
            status, payload = int(result[0]), result[1]
        else:
            status, payload = 200, result
        if isinstance(payload, (dict, list)):
            self._json(status, payload if isinstance(payload, dict) else {"ok": True, "items": payload})
        else:
            self._bytes(status, str(payload).encode("utf-8"), "text/plain; charset=utf-8")

    def _plugin_asset(self, plugin: str, rel: str) -> None:
        """送出插件目录内的面板脚本。

        路径必须是该插件目录下的真实文件：先解析绝对路径，再校验它落在插件目录内
        （挡 `..` 与符号链接绕行）。只送文本类脚本，不送任意文件。
        """
        host = getattr(self.shell.app, "plugin_host", None) if self.shell.app else None
        base = getattr(host, "plugins_dir", None) if host is not None else None
        if base is None:
            self._json(404, {"error": "插件目录未接入"})
            return
        tracked = host.plugin_root(plugin) if host is not None else None
        root = Path(tracked).resolve() if tracked is not None else (Path(base) / plugin).resolve()
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self._json(403, {"error": "路径越出插件目录"})
            return
        if not target.is_file():
            self._json(404, {"error": "脚本不存在", "path": f"{plugin}/{rel}"})
            return
        suffix = target.suffix.lower()
        ctype = {
            ".js": "application/javascript; charset=utf-8",
            ".mjs": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".html": "text/html; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
        }.get(suffix)
        if ctype is None:
            self._json(415, {"error": f"不送该类型：{suffix or '(无扩展名)'}"})
            return
        try:
            body = target.read_bytes()
        except OSError as exc:
            self._json(500, {"error": f"{type(exc).__name__}"})
            return
        self._bytes(200, body, ctype)

