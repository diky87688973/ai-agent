# 模型调用

`agent/mechanisms/model_provider.py` 定义模型调用协议与它的两个实现。

## 协议

```python
class ModelProvider:
    def stream(self, request: LogicalRequest) -> Iterator[StreamDelta]: ...
```

消费方只认这个接口。更换网关或模型只需换一个 provider 实例。

| 实现 | 用途 |
|---|---|
| `EchoProvider` | 不依赖网络。首次请求发起一次 `echo` 工具调用，拿到结果后给出文本应答 |
| `OpenAICompatibleProvider` | 真实适配。标准库 `urllib` 发请求，流式解析 SSE |

## 请求体

`OpenAICompatibleProvider.stream()` 构造的请求体：

```json
{
  "model": "<本次会话选定的模型>",
  "messages": [...],
  "reasoning_effort": "<取自 LogicalRequest.effort>",
  "thinking": {"type": "enabled"},
  "temperature": 0.2,
  "stream": true
}
```

带工具时追加 `tools` 与 `tool_choice: "auto"`；有会话身份时追加 `user`（对服务端做 KV 缓存隔离）；构造参数 `include_usage=True` 时追加 `stream_options.include_usage`。

两处取值来源：

- **`reasoning_effort` 取自请求**（`LogicalRequest.effort`，由会话级设置解析而来），不是写死的常量。官方取值 `none` / `low` / `high` / `max`，缺省回落 `high`，非空值如实下发。
- **本地模型整键剥离** `thinking` / `reasoning_effort` / `temperature`。`_is_local_model()` 判定（模型名是 `local-model` 或以它开头），走浏览器页面的本地模型不支持这几个参数。

## 地址推导

`_chat_completions_url(base_url)` 把基址补成完整端点，幂等：

| 基址形态 | 结果 |
|---|---|
| 已含 `/chat/completions` | 原样 |
| 尾段是版本段（`v1` / `v4` …） | 直拼 `/chat/completions` |
| 其它 | 补 `/v1/chat/completions` |

## 流式解析

`_parse_sse_lines()` 只处理 `data:` 行，跳过 `event:` / `id:` / 注释；`[DONE]` 终止；单行 JSON 解析失败**跳过不中断**。

`_assemble_stream_deltas()` 把 chunk 序列转成 `StreamDelta`：

| 增量类型 | 来源字段 |
|---|---|
| 正文 | `delta.content` |
| 思考 | `delta.reasoning_content` 或 `delta.reasoning`（`_best_reasoning_field()` 取最长者） |
| 工具调用 | `delta.tool_calls` 分片 |
| 用量 | 末帧的 `usage` |

## 工具调用分片归并

流式响应里一次工具调用可能被切成多个分片：第一片带 `id` 与函数名，后续片只带 `arguments` 的字符串片段。

`_merge_tool_call_fragments()` 按数组下标归并分片，拼出完整的 `ToolCallRequest`。

`_tool_calls_from_snapshot_message()` 是兜底：部分网关在末帧给出完整的 `message.tool_calls`，用它覆盖分片归并的结果。

## 图片

`supports_vision(model)` 判定本次请求能不能带图：模型名含 `vision` 即算。

不能带图时 `_strip_images()` 剥掉图片内容块，只留文本。

带图却声称看不到时（`_IMAGE_DENIAL_HINTS` / `_denies_seeing_images()` 识别这类措辞），**丢弃被历史污染的上下文**，只带系统提示与当前那条带图消息重试一次，后续增量照常产出。历史里"我看不到图片"的断言会像 few-shot 一样把后续每轮锚死在否认上。

## 错误映射

`ModelRequestError` 携带面向用户的说明与 HTTP 状态码。

`_http_error()` 对 DeepSeek 网关按状态码给出可读提示（400 / 401 / 402 / 422 / 429 / 500 / 503），并附上游返回的原始 message（截断到 8000 字符）。非 DeepSeek 网关直接用原始文本。

这些提示**直接显示给用户**，所以措辞只描述"哪一端出了问题"。

模型名或基址里含 `deepseek` 才算 DeepSeek 网关（`_is_deepseek()`）。

## 请求留痕

发送前打印一行摘要（`describe_request()`），内容为模型名、地址、消息数、工具数、图片数、请求体字节数。

- `AI_AGENT_LOG_REQUESTS=0` 关闭；
- `AI_AGENT_LLM_LOG` 指定落盘路径，留空则写到 `%TEMP%/fan_agent_llm_requests.log`（`TEMP` 与 `TMP` 都缺时退到当前目录）。

摘要同时写 stderr 与日志文件，图片信息在其中逐条列出（第几条消息、什么角色、几张图、每张多少字符）。

## 延伸阅读

- [architecture.md](../architecture.md)：端口与请求契约
- [context.md](context.md)：messages 的组装
- [guide/config.md](../guide/config.md)：`[model_reasoning]` 配置
