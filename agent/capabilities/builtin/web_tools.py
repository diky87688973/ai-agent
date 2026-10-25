# -*- coding: utf-8 -*-
"""网络工具：web_fetch / web_fetch_render。

- web_fetch：urllib 抓取 + HTML 转纯文本 + 验收（min_chars / require_keywords）+ 结构化错误码；
- web_fetch_render：Playwright 渲染抓取（可选依赖，缺失时给安装提示）。
"""
from __future__ import annotations

import html as _html
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.capabilities.registry import ToolPlugin
from agent.core.error_report import report_error

BUILTIN_TIMEOUT_SEC = 20
BUILTIN_MAX_CHARS = 20000
BUILTIN_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
RENDER_MAX_CHARS = 100000
RENDER_WAIT_SEC = 3.0


class WebFetchError(RuntimeError):
    """web_fetch 结构化错误：code / hint / retryable 随 data 透传。"""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        hint: str = "",
        retryable: bool = False,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        payload: Dict[str, Any] = dict(data or {})
        payload.update({"code": code, "type": "WebFetchError", "message": message, "hint": hint, "retryable": retryable})
        self.data = payload


def _strip_html_to_text(raw_html: str) -> str:
    """HTML → 纯文本：剥离 script/style/noscript，br/p 转换行，实体反转义，空白折叠。"""
    s = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw_html)
    s = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", s)
    s = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</p>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = _html.unescape(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t\f\v]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _parse_keywords(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    out: List[str] = []
    for x in str(raw).split(","):
        k = x.strip()
        if k and k not in out:
            out.append(k)
    return out


def _ascii_safe_url(url: str) -> str:
    """含非 ASCII 主机名的 URL 转 IDNA，避免 urllib 按 latin-1 编码请求行失败。"""
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    if not host:
        return url
    try:
        host.encode("ascii")
        return url
    except UnicodeEncodeError as exc:
        report_error("agent.capabilities.builtin.web_tools._ascii_safe_url", exc)
    try:
        host_ascii = host.encode("idna").decode("ascii")
    except Exception as exc:
        report_error("agent.capabilities.builtin.web_tools._ascii_safe_url", exc)
        return url
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += ":" + parsed.password
        userinfo += "@"
    port = parsed.port
    netloc = userinfo + host_ascii + (f":{port}" if port else "")
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def _fetch_url(url: str, timeout_sec: int, max_chars: int, user_agent: str) -> Dict[str, Any]:
    safe_url = _ascii_safe_url(url)
    req = urllib.request.Request(safe_url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        final_url = resp.geturl()
        status = getattr(resp, "status", 200)
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.read()

    encoding = "utf-8"
    m = re.search(r"charset=([A-Za-z0-9_\-]+)", content_type, flags=re.I)
    if m:
        encoding = m.group(1)
    try:
        html_text = raw.decode(encoding, errors="replace")
    except LookupError:
        html_text = raw.decode("utf-8", errors="replace")

    text = _strip_html_to_text(html_text)
    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    title = ""
    mt = re.search(r"(?is)<title[^>]*>(.*?)</title>", html_text)
    if mt:
        title = _html.unescape(mt.group(1)).strip()

    return {
        "url": url,
        "request_url": safe_url,
        "final_url": final_url,
        "status": int(status),
        "content_type": content_type,
        "title": title,
        "text": text,
        "text_len": len(text),
        "truncated": truncated,
    }


def _run_hard_checks(text: str, *, min_chars: Optional[int], keywords: List[str]) -> Tuple[bool, Dict[str, Any]]:
    checks: Dict[str, Any] = {"min_chars": min_chars, "require_keywords": keywords, "hit_keywords": []}
    if min_chars is not None and len(text) < min_chars:
        checks["failed"] = "min_chars"
        checks["actual_chars"] = len(text)
        return False, checks
    if keywords:
        lower = text.lower()
        hit = [k for k in keywords if k.lower() in lower]
        checks["hit_keywords"] = hit
        if not hit:
            checks["failed"] = "require_keywords"
            return False, checks
    checks["failed"] = None
    checks["actual_chars"] = len(text)
    return True, checks


class WebFetchTool(ToolPlugin):
    """抓取网页并提取纯文本。"""

    name = "web_fetch"
    label = "抓取网页内容"
    icon = "🌐"
    description = "抓取网页（urllib 无第三方依赖）并提取纯文本；支持超时、长度限制、min_chars/require_keywords 验收与落盘。"
    parameters = {
        "url": {"type": "string", "description": "http/https 完整 URL"},
        "timeout_sec": {"type": "integer", "description": "连接+读响应总超时秒数（默认 20）"},
        "max_chars": {"type": "integer", "description": "正文最大字符数（默认 20000）"},
        "user_agent": {"type": "string", "description": "自定义 User-Agent（缺省内置浏览器串）"},
        "out_file": {"type": "string", "description": "若指定，将正文写入该路径（仍返回元信息）"},
        "min_chars": {"type": "integer", "description": "正文长度下限，不足则失败"},
        "require_keywords": {"type": "string", "description": "逗号分隔关键词，正文须至少命中其一"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            url = str(arguments.get("url") or "").strip()
            if not url:
                raise WebFetchError("url 不能为空", code="E_INVALID_INPUT", hint="提供 http/https 完整 URL")
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ("http", "https"):
                raise WebFetchError("只支持 http/https URL", code="E_INVALID_INPUT", hint="检查 URL 协议头")
            raw_timeout = arguments.get("timeout_sec")
            raw_max = arguments.get("max_chars")
            try:
                timeout_sec = int(raw_timeout) if raw_timeout is not None and str(raw_timeout).strip() != "" else BUILTIN_TIMEOUT_SEC
                max_chars = int(raw_max) if raw_max is not None and str(raw_max).strip() != "" else BUILTIN_MAX_CHARS
            except (TypeError, ValueError):
                raise WebFetchError("timeout_sec / max_chars 须为整数", code="E_INVALID_INPUT", hint="检查参数类型")
            if timeout_sec <= 0:
                raise WebFetchError("timeout_sec 必须 > 0", code="E_INVALID_INPUT", hint="检查参数取值")
            if max_chars <= 0:
                raise WebFetchError("max_chars 必须 > 0", code="E_INVALID_INPUT", hint="检查参数取值")
            min_chars: Optional[int] = None
            raw_min = arguments.get("min_chars")
            if raw_min is not None and str(raw_min).strip() != "":
                try:
                    min_chars = int(raw_min)
                except (TypeError, ValueError):
                    raise WebFetchError("min_chars 须为整数", code="E_INVALID_INPUT", hint="检查参数类型")
                if min_chars <= 0:
                    raise WebFetchError("min_chars 必须 > 0", code="E_INVALID_INPUT", hint="检查参数取值")
            ua = str(arguments.get("user_agent") or "").strip() or BUILTIN_USER_AGENT

            data = _fetch_url(url, timeout_sec, max_chars, ua)
            keywords = _parse_keywords(arguments.get("require_keywords"))
            passed, checks = _run_hard_checks(str(data.get("text", "")), min_chars=min_chars, keywords=keywords)
            data["checks"] = checks

            out_f = str(arguments.get("out_file") or "").strip()
            if out_f:
                fp = Path(out_f)
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(str(data.get("text", "")), encoding="utf-8")
                data["out_file"] = str(fp)
                data["written"] = True
            else:
                data["written"] = False

            if not passed:
                raise WebFetchError(
                    f"内容验收失败: {checks.get('failed')}",
                    code="E_ACCEPTANCE",
                    hint="调整 URL / max_chars 或放宽 min_chars/require_keywords 限制",
                    retryable=True,
                    data=data,
                )
            return data
        except WebFetchError:
            raise
        except urllib.error.HTTPError as e:
            raise WebFetchError(
                f"HTTPError {e.code}: {e.reason}",
                code="E_HTTP_STATUS",
                hint="检查 URL 是否正确或目标服务可用",
                retryable=500 <= int(e.code) < 600,
            )
        except urllib.error.URLError as e:
            raise WebFetchError(f"网络错误: {e.reason}", code="E_NETWORK", hint="检查网络连接或代理设置", retryable=True)
        except Exception as e:
            report_error("agent.capabilities.builtin.web_tools.WebFetchTool.execute", e)
            raise WebFetchError(str(e), code="E_INVALID_INPUT", hint="检查 URL/参数是否正确")


class WebFetchRenderTool(ToolPlugin):
    """JS 渲染抓取（可选依赖 Playwright）。"""

    name = "web_fetch_render"
    label = "抓取网页内容"
    icon = "🌐"
    description = "用 Playwright 无头浏览器抓取 JS 渲染后的页面（可选依赖；缺失时给出安装提示）。"
    parameters = {
        "url": {"type": "string", "description": "目标网页 URL"},
        "wait_sec": {"type": "string", "description": "等待 JS 渲染的秒数（默认 3）"},
        "max_chars": {"type": "integer", "description": "正文最大字符数（默认 100000）"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        url = str(arguments.get("url") or "").strip()
        if not url:
            raise ValueError("缺少 url 参数")
        raw_mc = arguments.get("max_chars")
        try:
            wait_sec = float(arguments.get("wait_sec")) if arguments.get("wait_sec") is not None else RENDER_WAIT_SEC
            max_chars = int(raw_mc) if raw_mc is not None and str(raw_mc).strip() != "" else RENDER_MAX_CHARS
        except (TypeError, ValueError) as e:
            raise ValueError(f"wait_sec / max_chars 必须为数字: {e}")
        if max_chars <= 0:
            raise ValueError("max_chars 必须 > 0")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "缺少 Playwright 依赖。安装命令：pip install playwright；然后 python -m playwright install chromium"
            )
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=BUILTIN_USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                    locale="zh-CN",
                )
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=30000)
                if wait_sec > 0:
                    time.sleep(wait_sec)
                title = page.title()
                body_text = page.inner_text("body") or ""
                html = page.content()
                meta_desc = ""
                try:
                    meta_desc = page.get_attribute("meta[name=description]", "content") or ""
                except Exception as exc:
                    # 旁路，刻意吞掉：meta 描述是抓取时的可选信息，
                    # 页面没有这个标签（或选择器不合法）就拿空串，不影响正文抓取。
                    report_error("agent.capabilities.builtin.web_tools.WebFetchRenderTool.execute", exc)
                browser.close()
            if len(body_text) > max_chars:
                body_text = body_text[:max_chars] + "\n...(截断)"
            return {
                "url": url,
                "title": title,
                "text": body_text,
                "html_len": len(html),
                "meta_description": meta_desc,
            }
        except Exception as e:
            report_error("agent.capabilities.builtin.web_tools.WebFetchRenderTool.execute", e)
            raise RuntimeError(f"渲染抓取失败: {e}")


def build_plugins() -> List[ToolPlugin]:
    """构造本组工具（web_fetch / web_fetch_render）。"""
    return [WebFetchTool(), WebFetchRenderTool()]
