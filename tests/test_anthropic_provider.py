# -*- coding: utf-8 -*-
"""Anthropic 适配测试：SSE 归并、消息折叠与修补、请求体、错误映射。

断言只碰契约：`StreamDelta` 的形状与 Anthropic 线格式。
不测内部临时字典，避免把实现细节写死成测试。
"""
from __future__ import annotations

import io
import json
import time
import unittest
import urllib.error
from unittest import mock

from agent.core.model_call import PROVIDER_META_KEY
from agent.core.ports import LogicalRequest
from agent.mechanisms.providers import anthropic as ap
from agent.mechanisms.providers.anthropic import (
    AnthropicProvider,
    _assemble_deltas,
    _to_anthropic_messages,
    drop_dangling_tool_results,
    messages_url,
    strip_stale_thinking,
)
from agent.mechanisms.providers.base import ModelRequestError

# ── SSE 夹具 ────────────────────────────────


def _sse(event_type: str, payload: dict) -> str:
    """不带 `event:` 行：适配器只认载荷里的 `data.type`。"""
    return "data: " + json.dumps({"type": event_type, **payload}, ensure_ascii=False)


def _text_stream(texts=("你", "好")) -> list[dict]:
    out: list[dict] = [{
        "type": "message_start",
        "message": {"usage": {
            "input_tokens": 10,
            "cache_read_input_tokens": 3,
            "cache_creation_input_tokens": 2,
        }},
    }, {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}]
    out += [{"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": text}} for text in texts]
    out.append({"type": "content_block_stop", "index": 0})
    out.append({"type": "message_delta", "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 7}})
    out.append({"type": "message_stop"})
    return out


def _tool_stream(with_thinking: bool = True) -> list[dict]:
    chunks: list[dict] = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 5}}},
    ]
    if with_thinking:
        chunks += [
            {"type": "content_block_start", "index": 0,
             "content_block": {"type": "thinking", "thinking": ""}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "thinking_delta", "thinking": "先看文件"}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "signature_delta", "signature": "sig-"}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "signature_delta", "signature": "tail"}},
            {"type": "content_block_stop", "index": 0},
        ]
    chunks += [
        {"type": "content_block_start", "index": 1, "content_block": {
            "type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {}}},
        {"type": "content_block_delta", "index": 1,
         "delta": {"type": "input_json_delta", "partial_json": '{"pa'}},
        {"type": "content_block_delta", "index": 1,
         "delta": {"type": "input_json_delta", "partial_json": 'th": "a.txt"}'}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_stop"},
    ]
    return chunks


class StreamAssemblyTest(unittest.TestCase):
    def test_text_deltas_stream_through_and_usage_is_mapped(self) -> None:
        deltas = list(_assemble_deltas(_text_stream()))
        self.assertEqual([d.text for d in deltas if d.kind == "text"], ["你", "好"])
        usage = [d for d in deltas if d.kind == "usage"]
        self.assertEqual(len(usage), 1)
        self.assertEqual(usage[0].usage, {
            "prompt_tokens": 15,
            "completion_tokens": 7,
            "prompt_cache_hit_tokens": 3,
            "prompt_cache_miss_tokens": 12,
        })

    def test_cache_fields_default_to_zero_when_absent(self) -> None:
        streams = _text_stream()
        streams[0] = {"type": "message_start", "message": {"usage": {"input_tokens": 4}}}
        usage = [d for d in _assemble_deltas(streams) if d.kind == "usage"][0]
        self.assertEqual(usage.usage["prompt_cache_hit_tokens"], 0)
        self.assertEqual(usage.usage["prompt_cache_miss_tokens"], 4)

    def test_thinking_and_tool_use_are_reassembled(self) -> None:
        deltas = list(_assemble_deltas(_tool_stream()))
        reasoning = "".join(d.text for d in deltas if d.kind == "reasoning")
        self.assertEqual(reasoning, "先看文件")
        calls = [d.tool_call for d in deltas if d.kind == "tool_call"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].call_id, "toolu_1")
        self.assertEqual(calls[0].name, "read_file")
        self.assertEqual(calls[0].arguments, {"path": "a.txt"})

    def test_meta_is_emitted_only_when_thinking_and_tools_coexist(self) -> None:
        deltas = list(_assemble_deltas(_tool_stream(with_thinking=True)))
        meta = [d.meta for d in deltas if d.kind == "meta"]
        self.assertEqual(meta, [{"anthropic": {
            "thinking_blocks": [{"thinking": "先看文件", "signature": "sig-tail"}],
        }}])
        without = list(_assemble_deltas(_tool_stream(with_thinking=False)))
        self.assertEqual([d for d in without if d.kind == "meta"], [])

    def test_thinking_without_signature_is_skipped_with_a_warning(self) -> None:
        chunks = _tool_stream(with_thinking=True)
        for chunk in chunks:
            if chunk.get("delta", {}).get("type") == "signature_delta":
                chunk["delta"]["signature"] = ""
        with mock.patch.object(ap, "_warn") as warn:
            deltas = list(_assemble_deltas(chunks))
        self.assertEqual([d for d in deltas if d.kind == "meta"], [],
                         msg="缺签名无法回传，不能落盘")
        self.assertTrue(warn.called)

    def test_invalid_tool_json_degrades_to_empty_arguments(self) -> None:
        chunks = _tool_stream(with_thinking=False)
        for chunk in chunks:
            delta = chunk.get("delta") or {}
            if delta.get("type") == "input_json_delta":
                delta["partial_json"] = "{broken"
        call = [d.tool_call for d in _assemble_deltas(chunks) if d.kind == "tool_call"][0]
        self.assertEqual(call.arguments, {})

    def test_missing_tool_id_gets_a_generated_one(self) -> None:
        chunks = _tool_stream(with_thinking=False)
        for chunk in chunks:
            block = chunk.get("content_block") or {}
            if block.get("type") == "tool_use":
                block["id"] = ""
        call = [d.tool_call for d in _assemble_deltas(chunks) if d.kind == "tool_call"][0]
        self.assertTrue(call.call_id.startswith("call_"))

    def test_error_event_becomes_model_request_error(self) -> None:
        with self.assertRaises(ModelRequestError) as caught:
            list(_assemble_deltas([{
                "type": "error", "error": {"type": "overloaded_error", "message": "过载"},
            }]))
        self.assertIn("过载", str(caught.exception))

    def test_ping_and_unknown_events_are_ignored(self) -> None:
        deltas = list(_assemble_deltas([
            {"type": "ping"},
            {"type": "mystery_future_event", "whatever": 1},
            {"type": "message_stop"},
        ]))
        self.assertEqual(deltas, [])


class MessageConversionTest(unittest.TestCase):
    def test_system_is_hoisted_and_user_text_becomes_a_block(self) -> None:
        request = LogicalRequest(
            messages=[
                {"role": "system", "content": "规则一"},
                {"role": "system", "content": "规则二"},
                {"role": "user", "content": "你好"},
            ],
            tools=[],
        )
        payload = AnthropicProvider(base_url="https://x", api_key="k", model="m")\
            .build_payload(request)
        self.assertEqual(payload["system"], "规则一\n\n规则二")
        self.assertNotIn("system", [m["role"] for m in payload["messages"]])
        self.assertEqual(payload["messages"][0]["content"], [{"type": "text", "text": "你好"}])

    def test_image_urls_are_split_into_image_blocks(self) -> None:
        request = LogicalRequest(messages=[{"role": "user", "content": [
            {"type": "text", "text": "看图"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
            {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
        ]}], tools=[])
        content = AnthropicProvider(base_url="u", api_key="k", model="m")\
            .build_payload(request)["messages"][0]["content"]
        self.assertEqual(content[0], {"type": "text", "text": "看图"})
        self.assertEqual(content[1], {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"},
        })
        # 远程 URL 走 `source.type=url`：官方与 DeepSeek 兼容层都支持这种源。
        # 直接丢掉的后果是同一张图在 openai 条目里发得出去、在 anthropic 条目里消失。
        self.assertEqual(content[2], {
            "type": "image",
            "source": {"type": "url", "url": "https://example.com/x.png"},
        })
        self.assertEqual(len(content), 3)

    def test_assistant_tool_calls_become_tool_use_blocks(self) -> None:
        messages = [
            {"role": "user", "content": "查文件"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "name": "read_file", "arguments": {"path": "a.txt"}},
            ]},
        ]
        converted = _to_anthropic_messages(messages, turn_start=None)
        self.assertEqual(converted[-1]["content"], [{
            "type": "tool_use", "id": "c1", "name": "read_file", "input": {"path": "a.txt"},
        }])

    def test_consecutive_tool_results_merge_into_one_user_message(self) -> None:
        messages = [
            {"role": "user", "content": "查两个文件"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "name": "read_file", "arguments": {}},
                {"id": "c2", "name": "read_file", "arguments": {}},
            ]},
            {"role": "tool", "tool_call_id": "c1", "content": "A"},
            {"role": "tool", "tool_call_id": "c2", "content": ""},
        ]
        converted = _to_anthropic_messages(messages, turn_start=None)
        self.assertEqual([m["role"] for m in converted], ["user", "assistant", "user"])
        results = converted[-1]["content"]
        self.assertEqual([block["tool_use_id"] for block in results], ["c1", "c2"])
        self.assertEqual(results[1]["content"], "（工具没有返回内容）")

    def test_duplicate_tool_ids_are_suffixed_and_results_follow(self) -> None:
        messages = [
            {"role": "user", "content": "开始"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "dup", "name": "read_file", "arguments": {}},
            ]},
            {"role": "tool", "tool_call_id": "dup", "content": "A"},
            {"role": "user", "content": "继续"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "dup", "name": "read_file", "arguments": {}},
            ]},
            {"role": "tool", "tool_call_id": "dup", "content": "B"},
        ]
        converted = _to_anthropic_messages(messages, turn_start=None)
        uses = [block["id"] for m in converted for block in m["content"]
                if block.get("type") == "tool_use"]
        results = [block["tool_use_id"] for m in converted for block in m["content"]
                   if block.get("type") == "tool_result"]
        self.assertEqual(uses, ["dup", "dup_2"])
        self.assertEqual(results, uses, msg="配对必须同步改名，否则 API 无法关联")

    def test_leading_assistant_is_dropped(self) -> None:
        converted = _to_anthropic_messages([
            {"role": "assistant", "content": "开场白"},
            {"role": "user", "content": "正文"},
        ], turn_start=None)
        self.assertEqual(converted, [{"role": "user", "content": [{"type": "text", "text": "正文"}]}])

    def test_dangling_tool_result_is_dropped(self) -> None:
        messages = [
            {"role": "user", "content": "x"},
            {"role": "tool", "tool_call_id": "ghost", "content": "无主结果"},
        ]
        self.assertEqual(len(drop_dangling_tool_results(messages)), 1)
        converted = _to_anthropic_messages(messages, turn_start=None)
        self.assertNotIn("tool_result", json.dumps(converted, ensure_ascii=False))

    def test_thinking_blocks_replay_only_within_the_current_turn(self) -> None:
        old = {"role": "assistant", "content": "旧回答", "provider_meta": {
            "anthropic": {"thinking_blocks": [{"thinking": "旧", "signature": "s1"}],
                          "future_key": 1}}}
        new = {"role": "assistant", "content": "新回答", "provider_meta": {
            "anthropic": {"thinking_blocks": [{"thinking": "新", "signature": "s2"}]}}}
        stripped = strip_stale_thinking([old, new], turn_start=1)
        self.assertNotIn("thinking_blocks", stripped[0]["provider_meta"]["anthropic"])
        self.assertEqual(stripped[0]["provider_meta"]["anthropic"]["future_key"], 1,
                         msg="未知子键必须原样保留（前滚契约）")
        self.assertEqual(thinking_blocks(stripped[1]),
                         [{"thinking": "新", "signature": "s2"}])

    def test_tools_payload_accepts_both_declaration_shapes(self) -> None:
        request = LogicalRequest(messages=[{"role": "user", "content": "x"}], tools=[
            {"type": "function", "function": {
                "name": "read_file", "description": "读文件",
                "parameters": {"type": "object", "properties": {}},
            }},
            {"name": "flat", "description": "", "input_schema": {"type": "object"}},
        ])
        payload = AnthropicProvider(base_url="u", api_key="k", model="m").build_payload(request)
        self.assertEqual([tool["name"] for tool in payload["tools"]], ["read_file", "flat"])
        self.assertEqual(payload["tool_choice"], {"type": "auto"})
        no_tools = AnthropicProvider(base_url="u", api_key="k", model="m").build_payload(
            LogicalRequest(messages=[{"role": "user", "content": "x"}], tools=[]))
        self.assertNotIn("tools", no_tools)
        self.assertNotIn("tool_choice", no_tools)

    def test_logic_shaped_tool_becomes_a_valid_object_schema(self) -> None:
        """`ToolRegistry.schemas()` 给的是属性映射，必须包装成 object schema。

        直接把它当 `input_schema` 下发，线上会变成 `type: null`，Anthropic 报
        `Invalid schema for function ... got 'type: null'`（400）。OpenAI 兼容网关
        不校验这个字段，所以只有在 Anthropic 协议上才会暴露。
        """
        request = LogicalRequest(messages=[{"role": "user", "content": "x"}], tools=[
            {
                "name": "apply_patch",
                "description": "预览补丁",
                "parameters": {
                    "path": {"type": "string", "description": "根目录"},
                    "patch_text": {"type": "string", "description": "补丁正文"},
                },
                "parallel_safe": False,
            },
        ])
        payload = AnthropicProvider(
            base_url="u", api_key="k", model="m",
        ).build_payload(request)
        schema = payload["tools"][0]["input_schema"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(sorted(schema["properties"]), ["patch_text", "path"])
        self.assertNotIn("parallel_safe", json.dumps(payload["tools"], ensure_ascii=False),
                         msg="注册表内部字段不得漏进线格式")

    def test_thinking_is_enabled_only_when_the_budget_fits(self) -> None:
        payload = AnthropicProvider(
            base_url="u", api_key="k", model="m", max_tokens=8000,
            thinking=True, thinking_budget_tokens=4096,
        ).build_payload(LogicalRequest(messages=[{"role": "user", "content": "x"}], tools=[]))
        self.assertEqual(payload["thinking"], {"type": "enabled", "budget_tokens": 4096})
        self.assertNotIn("temperature", payload)

        with mock.patch.object(ap, "_warn") as warn:
            too_small = AnthropicProvider(
                base_url="u", api_key="k", model="m", max_tokens=4096,
                thinking_budget_tokens=4096,
            ).build_payload(LogicalRequest(messages=[], tools=[]))
        # 关闭必须是显式的：DeepSeek 兼容层不传 thinking 等于默认开启思考，
        # 而思考模式下带 tool_use 的消息必须回传 thinking 块，静默省略会让工具轮 400。
        self.assertEqual(too_small["thinking"], {"type": "disabled"})
        self.assertTrue(warn.called)

    def test_thinking_off_is_sent_as_disabled_not_omitted(self) -> None:
        payload = AnthropicProvider(
            base_url="u", api_key="k", model="m", thinking=False,
        ).build_payload(LogicalRequest(messages=[{"role": "user", "content": "x"}], tools=[]))
        self.assertEqual(payload["thinking"], {"type": "disabled"})

    def test_tool_turn_without_thinking_blocks_disables_thinking(self) -> None:
        """历史工具轮丢了 thinking 块就补不回来，本轮只能关掉思考，否则必被拒。

        DeepSeek：`content[].thinking in the thinking mode must be passed back`。
        """
        messages = [
            {"role": "user", "content": "查文件"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "name": "read_file", "arguments": {"path": "a.txt"}},
            ]},
            {"role": "tool", "tool_call_id": "c1", "content": "内容"},
        ]
        with mock.patch.object(ap, "_warn") as warn:
            payload = AnthropicProvider(
                base_url="u", api_key="k", model="m", max_tokens=16000,
                thinking=True, thinking_budget_tokens=4096,
            ).build_payload(LogicalRequest(messages=messages, tools=[], turn_start=0))
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(warn.call_count, 1)
        self.assertNotIn("thinking", json.dumps(payload["messages"], ensure_ascii=False))

    def test_disabled_thinking_does_not_replay_stored_blocks(self) -> None:
        """思考关闭时不带 thinking 块：官方端点会拒“思考未开启却带块”。"""
        messages = [
            {"role": "user", "content": "查文件"},
            {"role": "assistant", "content": "读完了", "provider_meta": {
                "anthropic": {"thinking_blocks": [
                    {"thinking": "想一想", "signature": "sig-1"}]}}},
        ]
        payload = AnthropicProvider(
            base_url="u", api_key="k", model="m", thinking=False,
        ).build_payload(LogicalRequest(messages=messages, tools=[], turn_start=0))
        self.assertNotIn("thinking", json.dumps(payload["messages"], ensure_ascii=False))

    def test_thinking_block_with_empty_text_is_still_replayed(self) -> None:
        """正文为空、签名在的思考块也要回传。

        有的模型（旧名 `deepseek-chat`）思考块正文就是空串；丢掉块会让带
        `tool_use` 的下一子请求被拒（`content[].thinking must be passed back`）。
        """
        messages = [
            {"role": "user", "content": "查文件"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "name": "read_file", "arguments": {"path": "a.txt"}},
            ], "provider_meta": {"anthropic": {"thinking_blocks": [
                {"thinking": "", "signature": "sig-empty"},
            ]}}},
        ]
        converted = _to_anthropic_messages(messages, turn_start=0)
        blocks = converted[1]["content"]
        self.assertEqual(blocks[0], {"type": "thinking", "thinking": "",
                                     "signature": "sig-empty"})


def thinking_blocks(message: dict) -> list[dict]:
    """从带 `provider_meta` 的消息里取 thinking 块（测试辅助）。"""
    meta = message.get(PROVIDER_META_KEY) or {}
    return (meta.get("anthropic") or {}).get("thinking_blocks") or []


class EndpointAndErrorTest(unittest.TestCase):
    def test_messages_url_variants(self) -> None:
        self.assertEqual(messages_url("https://api.anthropic.com"), "https://api.anthropic.com/v1/messages")
        self.assertEqual(messages_url("https://api.anthropic.com/v1"), "https://api.anthropic.com/v1/messages")
        self.assertEqual(messages_url("https://proxy/messages"), "https://proxy/messages")
        self.assertEqual(messages_url(""), "")

    def test_http_errors_use_the_anthropic_table_and_keep_upstream_detail(self) -> None:
        provider = AnthropicProvider(base_url="u", api_key="k", model="m")
        err = provider._http_error(401, '{"error":{"message":"invalid x-api-key"}}')
        self.assertEqual(err.status, 401)
        self.assertIn("认证失败", err.detail)
        self.assertIn("invalid x-api-key", err.detail)
        self.assertIn("过载", provider._http_error(529, "").detail)
        self.assertIn("HTTP 418", provider._http_error(418, "").detail)

    def test_missing_credentials_fail_before_any_network_call(self) -> None:
        with self.assertRaises(ModelRequestError):
            list(AnthropicProvider(base_url="u", api_key="", model="m").stream(
                LogicalRequest(messages=[], tools=[])))
        with self.assertRaises(ModelRequestError):
            list(AnthropicProvider(base_url="", api_key="k", model="m").stream(
                LogicalRequest(messages=[], tools=[])))

    def test_stream_posts_headers_and_payload_then_parses_sse(self) -> None:
        lines = [(_sse("message_start", {"message": {"usage": {"input_tokens": 1}}}) + "\n").encode(),
                 (_sse("content_block_start", {
                     "index": 0, "content_block": {"type": "text", "text": ""}}) + "\n").encode(),
                 (_sse("content_block_delta", {
                     "index": 0, "delta": {"type": "text_delta", "text": "hi"}}) + "\n").encode(),
                 (_sse("content_block_stop", {"index": 0}) + "\n").encode(),
                 (_sse("message_stop", {}) + "\n").encode()]

        class _Response:
            def __iter__(self):
                return iter(lines)

            def close(self) -> None:
                pass

        captured = {}

        def fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            captured["headers"] = {k.lower(): v for k, v in req.header_items()}
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _Response()

        request = LogicalRequest(messages=[{"role": "user", "content": "q"}], tools=[])
        provider = AnthropicProvider(base_url="https://api.anthropic.com", api_key="sk-ant",
                                     model="claude-x", thinking=False)
        with mock.patch.object(ap, "LOG_REQUESTS", False), \
                mock.patch.object(ap.urllib.request, "urlopen", side_effect=fake_urlopen):
            deltas = list(provider.stream(request))
        self.assertEqual(captured["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(captured["headers"]["x-api-key"], "sk-ant")
        self.assertEqual(captured["headers"]["anthropic-version"], "2023-06-01")
        self.assertTrue(captured["body"]["stream"])
        self.assertEqual(captured["body"]["model"], "claude-x")
        self.assertEqual([d.text for d in deltas if d.kind == "text"], ["hi"])

    def test_stream_watchdog_stops_a_stalled_upstream(self) -> None:
        class _StalledResponse:
            def __iter__(self):
                time.sleep(0.2)
                return iter(())

            def close(self) -> None:
                pass

        provider = AnthropicProvider(
            base_url="https://x", api_key="k", model="m", timeout=0.02,
        )
        with mock.patch.object(ap, "LOG_REQUESTS", False), \
                mock.patch.object(ap.urllib.request, "urlopen",
                                  return_value=_StalledResponse()):
            with self.assertRaises(ModelRequestError) as caught:
                list(provider.stream(LogicalRequest(messages=[{"role": "user", "content": "q"}],
                                                    tools=[])))
        self.assertIn("超时", caught.exception.detail)

    def test_http_error_response_is_mapped(self) -> None:
        error = urllib.error.HTTPError(
            "https://x/v1/messages", 429, "Too Many Requests", {},
            io.BytesIO(b'{"error":{"message":"rate limited"}}'),
        )
        provider = AnthropicProvider(base_url="https://x", api_key="k", model="m")
        with mock.patch.object(ap, "LOG_REQUESTS", False), \
                mock.patch.object(ap.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(ModelRequestError) as caught:
                list(provider.stream(LogicalRequest(messages=[], tools=[])))
        self.assertEqual(caught.exception.status, 429)
        self.assertIn("请求过于频繁", caught.exception.detail)


if __name__ == "__main__":
    unittest.main()
