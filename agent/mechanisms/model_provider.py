# -*- coding: utf-8 -*-
"""模型提供者：协议 + Echo 假实现 + OpenAI 兼容真实适配。

- 协议（替换点）：`provider.stream(request) -> Iterator[StreamDelta]`；
  request 为 core.ports.LogicalRequest（messages + tools）。
- EchoProvider：MVP 假模型（内核循环验证，不依赖真实 API）；
- OpenAICompatibleProvider：真实适配（stdlib urllib）——SSE 流式解析、
  工具调用分片归并、末帧快照兜底、DeepSeek 错误映射、
  usage 结算。
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional
from uuid import uuid4

from agent.core.model_call import StreamDelta
from agent.core.tool_call import ToolCallRequest

_REASONING_FIELDS = ("reasoning_content", "reasoning")

# DeepSeek 官方 Error Codes：
# https://api-docs.deepseek.com/quick_start/error_codes
# 取值直接回给用户（见 `_http_error`）。500/503 说的是模型服务方，与本工程无关。
_DEEPSEEK_HTTP_HINTS: Dict[int, str] = {
    400: "请求格式无效，请检查请求体后重试。",
    401: "认证失败，请检查 API Key。",
    402: "余额不足，请充值后重试。",
    422: "请求参数无效，请检查参数后重试。",
    429: "请求过于频繁，请稍后再试。",
    500: "模型服务端错误，请稍后再试。",
    503: "模型服务端繁忙，请稍后再试。",
}


#: 发送前打印请求摘要（`AI_AGENT_LOG_REQUESTS=0` 可关）。
#: 默认开：视觉/多模态出问题时，"图片有没有进请求、是不是被剥了"必须一眼可见。
_LOG_REQUESTS = str(os.environ.get("AI_AGENT_LOG_REQUESTS", "1")).strip().lower() \
    not in ("0", "false", "no", "off")


class ModelRequestError(Exception):
    """模型请求失败（网络 / HTTP 错误）；detail 为面向用户的说明文本。"""

    def __init__(self, detail: str, *, status: int = 0) -> None:
        super().__init__(detail)
        self.detail = str(detail)
        self.status = int(status)


class ModelProvider:
    """提供者协议（替换点）：实现 `stream(request) -> Iterator[StreamDelta]`。"""

    def stream(self, request: Any) -> Iterator[StreamDelta]:
        raise NotImplementedError


class EchoProvider(ModelProvider):
    """假模型：首次请求发起 echo 工具调用；拿到工具结果后给出文本应答。

    用途：MVP 验证内核循环（模型→工具→回灌→再模型→结束），不依赖真实 API。
    """

    def stream(self, request: Any) -> Iterator[StreamDelta]:
        has_tool_result = any(m.get("role") == "tool" for m in request.messages)
        if not has_tool_result:
            yield StreamDelta(
                kind="tool_call",
                tool_call=ToolCallRequest(
                    call_id=f"call-{uuid4().hex[:8]}",
                    name="echo",
                    arguments={"text": "来自内核的第一次工具调用"},
                ),
            )
            return
        yield StreamDelta(kind="text", text="收到工具结果，")
        yield StreamDelta(kind="text", text="内核循环验证完成。")


# ── OpenAI 兼容真实适配──────────────────


def _chat_completions_url(base_url: str) -> str:
    """基址 → chat/completions 完整地址（幂等）。

    规则：去尾斜杠；已含 /chat/completions 原样；路径尾段为版本段（v1 / v4…）直拼
    /chat/completions；否则补 /v1/chat/completions（DeepSeek / 本地代理形态）。
    """
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        raise ModelRequestError("api_base_url 未配置。")
    if base.endswith("/chat/completions"):
        return base
    tail = base.rsplit("/", 1)[-1]
    if re.match(r"^v\d+", tail):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _parse_sse_lines(lines: Iterable[str]) -> Iterator[Dict[str, Any]]:
    """SSE 行流 → chunk 字典。

    只处理 data: 行；空行 / 其他字段（event: / id: / 注释）跳过；
    [DONE] 终止；JSON 解析失败的行跳过不中断。
    """
    for raw in lines:
        line = str(raw or "").rstrip("\r\n")
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data:
            continue
        if data == "[DONE]":
            return
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def _best_reasoning_field(message: Dict[str, Any]) -> str:
    """末帧消息中最长的推理字段。"""
    best = ""
    for field in _REASONING_FIELDS:
        val = message.get(field)
        if isinstance(val, str) and len(val) > len(best):
            best = val
    return best


def _tool_call_request(raw_id: str, name: str, arguments_json: str) -> ToolCallRequest:
    """(id, name, 参数 JSON 文本) → ToolCallRequest；参数解析失败降级为空参（同源）。"""
    text = str(arguments_json or "").strip() or "{}"
    try:
        args = json.loads(text)
    except json.JSONDecodeError:
        args = {}
    if not isinstance(args, dict):
        args = {}
    call_id = str(raw_id or "").strip() or f"call_{uuid4().hex[:12]}"
    return ToolCallRequest(call_id=call_id, name=str(name or "").strip(), arguments=args)


def _merge_tool_call_fragments(fragments: List[Dict[str, Any]]) -> List[ToolCallRequest]:
    """工具调用分片按 index 归并；name 为空的分片丢弃；输出按 index 升序。"""
    merged: Dict[int, Dict[str, str]] = {}
    for item in fragments:
        try:
            idx = int(item.get("index", 0) or 0)
        except (TypeError, ValueError):
            idx = 0
        cur = merged.setdefault(idx, {"id": "", "name": "", "arguments": ""})
        if item.get("id"):
            cur["id"] = str(item["id"])
        fn = item.get("function")
        if isinstance(fn, dict):
            name_part = fn.get("name")
            args_part = fn.get("arguments")
            if isinstance(name_part, str) and name_part:
                cur["name"] += name_part
            if isinstance(args_part, str) and args_part:
                cur["arguments"] += args_part
    out: List[ToolCallRequest] = []
    for idx in sorted(merged):
        tc = merged[idx]
        if not tc["name"]:
            continue
        out.append(_tool_call_request(tc["id"], tc["name"], tc["arguments"]))
    return out


def _tool_calls_from_snapshot_message(message: Dict[str, Any]) -> List[ToolCallRequest]:
    """末帧 message.tool_calls 快照兜底。"""
    raw = message.get("tool_calls")
    if not isinstance(raw, list):
        return []
    out: List[ToolCallRequest] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fn = item.get("function")
        if not isinstance(fn, dict):
            continue
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        args_raw = fn.get("arguments")
        if isinstance(args_raw, str):
            args_json = args_raw
        else:
            try:
                args_json = json.dumps(args_raw if args_raw is not None else {}, ensure_ascii=False)
            except (TypeError, ValueError):
                args_json = "{}"
        out.append(_tool_call_request(str(item.get("id") or ""), name, args_json))
    return out


def _assemble_stream_deltas(chunks: Iterable[Dict[str, Any]]) -> Iterator[StreamDelta]:
    """chunk 序列 → 流式增量。

    流中：正文 / 推理增量实时产出；工具分片累积。
    流末：正文为空取末帧快照；推理快照更长且为其前缀时补发差额；工具分片归并
    （为空则取快照）；usage 结算产出。
    """
    content_parts: List[str] = []
    reasoning_parts: List[str] = []
    tool_fragments: List[Dict[str, Any]] = []
    last_message: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, Any]] = None

    for chunk in chunks:
        u = chunk.get("usage")
        if isinstance(u, dict) and u:
            usage = u
        choices = chunk.get("choices") or []
        if not isinstance(choices, list) or not choices:
            continue
        ch0 = choices[0] if isinstance(choices[0], dict) else {}
        msg = ch0.get("message")
        if isinstance(msg, dict) and msg:
            last_message = msg
        delta = ch0.get("delta")
        if not isinstance(delta, dict):
            continue
        piece = delta.get("content")
        if isinstance(piece, str) and piece:
            content_parts.append(piece)
            yield StreamDelta(kind="text", text=piece)
        for field in _REASONING_FIELDS:
            rp = delta.get(field)
            if isinstance(rp, str) and rp:
                reasoning_parts.append(rp)
                yield StreamDelta(kind="reasoning", text=rp)
        tdelta = delta.get("tool_calls")
        if isinstance(tdelta, list):
            tool_fragments.extend(x for x in tdelta if isinstance(x, dict))

    content = "".join(content_parts)
    if last_message is not None and not content.strip():
        snap_content = last_message.get("content")
        if isinstance(snap_content, str) and snap_content:
            yield StreamDelta(kind="text", text=snap_content)

    reasoning = "".join(reasoning_parts)
    if last_message is not None:
        snap_reasoning = _best_reasoning_field(last_message)
        if (
            snap_reasoning
            and len(snap_reasoning) > len(reasoning)
            and snap_reasoning.startswith(reasoning)
        ):
            yield StreamDelta(kind="reasoning", text=snap_reasoning[len(reasoning):])

    merged = _merge_tool_call_fragments(tool_fragments)
    if not merged and last_message is not None:
        merged = _tool_calls_from_snapshot_message(last_message)
    for call in merged:
        yield StreamDelta(kind="tool_call", tool_call=call)

    if isinstance(usage, dict) and usage:
        yield StreamDelta(kind="usage", usage=usage)


def _upstream_error_message(body: str) -> str:
    """错误响应体中 message 字段的提取（≤800 字）。"""
    raw = (body or "").strip()
    if not raw:
        return ""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:800]
    if isinstance(obj, dict):
        err = obj.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()[:800]
        msg2 = obj.get("message")
        if isinstance(msg2, str) and msg2.strip():
            return msg2.strip()[:800]
    return raw[:800]


# ── 逻辑→线格式适配 ─────────────


def _to_wire_tool(tool: Dict[str, Any]) -> Dict[str, Any]:
    """逻辑工具（name / description / parameters 属性映射）→ OpenAI tools 项。

    parameters 为「参数名 → JSON Schema 片段」的属性映射；线格式要求
    {"type": "object", "properties": {...}}，此处补包装；已是线格式则原样透传。
    """
    if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
        return tool
    props = {
        str(k): dict(v) if isinstance(v, dict) else {}
        for k, v in dict(tool.get("parameters") or {}).items()
    }
    return {
        "type": "function",
        "function": {
            "name": str(tool.get("name") or ""),
            "description": str(tool.get("description") or ""),
            "parameters": {"type": "object", "properties": props},
        },
    }


def _to_wire_messages(messages: List[Any],
                      *,
                      keep_reasoning_from: Optional[int] = None) -> List[Dict[str, Any]]:
    """消息列表 → 线格式：assistant.tool_calls 扁平结构（id/name/arguments(dict)）
    包装为 OpenAI 形态（type=function / function.arguments 为 JSON 文本）；其余透传。

    `keep_reasoning_from` 给了下标（含）就**只保留该下标之后**的 `reasoning_content`。
    思维链是模型的中间产物：回传它就是让每次请求的输入里多一大段**必然未命中缓存**
    的内容（每轮几万 token，按未命中价计费），而且同一轮内每次请求的前缀都在变，
    缓存根本落不住。裁掉之后同一轮内前缀逐字节相同，缓存能吃满。
    实测丢弃它不会让 API 报错（带 `tools` 的思考模式同样接受）。
    """
    out: List[Dict[str, Any]] = []
    cut = None if keep_reasoning_from is None else max(0, int(keep_reasoning_from))
    for index, m in enumerate(messages):
        if not isinstance(m, dict):
            continue
        msg = dict(m)
        if cut is not None and index < cut:
            msg.pop("reasoning_content", None)
            msg.pop("reasoning", None)
        tcs = msg.get("tool_calls")
        if isinstance(tcs, list) and tcs:
            wire: List[Dict[str, Any]] = []
            for tc in tcs:
                if not isinstance(tc, dict):
                    continue
                if tc.get("type") == "function" and isinstance(tc.get("function"), dict):
                    wire.append(tc)
                    continue
                args = tc.get("arguments")
                if isinstance(args, str):
                    args_json = args or "{}"
                else:
                    try:
                        args_json = json.dumps(
                            args if args is not None else {}, ensure_ascii=False
                        )
                    except (TypeError, ValueError):
                        args_json = "{}"
                wire.append(
                    {
                        "id": str(tc.get("id") or ""),
                        "type": "function",
                        "function": {
                            "name": str(tc.get("name") or ""),
                            "arguments": args_json,
                        },
                    }
                )
            msg["tool_calls"] = wire
        out.append(msg)
    return out


#: 请求日志落盘位置（`AI_AGENT_LLM_LOG` 可改；留空则回落到 `%TEMP%\fan_agent_llm_requests.log`（**不是关闭**））。
_LLM_LOG_PATH = str(os.environ.get("AI_AGENT_LLM_LOG", "") or "").strip() or str(
    Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / "fan_agent_llm_requests.log"
)


def _append_request_log(line: str) -> None:
    """把请求摘要追加到日志文件（失败静默：日志不能反过来影响对话）。"""
    if not _LLM_LOG_PATH:
        return
    try:
        from datetime import datetime

        stamp = datetime.now().strftime("%H:%M:%S")
        with open(_LLM_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {line}\n")
    except OSError:
        pass
def describe_request(model: str, url: str, payload: Dict[str, Any]) -> str:
    """发送前把请求摘要成**一行**（`AI_AGENT_LOG_REQUESTS=1` 时打）。

    图片在 `content` 数组里与文本同层，消息条数反映不出它，所以单独列出：
    逐条给出"第几条消息、什么角色、带几张图、每张多少字符"。
    """
    msgs = payload.get("messages") or []
    img_rows: List[str] = []
    total_img_chars = 0
    for i, m in enumerate(msgs):
        content = m.get("content")
        if not isinstance(content, list):
            continue
        kinds = [p.get("type") for p in content if isinstance(p, dict)]
        if "image_url" not in kinds:
            continue
        sizes = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "image_url":
                url_value = p.get("image_url")
                url_value = (url_value.get("url") if isinstance(url_value, dict) else url_value) or ""
                sizes.append(len(str(url_value)))
                total_img_chars += len(str(url_value))
        img_rows.append(f"#{i}:{m.get('role')}×{len(sizes)}({[s for s in sizes]})")
    parts = [
        f"model={model}",
        f"messages={len(msgs)}",
        f"tools={len(payload.get('tools') or [])}",
        f"images={len(img_rows)}",
    ]
    if img_rows:
        parts.append("where=" + " ".join(img_rows))
        parts.append(f"img_chars={total_img_chars}")
    else:
        parts.append("**本轮请求不含任何图片**")
    try:
        parts.append(f"body_bytes={len(json.dumps(payload, ensure_ascii=False))}")
    except (TypeError, ValueError):
        pass
    return " ".join(parts)


class OpenAICompatibleProvider(ModelProvider):
    """OpenAI 兼容真实适配（SSE 流式；stdlib urllib）。

      时剥离并重试一次（部分网关不支持该字段）；
    - HTTP 错误：DeepSeek 基址 / 模型名命中时映射中文提示，否则原样返回；
    - 超时：默认 300s；
    - 逻辑→线格式：tools（属性映射）与 messages 内 tool_calls（扁平结构）发送前
      包装为 OpenAI 形态。
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 300.0,
        replay_history_reasoning: bool = False,
        # usage 取官方流末帧自带的那一份：`stream_options.include_usage` 只是让中间帧
        # 也带上 usage（官方文档），单次请求用它属于多余，本实现不下发。
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.base_url = str(base_url or "").strip()
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip()
        self.timeout = float(timeout)
        #: 历史轮次的思维链**默认不回传**（见 `_to_wire_messages`）。
        self.replay_history_reasoning = bool(replay_history_reasoning)
        self.extra_headers = {str(k): str(v) for k, v in dict(extra_headers or {}).items()}

    def stream(self, request: Any) -> Iterator[StreamDelta]:
        """发送流式请求并产出归一化增量（text / reasoning / tool_call / usage）。

        `request.model` 非空时**以它为准**（会话级选择），否则用实例默认 ——
        这样同一个 provider 实例能服务多个模型名。
        """
        model = str(getattr(request, "model", "") or "").strip() or self.model
        if not model:
            raise ModelRequestError("model 未配置。")
        if not self.api_key:
            raise ModelRequestError("api_key 未配置。")
        url = _chat_completions_url(self.base_url)
        messages = _to_wire_messages(
            getattr(request, "messages", None) or [],
            keep_reasoning_from=(None if self.replay_history_reasoning
                                 else getattr(request, "turn_start", None)))
        # ── 请求体：**逐键**──
        #
        # 请求体的键序与取值：
        #   {"model", "messages", "reasoning_effort", "thinking", "temperature", "tools"}
        #   再加一个会话身份 "user"（它对 provider 侧做 KV 缓存隔离）。
        #
        # **`thinking` 与 `temperature` 显式下发**：官方文档里
        #   `thinking:{type:enabled|disabled}` 控制思考模式，`temperature` 默认 1；
        #   这里显式下发 `{"type":"enabled"}` + `0.2`。采样温度直接决定"同一个请求
        #   会不会给出不同结论"，不下发就等于每次都用默认 1.0（更随机）。
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "thinking": {"type": "enabled"},
            "temperature": 0.2,
            "stream": True,
        }
        tools = [t for t in (getattr(request, "tools", None) or []) if isinstance(t, dict)]
        if tools:
            payload["tools"] = [_to_wire_tool(t) for t in tools]
            # 每次带工具都同时下发 `tool_choice`（官方默认值也是 auto，显式下发更明确）。
            payload["tool_choice"] = "auto"
        # 推理档位：**取自请求**（`LogicalRequest.effort`，由会话级
        # 设置解析而来）。官方取值 none/low/high/max —— 缺省回落 high，但非空值**如实
        # 下发**（不把 `low` 静默吞成 `high`）；本地模型整键剥掉。
        #
        # `reasoning_effort` 由请求驱动、不写死：写死会让「思考 · High / Max」
        # 档位失效（选 Max 发出去的仍是 high）。`LogicalRequest` 契约 docstring 规定
        # provider 侧把它放进请求体，`tests/test_protocol_contract.py` 有断言守着这一点。
        effort = str(getattr(request, "effort", "") or "").strip().lower()
        if not effort:
            effort = "high"
        if self._is_local_model(model):
            # 本地模型（浏览器页面）不支持 thinking / reasoning_effort。
            payload.pop("thinking", None)
            payload.pop("temperature", None)
        else:
            payload["reasoning_effort"] = effort
        # 会话身份（同一写法：过滤成官方 `user` 允许的字符集再下发）。
        uid = re.sub(r"[^a-zA-Z0-9_-]", "", str(getattr(request, "conversation_id", "") or ""))[:512]
        if uid:
            payload["user"] = uid
        if _LOG_REQUESTS:
            # 发送前留痕：出问题时第一件要回答的是"图片有没有进请求"。
            # **同时写 stderr 与文件**：控制台可能被重定向/管道吞掉，
            # 而"图片有没有发出去"这种证据不能只寄望于终端能看到。
            line = f"[llm→] url={url} {describe_request(model, url, payload)}"
            print(line, file=sys.stderr, flush=True)
            _append_request_log(line)

        yield from _assemble_stream_deltas(self._post_stream(url, payload))

    def _is_local_model(self, model: str = "") -> bool:
        """本地模型（浏览器页面）不支持 tools / thinking / reasoning_effort。

        `model` 为空时看实例默认 —— 判定跟着**本次真正要用的**模型走：用实例默认去判
        另一个模型，会把云端模型请求的 `reasoning_effort` 误剥掉。
        """
        name = (str(model or "").strip() or self.model).strip().lower()
        return name == "local-model" or name.startswith("local-model")

    # ── HTTP 传输────────────────────────────

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        headers.update(self.extra_headers)
        return headers

    def _post_stream(self, url: str, payload: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            try:
                detail_body = exc.read().decode("utf-8", errors="replace")
            except Exception as read_exc:
                print(
                    f"[model_provider] 读 HTTP 错误体失败: "
                    f"{type(read_exc).__name__}: {read_exc}",
                    file=sys.stderr, flush=True,
                )
                detail_body = ""
            raise self._http_error(exc.code, detail_body) from exc
        except urllib.error.URLError as exc:
            raise ModelRequestError(f"网络错误：{getattr(exc, 'reason', exc)}") from exc
        try:
            lines = (raw.decode("utf-8", errors="replace") for raw in resp)
            yield from _parse_sse_lines(lines)
        finally:
            try:
                resp.close()
            except Exception:
                pass

    def _http_error(self, status: int, body: str) -> ModelRequestError:
        plain = f"HTTP {status}: {body[:8000]}" if (body or "").strip() else f"HTTP {status}"
        if not self._is_deepseek():
            return ModelRequestError(plain, status=status)
        hint = _DEEPSEEK_HTTP_HINTS.get(int(status))
        if not hint:
            return ModelRequestError(plain, status=status)
        upstream = _upstream_error_message(body)
        detail = f"{hint} 接口返回：{upstream}" if upstream and upstream not in hint else hint
        return ModelRequestError(detail, status=status)

    def _is_deepseek(self) -> bool:
        return "deepseek" in self.base_url.lower() or self.model.lower().startswith("deepseek")
