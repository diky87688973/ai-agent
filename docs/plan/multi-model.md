# 多模型配置方案

## 1. 背景与目标

核心模型链路：

- `mechanisms/model_provider.py` 提供各协议适配器；
- 模型配置只由 `plugins/multi_model/plugin-config.ini` 提供；
- 会话级模型选择落在 `live_state`，请求经 `LogicalRequest.model` 传给 provider。

目标：

1. 每条模型独立配置厂商、网关、凭据与模型 id，可跨网关、跨厂商。
2. 增加 原生协议 Messages API 适配，支持文本、工具调用、extended thinking。
3. 模型配置由插件管理，结构对齐知识库插件：自己的配置文件、端点、界面资产。
4. 界面提供模型下拉，切换后会话级持久化，并广播到同一会话的其它标签页与页头模型名。
5. 插件停用或多模型条目为空时，模型清单为空，不回退到内核配置。

## 2. 不变量

1. 模型配置的唯一权威是 `plugins/multi_model/plugin-config.ini`。
   该插件启用且至少一条有效条目时提供模型；没有有效条目时清单为空。
2. 凭据只留在服务端。任何 HTTP 响应都不下发 `api_key` 与 `base_url`。
3. 依赖方向不变：`shell → capabilities → mechanisms → core`。
   插件在包外，只能向下依赖；`mechanisms` 与 `core` 永不 import 插件，
   也**不得出现插件目录名**（`check_architecture_hygiene.py` 以词边界扫描，机检）。
4. provider 适配器只产出 `StreamDelta`。内核不认识 Native 的线格式、thinking 块或签名。
5. 插件停用即贡献消失：下拉、路由、开屏脚本与样式一并注销，回退路径不报错。
6. 未配置的模型 id 直接报错，不回退到默认模型。
7. 配置错快速失败，依赖不可用才允许降级；任何降级必须在 `/health` 可见。
8. `provider_meta` 由内核**原样透传、不解释**，只在 `model_message` 与 assistant 消息之间往返。

## 3. 分层与组件

| 层 | 组件 | 职责 |
|---|---|---|
| core | `StreamDelta`、`LogicalRequest` | 流帧契约、请求契约、`PROVIDER_META_KEY` |
| core | `session_log.derive_messages` | 把事实折成逻辑消息（含 `provider_meta` 透传） |
| mechanisms | `NativeProvider` | Native 线格式、SSE、消息与工具转换 |
| mechanisms | `provider_registry` | 厂商名 → 构造器；唯一知道"怎么 new 一个 provider"的地方 |
| mechanisms | `ProviderRouter` | 按 `request.model` 选 provider 实例 |
| mechanisms | `CompatibleProvider` | 兼容协议网关（现有实现，位置不变） |
| capabilities | `ModelCatalog` | 模型描述注册表 + provider 缓存 + 权威判定 |
| capabilities | `PluginContext.add_model_catalog` | 插件的注册口 |
| 装配根 | `app.build_app` | 建目录与路由，装载插件，确定权威来源与降级态 |
| shell | `web_api` / `classic_adapter` | 下发模型清单、持久化选择、广播变化 |
| plugins | `plugins/multi_model` | 配置解析、下拉界面 |

## 4. 模型目录

### 4.1 数据结构

新增 `agent/capabilities/model_catalog.py`。它只有**一个权威来源**，语义是"替换"，
不是"合并"：

```python
@dataclass(frozen=True)
class ModelEntry:
    id: str
    provider: str                 # provider_registry 的键："compatible" | "native"
    options_json: str = "{}"      # 规范化 JSON；目录不解释内容
    label: str = ""
    is_default: bool = False

    @classmethod
    def from_options(cls, *, id, provider, label="", options=None, is_default=False):
        ...

    @property
    def options(self) -> dict:    # 每次返回新副本，调用方改不到目录里的那份
        return json.loads(self.options_json)

@dataclass(frozen=True)
class CatalogSnapshot:
    entries: tuple[ModelEntry, ...]
    default_id: str
    authoritative: bool
    source: str                   # "" 表示没有来源

class ModelCatalog:
    def set_source(self, source: str,
                   entries: Sequence[ModelEntry] | Callable[[], Sequence[ModelEntry]]) -> Disposer
    def snapshot(self) -> CatalogSnapshot
    def ids(self) -> tuple[str, ...]
    def default_id(self) -> str
    def provider_for(self, model_id: str) -> ModelProvider | None
```

`options` 用规范化 JSON 存，不存共享字典：描述对象是 `frozen` 的，但字段里塞一个
可变 dict 仍然能被调用方改写，那就等于"只读视图"是假的。存 JSON、属性返回副本，
也免掉了一个可变的缓存键。

`provider_for` 的返回类型是 `ModelProvider | None`，不是 `Any`：目录与 provider
之间的契约只有 `stream()`，用基类表达就够，不需要在端口上开任意扩展点。

### 4.2 行为

1. `set_source` 是**替换**：同一 `source` 再调一次就是"配置变了"，整批覆盖，
   不是追加。这与不变量 1「唯一权威」一致——合并式注册表一旦真出现第二个来源，
   `default_id` 该听谁的就没法回答了，那是设计缺陷，不是功能。
2. `entries` 可以是回调。每次 `snapshot()` 调用它，插件自行决定是否重读配置文件，
   配置改动不需要重启进程。
3. **第二个来源被拒绝**：`set_source` 遇到已存在的不同 `source` 时抛 `RuntimeError`。
   `PluginContext.add_model_catalog` 捕获它，写一条带两个 `source` 名的 stderr 诊断，
   返回一个空的 disposer——插件装载不因此失败，首个来源保持不变。
   行为必须是确定的：不能"谁先装载谁生效"而不留痕，装载顺序不是契约。
4. **权威是算出来的，不是存下来的**：`authoritative = len(valid_entries) > 0`。
   不能把 `authoritative=True` 固化在设置那一刻——配置文件从 3 条改成 0 条时，
   布尔值不会跟着变，权威就会指着一个空目录。
5. `entries` 回调抛异常时按空表处理，并写一条带 `source` 与异常文本的 stderr 诊断。
   一个插件的配置解析错误不能让整条模型链路不可用；但"吞掉"必须留痕。
6. **provider 缓存按整批重建**：`entries` 序列（顺序、id、`options_json`、`provider`）
   任一变化，就丢光全部缓存实例并重建需要的那一个。条目数是十几个，重建成本可忽略，
   换来的是没有"指纹算错导致拿了旧实例"这类难以复现的问题。
7. `Disposer` 触发时清空该来源的条目与全部 provider 实例。
8. 未知 `provider` 的条目在快照期被跳过并留痕（`provider_registry` 抛 `ValueError`）。
9. `default_id` 取第一条 `is_default`，没有则取第一条；`entries` 为空时为 `""`。

### 4.3 插件扩展点

`PluginContext` 新增（与 `add_panel` / `add_context_source` 同位阶）：

```python
def add_model_catalog(self, entries) -> Disposer
```

`PluginContext` 用插件名作为 `source` 调 `catalog.set_source(self.name, entries)`，
并把返回的 disposer 收进自己的回收表。入参只有条目或取条目的回调，
插件不必 import 任何内核实现，也不构造 provider。
`PluginHost` 构造参数增加 `model_catalog`，由装配根创建并注入。

## 5. Provider 注册表

新增 `agent/mechanisms/provider_registry.py`：

```python
def build_provider(kind: str, options: Mapping[str, Any]) -> ModelProvider
def known_kinds() -> tuple[str, ...]
```

1. 内部是一张 `kind → 构造器` 的映射，`compatible` 与 `native` 两行。
2. 新增一个厂商 = **新增一个适配器文件 + 映射里加一行**；不改路由、不改目录、
   不改插件。这是 `A4` 的判据：扩展成本不随厂商数增长。
3. `kind` 未知时抛 `ValueError(kind)`，由调用方决定是"跳过该条目"还是"启动失败"。
4. 选项键（`base_url` / `api_key` / `model` / `max_tokens` / `thinking` …）由各构造器
   自己解释；注册表只做分发。

## 6. Provider 路由

新增 `agent/mechanisms/provider_router.py`：

```python
class ProviderRouter(ModelProvider):
    def __init__(self, *, default, resolve, allowed_ids, default_id,
                 fallback_to_default=False): ...
    def reload_default(self, provider): ...
    @property
    def model(self) -> str: ...
    @property
    def allowed_models(self) -> tuple[str, ...]: ...
    def stream(self, request): ...
```

规则：

1. `mid = request.model or default_id`；`mid` 为空时直接用 `default`。
2. `provider = resolve(mid)`；命中则 `provider.stream(request)`。
3. 未命中且 `fallback_to_default` 为真且 `mid in allowed_ids` 时用 `default`
   （对应"非权威"模式：`config.ini` 的 `models` 都由同一个网关服务）。
4. 其余情况抛 `ModelRequestError("未配置的模型：<id>")`，不静默回退。
5. `resolve` 是注入的回调，由装配根接到 `ModelCatalog.provider_for`。
   router 不读 ini、不 import 插件、不认识任何厂商名。
6. `model` 返回 `default_id`，供 `ModelPort.name()` 与日志使用。
7. `reload_default(provider)` 在锁内替换默认实例，供设置页保存后热更新
   （见 9.3）。它是唯一允许改 `default` 的入口。

## 7. Native 适配

新增 `agent/mechanisms/native_provider.py`：

```python
class NativeProvider(ModelProvider):
    def __init__(self, *, base_url, api_key, model,
                 max_tokens=16000, thinking=True, thinking_budget_tokens=4096,
                 native_version="2023-06-01", timeout=300.0,
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

请求头：`x-api-key`、`protocol-version`、`content-type: application/json`。

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

1. `thinking` 开启时不下发 `temperature`（Native 要求 `temperature=1`，省略等价）。
   思考模式下 Upstream 也忽略 `temperature`（官方文档：不报错但不生效）。
2. `thinking` 的有效条件是 `budget_tokens >= 1024` **且** `max_tokens > budget_tokens`
   （Native 官方的硬约束）。任一不满足就关闭 thinking 并写一条 stderr 诊断，
   请求照常发出——配置瑕疵不该让整轮对话失败。
   **关闭必须显式下发 `{"type":"disabled"}`**：Upstream 兼容层的思考模式默认打开，
   省略字段等于继续思考；而思考模式下带 `tool_use` 的消息必须回传 thinking 块，
   静默省略会让工具轮直接 400。
3. Upstream 兼容层按官方文档**忽略** `budget_tokens`，深度走 `output_config.effort`
   （`low/high/max`）。适配器不下发 `output_config`——Native 官方会拒绝这个未知
   字段，而同一个适配器要服务两家。因此 `LogicalRequest.effort` 对本适配器不生效，
   Upstream 侧取服务端默认（high）；要按档位调深度就用同一模型的 compatible 协议条目。
4. 思考模式 + 工具调用：两家都要求把**本轮**带 `tool_use` 的 assistant 消息里的
   thinking 块原样回传（Upstream：`content[].thinking ... must be passed back`）。
   跨轮不要求回传（去掉旧块仍可正常请求），所以 `strip_stale_thinking` 只留本轮。
   本轮块丢了（签名缺失被丢弃 / 历史来自另一协议条目）就补不回来，此时
   `_tool_turn_missing_thinking` 让本次请求关掉 thinking，避免会话永久打不开。
5. `tools` 为空时不下发 `tools` 与 `tool_choice`。
6. `max_tokens` 是该 API 的必填项，缺省取构造参数，插件可覆盖。
7. `input_schema` 必须是**带 `type` 的 object schema**。`ToolRegistry.schemas()` 给的
   `parameters` 是「参数名 → 片段」的属性映射，跟 Compatible 侧共用
   `model_provider.tool_parameters()` 规范化后再下发；直接把它当 schema 会得到
   `type: null`，Native 一侧报 `Invalid schema for function ...`（400）。
   兼容协议网关不校验这个字段，所以这个缺陷只在 Native 协议上暴露。
8. 图片支持 `source.type=base64`（`data:` URL）与 `source.type=url`（http(s)）。
   只认 base64 会让图片链接在 native 条目上静默消失，而同一张图在 compatible 条目
   照常发送。

### 7.2 消息转换

拆成两个纯函数再拼装，避免把"忠实折叠"和"下游硬约束修补"混在一处：

```python
def strip_stale_thinking(messages, turn_start): ...   # 只留本轮的 thinking 块
def drop_dangling_tool_results(messages): ...          # 删掉没有对应 tool_use 的 tool_result
def _to_native_messages(messages, turn_start): ...  # 纯映射
```

映射表：

| 逻辑消息 | 线格式 |
|---|---|
| `role=system` | 抽出正文，按出现顺序拼进顶层 `system`，用空行分隔 |
| `role=user` 且 `content` 为字符串 | `{role:"user", content:[{type:"text", text}]}` |
| `role=user` 且 `content` 为多模态数组 | `text` 原样；`image_url` 的 data URL 拆成 `{type:"image", source:{type:"base64", media_type, data}}` |
| `role=assistant` | `content` 非空时产出 `text` 块；`tool_calls` 逐个产出 `tool_use` 块 |
| `role=tool` | 转成 `role:"user"` 且 `content:[{type:"tool_result", tool_use_id, content}]` |
| assistant 的 `provider_meta.native.thinking_blocks` | 仅当该消息下标 `>= turn_start` 时，按原顺序插到 content 最前 |

修补规则（都是纯函数，可单测）：

1. 连续多条 `role=tool` 的消息合并进同一条 `role:"user"` 的 content 数组，保持顺序。
2. 相邻且角色相同的 user 消息同样合并，避免连续同角色被拒。
3. 工具结果为空时补一个占位文本，保证 `content` 非空。
4. 第一条必须是 `user`：前导的 assistant 消息直接丢弃（它们没有待回答的 `tool_result`）。
5. 没有对应 `tool_use` 的 `tool_result` 丢弃：留着会被 API 拒绝，整段会话打不开。
6. 同一请求内 `tool_use.id` 重复时，从第二次起追加 `_2`、`_3` 后缀；
   assistant 的 `tool_use` 与对应的 `tool_result` 必须同时改名，否则配对断裂。
7. `turn_start` 之前的 assistant 消息不带 thinking 块。

### 7.3 流事件映射

SSE 按行解析 `data:` 载荷。**事件类型取载荷里的 `data.type`**，不读 `event:` 行：
两处各存一份"这是什么事件"，迟早会漂移。`event:` 行只用于跳过，不作判据。

| `data.type` | 处理 |
|---|---|
| `message_start` | 记 `usage.input_tokens` / `cache_read_input_tokens` / `cache_creation_input_tokens`；缺失按 0 |
| `content_block_start` | 按 `index` 建块：`text` / `thinking` / `tool_use`（记 `id` 与 `name`；`input` 非空则作为初值） |
| `content_block_delta` | `text_delta` → `kind="text"`；`thinking_delta` → `kind="reasoning"`；`delta.signature` 累积；`input_json_delta` 累积 `partial_json` |
| `content_block_stop` | `tool_use` 块解析 JSON 转 `ToolCallRequest`；`thinking` 块记录 `{thinking, signature}` |
| `message_delta` | 记 `stop_reason` 与 `usage.output_tokens` |
| `message_stop` | 结束本流 |
| `error` | 抛 `ModelRequestError(error.message)` |
| `ping` | 忽略 |

`input_json_delta` 归并规则：

1. 按块的 `index` 累积 `partial_json`；`content_block_stop` 时一次性解析。
2. 解析失败时退化为空参 `{}`，调用仍发出，错误由工具侧暴露。
3. `tool_use` 的 `id` 为空时用 `call_<随机>` 兜底，与 Compatible 适配器同源。

`stop_reason` 只进诊断日志，不扩展流帧契约：`StreamDelta` 没有也不新增
`finish_reason`，与现有 Compatible 适配器保持一致。

### 7.4 流末顺序

固定顺序，便于模型模块按类型收集：

1. 文本与推理增量边到边出（流中实时产出，不攒列表）。
2. `kind="meta"`：仅当本轮有 thinking 块**且**存在工具调用时产出，
   载荷为 `{"native": {"thinking_blocks": [...]}}`。没有工具调用时签名无处回传，
   不必落盘。
3. `kind="tool_call"`：按块 `index` 升序逐个产出。
4. `kind="usage"`：映射后的用量。

### 7.5 usage 映射

```
prompt_tokens            = input_tokens + cache_read_input_tokens + cache_creation_input_tokens
completion_tokens        = output_tokens
prompt_cache_hit_tokens  = cache_read_input_tokens
prompt_cache_miss_tokens = input_tokens + cache_creation_input_tokens
```

字段名与现有 Compatible 适配器一致，界面与累计器无需分支。

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

响应体里的 `error.message` 附在提示后，截断到 800 字符。
Native 的错误提示独立成表，不与 Upstream 的表混用。

## 8. thinking 签名回传

Native 的 extended thinking 在带工具的同轮循环里要求把 thinking 块
（含 `signature`）原样回传，否则同一轮的后续请求会被拒绝。事实里现有字段
`reasoning_content` 只有文本，签名会丢。

方案：在 `model_message` 事实里增加一个内核不解释的 `provider_meta`。

1. `agent/core/model_call.py`：导出 `PROVIDER_META_KEY = "provider_meta"`；
   `StreamDelta` 增加 `meta: Optional[Dict[str, Any]] = None`，`kind` 增加取值 `"meta"`。
2. `agent/core/modules/model_mod.py`：收集 `kind=="meta"` 的载荷，合并后写入
   `model_message[PROVIDER_META_KEY]`；为空时不写该字段。
3. `agent/core/session_log.py` `derive_messages()`：`model_message` 带该键时原样带进
   assistant 消息。读方与写方引用**同一个常量**，不各写一遍字符串。
4. `agent/mechanisms/model_provider.py` 的 `_to_wire_messages` 必须
   `msg.pop(PROVIDER_META_KEY, None)`，避免未知字段发给 兼容协议网关。
5. 回放范围：只有消息下标 `>= request.turn_start` 时才带 thinking 块；
   跨用户轮直接丢弃，防止历史请求带上过期签名。

`provider_meta` 的约束：

1. 必须可 JSON 序列化，落盘与读取两侧都经过既有 `default=str` 兜底。
2. 内核不读取其内部结构，不参与分段统计、token 估算与压缩判定。
3. 压缩器丢弃被压缩区间的消息时，其 `provider_meta` 一并丢弃。
4. 只存 thinking 块的 `{thinking, signature}`，不存整段响应；不做截断——
   截断会让签名失效，回传反而报错。
5. **兼容窗口**：这是落盘格式的**可选**新增键，只前滚。
   旧日志没有该键按"无 thinking 块"处理；读取方忽略未知的 provider 子键；
   不提供回滚脚本，也不迁移历史文件。任何读方不得要求该键存在。

## 9. 装配根接线

### 9.1 接线

`agent/app.py` 的 `build_app()`：

1. 创建 `ModelCatalog`，把服务名 `SERVICE_MODEL_CATALOG` 加进
   `agent/core/context.py` 的进程级服务词汇表，并注入 `PluginHost`。
2. 从一开始就把 `ProviderRouter` 注册为 `SERVICE_PROVIDER`，不再直接暴露裸 provider：
   - `default`：`config.ini` 构造的 provider；
   - `resolve`：`catalog.provider_for`；
   - `allowed_ids` 与 `default_id`：装配后按权威来源确定；
   - `fallback_to_default`：非权威时为真。
3. `plugin_host.load_manifest(...)` 之后计算一次 `app.model_config_state`：

   | 取值 | 判据 |
   |---|---|
   | `"catalog"` | 目录权威且 `entries` 非空 |
   | `"config"` | 非权威，但 `config.ini` 有 `api_key` + `base_url` |
   | `"none"` | 两者都没有可用模型 |

4. `"catalog"` 时用目录的 `ids()` 与 `default_id()` 覆盖 `app._available_models`
   与 `live_state.default_model`；其余情况保留 `config.ini` 的值。
5. 收敛陈旧值：`live_state.get_model(cid)` 不在 `available_models()` 里时，
   回落到 `default_id` 并写回、同时写一条诊断。插件改配置后，旧标签页不会
   一直拿着一个已被删掉的 id 撞错误。
6. `MissingProvider` 的 `stream()` 只抛 `ModelRequestError("未配置任何模型")`。
   **报错文案不含插件目录名**：`mechanisms` 里出现插件名会直接命中原有的
   内核架构约束门禁，而且是把"去哪配"这种运维信息焊进了内核。
7. `shell/web.py` 与 `shell/chat.py` 删除各自的凭据预检与 provider 直接构造，
   统一走 `build_app`；但保留**启动期判定**：
   `model_config_state == "none"` 时快速失败，提示里给出两处配置路径
   （这句文案在 shell 层，属运维面，不进 core/mechanisms）。
   `V5`：配置错要立刻失败；只有"依赖不可用"才允许降级。
8. `/health` 增加：

   ```json
   "model_config": { "source": "catalog|config|none", "authoritative": true, "degraded": false }
   ```

   任何"启动了但模型不可用"的状态必须在健康检查里体现（`V6`），不能只留一行日志。

### 9.2 回退矩阵

| 插件状态 | `config.ini` 凭据 | 默认模型 / `default` 实例 | `model_config_state` | `/health.allowed_models` | 设置页模型节 |
|---|---|---|---|---|---|
| 启用且有有效条目 | 有或无 | 目录 `default_id`；`default` 实例不参与路由 | `catalog` | 目录 ids | 隐藏 |
| 启用但 0 条有效条目 | 有 | `config.ini` 的 `model` | `config` | `config.ini` 的 `models` | 显示 |
| 停用或缺失 | 有 | `config.ini` 的 `model` | `config` | `config.ini` 的 `models` | 显示 |
| 停用或缺失 | 无 | 无（`MissingProvider`） | `none` | `[]` | 显示 |
| 启用且有条目，但条目全部无效 | 无 | 无（`MissingProvider`） | `none` | `[]` | 显示 |

最后一行是重点：插件"启用了"不等于"可用"。权威判定看的是有效条目数，不是启用开关。

权威模式下 `default` 实例基本用不到——每轮请求都带目录 id，`resolve` 必然命中；
它只在 `allowed_ids` 为空或 `fallback_to_default` 为真时兜底。因此权威模式下
`config.ini` 没有凭据也不影响对话，`default` 可以是 `MissingProvider`。

### 9.3 设置页保存

`settings_panel.apply_host()` 不再直接改 provider 属性。原因很实际：
router 包装之后，`getattr(app, "provider")` 拿到的是 router，
`hasattr(provider, "base_url")` 为假，原来的分支会**静默跳过**——
设置页显示"已保存"，进程里还是旧模型。

改为：

1. `app.reload_model_config()` 是唯一入口，内部按 9.1 的规则重算：
   - `catalog` 时跳过并留痕（"目录权威，忽略 config.ini 模型设置"）；
   - 否则用 `build_provider("compatible", cfg)` 重建实例，调 `router.reload_default(p)`，
     再更新 `_available_models` 与 `live_state.default_model`。
2. `apply_host` 只调这一个方法，并把它返回的说明放进响应（`reload_error` 同款）。
3. 单测锁住："保存后 router 的默认实例是新建的那个，且下一轮请求用它"。

## 10. 插件

### 10.1 目录

```
plugins/multi_model/
  plugin.py
  plugin-config.ini
  ui/model-picker.js
  ui/model-picker.css
```

`plugins.ini` 增加 `[plugin:multi_model]` 节。
`plugin-config.ini` 已被 `.gitignore` 的 `plugins/*/plugin-config.ini` 覆盖，
真实配置只留在工作区，提交前用 `git ls-files` 确认历史与索引里都没有真实配置。

目录名不叫 `models` / `model` / `llm`：这几个词会被
`check_kernel_plugin_names` 当成 `core` / `mechanisms` 的禁用词。
`model` 在该范围命中 59 处（`agent/core/engine.py:47` 等），
`llm` 命中 1 处；`models` 为 0 命中，但它是通用复数名词，
后续容易被内核当作变量名。`multi_model` 与 `model_config` 都是 0 命中，
取前者：插件名会出现在 URL、上下文段键、日志前缀里，说"能力"比说"实现"更容易被读懂。

### 10.2 配置格式

```ini
[model:upstream]
provider = compatible
base_url = https://api.upstream.com
api_key = sk-…
model = upstream-flash
label = Upstream Flash
default = 1

[model:target]
provider = native
base_url = https://api.native.com
api_key = sk-ant-…
model = model-id
label = Target Sonnet 4.5
max_tokens = 16000
thinking = 1
thinking_budget_tokens = 4096
```

### 10.3 解析规则

1. 节名 `[model:<id>]`，`id` 是请求与界面里的唯一标识。
2. `model` 缺省等于 `id`。
3. `provider` 缺省 `compatible`；不在 `known_kinds()` 里的值使该条目无效并留痕。
4. `api_key` 或 `base_url` 缺失使该条目无效。
5. `default = 1` 至多一个；没有时取第一个有效条目；多个时第一个生效并留痕。
6. `thinking`、`max_tokens`、`thinking_budget_tokens` 只对 native 条目生效。
7. 任一条目解析失败只影响该条目，不影响其它条目与插件装载。
8. 配置用 `utf-8-sig` 读：Windows 记事本存 UTF-8 会带 BOM，
   用 `utf-8` 读会得到一个指不到根因的 `MissingSectionHeaderError`。
9. 每条诊断都必须能定位：`[plugin:multi_model] <文件路径> [model:<id>] <键> 无效：<原因>`。
   只写"配置有误"无法定位到文件、条目与键。

### 10.4 register

`register(ctx)` 做三件事：

1. `ctx.add_model_catalog(entries)`
   - `entries` 是回调，每次重读 `plugin-config.ini`，返回 `ModelEntry` 列表；
   - 不传工厂、不构造 provider——厂商分发在 `provider_registry` 里。
2. `ctx.add_route("GET", "catalog", handler)`：
   返回 `{"ok":true,"models":[{"id","label","provider","default"}],"default":id,"invalid":[{id,reason}]}`。
   不返回 `api_key` 与 `base_url`。`invalid` 是运维面：坏条目不能只活在日志里。
3. `ctx.add_boot_script("ui/model-picker.js")`。
4. 返回 disposer 列表，由插件宿主统一回收。

样式不走后端：`model-picker.js` 第一行调
`window.aiAgentShell.styles.load("ui/model-picker.css")`。理由见 11.2。

## 11. 壳层与界面

### 11.1 清单来源

`WebApi.available_models()` 在 `model_config_state == "catalog"` 时返回目录 `ids()`，
否则返回 `app._available_models`。`/health` 与 `ui-state` 都从这里取，
凭据字段永不出现在响应里。

### 11.2 界面桥

#### 11.2.1 模型桥

壳层在 `agent-ui.js` 里、与 `window.aiAgentPlugins` 相邻处定义：

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

约束：

1. 插件脚本在 `#modelPickerSlot` 内创建按钮与菜单，样式来自它自己的 CSS。
2. 插件不读壳层内部变量，不拼 `/api/chat/send`，不改页头元素。
3. `select` 由壳层写 `live_state` 并发起广播；插件只更新自己的按钮文字。
4. 桥是壳层的公共契约，插件停用后桥仍在，只是没有订阅者与下拉。
5. 桥本身**不持有状态**：`current()` 读的是当前 tab 的模型字段，
   `onChange` 只是转发。多份"当前模型"必然分叉。

#### 11.2.2 样式桥

插件资产目前有两条送达路径，模型下拉两条都用不上：

| 路径 | 端点 | 注入时机 |
|---|---|---|
| 面板脚本 / 面板样式 | `/api/plugin/<插件>/_asset/<相对路径>` | **面板打开时**（`loadPluginStyle`） |
| 开屏脚本 | `/api/boot-scripts` | 页面加载 |
| 开屏样式 | 无 | — |

下拉按钮在输入区、不属于任何面板，所以它需要在开屏阶段就生效的样式。
不新增后端扩展点（`add_boot_style` + `/api/boot-styles` 要动 `PluginContext`、
`contributions`、`web_api`、`web_routes` 四处，只为送一个 `<link>`），
改为把壳层**已有**的 `loadPluginStyle` 暴露到桥上：

```js
window.aiAgentShell.styles = {
  load: function (relPath) { /* → Promise<boolean>；relPath 是插件目录内相对路径 */ }
};
```

1. 壳层用 `window.aiAgentPluginCurrent` 拼
   `/api/plugin/<插件>/_asset/<relPath>`，插件不自己拼 URL、不碰 `document.head`。
2. 复用既有去重表 `_pluginStylesLoaded`，同一路径只注入一次。
3. 注入的 `<link>` 带 `data-plugin-style="<插件名>"`（该标记现已存在，只是没人读）。
4. `applyPluginsChanged` 新增一步：摘掉 `data-plugin-style` 不在 `loaded` 名单里的
   `<link>`。这顺带修掉一个既有缺陷——插件停用后样式不会残留。
5. 只接受插件目录内的相对路径，与 `add_panel(css_file=…)` 同一套校验，
   不接受绝对路径或越出插件目录的 `..`（`S2`：解析后比对，不做字符串前缀判断）。

### 11.3 下拉与广播

1. `agent-ui.html` 提供 `#modelPickerSlot` 挂载点，**删除**内建的
   `#modelPicker` / `#modelPickerBtn` / `#modelPickerMenu` 及其 JS 与 CSS。
   不是保留再隐藏：留下的死代码会被下一个人当成活路径（`R5`）。
   要删的函数：`renderModelChoices`、`openModelPicker`、`closeModelPicker`，
   以及它们绑定的 `click` / 文档级关闭监听。
2. 页头 `#hdrModel` 保留，由 `applyModel` 写「模型: xxx」。
3. `applyModel(id)` 的职责：
   - 写当前 tab 的 `selectedModel`；
   - 写页头；
   - 通知 `aiAgentShell.models.onChange` 的订阅者；
   - 服务端下发的值不受本地白名单限制，只有本地点击时校验。
4. 会话级持久化：`POST /api/chat/send` 与 `PUT /api/chat/ui-state` 的 `model` 字段
   继续写 `live_state`，值必须在清单内。
5. 广播：`ClassicAdapter.announce_model(cid, model)` 向全部 SSE 通道推
   `{"type":"conversation","conversation_id":cid,"model":model}`，
   与 `announce_plugins` 同构，不伪装成内核事件。
6. 触发点：`send` 与 `ui_state_put` 里模型值发生变化时。
7. 前端 SSE 的 `conversation` 分支处理 `ev.model`：
   **只有发起方写服务端**，其它标签页只更新页头与本地 tab 字段。
   接收方再写一次 `live_state` 会产生重复写与竞态；显示同步与状态写入必须分开。
8. 时序：开屏脚本在会话恢复之前加载（`agent-ui.js` 底部的启动链是
   面板 → 开屏 → 恢复会话），所以插件初始化时主动 `current()` 取一次，
   不能只等 `onChange`。
9. 插件停用时，`applyPluginsChanged` 清空 `#modelPickerSlot` 的内容，
   并摘掉它的样式表（11.2.2 第 4 条）。不清空的话，按钮会留在页面上，
   点了调的是一个已经不存在的端点。
10. **已知限制**：`loadPluginScript` 按 URL 去重（`agent-ui.js:901`），
   所以"停用 → 再启用"在不刷新页面的前提下，开屏脚本不会重跑，下拉不会回来。
   这是所有开屏脚本的既有行为，本方案不额外伪造一套"重新执行脚本"的机制。
   文档与设置页的插件开关旁写明"插件变更后建议刷新页面"。

### 11.4 设置页

1. 设置页不提供内核「模型」节；模型条目只由多模型插件表单维护。
2. 模型条目由插件的 `settings-schema.json` 驱动结构化编辑（新增/删除/逐条改），
   保存时只替换 `[model:*]` 节，其它节逐字节保留。
3. 保存接口只写插件自己的节，不写内核配置。

## 12. 文件清单

| 动作 | 文件 |
|---|---|
| 新增 | `agent/mechanisms/native_provider.py` |
| 新增 | `agent/mechanisms/provider_registry.py` |
| 新增 | `agent/mechanisms/provider_router.py` |
| 新增 | `agent/capabilities/model_catalog.py` |
| 修改 | `agent/core/model_call.py`（`StreamDelta.meta`、`PROVIDER_META_KEY`） |
| 修改 | `agent/core/modules/model_mod.py` |
| 修改 | `agent/core/session_log.py` |
| 修改 | `agent/core/context.py`（`SERVICE_MODEL_CATALOG`） |
| 修改 | `agent/mechanisms/model_provider.py`（剥离 `provider_meta`） |
| 修改 | `agent/capabilities/plugins.py`（`add_model_catalog`） |
| 修改 | `agent/app.py` |
| 修改 | `agent/shell/web.py` |
| 修改 | `agent/shell/chat.py` |
| 修改 | `agent/shell/web_api.py` |
| 修改 | `agent/shell/settings_panel.py` |
| 修改 | `agent/shell/classic_adapter/adapter.py` |
| 修改 | `agent/shell/classic_adapter/contract.py` |
| 修改 | `agent/shell/web_assets/classic/agent-ui.html` |
| 修改 | `agent/shell/web_assets/classic/js/agent-ui.js`（`aiAgentShell` 两条桥、样式摘除） |
| 新增 | `plugins/multi_model/plugin.py` |
| 新增 | `plugins/multi_model/plugin-config.ini` |
| 新增 | `plugins/multi_model/ui/model-picker.js` |
| 新增 | `plugins/multi_model/ui/model-picker.css` |
| 修改 | `plugins.ini` |
| 修改 | `docs/subsystems/plugins.md`（两条桥与开屏样式的限制） |
| 新增测试 | `tests/test_native_provider.py` |
| 新增测试 | `tests/test_provider_router.py` |
| 新增测试 | `tests/test_model_catalog.py` |
| 新增测试 | `tests/test_multi_model_plugin.py` |
| 修改测试 | `tests/test_model_provider.py`、`tests/test_settings_panel.py` |
| 同步 | `README.md` 的用例数（`scripts/check_readme.py` 核对） |

## 13. 测试与验收

### 13.1 单元测试

`tests/test_native_provider.py`：

1. SSE：文本增量、thinking 与 `signature`、`tool_use` 分片归并、`message_delta` 用量、
   `error`、`ping`、缺 cache 字段按 0。
2. 消息转换：system 合并到顶层、连续 `tool_result` 合并、图片 data URL、
   assistant `tool_calls`、前导 assistant 被丢弃、悬空 `tool_result` 被丢弃、
   重复 `tool_use.id` 加后缀且配对同步改名。
3. `provider_meta` 只在本轮回放，跨轮丢弃。
4. 地址构造、HTTP 错误映射、`thinking` 预算不足时降级为关闭。
5. 事件类型只认 `data.type`：删掉 `event:` 行后仍能正确解析。

`tests/test_provider_router.py`：按 `request.model` 选实例、默认回落、
非权威模式的 `fallback_to_default`、未知模型报错、`reload_default` 后下一请求生效、
`allowed_models` 与 `model` 属性。

`tests/test_model_catalog.py`：`set_source` 替换语义、第二个来源抛 `RuntimeError`、
`authoritative` 随条目数变化（3 条 → 0 条后失效）、`entries` 抛异常按空表并留痕、
条目变化后整批重建 provider、disposer 注销并清缓存、`options` 返回副本。

`tests/test_multi_model_plugin.py`：解析器读取真实配置的键集合
（防配置漂移）、BOM 文件可读、坏条目只影响自身、`default` 多于一个时的取舍、
`catalog` 响应不含凭据。

`tests/test_model_provider.py` 增补：`_to_wire_messages` 不把 `provider_meta`
发给 兼容协议网关（负向断言：构造带该键的历史，断言线格式里没有）。

`tests/test_settings_panel.py` 增补：权威时保存不动模型、非权威时保存后
router 的默认实例被替换。

### 13.2 集成与验收

1. `/health` 与 `ui-state` 返回目录 ids，响应体不含 `api_key` 与 `base_url`。
2. 插件停用后模型清单为空，`/health.model_config.source` 变为 `none`。
3. 没有有效模型时，`chat.py` 启动失败并提示配置 multi_model；
   `build_app` 本身仍可构造（测试与无模型场景）。
4. 切换模型后页头模型名更新，同会话第二个标签页同步更新，且服务端只被写一次。
5. 未配置的模型 id 在 `send` 与 `ui_state_put` 都被拒绝。
6. `plugins/multi_model` 坏条目不影响其它条目与服务启动，`catalog` 端点的
   `invalid` 里能看到它。
7. 插件删掉当前模型后，旧标签页的下一次发送回落到默认条目而不是报错。
8. 插件停用后，`#modelPickerSlot` 被清空、`data-plugin-style` 的 `<link>` 被摘除；
   再启用需要刷新页面（既有行为，见 11.3 第 10 条）。
9. `aiAgentShell.styles.load("../x.css")` 与绝对路径都被拒绝，不留痕地不注入
   不算通过——必须返回 `false` 并写 `console.error`。
10. `python scripts/ci.py` 全绿；`check_imports.py` 与
    `check_architecture_hygiene.py` 通过（内核里不出现 `multi_model` 这个词）。

## 14. 边界与风险

1. `provider_meta` 里的 thinking 文本与 `reasoning_content` 存在重复存储。
   这是换取原生 thinking 回传能力的代价；压缩与分段统计不读它。
2. 该键是落盘格式的新增可选键，只前滚；旧日志读不到它时按无 thinking 处理。
3. 模型 id 冲突会把请求路由到错误网关，因此重复 id 必须拒绝并留痕。
   `id` 是跨配置文件、界面、请求共用的唯一标识，不做别名。
4. 插件配置解析失败一律降级为「该条目无效」，不让服务起不来；
   但"全部无效"会让 `model_config_state` 变成 `none`，由 shell 快速失败。
5. 移除内建模型下拉是行为变更。若其它客户端依赖 `#modelPickerBtn`，
   需要改用 `aiAgentShell.models` 桥。
6. Native 的 `max_tokens` 必填且必须大于 thinking 预算；不满足时关闭 thinking。
7. `effort`（High / Max）对 Native 不生效；该差异写进插件配置注释。
8. 设置页不提供内核模型节；模型只由多模型插件维护。
9. 每次 `snapshot()` 都会重读插件配置。配置文件在 10k 会话规模下的读盘成本
   可忽略；条目数上千时再加 mtime 缓存，当前不提前优化。
10. 插件开关后开屏脚本不重跑（`loadPluginScript` 按 URL 去重），
    "停用 → 再启用"必须刷新页面才能恢复下拉。这是既有行为，方案选择如实记录
    而不是加一套"可重执行脚本"的机制——那会引入脚本重复执行、重复绑定事件
    这类更难排查的问题。

## 15. 工程标准对齐

| 准则 | 本方案的落点 | 验证方式 |
|---|---|---|
| `A2` / `A7` 依赖方向 | 新增文件全部落在既有层内；插件只在包外向下依赖 | `check_imports.py`（机） |
| `A4` 扩展只加文件 | 新厂商 = 适配器文件 + `provider_registry` 一行；插件不构造实例 | 审 + 用例 |
| `A6` 内核不知道插件名 | 目录改名 `multi_model`（内核零命中）；`MissingProvider` 文案不含插件路径 | `check_architecture_hygiene.py`（机） |
| `A5` 装配点集中 | `build_app` 是唯一决定权威来源与降级态的地方 | 审 |
| `A4` / `G3` 最小扩展 | 开屏样式复用既有 `loadPluginStyle`，不新增 HTTP 端点与贡献类型 | 文件清单差异 |
| `B1` 只读视图真不可变 | 条目存规范化 JSON，`options`/`snapshot` 返回深拷贝；快照用 `tuple` | 改返回值后重读不变（15.4） |
| `B3` 少用 `Any` | `provider_for → ModelProvider \| None`；`options` 只有 `dict` 一处 | 审 |
| `B4` 一物一名 | 不用 `cursor`；`multi_model` 与 `model` 分指插件与模型；桥挂 `aiAgentShell` | 审 |
| `B5` 折叠与修补分离 | `strip_stale_thinking` / `drop_dangling_tool_results` 都是纯函数 | 单测 |
| `B6` 契约版本化 | `provider_meta` 为可选新增键，只前滚、旧日志免迁移 | 文档 + 单测 |
| `C2` 终态穷尽 | `model_config_state` 三态；`/health` 显式暴露 | 验收 |
| `C3` 真流式 | 文本/推理增量边到边出，不攒列表 | 审 |
| `C4` 状态归属单一 | 权威只有 `ModelCatalog`；前端种子清空（15.2）；`live_state` 陈旧值在读取点收敛 | 单测 + `check_ui_js` |
| `K1` / `K4` 并发 | `set_source` 原子替换、`snapshot` 快照一致性；4 写 8 读争用用例 | `-X dev` 并发作业（15.1） |
| `E1` / `E3` 不丢错误、要留痕 | 坏条目、描述回调异常、越权保存都带定位信息写 stderr | 单测 |
| `E2` / `Y7` 无全局豁免 | 不新增任何门禁豁免 | 审 |
| `P6` 键名不硬编码 | `PROVIDER_META_KEY` 由 core 导出，读写两侧共用 | 审 |
| `R5` 无遗留兼容层 | 内建下拉的 HTML/JS/CSS 按 15.3 清单同 PR 删净，不留别名与空守卫 | 审 + 文件清单 |
| `S6` 秘密不进版本库 | 真实配置被 `.gitignore` 覆盖，不提交配置 | `git ls-files` |
| `T1` 配置错误可定位 | `utf-8-sig`；诊断含文件、节、键、原因 | 单测（BOM 文件） |
| `T4` 配置漂移检查 | 插件真实配置的键与 `config_schema` 比对 | `check_config_drift.py` |
| `V5` / `V6` 快速失败 + 降级可见 | `none` 时启动失败；`/health.model_config` 显式降级位 | 验收 |
| `X2` 负向测试 | 重复 id、线格式不含 `provider_meta`、未知子键忽略、缺 signature 降级（15.5） | 单测 |
| `X3` 失败路径有测试 | BOM、坏条目、预算不足、悬空 tool_result、未配置模型 | 单测 |
| `X6` 覆盖率归属 | 插件代码在 `--source=agent,plugins` 口径内（standards-alignment P3） | `check_coverage.py` |
| `R1` 复杂度 | 见 15.7 的单文件预算；超阈值直接失败 | `check_complexity.py` |
| `D3` 文档与代码一致 | README 用例数同步；`unit-tests.md` 由 `--check` 接管；插件扩展点补文档 | 门禁 |

**存量缺口**（覆盖率、并发作业、依赖环、生成文档漂移）由
[standards-alignment.md](standards-alignment.md) 统一整改。插件代码与
`agent.shell` 一样受分层约束；本方案新增文件全部落在 `plugins/multi_model/`
与 `agent/shell/web_assets/**`，不新增层。

路径口径按 **alignment P2 完成之后**的结构写：`build_shell_app` / `serve` 已在
`agent/entry/web.py`，`agent/shell/web.py` 只剩 `create_server`；第 12 节里凡是对
"构造 app / 启动参数"的改动，实际落在 `entry/web.py`，不再落 `shell/web.py`。

下面补本方案自身必须闭合的 7 项。

### 15.1 `K1` / `K4` `ModelCatalog` 并发

`ModelCatalog` 被 HTTP 请求线程与配置重载同时访问，"替换目录"必须是**原子**的：

1. 用 `threading.Lock`（不用 `RLock`：持锁期间只调 `_snapshot_locked()` /
   `_replace_locked()` 这类私有函数，禁止调公开方法；用 `RLock` 会把重入错误藏起来）。
2. `set_source(entries)`：锁外完成解析、校验、去重与 id 冲突检查，构造一个**完整的新
   元组**；进锁后只做一次引用替换；出锁。
3. `snapshot()`：进锁取当前元组引用，出锁；返回 `tuple`，不返回内部对象。
4. 不变量：任意一次 `snapshot()` 看到的条目集合要么全旧、要么全新，**不存在混合**；
   持锁期间不做 I/O、不调用 provider、不写 `live_state`。
5. 并发用例（`tests/test_concurrency.py`）：4 个写者 × 100 次交替 A/B 源（每条带
   `source_id`），8 个读者 × 200 次取快照；断言每次快照里的 `source_id` 只有一个值。
   去掉锁后该用例必须失败——这是锁的负向证明，PR 里记录演示。

### 15.2 `C4` / `A5` 前端不得有模型种子

`agent/shell/web_assets/classic/js/agent-ui.js:618` 目前硬编码 6 个模型
（`upstream-v4-pro` 等），`/health` 失败时它就是**事实上的第二权威**，与
"`ModelCatalog` 是唯一权威"冲突。

1. 内建白名单整体删除（不是改成空数组留着）：`allowedModels` 及其
   `splice/push` 补水（`:1180-1181`、`:1193`）全部移除；点击校验移入
   `aiAgentShell.models.select()`，对照 `list()` 的结果判断。
2. `/health` 不可用时：桥的 `list()` 返回空数组，插件据此禁用下拉 + `title`
   写明原因，桥内 `console.warn` 留痕；不回退到任何硬编码列表（`E3`）。
3. `check_ui_js.py` 增加规则：`agent/shell/web_assets/**/*.js` 不得出现厂商模型 id
   字面量（`upstream-` / `vision-` / `target-`）；负向用例喂一段含 `upstream-v4-pro`
   的 JS，断言失败。

### 15.3 `R5` 内建下拉删除清单

与 11.3 是同一件事，这里给完整清单。删除内建下拉的 HTML/CSS 后，以下符号必须
在同一个 PR 删净（不许留"空对象守卫"续命）：

| 符号 | 现状 | 处置 |
|---|---|---|
| `allowedModels` | `agent-ui.js:618` 种子、`:730` 校验、`:1180-1193` 补水 | 删，校验进 `models.select()` |
| `modelPickerBtn.onclick` | `:680` | 删 |
| `#modelPickerMenu` 委派处理器 | `:695-713` | 删 |
| `openModelPicker` / `closeModelPicker` / `toggleModelPicker` | `:715-727` | 删 |
| `renderModelChoices` | 菜单项渲染 | 删 |
| `applyModel` | `:728-737` | **保留**，收窄为 11.3 的三件事（写 tab、写页头、通知订阅者）；删掉其中的白名单校验 |
| `.model-choice` 相关 CSS | 样式表内 | 删 |

`#hdrModel` 保留：它是壳层的只读展示位，由收窄后的 `applyModel` 写入；
模型**选择**归插件，模型**展示**归壳层，这是两个渲染点，不冲突。

### 15.4 `B1` 深不可变

- `ModelEntry` 为 `frozen=True`，`options` 存规范化后的 `dict`；
- `options()` 每次返回 `dict(entry.options)`，嵌套 list 也复制；
- `snapshot()` 返回 `tuple[ModelEntry, ...]`，调用方改不动内部；
- 单测：改 `options()` 返回值 / `snapshot()[0]` 后再次读取，结果不变。

### 15.5 `X2` 负向断言（4 条）

1. 重复 `id` 的两个条目 → `set_source` 拒绝，保留原目录，stderr 含文件名与 id；
2. Native 适配器产出的线格式**不得**出现 `provider_meta`（Compatible 专属键）；
3. 未知的 `provider_meta` 子键 → 忽略且不抛错（前滚契约，`B6`）；
4. thinking 块缺 `signature` → 不重放该块、留一条可见降级日志，不整体失败。

### 15.6 `D3` / `T4` 文档与配置

- `docs/unit-tests.md` 重生成并由 `gen_unit_tests_md.py --check` 接管；
- `docs/subsystems/plugins.md` 补 `multi_model` 的扩展点（目录权威、`aiAgentShell.models`、样式桥）；
- README 用例数同步；
- `plugins/multi_model/plugin-config.ini` 的键集合必须与 schema 双向一致，
  接入 `standards-alignment` P3 的 `check_config_drift.py`（插件配置也纳入口径）。

### 15.7 `R1` / 覆盖率归属

| 文件 | 预算 |
|---|---|
| `agent/capabilities/model_catalog.py` | ≤ 250 行 |
| `agent/mechanisms/provider_router.py` | ≤ 200 行 |
| `agent/mechanisms/provider_registry.py` | ≤ 150 行 |
| `agent/mechanisms/native_provider.py` | ≤ 450 行 |
| `plugins/multi_model/plugin.py` | ≤ 250 行 |
| `plugins/multi_model/ui/model-picker.js` | ≤ 300 行 |

新文件不得进 `docs/complexity.md`。`standards-alignment` P3 把覆盖率口径改为
`--source=agent,plugins` 后，本插件与上述 `agent/*` 新模块才真正进入下限；
在那之前不宣称"已覆盖"。
