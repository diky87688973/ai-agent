# -*- coding: utf-8 -*-
"""GitHub API 工具：github_api——11 个远程操作动作 + 设备流登录 + token 链。

token 链：GH_TOKEN / GITHUB_TOKEN 环境变量 ＞ PROJECT_ROOT/gh_token.txt（及 DATA_ROOT 备用位）；
无 token → LoginRequired（附 action=login_required）；登录为长阻塞动作（上限约 10 分钟，含兜底输出）。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from agent.capabilities.registry import ToolPlugin
from agent.config import PROJECT_ROOT

CLIENT_ID = "178c6fc778ccc68e1d6a"  # GitHub CLI 官方公开 Client ID（设备流）
API_BASE = "https://api.github.com"
DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
HTTP_TIMEOUT = 15
LOGIN_SCOPE = "repo,read:org,admin:public_key"


class GitHubError(RuntimeError):
    """GitHub 操作失败：结构化载荷（type / message / 附加字段）随 data 透传。"""

    def __init__(self, message: str, err_type: str = "GitHubError", **extra: Any) -> None:
        super().__init__(message)
        self.data = {"type": err_type, "message": message, **extra}


def _http_json(
    url: str,
    *,
    method: str = "GET",
    headers: Dict[str, str] = None,
    json_body: Any = None,
    form_body: Dict[str, str] = None,
    timeout: float = HTTP_TIMEOUT,
) -> Any:
    """HTTP 请求并解析 JSON（标准库 urllib）；HTTP 错误携带响应体明细。"""
    hdrs = {str(k): str(v) for k, v in (headers or {}).items()}
    body_bytes = None
    if json_body is not None:
        body_bytes = json.dumps(json_body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json; charset=utf-8")
    elif form_body is not None:
        body_bytes = urllib.parse.urlencode(form_body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")

    req = urllib.request.Request(url, data=body_bytes, headers=hdrs, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as ex:
        detail = ""
        try:
            detail = ex.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(ex.reason)
        raise RuntimeError(f"HTTP {ex.code}: {detail or ex.reason}") from ex
    except urllib.error.URLError as ex:
        raise RuntimeError(str(ex.reason)) from ex

    if not raw.strip():
        return {}
    return json.loads(raw)


def _token_candidates() -> List[Path]:
    candidates = [PROJECT_ROOT / "gh_token.txt"]
    data_root = os.environ.get("AGENT_DATA_ROOT", "").strip() or os.environ.get("DATA_ROOT", "").strip()
    if data_root:
        candidates.append(Path(data_root) / "gh_token.txt")
    return candidates


def _find_token() -> str:
    """查找 GitHub Token：GH_TOKEN / GITHUB_TOKEN 环境变量 ＞ gh_token.txt 候选位。"""
    env = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if env.strip():
        return env.strip()
    for p in _token_candidates():
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8").strip()
            except OSError:
                continue
    return ""


def _save_token(token: str) -> None:
    for p in _token_candidates():
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(token, encoding="utf-8")
        except Exception:
            pass


def _api(repo: str, path: str, method: str = "GET", data: Any = None) -> Dict[str, Any]:
    """带认证的 GitHub REST 调用（repo 形如 owner/repo）。"""
    token = _find_token()
    if not token:
        raise GitHubError(
            "GitHub Token 未找到。请执行 action=login",
            err_type="LoginRequired",
            action="login_required",
        )
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
    url = f"{API_BASE}/repos/{repo}{path}"
    return _http_json(url, method=method, headers=headers, json_body=data if method in ("POST", "PUT", "PATCH") else None)


def _cmd_login() -> Dict[str, Any]:
    """设备流登录：输出验证码并轮询（最长约 10 分钟），成功后保存 token。"""
    data = _http_json(
        DEVICE_CODE_URL,
        method="POST",
        headers={"Accept": "application/json"},
        form_body={"client_id": CLIENT_ID, "scope": LOGIN_SCOPE},
    )
    user_code = str(data["user_code"])
    device_code = str(data["device_code"])
    verification_uri = str(data["verification_uri"])
    interval = int(data.get("interval", 5))

    print(f"[github_api] 验证码: {user_code}")
    print(f"[github_api] 打开: {verification_uri}，输入验证码后等待自动完成...")
    try:
        import webbrowser

        webbrowser.open(verification_uri)
    except Exception:
        pass

    for _attempt in range(120):
        time.sleep(interval)
        result = _http_json(
            ACCESS_TOKEN_URL,
            method="POST",
            headers={"Accept": "application/json"},
            form_body={
                "client_id": CLIENT_ID,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        if "access_token" in result:
            _save_token(str(result["access_token"]))
            return {
                "message": "登录成功！Token 已保存。",
                "user_code": user_code,
                "verification_uri": verification_uri,
                "saved_to": str(PROJECT_ROOT / "gh_token.txt"),
            }
        error = str(result.get("error") or "")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error == "expired_token":
            raise GitHubError("验证码已过期，请重新运行。", err_type="ExpiredToken", user_code=user_code)
        raise GitHubError(str(result), err_type="OAuthError", user_code=user_code)
    raise GitHubError("等待超时（10 分钟）。", err_type="TimeoutError", user_code=user_code)


class GithubApiTool(ToolPlugin):
    """GitHub 远程操作。"""

    name = "github_api"
    description = (
        "GitHub 远程操作：login / get_repo / list_issues / create_issue / list_releases / set_topics / "
        "list_prs / get_pr / create_pr / close_pr / update_pr。"
    )
    parameters = {
        "action": {"type": "string", "description": "动作名（见描述；login 走设备流）"},
        "repo": {"type": "string", "description": "仓库 owner/repo（login 之外必填）"},
        "title": {"type": "string", "description": "标题（create_issue / create_pr / update_pr）"},
        "body": {"type": "string", "description": "正文（create_issue / create_pr / update_pr）"},
        "state": {"type": "string", "description": "状态筛选（list_issues / list_prs 默认 open；update_pr 可改）"},
        "topics": {"type": "string", "description": "话题列表，逗号分隔（set_topics）"},
        "pr_number": {"type": "integer", "description": "PR 编号（get_pr / close_pr / update_pr）"},
        "head": {"type": "string", "description": "源分支（create_pr，如 fork:branch）"},
        "base": {"type": "string", "description": "目标分支（create_pr，如 main）"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        action = str(arguments.get("action") or "").strip().lower()
        repo = str(arguments.get("repo") or "").strip().strip("/")
        if not action:
            raise GitHubError("action 必填", err_type="ValueError")
        if action != "login" and not repo:
            raise GitHubError("repo 必填，格式: owner/repo", err_type="ValueError")

        if action == "login":
            return _cmd_login()

        state = str(arguments.get("state") or "open").strip() or "open"
        try:
            pr_number = int(arguments.get("pr_number") or 0)
        except (TypeError, ValueError):
            raise GitHubError("pr_number 须为整数", err_type="ValueError")

        if action == "get_repo":
            return _api(repo, "")
        if action == "list_issues":
            return _api(repo, f"/issues?state={state}&per_page=20")
        if action == "create_issue":
            return _api(
                repo,
                "/issues",
                "POST",
                {"title": str(arguments.get("title") or ""), "body": str(arguments.get("body") or "")},
            )
        if action == "list_releases":
            return _api(repo, "/releases?per_page=10")
        if action == "set_topics":
            topics_list = [t.strip() for t in str(arguments.get("topics") or "").split(",") if t.strip()]
            return _api(repo, "/topics", "PUT", {"names": topics_list})
        if action == "list_prs":
            return _api(repo, f"/pulls?state={state}&per_page=20")
        if action == "get_pr":
            return _api(repo, f"/pulls/{pr_number}")
        if action == "create_pr":
            return _api(
                repo,
                "/pulls",
                "POST",
                {
                    "title": str(arguments.get("title") or ""),
                    "head": str(arguments.get("head") or ""),
                    "base": str(arguments.get("base") or ""),
                    "body": str(arguments.get("body") or ""),
                },
            )
        if action == "close_pr":
            return _api(repo, f"/pulls/{pr_number}", "PATCH", {"state": "closed"})
        if action == "update_pr":
            payload: Dict[str, Any] = {}
            if arguments.get("title") is not None:
                payload["title"] = str(arguments.get("title"))
            if arguments.get("body") is not None:
                payload["body"] = str(arguments.get("body"))
            if arguments.get("state") is not None:
                payload["state"] = str(arguments.get("state"))
            if not payload:
                raise GitHubError("至少提供一个要更新的字段", err_type="ValueError")
            return _api(repo, f"/pulls/{pr_number}", "PATCH", payload)
        raise GitHubError(f"未知 action: {action}", err_type="ValueError")


def build() -> GithubApiTool:
    """构造 github_api 插件。"""
    return GithubApiTool()
