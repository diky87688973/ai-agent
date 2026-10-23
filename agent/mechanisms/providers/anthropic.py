# -*- coding: utf-8 -*-
"""Anthropic 原生 Messages API 适配。

与 OpenAI 兼容适配的差别集中在三处：

1. 消息形状：system 提到顶层；工具结果是 `role:"user"` 里的 `tool_result` 块；
   assistant 的工具调用是 `tool_use` 块（参数是对象，不是 JSON 文本）。
2. extended thinking：推理增量是 `thinking_delta`，签名随块回传；同一轮里带工具的
   后续请求必须把 thinking 块（含 `signature`）原样带回，否则会被 API 拒绝。
   签名由内核 `provider_meta` 透传（见 `docs/plan/multi-model.md` 第 8 节）。
3. 必填参数：`max_tokens` 必填，且必须大于 thinking 预算。

适配器只产出 `StreamDelta`；内核不认识 Anthropic 的线格式、块类型或签名。

`LogicalRequest.effort`（High / Max）对本适配器不生效：本适配器不下发任何
强度参数。两家的控制方式不同——Anthropic 官方用 `thinking.budget_tokens`（本适配器
按条目的 `thinking_budget_tokens` 下发），DeepSeek 兼容层忽略 `budget_tokens`、
改用 `output_config.effort`，而 Anthropic 官方会拒绝 `output_config` 这个未知字段。
同一个适配器要同时服务两家，就只能不下发强度：DeepSeek 侧取服务端默认（high）。
需要按档位调深度时用同一模型的 openai 协议条目（那里下发 `reasoning_effort`）。
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Tuple

from agent.core.error_report import report_error
from agent.core.model_call import StreamDelta
from agent.core.tool_call import ToolCallRequest
from agent.mechanisms.providers.base import ModelProvider, ModelRequestError
from agent.mechanisms.providers.debug import LOG_REQUESTS
from agent.mechanisms.providers.sse import stream_with_timeout
from agent.mechanisms.providers.tool_schema import tool_parameters

#: HTTP 状态 → 面向用户的提示。与 DeepSeek 的表分开：同一状态码在两家的含义
#: 不完全一致（例如 529 只有 Anthropic 侧常见）。
_HTTP_HINTS: Dict[int, str] = {
    400: "请求参数无效，请检查模型与参数配置。",
    401: "认证失败，请检查 API Key。",
    403: "无访问权限，请检查 Key 的权限范围。",
    404: "模型或接口不存在，请检查 base_url 与模型 id。",
    413: "请求体过大，请减少历史图片或上下文。",
    429: "请求过于频繁，请稍后再试。",
    500: "模型服务端错误，请稍后再试。",
    529: "模型服务过载，请稍后再试。",
}

#: thinking 预算的下限（Anthropic 要求 `budget_tokens >= 1024`）。
_MIN_THINKING_BUDGET = 1024

#: `provider_meta` 里 thinking 块的落点：`{"anthropic": {"thinking_blocks": [...]}}`
_META_VENDOR = "anthropic"
_META_BLOCKS = "thinking_blocks"


# ── 地址与错误 ──────────────────────────────


def messages_url(base_url: str) -> str:
    """基址 → Messages 端点。

    支持三种写法：已带 `/messages` 原样；以 `/v1` 结尾补 `/messages`；
    其它补 `/v1/messages`（与 OpenAI 适配的基址推导同风格）。
    """
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/messages"):
        return base
    if base.endswith("/v1"):
        return base + "/messages"
    return base + "/v1/messages"


def _upstream_message(body: str) -> str:
    """从错误体里取 `error.message`（截断到 800 字符）。"""
    try:
        obj = json.loads(body or "")
    except (TypeError, ValueError):
        # 上游错误体不保证是 JSON；这里只取错误文案，取不到就当没有。
        return ""
    err = obj.get("error") if isinstance(obj, dict) else None
    text = err.get("message") if isinstance(err, dict) else None
    if not isinstance(text, str):
        return ""
    return text.strip()[:800]


def _warn(message: str) -> None:
    """诊断必须留痕：只吞不记等于把配置问题埋掉。"""
    print(f"[providers.anthropic] {message}", file=sys.stderr, flush=True)


# ── 消息折叠（纯函数，便于单测）──────────────


def _system_text(messages: List[Any]) -> str:
    """把所有 system 消息的正文按出现顺序拼起来（空行分隔）。"""
    parts: List[str] = []
    for m in messages:
        if isinstance(m, dict) and str(m.get("role") or "") == "system":
            text = m.get("content")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n\n".join(parts)


def _meta_blocks(m: Mapping[str, Any]) -> List[Dict[str, str]]:
    """取一条 assistant 消息里的 thinking 块；形状不对按"没有"处理。"""
    meta = m.get("provider_meta")
    vendor = meta.get(_META_VENDOR) if isinstance(meta, dict) else None
    blocks = vendor.get(_META_BLOCKS) if isinstance(vendor, dict) else None
    if not isinstance(blocks, list):
        return []
    out: List[Dict[str, str]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        thinking = block.get("thinking")
        signature = block.get("signature")
        # 文本允许为空：有的模型（如旧名 deepseek-chat）思考块正文就是空串，
        # 但块本身仍必须原样回传（见下方 `_consume_block_stop` 的同一条约束）。
        if isinstance(thinking, str) and isinstance(signature, str) and signature:
            out.append({"thinking": thinking, "signature": signature})
    return out


def strip_stale_thinking(messages: List[Any], turn_start: Optional[int]) -> List[Any]:
    """只保留本轮（下标 >= `turn_start`）的 thinking 块。

    跨用户轮重放旧签名没有意义，还可能因为签名过期被拒。缺 `signature` 的块同样丢弃
    并留一条降级日志——留着它一定会被 API 拒绝，丢块最多损失一点推理上下文。
    """
    cut = max(0, int(turn_start or 0))
    out: List[Any] = []
    dropped = 0
    for index, m in enumerate(messages):
        if not isinstance(m, dict):
            continue
        item = dict(m)
        raw = item.get("provider_meta")
        if isinstance(raw, dict):
            vendor = raw.get(_META_VENDOR)
            if isinstance(vendor, dict):
                blocks = vendor.get(_META_BLOCKS)
                if index < cut:
                    # 跨轮：整段 thinking 不重放，provider_meta 也不再下发
                    vendor = {k: v for k, v in vendor.items() if k != _META_BLOCKS}
                elif isinstance(blocks, list):
                    kept = _meta_blocks(item)
                    dropped += max(0, len(blocks) - len(kept))
                    vendor = {k: v for k, v in vendor.items() if k != _META_BLOCKS}
                    if kept:
                        vendor[_META_BLOCKS] = kept
                item["provider_meta"] = {**raw, _META_VENDOR: vendor}
        out.append(item)
    if dropped:
        _warn(f"丢弃了 {dropped} 个缺 signature 的 thinking 块（无法安全重放）")
    return out


def _assistant_tool_ids(messages: List[Any]) -> Tuple[Dict[int, List[str]], Dict[str, List[str]]]:
    """给每次 `tool_use` 分配唯一 id，并登记 tool 消息的消费队列。

    重复 id 会让 API 无法配对（同一 id 出现两次），从第二次起追加 `_2`、`_3`。
    返回 `(消息下标 → 该消息内 tool_use 的新 id 列表, 旧 id → 新 id 队列)`。
    """
    per_message: Dict[int, List[str]] = {}
    queues: Dict[str, List[str]] = {}
    seen: Dict[str, int] = {}
    for index, m in enumerate(messages):
        if not isinstance(m, dict) or str(m.get("role") or "") != "assistant":
            continue
        calls = m.get("tool_calls")
        if not isinstance(calls, list):
            continue
        ids: List[str] = []
        for call in calls:
            if not isinstance(call, dict):
                continue
            old = str(call.get("id") or "").strip()
            if not old or not str(call.get("name") or "").strip():
                # 无 id / 无名调用不会产出 tool_use，也不能占用 id 序号，
                # 否则同一消息里的后续调用会与 tool_result 队列错位。
                continue
            seen[old] = seen.get(old, 0) + 1
            new = old if seen[old] == 1 else f"{old}_{seen[old]}"
            ids.append(new)
            queues.setdefault(old, []).append(new)
        per_message[index] = ids
    return per_message, queues


def drop_dangling_tool_results(messages: List[Any]) -> List[Any]:
    """丢掉没有对应 `tool_use` 的 tool 消息。

    悬空结果会被 API 拒绝，且是整段会话打不开——比丢一条结果严重得多。
    """
    known = set()
    for m in messages:
        if not isinstance(m, dict) or str(m.get("role") or "") != "assistant":
            continue
        calls = m.get("tool_calls")
        if not isinstance(calls, list):
            continue
        for call in calls:
            if isinstance(call, dict) and str(call.get("id") or "").strip():
                known.add(str(call["id"]).strip())
    out: List[Any] = []
    for m in messages:
        if isinstance(m, dict) and str(m.get("role") or "") == "tool":
            cid = str(m.get("tool_call_id") or "").strip()
            if cid not in known:
                continue
        out.append(m)
    return out


def _image_block(url: str) -> Optional[Dict[str, Any]]:
    """图片地址 → Anthropic image 块：`data:` 走 base64，http(s) 走 url 源。

    DeepSeek 兼容层的 `source.type` 支持 `base64` 与 `url`（Anthropic 官方也支持
    这两种）。只认 `data:` 会让粘贴的图片链接在 anthropic 条目上静默消失，
    而同一张图在 openai 条目里照常发送 —— 同一份输入在两个协议下不一致。
    """
    text = str(url or "").strip()
    if text.startswith(("http://", "https://")):
        return {"type": "image", "source": {"type": "url", "url": text}}
    if not text.startswith("data:"):
        return None
    head, _, data = text[5:].partition(",")
    if not data or ";base64" not in head:
        return None
    media = head.split(";")[0].strip()
    if not media:
        return None
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}


def _user_blocks(content: Any) -> List[Dict[str, Any]]:
    """用户消息正文 → 块数组（字符串或多模态数组都认）。"""
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    if not isinstance(content, list):
        return []
    out: List[Dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            text = part.get("text")
            if isinstance(text, str) and text:
                out.append({"type": "text", "text": text})
            continue
        if part.get("type") == "image_url":
            raw = part.get("image_url")
            url = raw.get("url") if isinstance(raw, dict) else raw
            block = _image_block(str(url or ""))
            if block:
                out.append(block)
    return out


def _tool_result_content(content: Any) -> Any:
    """工具结果正文：文本原样；多模态数组转成 Anthropic 块；空内容补占位。

    `content` 为空数组会被 API 拒绝，所以"没有输出"也必须有一个占位文本。
    """
    if isinstance(content, str) and content:
        return content
    if isinstance(content, list):
        blocks = _user_blocks(content)
        if blocks:
            return blocks
    return "（工具没有返回内容）"


def _to_anthropic_messages(messages: List[Any], turn_start: Optional[int],
                           *, keep_thinking: bool = True) -> List[Dict[str, Any]]:
    """逻辑消息 → Anthropic 线格式消息（system 另行提取，不在这里）。

    `keep_thinking=False` 时一条 thinking 块都不下发：思考关闭时带着思考块，
    官方端点会拒（"thinking is not enabled"）；DeepSeek 兼容层虽然忽略，
    也没有重放的意义。
    """
    cleaned = drop_dangling_tool_results(strip_stale_thinking(messages, turn_start))
    ids_per_message, id_queues = _assistant_tool_ids(cleaned)
    out: List[Dict[str, Any]] = []

    def _push(role: str, blocks: List[Dict[str, Any]]) -> None:
        if not blocks:
            return
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
            return
        out.append({"role": role, "content": list(blocks)})

    for index, m in enumerate(cleaned):
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "")
        if role == "system":
            continue
        if role == "user":
            _push("user", _user_blocks(m.get("content")))
            continue
        if role == "tool":
            old = str(m.get("tool_call_id") or "").strip()
            queue = id_queues.get(old) or []
            if not queue:
                continue
            new_id = queue.pop(0)
            _push("user", [{
                "type": "tool_result",
                "tool_use_id": new_id,
                "content": _tool_result_content(m.get("content")),
            }])
            continue
        if role != "assistant":
            continue
        blocks: List[Dict[str, Any]] = []
        if keep_thinking:
            for block in _meta_blocks(m):
                blocks.append({"type": "thinking", **block})
        text = m.get("content")
        if isinstance(text, str) and text:
            blocks.append({"type": "text", "text": text})
        calls = m.get("tool_calls")
        if isinstance(calls, list):
            new_ids = ids_per_message.get(index, [])
            seq = 0
            for call in calls:
                if not isinstance(call, dict):
                    continue
                name = str(call.get("name") or "").strip()
                if not name:
                    continue
                new_id = new_ids[seq] if seq < len(new_ids) else f"call_{index}_{seq}"
                seq += 1
                args = call.get("arguments")
                blocks.append({
                    "type": "tool_use",
                    "id": new_id,
                    "name": name,
                    "input": args if isinstance(args, dict) else {},
                })
        _push("assistant", blocks)

    # 第一条必须是 user：前导 assistant 没有待回答的 tool_result，留着会被拒。
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def _tools_payload(tools: Iterable[Any]) -> List[Dict[str, Any]]:
    """工具声明 → Anthropic `tools`（`input_schema`）。"""
    out: List[Dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "name": name,
            "description": str(fn.get("description") or ""),
            # 与 OpenAI 侧共用同一个规范化函数：`input_schema` 必须是带 `type` 的
            # object schema，逻辑形的属性映射不能直接当 schema 下发。
            "input_schema": tool_parameters(tool),
        })
    return out


# ── 流装配 ──────────────────────────────────


def _stop_reason_note(reason: str) -> str:
    return f"[anthropic] stop_reason={reason}" if reason else ""


def _tool_turn_missing_thinking(messages: List[Any], turn_start: Optional[int]) -> bool:
    """本轮有带 `tool_calls` 的 assistant 消息但没有任何可回传的 thinking 块？

    DeepSeek 与 Anthropic 官方都要求：思考模式下，带 `tool_use` 的 assistant 消息
    必须把 thinking 块原样带回（DeepSeek 报 `content[].thinking ... must be passed
    back`，官方同义）。历史里丢了块（换了协议条目 / 签名缺失被丢弃）就再也补不回来，
    此时只能关掉思考，否则这条会话在这条模型上永远打不开。
    """
    cut = max(0, int(turn_start or 0))
    for index, m in enumerate(messages):
        if index < cut or not isinstance(m, dict):
            continue
        if str(m.get("role") or "") != "assistant":
            continue
        calls = m.get("tool_calls")
        if not isinstance(calls, list) or not calls:
            continue
        if not _meta_blocks(m):
            return True
    return False


class AnthropicProvider(ModelProvider):
    """Anthropic Messages API 适配（流式、工具调用、extended thinking）。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        max_tokens: int = 16000,
        thinking: bool = True,
        thinking_budget_tokens: int = 4096,
        anthropic_version: str = "2023-06-01",
        timeout: float = 300.0,
        extra_headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.base_url = str(base_url or "").strip()
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip()
        self.max_tokens = _positive_int(max_tokens, 16000)
        self.thinking = bool(thinking)
        self.thinking_budget_tokens = _positive_int(thinking_budget_tokens, 4096)
        self.anthropic_version = str(anthropic_version or "2023-06-01")
        self.timeout = float(timeout)
        self.extra_headers = {str(k): str(v) for k, v in dict(extra_headers or {}).items()}

    # ── 请求体 ──

    def _thinking_enabled(self) -> bool:
        """预算不足时关闭 thinking 并留痕（请求照常发出，配置瑕疵不该阻断对话）。

        这两条约束来自 Anthropic 官方（`budget_tokens >= 1024` 且
        `max_tokens > budget_tokens`）。DeepSeek 兼容层会忽略 `budget_tokens`
        （官方文档：`thinking` 支持、`budget_tokens` 被忽略），但同一个适配器
        要能直接切到官方端点，所以约束照旧；关掉时显式下发 `disabled`，
        而不是省略字段——省略在 DeepSeek 侧意味着"继续思考"。
        """
        if not self.thinking:
            return False
        budget = self.thinking_budget_tokens
        if budget < _MIN_THINKING_BUDGET:
            _warn(f"thinking_budget_tokens={budget} < {_MIN_THINKING_BUDGET}，已关闭 thinking")
            return False
        if self.max_tokens <= budget:
            _warn(f"max_tokens={self.max_tokens} 不大于 thinking 预算 {budget}，已关闭 thinking")
            return False
        return True

    def build_payload(self, request: Any) -> Dict[str, Any]:
        """逻辑请求 → Messages 请求体（单测直接断言这个形状）。"""
        model = str(getattr(request, "model", "") or "").strip() or self.model
        if not model:
            raise ModelRequestError("model 未配置。")
        raw_messages = list(getattr(request, "messages", None) or [])
        turn_start = getattr(request, "turn_start", None)
        thinking_on = self._thinking_enabled()
        if thinking_on and _tool_turn_missing_thinking(raw_messages, turn_start):
            # 历史工具轮丢了 thinking 块：补不回来，只能本轮关掉思考（否则必被拒）。
            _warn("本轮带工具调用的 assistant 消息缺 thinking 块，已关闭 thinking")
            thinking_on = False
        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": self.max_tokens,
            "stream": True,
            "messages": _to_anthropic_messages(
                raw_messages, turn_start, keep_thinking=thinking_on),
        }
        system = _system_text(raw_messages)
        if system:
            payload["system"] = system
        tools = _tools_payload(getattr(request, "tools", None) or [])
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = {"type": "auto"}
        if thinking_on:
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget_tokens,
            }
        else:
            # 必须显式关闭：DeepSeek 兼容层默认开启思考模式，不传 `thinking`
            # 等于继续思考；而思考模式下带 `tool_use` 的 assistant 消息必须回传
            # thinking 块，关掉思考就再也拿不到块 → 工具轮 400。Anthropic 官方同样
            # 接受 `{"type":"disabled"}`。
            payload["thinking"] = {"type": "disabled"}
        return payload

    # ── 传输 ──

    def _headers(self) -> Dict[str, str]:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json; charset=utf-8",
        }
        headers.update(self.extra_headers)
        return headers

    def _http_error(self, status: int, body: str) -> ModelRequestError:
        plain = f"HTTP {status}: {body[:8000]}" if (body or "").strip() else f"HTTP {status}"
        hint = _HTTP_HINTS.get(int(status))
        if not hint:
            return ModelRequestError(plain, status=status)
        upstream = _upstream_message(body)
        detail = f"{hint} 接口返回：{upstream}" if upstream and upstream not in hint else hint
        return ModelRequestError(detail, status=status)

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
                body = exc.read().decode("utf-8", errors="replace")
            except Exception as read_exc:
                report_error("agent.mechanisms.providers.anthropic.AnthropicProvider._post_stream", read_exc)
                _warn(f"读 HTTP 错误体失败：{type(read_exc).__name__}: {read_exc}")
                body = ""
            raise self._http_error(exc.code, body) from exc
        except urllib.error.URLError as exc:
            raise ModelRequestError(f"网络错误：{getattr(exc, 'reason', exc)}") from exc
        yield from stream_with_timeout(resp, self.timeout, label="anthropic")

    def stream(self, request: Any) -> Iterator[StreamDelta]:
        if not self.api_key:
            raise ModelRequestError("api_key 未配置。")
        url = messages_url(self.base_url)
        if not url:
            raise ModelRequestError("base_url 未配置。")
        payload = self.build_payload(request)
        if LOG_REQUESTS:
            print(
                f"[llm→] url={url} model={payload['model']} "
                f"messages={len(payload['messages'])} tools={len(payload.get('tools') or [])} "
                f"thinking={'yes' if 'thinking' in payload else 'no'}",
                file=sys.stderr, flush=True,
            )
        yield from _assemble_deltas(self._post_stream(url, payload))


def _positive_int(value: Any, fallback: int) -> int:
    try:
        got = int(value)
    except (TypeError, ValueError):
        # 配置/响应里的数值可能缺失或非法；退回调用方给的默认值。
        return fallback
    return got if got > 0 else fallback


def _empty_block() -> Dict[str, Any]:
    """流式块的可变累积槽：文本/签名/工具参数都是边到边拼。"""
    return {"type": "", "id": "", "name": "", "json": "",
            "signature": "", "thinking": ""}


def _consume_block_start(data: Dict[str, Any],
                         blocks: Dict[int, Dict[str, Any]]) -> Iterator[StreamDelta]:
    """`content_block_start`：登记块并把起始内容先发给前端。"""
    index = _int(data.get("index"))
    raw = data.get("content_block") if isinstance(data.get("content_block"), dict) else {}
    block_type = str(raw.get("type") or "")
    block = _empty_block()
    block["type"] = block_type
    block["id"] = str(raw.get("id") or "")
    block["name"] = str(raw.get("name") or "")
    blocks[index] = block
    initial = raw.get("text")
    if block_type == "text" and isinstance(initial, str) and initial:
        yield StreamDelta(kind="text", text=initial)
    if block_type == "thinking" and isinstance(raw.get("thinking"), str) and raw["thinking"]:
        block["thinking"] = str(raw["thinking"])
        yield StreamDelta(kind="reasoning", text=str(raw["thinking"]))
    if block_type == "tool_use" and isinstance(raw.get("input"), dict) and raw["input"]:
        block["json"] = json.dumps(raw["input"], ensure_ascii=False)


def _consume_block_delta(data: Dict[str, Any],
                         blocks: Dict[int, Dict[str, Any]]) -> Iterator[StreamDelta]:
    """`content_block_delta`：按增量类型累积，并同步产出可见增量。"""
    index = _int(data.get("index"))
    block = blocks.setdefault(index, _empty_block())
    delta = data.get("delta") if isinstance(data.get("delta"), dict) else {}
    delta_type = str(delta.get("type") or "")
    if delta_type == "text_delta":
        text = delta.get("text")
        if isinstance(text, str) and text:
            yield StreamDelta(kind="text", text=text)
    elif delta_type == "thinking_delta":
        text = delta.get("thinking")
        if isinstance(text, str) and text:
            block["thinking"] += text
            yield StreamDelta(kind="reasoning", text=text)
    elif delta_type == "signature_delta":
        sig = delta.get("signature")
        if isinstance(sig, str):
            block["signature"] += sig
    elif delta_type == "input_json_delta":
        partial = delta.get("partial_json")
        if isinstance(partial, str):
            block["json"] += partial


def _consume_block_stop(data: Dict[str, Any],
                        blocks: Dict[int, Dict[str, Any]],
                        calls: List[Tuple[int, ToolCallRequest]],
                        thinking: List[Dict[str, str]]) -> None:
    """`content_block_stop`：工具块转成调用，thinking 块收进回传签名。"""
    index = _int(data.get("index"))
    block = blocks.get(index) or {}
    if block.get("type") == "tool_use":
        calls.append((index, _tool_call(block.get("id"), block.get("name"),
                                        block.get("json"))))
    elif block.get("type") == "thinking":
        text = str(block.get("thinking") or "")
        sig = str(block.get("signature") or "")
        if sig:
            # 正文允许为空：DeepSeek 兼容层要求带 `tool_use` 的思考块原样回传，
            # 而有的模型思考正文就是空串；丢掉它会让下一子请求直接 400。
            thinking.append({"thinking": text, "signature": sig})
        elif text:
            _warn("收到缺 signature 的 thinking 块，已跳过（无法回传）")


def _assemble_deltas(chunks: Iterable[Dict[str, Any]]) -> Iterator[StreamDelta]:
    """Anthropic 流帧 → 归一化增量。

    顺序固定：文本/推理边到边出 → `meta`（thinking 块）→ `tool_call` → `usage`。
    事件类型只认载荷里的 `data.type`，不读 `event:` 行（两处各存一份迟早漂移）。
    """
    blocks: Dict[int, Dict[str, Any]] = {}
    thinking: List[Dict[str, str]] = []
    calls: List[Tuple[int, ToolCallRequest]] = []
    usage = {"input": 0, "cache_read": 0, "cache_create": 0, "output": 0}
    stop_reason = ""

    for data in chunks:
        kind = str(data.get("type") or "")
        if kind == "message_start":
            msg = data.get("message") if isinstance(data.get("message"), dict) else {}
            u = msg.get("usage") if isinstance(msg.get("usage"), dict) else {}
            usage["input"] = _int(u.get("input_tokens"))
            usage["cache_read"] = _int(u.get("cache_read_input_tokens"))
            usage["cache_create"] = _int(u.get("cache_creation_input_tokens"))
        elif kind == "content_block_start":
            yield from _consume_block_start(data, blocks)
        elif kind == "content_block_delta":
            yield from _consume_block_delta(data, blocks)
        elif kind == "content_block_stop":
            _consume_block_stop(data, blocks, calls, thinking)
        elif kind == "message_delta":
            delta = data.get("delta") if isinstance(data.get("delta"), dict) else {}
            stop_reason = str(delta.get("stop_reason") or "") or stop_reason
            u = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            usage["output"] = _int(u.get("output_tokens")) or usage["output"]
        elif kind == "message_stop":
            break
        elif kind == "error":
            err = data.get("error") if isinstance(data.get("error"), dict) else {}
            raise ModelRequestError(str(err.get("message") or "模型返回错误")[:800])
        # ping / 未知事件：忽略（前滚契约）

    if stop_reason:
        print(_stop_reason_note(stop_reason), file=sys.stderr, flush=True)
    if thinking and calls:
        # 只有"要带工具继续这一轮"时才需要回传签名；纯文本回答没有回传落点。
        yield StreamDelta(kind="meta", meta={_META_VENDOR: {_META_BLOCKS: thinking}})
    for _index, call in sorted(calls, key=lambda item: item[0]):
        yield StreamDelta(kind="tool_call", tool_call=call)
    mapped = _usage_payload(usage)
    if mapped:
        yield StreamDelta(kind="usage", usage=mapped)


def _tool_call(raw_id: Any, raw_name: Any, arguments_json: Any) -> ToolCallRequest:
    text = str(arguments_json or "").strip() or "{}"
    try:
        args = json.loads(text)
    except (TypeError, ValueError):
        args = {}
    if not isinstance(args, dict):
        args = {}
    call_id = str(raw_id or "").strip() or f"call_{_random_suffix()}"
    return ToolCallRequest(call_id=call_id, name=str(raw_name or "").strip(), arguments=args)


def _usage_payload(usage: Mapping[str, int]) -> Dict[str, int]:
    """Anthropic 用量 → 与 OpenAI 适配同名的字段（界面与累计器无分支）。"""
    prompt = usage["input"] + usage["cache_read"] + usage["cache_create"]
    if prompt <= 0 and usage["output"] <= 0:
        return {}
    return {
        "prompt_tokens": prompt,
        "completion_tokens": usage["output"],
        "prompt_cache_hit_tokens": usage["cache_read"],
        "prompt_cache_miss_tokens": usage["input"] + usage["cache_create"],
    }


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        # 用量字段缺失或格式异常时按 0 计；统计问题不该打断已完成的一轮。
        return 0


def _random_suffix() -> str:
    from uuid import uuid4

    return uuid4().hex[:12]
