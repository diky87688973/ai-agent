# 模型调用

`agent/mechanisms/providers/` 定义模型调用协议与具体实现；路由只在 `provider_router.py`。

## 思维链的回传预算

思考模式下模型逐轮产出思维链（`reasoning_content`）。它是模型产生的**中间稿**：
全量回传等于每次请求的输入里多一大段**必然未命中缓存**的内容，
而且同一轮内每次请求的前缀都在变，前缀缓存落不住。

预算由 `[context] reasoning_replay_tokens` 控制（token）：

| 取值 | 行为 |
|---|---|
| `-1` | 全量回传（官方文档在带 `tools` 时的写法） |
| `0` | 不回传 |
| 正数（默认 `8000`） | 超出预算就**取两头、中间以 `<此处省略 N token 的推理>` 代替** |

取两头而不是只留尾部：推理的开头是"打算干什么"、结尾是"得出了什么"，
中间的过程模型能按这两头补出来。

**键不能丢**：Upstream 思考模式下，带 `tool_calls` 的 assistant 消息必须把
`reasoning_content` 回传给 API（空串也接受），缺键直接 400
`The reasoning_content in the thinking mode must be passed back to the API`。
所以历史轮的工具消息只清空内容、保留键；老记录里本来没存思维链的工具消息补一个
空串。纯文本 assistant 消息没有这条要求，历史轮照旧整个摘键。历史轮里的工具消息
丢了键，**整条会话在第二次提问时就会 400**。

裁剪在**装配期**做（`set_dialogue` 调 `clip_reasoning`），不在线上做 ——
分段统计、预算估算、真正发出去的请求三者看的是同一份；两处不一致时界面会把窗口算满、
压缩也会提前或滞后触发。事实流不受影响：记录与界面的事件照旧带完整推理。


## 协议

```python
class ModelProvider:
    def stream(self, request: LogicalRequest) -> Iterator[StreamDelta]: ...
```

消费方只认这个接口。更换网关或模型只需换一个 provider 实例。

| 实现 | 用途 |
|---|---|
| `EchoProvider` | 不依赖网络；首次请求发起一次 `echo` 工具调用，拿到结果后给出文本应答 |
| `MissingProvider` | 缺少可用模型时的占位实现，不访问网络 |
| `CompatibleCompatibleProvider` | Compatible 兼容真实适配，流式解析 SSE |
| `NativeProvider` | Native Messages 真实适配，独立导入协议与 SSE 工具 |

## 请求体

`CompatibleCompatibleProvider.stream()` 构造的请求体：

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


两处取值来源：

- **`reasoning_effort` 取自请求**（`LogicalRequest.effort`，由会话级设置解析而来），不是写死的常量。官方取值 `none` / `low` / `high` / `max`，缺省回落 `high`，非空值如实下发。
- **`temperature` 在思考模式下不生效**：Upstream 官方文档写明思考模式不支持该参数（**不报错，但也不会生效**），所以 `0.2` 只在非思考请求或其它兼容网关上起作用。
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

图片**原样下发**，不按模型名猜能力、不做降级剥图 —— 剥图是有损的，猜错一次就是"用户发了图而模型只看到一句占位"。带不带图、带几张由 `[context]` 的 `image_turns` / `image_max` 决定（见 [context.md](context.md)）。


## 错误映射

`ModelRequestError` 携带面向用户的说明与 HTTP 状态码。

`_http_error()` 对 Upstream 网关按状态码给出可读提示（400 / 401 / 402 / 422 / 429 / 500 / 503），并附上游返回的原始 message（截断到 8000 字符）。非 Upstream 网关直接用原始文本。

这些提示**直接显示给用户**，所以措辞只描述"哪一端出了问题"。

模型名或基址里含 `upstream` 才算 Upstream 网关（`_is_upstream()`）。

## 请求留痕

发送前打印一行摘要（`describe_request()`），内容为模型名、地址、消息数、工具数、图片数、请求体字节数。

- `AI_AGENT_LOG_REQUESTS=0` 关闭；
- `AI_AGENT_LLM_LOG` 指定落盘路径，留空则写到 `%TEMP%/fan_agent_llm_requests.log`（`TEMP` 与 `TMP` 都缺时退到当前目录）。

摘要同时写 stderr 与日志文件，图片信息在其中逐条列出（第几条消息、什么角色、几张图、每张多少字符）。

## 延伸阅读

- [architecture.md](../architecture.md)：端口与请求契约
- [context.md](context.md)：messages 的组装
- [guide/config.md](../guide/config.md)：宿主配置
