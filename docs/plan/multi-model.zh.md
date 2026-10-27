[English](multi-model.md) | **中文**

# 多模型配置方案

## 1. 背景与目标

模型链路分三段：

- `agent/mechanisms/providers/` 按协议各放一个适配器，适配器只实现 `ModelProvider.stream()`；
- 模型配置只由 `plugins/multi_model/plugin-config.ini` 提供；
- 会话级模型选择落在 `live_state`，请求经 `LogicalRequest.model` 传给 provider。

目标：

1. 每条模型独立声明厂商、网关、凭据与线格式模型名，可跨网关、跨协议。
2. 提供 Messages 协议适配，支持文本、工具调用与 extended thinking。
3. 模型配置由插件管理，形态对齐知识库插件：自己的配置文件、端点与界面资产。
4. 界面提供模型下拉，选择按会话持久化，并广播到同一会话的其它标签页与页头。
5. 插件停用或没有有效条目时，模型清单为空，不回退到内核配置。

## 2. 不变量

1. 模型配置的唯一权威是 `plugins/multi_model/plugin-config.ini`。
   插件启用且至少有一条有效条目时提供模型；没有有效条目时目录为空。
2. 凭据只留在服务端。任何 HTTP 响应都不下发 `api_key` 与 `base_url`。
3. 依赖方向固定：`shell → capabilities → mechanisms → core`。
   插件在包外，只能向下依赖；`mechanisms` 与 `core` 永不 import 插件，也不得出现插件目录名
   （`check_architecture_hygiene.py` 以词边界扫描）。
4. provider 适配器只产出 `StreamDelta`。内核不认识线格式、thinking 块或签名。
5. 插件停用即贡献消失：下拉、路由、开屏脚本与样式一并注销，回退路径不报错。
6. 未配置的模型 id 直接报错，不回退到默认模型。
7. 配置错误只让受影响的条目失效，并留下诊断；没有可用模型是一种降级态，
   必须在 `/health` 可见，不能被隐藏的默认值静默替换。
8. `provider_meta` 由内核原样透传、不解释，只在 `model_message` 与 assistant 消息之间往返。

## 3. 分层与组件

| 层 | 组件 | 职责 |
|---|---|---|
| core | `StreamDelta`、`LogicalRequest` | 流帧契约、请求契约、`PROVIDER_META_KEY` |
| core | `session_log.derive_messages` | 把事实折成逻辑消息，携带 `provider_meta` |
| mechanisms | `AnthropicProvider` | Messages 线格式、SSE、消息与工具转换 |
| mechanisms | `OpenAICompatibleProvider` | Chat Completions 线格式与 SSE |
| mechanisms | `provider_registry` | 厂商名 → 构造器；唯一知道怎么 new 一个 provider 的地方 |
| mechanisms | `ProviderRouter` | 按 `request.model` 选 provider 实例 |
| capabilities | `ModelCatalog` | 模型描述注册表、provider 缓存、权威判定 |
| capabilities | `PluginContext.add_model_catalog` | 插件的注册口 |
| 装配根 | `app.build_app` | 建目录与路由、装载插件、确定权威来源与降级态 |
| shell | `web_api`、`web_state` | 下发模型清单、持久化选择、广播变化 |
| shell | `classic_adapter` | 广播会话模型变化 |
| shell | 界面资产、插件宿主 | 模型桥与样式桥 |
| plugins | `plugins/multi_model` | 配置解析、目录来源、下拉界面 |

## 4. 模型目录

### 4.1 数据结构

模型目录位于 `agent/capabilities/model_catalog.py`。它只有一个权威来源，语义是替换，不是合并：

```python
@dataclass(frozen=True)
class ModelEntry:
    id: str
    provider: str                 # provider_registry 的键："openai" | "anthropic"
    options_json: str = "{}"      # 规范化 JSON；目录不解释内容
    label: str = ""
    is_default: bool = False

    @classmethod
    def from_options(cls, *, id, provider, label="", options=None, is_default=False):
        ...

    @property
    def options(self) -> dict:    # 每次返回新副本
        ...

    @property
    def context_window(self) -> int:        # 未声明时为 0
        ...

    @property
    def compression_percent(self) -> int:   # 缺失或写坏时为 70
        ...

@dataclass(frozen=True)
class CatalogSnapshot:
    entries: tuple[ModelEntry, ...]
    default_id: str
    authoritative: bool
    source: str                   # "" 表示没有来源

    def entry(self, model_id: str) -> ModelEntry | None:
        ...

class ModelCatalog:
    def set_source(self, source, entries) -> Disposer: ...
    def snapshot(self) -> CatalogSnapshot: ...
    def ids(self) -> tuple[str, ...]: ...
    def default_id(self) -> str: ...
    def provider_for(self, model_id: str) -> ModelProvider | None: ...
```

`options` 用规范化 JSON 存，不存共享字典：`frozen` 只保证字段不能重新赋值，
字段里塞一个可变 dict 仍然能被调用方改写，那样的只读视图是假的。存 JSON、每次读返回副本，
也免掉了一个可变的缓存键。

`context_window` 与 `compression_percent` 是从 `options` 派生的模型元数据。上下文窗口是压缩阈值
与界面占用率的分母，压缩百分比是触发比例；窗口缺失按 `0`，百分比缺失或越界按 `70`。

`provider_for` 返回 `ModelProvider | None`，不是 `Any`：目录与 provider 之间的契约只有 `stream()`，
用基类表达就够，端口上不需要开任意扩展点。

### 4.2 行为

1. `set_source` 是替换。同一 `source` 再调一次就是配置变了，整批覆盖，不是追加。
   这与唯一权威一致：合并式注册表一旦真出现第二个来源，`default_id` 该听谁的就没法回答。
2. `entries` 可以是回调。每次 `snapshot()` 调用它，插件自行决定是否重读配置文件，
   配置改动不需要重启进程。
3. 第二个来源被拒绝。已存在不同 `source` 时 `set_source` 抛 `RuntimeError`。
   `PluginContext.add_model_catalog` 捕获它，写一条带两个来源名的诊断，返回空 disposer；
   插件装载不因此失败，首个来源保持不变。行为必须确定：装载顺序不是契约，但结果必须可审计。
4. 权威是算出来的，不是存下来的：`authoritative = len(有效条目) > 0`。
   把布尔值固化在登记那一刻，配置从 3 条改成 0 条时它不会跟着变，权威就会指着一个空目录。
5. `entries` 回调失败表示"这次没读到"：快照沿用上一份好条目；一份都没有时结果为空。
   诊断带来源名与异常文本。重复 id 是配置错误，不是临时读失败：`set_source` 以 `ValueError`
   拒绝该批，`snapshot()` 则沿用上一份好配置。
6. provider 缓存按整批重建。指纹是有序的 `(id, provider, options_json)` 元组；指纹一变，
   丢掉全部缓存实例，下一次查询只重建需要的那一个。条目数是十几个，重建成本可忽略，
   换来的是没有"指纹算错拿了旧实例"这类难复现的问题。
7. `Disposer` 触发时清空该来源的条目与全部 provider 实例。generation 计数器保证旧 disposer
   不会清掉后来登记的来源。
8. 未知 `provider` 的条目在规范化阶段被跳过并留痕（`provider_registry` 对未知 kind 抛 `ValueError`）。
9. `id` 为空、或不是 `ModelEntry` 的值，跳过并留痕；单条 `options_json` 写坏只让该条目的选项为空。
10. `default_id` 取第一条 `is_default`，没有则取第一条；目录为空时为 `""`。

### 4.3 插件扩展点

`PluginContext` 新增（与 `add_panel` / `add_context_source` 同位阶）：

```python
def add_model_catalog(self, entries) -> Disposer
```

`PluginContext` 用插件名作为 `source` 调 `catalog.set_source(self.name, entries)`，
并把返回的 disposer 收进自己的回收表。入参是条目序列或取条目的回调；
插件不必 import 任何内核实现，也不构造 provider。

`PluginHost` 构造参数增加 `model_catalog`，由装配根创建并注入。

## 5. Provider 注册表

注册表位于 `agent/mechanisms/provider_registry.py`：

```python
def build_provider(kind: str, options: Mapping[str, Any]) -> ModelProvider
def known_kinds() -> tuple[str, ...]
```

1. 内部是一张 `kind → 构造器` 的映射，两行：`openai` 与 `anthropic`。
2. 新增一个厂商 = 新增一个适配器文件 + 映射里加一行；不改路由、不改目录、不改插件。
3. `kind` 未知时抛 `ValueError(kind)`，由调用方决定是"跳过该条目"还是"启动失败"。
4. 选项键由各构造器自己解释；注册表只做分发与过滤。每种 kind 有白名单，
   配置里多写一个键不会让构造器因 `unexpected keyword` 报错：
   - `openai`：`base_url`、`api_key`、`model`、`timeout`、`replay_history_reasoning`、`extra_headers`；
   - `anthropic`：`base_url`、`api_key`、`model`、`max_tokens`、`thinking`、`thinking_budget_tokens`、`anthropic_version`、`timeout`、`extra_headers`。
   值为 `None` 的键被丢掉，让构造器用自己的默认值。

## 6. Provider 路由

路由位于 `agent/mechanisms/provider_router.py`：

```python
class ProviderRouter(ModelProvider):
    def __init__(self, *, default, resolve, allowed_ids=(), default_id="",
                 fallback_to_default=False): ...
    def reload_policy(self, *, allowed_ids, default_id, fallback_to_default): ...
    def reload_default(self, provider): ...
    @property
    def model(self) -> str: ...
    @property
    def allowed_models(self) -> tuple[str, ...]: ...
    @property
    def default_provider(self) -> ModelProvider: ...
    def stream(self, request): ...
```

规则：

1. `mid = request.model or default_id`；`mid` 为空时直接用 `default`。
2. `provider = resolve(mid)`；命中则调用 `provider.stream()`。目录 id 是路由键，
   线格式模型名归 provider（`options.model`）。两者可能不同，因此命中目录时 router
   先把 `request.model` 换成实例的线格式模型名，再发请求。
3. 未命中、`fallback_to_default` 为真且 `mid in allowed_ids` 时用 `default`。
   这个开关是给没有权威目录的嵌入方用的策略项；标准装配传 `false`。
4. 其余情况抛 `ModelRequestError("未配置的模型：<id>")`，不静默替换模型。
5. `resolve` 是注入的回调，由装配根接到 `ModelCatalog.provider_for`。
   router 不读 ini、不 import 插件、不认识任何厂商名。
6. `model` 返回 `default_id`；没有默认 id 时返回 `default` 实例的模型名。
   它供 `ModelPort.name()` 与日志使用，不参与路由判定。
7. `reload_default(provider)` 在锁内替换默认实例，是唯一允许改 `default` 的入口。
8. `reload_policy(...)` 在插件装载完成、权威清单可知后刷新允许列表、默认 id 与回退开关；
   `default_provider` 只读地暴露当前默认实例。

## 7. Messages 适配

Messages 适配器位于 `agent/mechanisms/providers/anthropic.py`：

```python
class AnthropicProvider(ModelProvider):
    def __init__(self, *, base_url, api_key, model,
                 max_tokens=16000, thinking=True, thinking_budget_tokens=4096,
                 anthropic_version="2023-06-01", timeout=300.0,
                 extra_headers=None): ...
    def stream(self, request) -> Iterator[StreamDelta]: ...
```

### 7.1 请求

地址构造：

| 基址形态 | 结果 |
|---|---|
| 以 `/messages` 结尾 | 原样 |
| 以 `/v1` 结尾 | 补 `/messages` |
| 其它 | 补 `/v1/messages` |

请求头：`x-api-key`、`anthropic-version`、`content-type: application/json; charset=utf-8`。
配置里的额外请求头最后合并。

请求体：

```json
{
  "model": "model-id",
  "max_tokens": 16000,
  "stream": true,
  "system": "系统提示与各系统段合并后的文本",
  "messages": [],
  "tools": [
    { "name": "read_file", "description": "…", "input_schema": { "type": "object", "properties": {} } }
  ],
  "tool_choice": { "type": "auto" },
  "thinking": { "type": "enabled", "budget_tokens": 4096 }
}
```

约束：

1. 适配器完全不下发 `temperature`。思考模式下该参数不生效，下发只会多一个在不同网关
   含义不一致的字段。
2. `thinking` 的有效条件是 `budget_tokens >= 1024` 且 `max_tokens > budget_tokens`。
   任一不满足就关闭 thinking 并写一条 stderr 诊断，请求照常发出——配置瑕疵不该让整轮对话失败。
   关闭必须显式下发 `{"type":"disabled"}`：省略字段会保留网关的默认行为，可能继续思考；
   而思考模式下带 `tool_use` 的 assistant 消息必须回传 thinking 块，静默省略会让下一次工具轮直接 400。
3. Chat Completions 网关按官方文档忽略 `budget_tokens`，思考深度走 `output_config.effort`
   （`low` / `high` / `max`）。适配器不下发 `output_config`：Messages 端点会拒绝这个未知字段，
   而同一个适配器要服务两套协议。因此 `LogicalRequest.effort` 对本适配器不生效，
   网关侧取服务端默认（`high`）；要按档位调深度，就用同一模型的 Chat Completions 条目。
4. 思考模式 + 工具调用：两套协议都要求把本轮带 `tool_use` 的 assistant 消息里的 thinking 块
   原样回传。跨轮不要求回传，所以 `strip_stale_thinking` 只留本轮。本轮块丢了且补不回来
   （签名缺失被丢弃，或历史来自另一协议条目）时，`_tool_turn_missing_thinking` 让本次请求
   关掉 thinking，避免会话永久打不开。
5. `tools` 为空时不下发 `tools` 与 `tool_choice`。
6. `max_tokens` 是该 API 的必填项；条目没覆盖时用构造参数默认值。
7. `input_schema` 必须是带 `type` 的 object schema。`ToolRegistry.schemas()` 给的 `parameters`
   是「参数名 → 片段」的属性映射，先经 `agent/mechanisms/providers/tool_schema.py` 的共用
   `tool_parameters()` 规范化再下发；直接把它当 schema 会得到 `type: null`，
   Messages 端点报 `Invalid schema for function ...`（400）。Chat Completions 网关不校验这个字段，
   所以该缺陷只在 Messages 协议上暴露。
8. 图片支持 `source.type=base64`（`data:` URL）与 `source.type=url`（http(s)）。
   只认 base64 会让图片链接在 Messages 条目上静默消失，而同一张图在 Chat Completions 条目
   照常发送。

### 7.2 消息转换

拆成纯函数与最后的拼装两步，避免把「忠实折叠」和「下游硬约束修补」混在一处：

```python
def strip_stale_thinking(messages, turn_start): ...   # 只留本轮的 thinking 块
def drop_dangling_tool_results(messages): ...          # 删掉没有对应 tool_use 的 tool_result
def _to_anthropic_messages(messages, turn_start, *, keep_thinking=True): ...
```

映射表：

| 逻辑消息 | 线格式 |
|---|---|
| `role=system` | 抽出正文，按出现顺序拼进顶层 `system`，用空行分隔 |
| `role=user` 且 `content` 为字符串 | `{role:"user", content:[{type:"text", text}]}` |
| `role=user` 且 `content` 为多模态数组 | `text` 原样；`image_url` 的 data URL 拆成 `{type:"image", source:{type:"base64", media_type, data}}`，http(s) URL 转成 `url` 源 |
| `role=assistant` | `content` 非空时产出 `text` 块；`tool_calls` 逐个产出 `tool_use` 块 |
| `role=tool` | 转成 `role:"user"` 且 `content:[{type:"tool_result", tool_use_id, content}]` |
| assistant 的 `provider_meta.anthropic.thinking_blocks` | 仅当该消息下标 `>= turn_start` 且本次请求开启 thinking 时，按原顺序插到 content 最前 |

修补规则（都是纯函数，可单测）：

1. 连续多条 `role=tool` 的消息合并进同一条 `role:"user"` 的 content 数组，保持顺序。
2. 相邻且角色相同的 user 消息同样合并，避免连续同角色被拒。
3. 工具结果为空时补一个占位文本，保证 `content` 非空。
4. 第一条必须是 `user`：前导的 assistant 消息直接丢弃（它们没有待回答的 `tool_result`）。
5. 没有对应 `tool_use` 的 `tool_result` 丢弃：留着会被 API 拒绝，整段会话打不开。
6. 同一请求内 `tool_use.id` 重复时，从第二次起追加 `_2`、`_3` 后缀；
   assistant 的 `tool_use` 与对应的 `tool_result` 必须同时改名，否则配对断裂。
7. `turn_start` 之前的 assistant 消息不带 thinking 块；thinking 关闭时任何消息都不带。

### 7.3 流事件映射

SSE 按行解析 `data:` 载荷。事件类型取载荷里的 `data.type`，不读 `event:` 行：
两处各存一份"这是什么事件"，迟早会漂移。`event:` 行只用于跳过，不作判据。

| `data.type` | 处理 |
|---|---|
| `message_start` | 记 `usage.input_tokens` / `cache_read_input_tokens` / `cache_creation_input_tokens`；缺失按 0 |
| `content_block_start` | 按 `index` 建块：`text` / `thinking` / `tool_use`（记 `id` 与 `name`；`input` 非空则作为初值）。起始文本与思考内容立即产出 |
| `content_block_delta` | `text_delta` → `kind="text"`；`thinking_delta` → `kind="reasoning"`；`signature_delta` 累积 `delta.signature`；`input_json_delta` 累积 `partial_json` |
| `content_block_stop` | `tool_use` 块解析 JSON 转 `ToolCallRequest`；`thinking` 块记录 `{thinking, signature}`，缺签名时丢弃，有正文则写一条警告 |
| `message_delta` | 记 `stop_reason` 与 `usage.output_tokens` |
| `message_stop` | 结束本流 |
| `error` | 抛 `ModelRequestError(error.message)`，文案截断到 800 字符 |
| `ping` | 忽略 |

`input_json_delta` 归并规则：

1. 按块的 `index` 累积 `partial_json`；`content_block_stop` 时一次性解析。
2. 解析失败时退化为空参 `{}`，调用仍发出，错误由工具侧暴露。
3. `tool_use` 的 `id` 为空时用 `call_<随机>` 兜底，与 Chat Completions 适配器同源。

`stop_reason` 只进诊断日志，不扩展流帧契约：`StreamDelta` 没有也不新增
`finish_reason`，与 Chat Completions 适配器保持一致。

### 7.4 流末顺序

固定顺序，便于模型模块按类型收集：

1. 文本与推理增量边到边出（流中实时产出，不攒列表）。
2. `kind="meta"`：仅当本轮有 thinking 块且存在工具调用时产出，
   载荷为 `{"anthropic": {"thinking_blocks": [...]}}`。没有工具调用时签名无处回传，
   不必落盘。
3. `kind="tool_call"`：按块 `index` 升序逐个产出。
4. `kind="usage"`：映射后的用量；所有字段都为 0 时不产出。

### 7.5 usage 映射

```text
prompt_tokens            = input_tokens + cache_read_input_tokens + cache_creation_input_tokens
completion_tokens        = output_tokens
prompt_cache_hit_tokens  = cache_read_input_tokens
prompt_cache_miss_tokens = input_tokens + cache_creation_input_tokens
```

字段名与 Chat Completions 适配器一致，界面与累计器无需分支。

### 7.6 错误映射

| 状态码 | 提示 |
|---|---|
| 400 | 请求参数无效，请检查模型与参数配置。 |
| 401 | 认证失败，请检查 API Key。 |
| 403 | 无访问权限，请检查 Key 的权限范围。 |
| 404 | 模型或接口不存在，请检查 base_url 与模型 id。 |
| 413 | 请求体过大，请减少历史图片或上下文。 |
| 429 | 请求过于频繁，请稍后再试。 |
| 500 | 模型服务端错误，请稍后再试。 |
| 529 | 模型服务过载，请稍后再试。 |

响应体里的 `error.message` 附在提示后，截断到 800 字符。Messages 的错误提示独立成表，
不与 Chat Completions 的表混用；未知状态码返回原始 HTTP 响应体，截断到 8000 字符。

## 8. thinking 签名回传

Messages 的 extended thinking 在带工具的同轮循环里要求把 thinking 块（含 `signature`）
原样回传，否则同一轮的后续请求会被拒绝。事实里现有字段 `reasoning_content` 只有文本，
签名会丢。

方案：在 `model_message` 事实里增加一个内核不解释的 `provider_meta`。

1. `agent/core/model_call.py`：导出 `PROVIDER_META_KEY = "provider_meta"`；
   `StreamDelta` 增加 `meta: Optional[Dict[str, Any]] = None`，`kind` 增加取值 `"meta"`。
2. `agent/core/modules/model_mod.py`：收集 `kind=="meta"` 的载荷，合并后写入
   `model_message[PROVIDER_META_KEY]`；为空时不写该字段。
3. `agent/core/session_log.py` `derive_messages()`：`model_message` 带该键时原样带进
   assistant 消息。读方与写方引用同一个常量，不各写一遍字符串。
4. `agent/mechanisms/providers/openai.py` 的 `_to_wire_messages` 必须
   `msg.pop(PROVIDER_META_KEY, None)`，避免未知字段发给 Chat Completions 网关。
5. 回放范围：只有消息下标 `>= request.turn_start` 时才带 thinking 块；
   跨用户轮直接丢弃，防止历史请求带上过期签名。

`provider_meta` 的约束：

1. 必须可 JSON 序列化，落盘与读取两侧都经过既有 `default=str` 兜底。
2. 内核不读取其内部结构，不参与分段统计、token 估算与压缩判定。
3. 压缩器丢弃被压缩区间的消息时，其 `provider_meta` 一并丢弃。
4. 只存 thinking 块的 `{thinking, signature}`，不存整段响应；不做截断——
   截断会让签名失效，回传反而报错。
5. 它是落盘格式的**可选**新增键，只前滚。旧日志没有该键按"无 thinking 块"处理；
   读取方忽略未知的厂商子键；不需要迁移或回滚。任何读方不得要求该键存在。

## 9. 装配根接线

### 9.1 接线

`agent/app.py` 的 `build_app()`：

1. 创建 `ModelCatalog`，把服务名 `SERVICE_MODEL_CATALOG` 加进
   `agent/core/context.py` 的进程级服务词汇表，并注入 `PluginHost`。
2. 从一开始就把 `ProviderRouter` 注册为 `SERVICE_PROVIDER`，不直接暴露裸 provider：
   - `default`：入口提供的 provider；裸装配时用 echo provider；
   - `resolve`：`catalog.provider_for`；
   - `allowed_ids` 与 `default_id`：初值，插件装载完成后经 `reload_policy` 重算；
   - `fallback_to_default`：标准装配为 `false`。
3. `plugin_host.load_manifest(...)` 之后计算一次 `app.model_config_state`：

   | 取值 | 判据 |
   |---|---|
   | `"catalog"` | 目录权威且 `entries` 非空 |
   | `"config"` | 目录不权威，但装配时显式注入了 provider |
   | `"none"` | 两者都不成立 |

4. `"catalog"` 时用目录的 `ids()` 与 `default_id()` 覆盖 `app._available_models`
   与 `live_state.default_model`；其余情况保留装配时确定的值。
5. 收敛陈旧值：`live_state.get_model(cid)` 不在 `available_models()` 里时，
   回落到 `default_id` 并写回、同时写一条诊断。插件改配置后，旧标签页不会继续使用
   已删除的 id 并触发错误。
6. `MissingProvider` 的 `stream()` 只抛 `ModelRequestError("未配置任何模型")`。
   报错文案不含插件目录名：`mechanisms` 里出现插件名会直接命中原有的内核架构约束门禁，
   也会把"去哪配"这种运维信息固定进内核。
7. Web 入口与壳层不做各自的凭据预检、不直接构造 provider，统一走 `build_app`。
   没有可用模型时 shell 仍启动，打印一条指向设置路径的警告，并在 `/health` 报 `"none"`；
   装配过程抛出的意外异常仍以非零码退出。没有可用模型是一种可见的降级态，
   进程不会用隐藏的默认值替代它。
8. `/health` 增加：

   ```json
   "model_config": { "source": "catalog|config|none", "authoritative": true, "degraded": false }
   ```

   任何"启动了但模型不可用"的状态必须在健康检查里体现，不能只留一行日志。

### 9.2 回退矩阵

| 插件状态 | 显式注入 provider | 默认模型 / `default` 实例 | `model_config_state` | `/health.allowed_models` |
|---|---|---|---|---|
| 启用且有有效条目 | 有或无 | 目录 `default_id`；`default` 实例不参与路由 | `catalog` | 目录 ids |
| 启用但 0 条有效条目 | 无 | 无（`MissingProvider`） | `none` | `[]` |
| 启用但 0 条有效条目 | 有 | 注入的 provider | `config` | provider 的模型清单 |
| 停用或缺失 | 无 | 无（`MissingProvider`） | `none` | `[]` |
| 停用或缺失 | 有 | 注入的 provider | `config` | provider 的模型清单 |
| 启用且有条目，但条目全部无效 | 无 | 无（`MissingProvider`） | `none` | `[]` |

最后一行是重点：插件"启用了"不等于"可用"。权威判定看的是有效条目数，不是启用开关。

`config.ini` 不携带模型凭据或模型清单。`"config"` 态只在装配时显式注入 provider
（嵌入方或测试）时建立；运行期卸载插件会调 `refresh_model_config()`，
把应用置为 `"none"` 并装上 `MissingProvider`，不会回到注入的 provider。

权威模式下 `default` 实例基本用不到——每轮请求都带目录 id，`resolve` 必然命中；
它只在允许列表为空或回退开关打开时兜底。因此权威模式下 `default` 没有凭据也不影响对话，
`default` 可以是 `MissingProvider`。

### 9.3 设置页保存

`settings_panel.apply_host()` 不改 provider 属性。router 包装之后，
`getattr(app, "provider")` 拿到的是 router，`hasattr(provider, "base_url")` 为假，
直接写属性会被静默跳过——设置页显示"已保存"，进程里还是旧模型。

模型配置的路径是：

1. 插件声明 `settings-schema.json`，设置页按条目渲染表单，可新增、删除、逐条改。
2. 保存只重写 `[model:*]` 节，其它节逐字节保留；密钥字段留空表示沿用原值。
3. 写盘后插件被卸下再装载，`sync_plugins` 调 `app.refresh_model_config()`：
   - 目录权威：刷新 `_available_models`、`live_state.default_model`，并调 `router.reload_policy`；
   - 目录不权威：置 `model_config_state = "none"`，清空清单与默认 id，经 `reload_default`
     装上 `MissingProvider`。
4. `app.reload_model_config()` 只回答当前模型来源，不从 `config.ini` 重建 provider；
   它不是 provider 工厂。
5. 设置页不提供内核模型节；模型条目只由多模型插件表单维护。
   单测分别锁住插件保存路径与权威重算。

## 10. 插件

### 10.1 目录

```text
plugins/multi_model/
  plugin.py
  plugin-config.ini
  plugin-config.ini.example
  plugin-meta.json
  settings-schema.json
  ui/model-picker.js
  ui/model-picker.css
```

`plugins.ini` 增加 `[plugin:multi_model]` 节。
`plugin-config.ini` 列入 `.gitignore`（`plugins/multi_model/plugin-config.ini`），
真实配置只留在工作区；`git ls-files` 可确认历史与索引里都没有真实配置。

目录名就是插件身份：它出现在 URL、上下文段键与日志前缀里。`multi_model` 说的是"能力"，
不是一个具体实现。内核里不得出现这个名字；架构门禁会按词边界扫描每个插件目录名。

### 10.2 配置格式

```ini
[model:chat]
provider = openai
base_url = https://api.example.com
api_key = sk-…
model = chat-model
label = Chat
context_window = 128000
compression_percent = 70
default = 1

[model:messages]
provider = anthropic
base_url = https://api.example.com/messages
api_key = sk-…
model = messages-model
label = Messages
context_window = 200000
compression_percent = 70
max_tokens = 16000
thinking = 1
thinking_budget_tokens = 4096
```

### 10.3 解析规则

1. 节名 `[model:<id>]`，`id` 是请求与界面里的唯一标识。
2. `model` 缺省等于 `id`。
3. `provider` 缺省 `openai`；不在 `known_kinds()` 里的值使该条目无效，并留一条列出可用值的诊断。
4. `api_key` 或 `base_url` 缺失使该条目无效。模板占位符（例如 `sk-请替换`）不算已配置，
   否则目录会先接管路由，直到请求打到网关才报鉴权错误。
5. `context_window` 必填且为正整数，是压缩与占用率的分母。
6. `compression_percent` 缺省 `70`，必须是 10–90 的整数。
7. `default = 1` 至多一个生效；没有时取第一条有效条目；多个时第一个生效，其余按非默认处理并留痕。
8. `max_tokens`、`thinking`、`thinking_budget_tokens` 只对 `anthropic` 条目生效；
   写坏使该条目无效，写在 `openai` 条目上则忽略。
9. 任一条目解析失败只影响该条目。重复节或整个文件写坏是文件级错误：
   整份文件不产出条目，只给一条 `id=""` 的无效记录。
10. 配置用 `utf-8-sig` 读。Windows 编辑器保存的 UTF-8 可能带 BOM，
    用 `utf-8` 读会得到一个指不到根因的 `MissingSectionHeaderError`。
11. 每条诊断都必须能定位：`[plugin:multi_model] <文件路径> [model:<id>] <键> 无效：<原因>`。
    只写"配置有误"无法定位到文件、条目与键。

### 10.4 register

`register(ctx)` 做三件事：

1. `ctx.add_model_catalog(entries)`
   - `entries` 是回调，每次重读 `plugin-config.ini`，返回 `ModelEntry` 列表；
   - 不传工厂、不构造 provider——厂商分发在 `provider_registry` 里。
2. `ctx.add_route("GET", "catalog", handler)`：
   返回 `{"ok":true,"models":[{"id","label","provider","context_window","default"}],"default":id,"invalid":[{id,reason}]}`。
   不返回 `api_key` 与 `base_url`。`invalid` 是运维面：坏条目不能只活在日志里。
3. `ctx.add_boot_script("ui/model-picker.js")`。

`register` 返回 disposer 列表，由插件宿主统一回收。插件启动时解析一次配置，
坏文件在用户打开下拉之前就留痕。

样式不走后端：`model-picker.js` 第一行调
`window.aiAgentShell.styles.load("ui/model-picker.css")`。理由见 11.2.2。

## 11. 壳层与界面

### 11.1 清单来源

`WebApi.available_models()` 返回 `app.available_models()`：目录权威时读目录 `ids()`，
非权威时读装配时注入的清单。`/health` 与 `ui-state` 都从这里取，
响应里永不出现凭据字段。`/health` 另给 `model_labels`（id → 显示名），
让壳层不必认识插件也能渲染标签。

### 11.2 界面桥

#### 11.2.1 模型桥

壳层在 `agent/shell/web/web_assets/classic/js/plugins/host.js` 里、与
`window.aiAgentPlugins` 相邻处定义：

```js
window.aiAgentShell = window.aiAgentShell || {};
window.aiAgentShell.models = {
  list:     function () { /* → Promise<[{id,label,provider}]> */ },
  current:  function () { /* → string */ },
  select:   function (id) { /* → Promise<boolean> */ },
  onChange: function (fn) { /* → 取消订阅函数 */ }
};
```

不挂在 `window.AIA` 上：`AIA` 是 `image-lightbox.js` 的附件/灯箱命名空间
（`AIA.buildMsgAttachStrip` 等），把模型塞进去就是"同名不同物"。
`aiAgentShell` 是壳层公共契约，与 `aiAgentPlugins` 平级、职责互补。

`list()` 读 `/health`：`allowed_models` 给 id，`model_labels` 给显示名；
每项是 `{id, label, provider}`，`provider` 为空——壳层不认识插件目录，
协议与厂商由插件自己的 `/catalog` 端点补充。

约束：

1. 插件在 `#modelPickerSlot` 内创建按钮与菜单，样式来自它自己的 CSS。
2. 插件不读壳层内部变量，不拼 `/api/chat/send`，不改页头元素。
3. `select` 由壳层负责：先乐观更新界面，写 `/api/chat/ui-state`，失败时回滚；
   插件只更新自己的按钮文字。
4. 桥是壳层的公共契约，插件停用后桥仍在，只是没有订阅者与下拉。
5. 桥本身不持有状态：`current()` 读当前标签页的模型字段，`onChange` 只是转发。
   多份"当前模型"必然分叉。

#### 11.2.2 样式桥

插件资产有两条送达路径，模型下拉两条都用不上：

| 路径 | 端点 | 注入时机 |
|---|---|---|
| 面板脚本 / 面板样式 | `/api/plugin/<插件>/_asset/<相对路径>` | 面板打开时（`loadPluginStyle`） |
| 开屏脚本 | `/api/boot-scripts` | 页面加载 |
| 开屏样式 | 无 | — |

下拉按钮在输入区、不属于任何面板，所以它需要在开屏阶段就生效的样式。
不新增后端扩展点（`add_boot_style` + `/api/boot-styles` 要动 `PluginContext`、
`contributions`、`web_api`、`web_routes` 四处，只为送一个 `<link>`），
改为把壳层已有的 `loadPluginStyle` 暴露到桥上：

```js
window.aiAgentShell.styles = {
  load: function (relPath) { /* → Promise<boolean>；relPath 是插件目录内相对路径 */ }
};
```

1. 壳层用 `window.aiAgentPluginCurrent` 拼
   `/api/plugin/<插件>/_asset/<relPath>`，插件不自己拼 URL、不碰 `document.head`。
2. 复用既有去重表 `_pluginStylesLoaded`，同一路径只注入一次。
3. 注入的 `<link>` 带 `data-plugin-style="<插件名>"`。
4. `applyPluginsChanged` 摘掉 `data-plugin-style` 不在已装载名单里的 `<link>`，
   停用的插件不残留样式表。
5. 只接受插件目录内的相对路径：开头的 `/` 被剥掉，URI scheme 与任何 `..`、`.` 段被拒绝；
   服务端解析后还会比对插件目录，不做字符串前缀判断。
6. 路径被拒或加载失败时，`load` 解析为 `false`，不注入任何东西。

### 11.3 下拉与广播

1. `agent-ui.html` 只提供 `#modelPickerSlot` 挂载点。内建的 `#modelPicker`、
   `#modelPickerBtn`、`#modelPickerMenu` 及其 JS 与 CSS 都不存在；挂载点是唯一的模型入口。
2. 页头保留 `#hdrModel`，由 `applyModel` 写 `模型: <label>`。
3. `applyModel(id)` 的职责：
   - 写当前标签页的 `selectedModel`；
   - 写页头；
   - 通知 `aiAgentShell.models.onChange` 的订阅者。
   服务端下发的值即使不在本地缓存里也照常应用；真正的校验发生在服务端
   写入 `send` 或 `ui_state_put` 时。
4. 会话级持久化：`POST /api/chat/send` 与 `PUT /api/chat/ui-state` 的 `model` 字段
   继续写 `live_state`，值必须在清单内。
5. 广播：`ClassicAdapter.announce_model(cid, model)` 向全部 SSE 通道推
   `{"type":"conversation","conversation_id":cid,"model":model}`，
   与 `announce_plugins` 同构，不伪装成内核事件。
6. 触发点：`send` 与 `ui_state_put` 里模型值发生变化时。
7. 前端 SSE 的 `conversation` 分支处理 `ev.model`：
   只有发起方写服务端，其它标签页只更新页头与本地标签页字段。
   接收方再写一次 `live_state` 会产生重复写与竞态；显示同步与状态写入必须分开。
8. 时序：开屏脚本可能先于会话恢复加载，所以插件初始化时主动 `current()` 取一次，
   同时订阅 `onChange`，不能只等事件。
9. 插件停用时，`applyPluginsChanged` 清空 `#modelPickerSlot` 的内容，并摘掉它的样式表。
   不清空的话，按钮会留在页面上，点了调的是一个不存在的端点。
10. 重新启用不需要刷新页面：`applyPluginsChanged` 摘掉插件的脚本节点并清掉去重记录，
    `prunePluginMounts` 摘掉它的 DOM，下拉脚本自己也会先拆除旧监听再重建。
    这条清理路径失效时，刷新页面是兜底。

### 11.4 设置页

1. 设置页不提供内核「模型」节；模型条目只由多模型插件表单维护。
2. 模型条目由插件的 `settings-schema.json` 驱动结构化编辑（新增、删除、逐条改），
   保存时只替换 `[model:*]` 节，其它节逐字节保留。
3. 保存接口只写插件自己的节，不写内核配置。
4. schema 声明协议枚举、数值字段，以及 `max_tokens`、`thinking`、`thinking_budget_tokens`
   对 `anthropic` 条目的条件显隐。密钥字段只回显是否已配置，留空表示沿用原值。

## 12. 文件清单

| 文件 | 职责 |
|---|---|
| `agent/mechanisms/providers/anthropic.py` | Messages 适配器 |
| `agent/mechanisms/providers/openai.py` | Chat Completions 适配器；从线格式消息里剥离 `provider_meta` |
| `agent/mechanisms/providers/tool_schema.py` | 共用的工具 schema 规范化 |
| `agent/mechanisms/providers/sse.py` | SSE 行解析与流总超时 |
| `agent/mechanisms/provider_registry.py` | kind → 构造器映射 |
| `agent/mechanisms/provider_router.py` | 模型 id 路由与默认实例热替换 |
| `agent/capabilities/model_catalog.py` | 目录、provider 缓存、权威判定 |
| `agent/capabilities/plugin_context.py` | `add_model_catalog` |
| `agent/capabilities/plugins.py` | `PluginHost(model_catalog=...)` |
| `agent/app.py` | 装配：目录、router、权威态 |
| `agent/app_model_policy.py` | 可用清单、陈旧模型收敛、上下文窗口与压缩阈值 |
| `agent/core/model_call.py` | `StreamDelta.meta`、`PROVIDER_META_KEY` |
| `agent/core/modules/model_mod.py` | 收集 `meta` 增量写入 `model_message` |
| `agent/core/session_log.py` | 把 `provider_meta` 带进 assistant 消息 |
| `agent/core/context.py` | `SERVICE_MODEL_CATALOG` |
| `agent/shell/web/web_api.py` | 模型清单、标签、`/health` 的模型配置态 |
| `agent/shell/web/web_state.py` | `ui-state` 的模型读写与广播 |
| `agent/shell/web/web_chat.py` | 发送时的模型校验 |
| `agent/shell/web/web_routes.py` | 模型相关端点的路由分发 |
| `agent/shell/web/server.py` | 无模型时的启动警告 |
| `agent/shell/settings_panel.py` | 宿主设置落位；无模型节 |
| `agent/shell/plugin_settings.py` | 插件同步与目录重算 |
| `agent/shell/classic_adapter/channel.py` | `announce_model` |
| `agent/shell/classic_adapter/contract.py` | 会话事件契约 |
| `agent/shell/web/web_assets/classic/agent-ui.html` | `#modelPickerSlot`、`#hdrModel` |
| `agent/shell/web/web_assets/classic/js/plugins/host.js` | `aiAgentShell.models` 与 `aiAgentShell.styles` |
| `agent/shell/web/web_assets/classic/js/composer/pickers.js` | `applyModel` |
| `agent/shell/web/web_assets/classic/js/composer/model-sync.js` | 会话模型回填、允许列表缓存 |
| `agent/shell/web/web_assets/classic/js/chat/stream.js` | SSE `conversation` 分支 |
| `plugins/multi_model/plugin.py` | 配置解析、目录来源、`/catalog`、开屏脚本 |
| `plugins/multi_model/plugin-config.ini` | 真实配置，不入库 |
| `plugins/multi_model/plugin-config.ini.example` | 不含凭据的配置模板 |
| `plugins/multi_model/plugin-meta.json` | 插件身份与设置页入口 |
| `plugins/multi_model/settings-schema.json` | 结构化设置表单 |
| `plugins/multi_model/ui/model-picker.js` | 输入区模型下拉 |
| `plugins/multi_model/ui/model-picker.css` | 下拉样式 |
| `plugins.ini` | `[plugin:multi_model]` |
| `docs/subsystems/plugins.md` | 插件扩展点与壳层桥 |
| `docs/subsystems/multi-model.md` | 插件配置与目录行为 |
| `tests/test_anthropic_provider.py` | Messages 适配测试 |
| `tests/test_provider_router.py` | 路由测试 |
| `tests/test_model_catalog.py` | 目录测试 |
| `tests/test_multi_model_plugin.py` | 插件测试 |
| `tests/test_provider_meta.py` | 签名透传测试 |
| `tests/test_model_provider.py` | 线格式消息测试 |
| `tests/test_settings_panel.py` | 设置页与插件表单测试 |
| `README.md` | 单元测试用例数 |
| `docs/unit-tests.md` | 生成的测试索引 |

## 13. 测试与验收

### 13.1 单元测试

`tests/test_anthropic_provider.py`：

1. SSE：文本增量、thinking 与 `signature`、`tool_use` 分片归并、`message_delta` 用量、
   `error`、`ping`、缺 cache 字段按 0。
2. 消息转换：system 合并到顶层、连续 `tool_result` 合并、图片 data URL 与 http(s) URL、
   assistant `tool_calls`、前导 assistant 被丢弃、悬空 `tool_result` 被丢弃、
   重复 `tool_use.id` 加后缀且配对同步改名。
3. `provider_meta` 只在本轮回放，跨轮丢弃；thinking 关闭时不下发任何块；
   缺签名的 thinking 块被跳过并留警告。
4. 地址构造、HTTP 错误映射、`thinking` 预算不足时降级为关闭。
5. 事件类型只认 `data.type`：删掉 `event:` 行后仍能正确解析。

`tests/test_provider_router.py`：按 `request.model` 选实例、模型为空时用默认、
允许列表内模型的 `fallback_to_default` 行为、未知模型报错、`reload_default` 后下一请求生效、
`reload_policy` 更新、线格式模型名替换。

`tests/test_model_catalog.py`：`set_source` 替换语义、第二个来源抛 `RuntimeError`、
`authoritative` 随当前条目数变化并在目录清空时翻转、回调失败沿用上一份好条目、
重复 id 被拒绝且不覆盖旧目录、条目变化后整批重建 provider、disposer 注销并清缓存、
`options` 返回副本。

`tests/test_multi_model_plugin.py`：文件缺失得到空目录且不刷诊断、缺省值与首条默认、
BOM 文件可读、`context_window` 必填且 `compression_percent` 校验范围、
`anthropic` 选项按类型解析并在 `openai` 条目上忽略、坏条目只影响自身、
占位密钥被拒、重复节使整份文件作废、`default` 取舍规则、`catalog` 响应不含凭据、
`register` 贡献三个 disposer 且热读配置。

`tests/test_provider_meta.py`：内核原样透传 `provider_meta`；未知子键被携带而不是被校验；
没有该键的旧日志仍能派生消息；`_to_wire_messages` 从线格式消息里剥离该键。

`tests/test_model_provider.py`：线格式消息构造、工具声明包装，以及思维链回传规则
（历史轮的工具消息保留键、内容清空；纯文本 assistant 消息摘键）。

`tests/test_settings_panel.py`：内核无模型节；插件 schema 渲染器遮蔽密钥、拒绝必填项为空、
保存保留其它节；宿主设置保存不碰模型目录。

### 13.2 集成与验收

1. `/health` 与 `ui-state` 返回目录 ids，响应体不含 `api_key` 与 `base_url`。
2. 插件停用后模型清单为空，`/health.model_config.source` 变为 `none`。
3. 没有有效模型时，Web 壳启动并打印警告，`build_app` 本身仍可构造，
   发送时得到明确的"未配置模型"错误。
4. 切换模型后页头模型名更新，同会话第二个标签页同步更新，且服务端只被写一次。
5. 未配置的模型 id 在 `send` 与 `ui_state_put` 都被拒绝。
6. `plugins/multi_model` 坏条目不影响其它条目与服务启动，`catalog` 端点的
   `invalid` 里能看到它。
7. 插件删掉当前模型后，旧标签页的下一次读取或发送回落到默认条目而不是报错。
8. 插件停用后，`#modelPickerSlot` 被清空、`data-plugin-style` 的 `<link>` 被摘除；
   重新启用无需刷新页面即可重建下拉。
9. `aiAgentShell.styles.load("../x.css")`、带 URI scheme 的路径与空路径都解析为 `false`
   且不注入；服务端资产路由另行拒绝越出插件目录的路径。
10. `python scripts/ci.py` 全绿；`check_imports.py` 与
    `check_architecture_hygiene.py` 通过（内核里不出现 `multi_model` 这个词）。

## 14. 边界与风险

1. `provider_meta` 里的 thinking 文本与 `reasoning_content` 存在重复存储。
   这是换取 thinking 块回传能力的代价；压缩与分段统计不读它。
2. 该键是落盘格式的可选新增键，只前滚；旧日志读不到它时按无 thinking 处理。
3. 模型 id 冲突会把请求路由到错误网关，因此重复 id 必须拒绝并留痕。
   `id` 是跨配置文件、界面、请求共用的唯一标识，不做别名。
4. 单条解析失败降级为「该条目无效」，不让服务起不来；文件级错误（例如重复节）
   让整份文件作废。一条有效条目都不剩时，`model_config_state` 变成 `none`，由 shell 报出来。
5. 壳层没有内建模型下拉。其它客户端必须改用 `aiAgentShell.models` 桥，
   不能依赖 `#modelPickerBtn`。
6. Messages 的 `max_tokens` 必填且必须大于 thinking 预算；不满足时关闭 thinking。
7. `effort` 对 Messages 条目不生效；按档位调深度需要同一模型的 Chat Completions 条目。
8. 设置页不提供内核模型节；模型只由多模型插件维护。
9. 每次 `snapshot()` 都会重读插件配置。当前规模下读盘成本可忽略；
   按 mtime 缓存会引入不必要的失效复杂度。
10. 插件重新启用依赖脚本与挂载点清理。这条路径退化时，下拉要刷新页面才会回来。

## 15. 工程约束

相关标准：[standards-alignment.md](standards-alignment.md)。

| 约束 | 落点 | 验证方式 |
|---|---|---|
| 依赖方向 | 新增文件全部落在既有层内；插件只向下依赖 | `check_imports.py` |
| 扩展只加文件 | 新厂商 = 适配器文件 + `provider_registry` 一行；插件不构造实例 | 审 + 用例 |
| 内核不知道插件名 | 插件名只出现在插件里；`MissingProvider` 文案不含任何路径 | `check_architecture_hygiene.py` |
| 装配点集中 | `build_app` 是唯一决定权威来源与降级态的地方 | 审 |
| 最小扩展 | 开屏样式复用既有 `loadPluginStyle`，不新增 HTTP 端点与贡献类型 | 文件清单 |
| 只读视图真不可变 | 条目存规范化 JSON；`options` 与 `snapshot` 返回副本与元组 | 改返回值后重读不变 |
| 少用 `Any` | `provider_for` 返回 `ModelProvider` 或 `None`；选项是唯一的字典 | 审 |
| 一物一名 | 函数按职责命名，不用有两种含义的缩写 | 审 |
| 折叠与修补分离 | `strip_stale_thinking` / `drop_dangling_tool_results` 都是纯函数 | 单测 |
| 契约版本化 | `provider_meta` 为可选新增键，旧日志免迁移 | 文档 + 单测 |
| 终态穷尽 | `model_config_state` 三态；`/health` 显式暴露 | 验收 |
| 真流式 | 文本/推理增量边到边出，不攒列表 | 审 |
| 状态归属单一 | 权威只有 `ModelCatalog`；前端没有模型种子；`live_state` 陈旧值在读取点收敛 | 单测 + `check_ui_js.py` |
| 并发 | `set_source` 原子替换引用；`snapshot` 快照一致 | 并发用例 |
| 不丢错误、要留痕 | 坏条目、回调异常、被拒的保存都带定位信息 | 单测 |
| 无全局豁免 | 没有为这套设计设置任何门禁豁免 | 审 |
| 键名不硬编码 | `PROVIDER_META_KEY` 由 core 导出，读写两侧共用 | 审 |
| 无遗留兼容层 | 没有内建下拉、别名或空守卫 | 审 + 文件清单 |
| 秘密不进版本库 | 真实配置被 `.gitignore` 覆盖 | `git ls-files` |
| 配置错误可定位 | `utf-8-sig`；诊断含文件、节、键、原因 | 单测（BOM 文件） |
| 配置漂移检查 | 插件真实配置的键与 `settings-schema.json` 双向比对 | `check_config_drift.py` |
| 降级可见 | `none` 在启动与 `/health` 都报出来；没有隐藏回退 | 验收 |
| 负向测试 | 重复 id、线格式不含 `provider_meta`、未知子键忽略、缺签名降级 | 单测 |
| 失败路径有测试 | BOM、坏条目、预算不足、悬空 tool_result、未配置模型 | 单测 |
| 覆盖率归属 | 插件与新增模块在 `agent`、`plugins` 的覆盖率口径内 | `check_coverage.py` |
| 复杂度预算 | 单文件上限由 `check_complexity.py` 执行；新文件不进白名单 | `check_complexity.py` |
| 文档与代码一致 | README 用例数、生成的测试索引、插件扩展点 | 门禁 |

### 15.1 `ModelCatalog` 并发

`ModelCatalog` 被 HTTP 请求线程与配置重载同时访问，"替换目录"必须是**原子**的：

1. 用 `threading.Lock`（不用 `RLock`：持锁期间只做一次引用替换或引用读取，不调公开方法；
   用 `RLock` 会把重入错误藏起来）。
2. `set_source(entries)`：锁外完成解析、校验、去重与 id 冲突检查，构造一个**完整的新元组**；
   进锁后只做一次引用替换；出锁。
3. `snapshot()`：进锁取当前元组引用，出锁；返回 `tuple`，不返回内部对象。
4. 不变量：任意一次 `snapshot()` 看到的条目集合要么全旧、要么全新，**不存在混合**；
   持锁期间不做 I/O、不调用 provider、不写 `live_state`。
5. 并发用例（`tests/test_concurrency.py`）：写者交替登记两组完整条目 `a` / `b`，
   读者持续取快照，断言每次快照只来自同一组、`authoritative` 与条目数一致、
   `default_id` 属于该快照；另一用例在读者取 provider 时轮换条目选项，
   断言缓存不会返回用另一组选项构造的实例。

### 15.2 前端不得有模型种子

壳层不得内置模型清单。`allowedModels` 只是从 `/health` 与 `ui-state` 填充的运行期缓存，
不是权威，也不预置任何模型名。`/health` 不可用时清单可以为空，
插件据此禁用下拉并在 `title` 里写明原因，不回退到任何硬编码列表。

`check_ui_js.py` 拒绝 `agent/shell/web/web_assets/**/*.js` 里的厂商模型 id 字面量；
负向用例喂一段含该字面量的脚本，断言失败。

### 15.3 模型展示归属

| 符号 | 归属 | 行为 |
|---|---|---|
| `#modelPickerSlot` | 壳层 | 只做挂载点；按钮与菜单由插件渲染 |
| `#hdrModel` | 壳层 | 只读展示 `模型: <label>` |
| `applyModel` | 壳层 | 写当前标签页的 `selectedModel`、写页头、通知订阅者 |
| 模型清单与点击校验 | 插件与服务端 | 插件发出点击的 id；服务端在 `send` 与 `ui_state_put` 拒绝清单外的 id |
| `#modelPicker` 及其菜单 | 不存在 | 没有内建下拉，也没有空守卫 |

模型**选择**归插件，模型**展示**归壳层；这是两个渲染点，不是互相竞争的所有者。

### 15.4 深不可变

- `ModelEntry` 为 `frozen=True`，`options` 存规范化 JSON；
- `options` 每次返回 `dict(entry.options)`；选项是扁平的配置值，改返回的字典改不到目录；
- `snapshot()` 返回 `tuple[ModelEntry, ...]`，调用方改不动内部；
- 单测：改 `options()` 返回值或 `snapshot()` 的元素后再次读取，结果不变。

### 15.5 负向断言

1. 重复 `id` 的两个条目：`set_source` 拒绝该批，原目录保留，错误里带来源名与 id。
2. 任一适配器产出的线格式都不得出现 `provider_meta`；它只是内核侧的键。
3. 未知的 `provider_meta` 子键 → 忽略且不抛错（前滚契约）。
4. thinking 块缺 `signature` → 不重放该块、留一条可见降级日志，不整体失败。

### 15.6 文档与配置

- `docs/unit-tests.md` 重生成并由 `gen_unit_tests_md.py --check` 核对；
- `docs/subsystems/plugins.md` 记录多模型的扩展点（目录权威、`aiAgentShell.models`、样式桥）；
- README 的用例数与实际一致；
- `plugins/multi_model/plugin-config.ini` 的键集合必须与 `settings-schema.json` 双向一致，
  由 `check_config_drift.py` 核对。

### 15.7 复杂度与覆盖率

覆盖率按 `agent` 与 `plugins` 统计，新模块与插件都落在这个口径内。
单文件复杂度上限由 `check_complexity.py` 执行，新文件不进复杂度白名单。
模块只有在统计口径内才算已覆盖。
