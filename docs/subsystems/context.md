# 上下文管理

上下文管线回答两个问题：**发给模型的请求体由哪些部分组成**，以及**历史太长时怎么压缩**。

实现在 `agent/mechanisms/context_pipeline.py`（装配与分段）与
`agent/mechanisms/context_compactor.py`（压缩与摘要）。

## 三拼接装

请求体只有三段：

```
messages = 头部 + 对话 + 尾部

头部 = 系统提示词 + 插件各段 + 记忆摘要
对话 = 从会话事实折叠出来的轮次
尾部 = 本轮新输入 / 工具结果 + 执行模式
```

**唯一装配入口是 `ContextPipeline.assembles(tail)`**。平常请求：

```python
messages = pipeline.assembles([新输入, 模式说明])
```

压缩时先把尾部摘掉再压，压完拼回去：

```python
zip_messages = compress(pipeline.assembles([]))   # 不带尾部
messages     = pipeline.assembles([新输入, 模式说明])
```

装配是**同步**的：没压完不接着往下跑。`rebuild_from_messages()` 只是
`set_dialogue()` 的兼容转发，不再是第二条装配路径 —— 从 `messages` 反推头部会丢掉
系统提示词与插件各段（那些不在事实记录里）。

## 五个块

管线按块持有内容，`CHUNK_ORDER` 固定展平顺序，空块跳过。

| 常量 | 块 | 内容 |
|---|---|---|
| `CHUNK_SYSTEM` | 系统提示词 | 基础提示词 + 工具速查 |
| `CHUNK_PLUGIN` | 插件段落 | 插件按段注册的注入内容 |
| `CHUNK_MEM` | 记忆摘要 | 历次压缩产出的摘要，各占一条 `system` |
| `CHUNK_FULL` | 近期记忆 | 对话轮次，按原文保留 |
| `CHUNK_MODE` | 模式 | 保留结构；执行模式现由请求尾部现拼，不落此块 |

## 组装顺序

**顺序按"改动可能性"排：越不会变动的越靠前。**

```
系统提示词 → 记忆摘要 → 近期记忆        这三段的相对顺序固定，不随插件变
插件段整体                              落在"系统提示词"之后、"记忆摘要"之前
插件段之间                              按插件清单（plugins.ini）顺序，靠前的插件在前
模式                                    最后
```

插件清单顺序即组装顺序：清单里两个节的先后就是它们在请求里的先后。
排在前面的插件应当是更不容易变的那个 —— 会随界面操作变动的插件排在只读的之后。
应用级来源（不属任何插件、直接用 `ContextSources.add` 注册的）没有清单位次，
排在所有插件段之后。

实现在 `ContextSources.collect_segments()`：按 `SourceMeta.plugin_rank` 稳定排序，
`plugin_rank` 由宿主在装载插件时按清单序号写入（`PluginContext.set_rank`）。

## 内核与插件的协同

**内核不认识任何具体插件。** 它只知道"有个来源注册了一段"：

```python
@dataclass(frozen=True)
class SourceMeta:
    key: str = ""          # 段 key = 插件名（前端按它找插件的渲染钩子）
    label: str = ""        # 段名
    plugin: str = ""       # 提供者插件名
    prefix: str = ""       # 注入前缀，告诉模型这段是什么
    count: Callable[[str], int] | None = None   # 主体数量取数口 fn(cid) -> int
    plugin_rank: int | None = None              # 插件在清单里的位次 = 组装位次
```

插件侧一条口子：

```python
ctx.add_context_source(fn, {"label": "段名", "prefix": "【前缀】\n",
                            "count": 主体数量取数口})
```

- `fn(conversation_id) -> list[str]`，每个字符串各成一条 `system` 消息；
- 一个插件可以注册**多个来源**，它们共用段 key、在分层里各占一行；
- `prefix` 由来源给，宿主在收集时统一拼上 —— 拼错了模型会把它当对话内容；
- 单个来源抛错被隔离（记 stderr），不影响其它来源与本次请求。

收集结果是一个结构：

```python
PluginSegments(items=[(段 key, 段名, 正文)], counts=[按位置的主体数量])
```

`counts` **按位置**对应，不按 key —— 同一个插件的两段共用段 key，按 key 存会互相覆盖。

### 内核对插件段做的事

| 阶段 | 内核动作 |
|---|---|
| 收集 | 排序（按 `plugin_rank`）、拼前缀、隔离异常、取主体数量 |
| 装配 | 各段按 `CHUNK_PLUGIN` 顺序落成 `system` 消息，整体排在头部 |
| 分段 | 一段一行上报，`key` 是 `plugin:<插件名>`，段名与数量用插件给的 |
| 展平 | 末端统一过 `sanitize_fn` |

内核**不解释**段名与数量的含义：`count` 是"几个文件"还是"几个 Skills"，由插件决定。

### 观察面

内核每装配完一次请求发一条 `context_segments` 事件（`ModelModule` 里发），
内容就是 `layout_payload()` 的结果。经典界面适配层只把它换个名字转发成
`context_layout`，不自己另算一套 —— 另算必然与真实请求漂移。

**没有快照的旧会话**走 `layout_from_messages()` 兜底：真装一次上下文
（插件内容不在事实记录里，只能靠注入源产出），读它的头部按来源描述切段。

## 分段统计

`ContextPipeline.segment_tokens()` 逐段估 token，口径与真正发出去的请求一致
（同一个 `default_message_tokens`）。

| key | 来源 | `count` 的口径 |
|---|---|---|
| `system` | 系统提示词 | 消息条数 |
| `plugin:<插件名>` | 插件注册的每一段各成一行 | 插件自报；缺省按消息条数 |
| `summary` | 历次摘要 | 消息条数 |
| `full_recent` | 近期对话 | **用户轮数**（一轮里有问有答还有工具往返） |
| `mode` | **请求尾部**，不在管线里 | 由 `layout_payload(tail_messages=…)` 单独算 |

`layout_payload()` 补 `remaining`（剩余容量）与 `pct`；`pct` 相对预算
（预算 = 压缩阈值，取预算与已用中的较大者）。

自报数量**按位置**与来源对齐：`collect_segments()` 返回的数量表与段落表等长，
某个来源少了自报数就按它自己的条数算。错位是静默的（段名、token 都对，只有数字离谱），
所以两处都不允许用邻段的数字补位。

### 字段与边界

`context_layout.segments[]` 只给**数据**：

| 字段 | 含义 |
|---|---|
| `key` | 段标识；插件段是 `plugin:<插件名>` |
| `label` | 段名（插件自报） |
| `tokens` | 该段占用 |
| `count` | 主体数量（插件自报；缺省按消息条数） |
| `pct` | 相对预算的占比 |

**颜色、图标、布局由界面决定**：服务端不下发色号。插件的界面脚本在开屏时依次预载
（`preloadPluginScripts()`），脚本里调
`window.aiAgentPlugins.ctxSegments.register("<插件名>", {color, label})` 注册自己那一段的
外观；注册早于第一次渲染，所以**分段条与浮层两处同源同色**。
插件没注册时，壳层按段 key 从自己的色名表取一个稳定颜色。
面板样式仍是按需注入，只有脚本提前预载。

## 用户轮是原子单位

一条 `user` 起到下一条 `user` 前是**一个用户轮**。压缩只允许整轮处理：

- 圈定要压掉的区间时**向下取整到轮边界**（`turn_boundary_floor`）—— 宁可不压那一轮，
  也不从轮中间切开；
- 落点还受一条硬约束：不能切在**悬空工具链**上（`tool_chain_balanced`）——
  `assistant.tool_calls` 与它的 `tool` 结果必须同进同出，否则模型 API 硬拒绝 400。

## 工具往返不剥离

**普通请求只做追加**：已经发出去过的消息，后续请求里逐字节不变。
改中间任何一条，provider 的前缀缓存就从那一条起整段失效 —— 而 Agent 每轮都在
追加工具往返，一旦每轮都改写中间的内容，缓存命中率归零。

因此工具往返**不做“留最近 N 轮、剥更早的”**：

- 不在压缩区间里的工具往返原样保留，一条不删；
- 进了压缩区间的，它就在摘要请求的前缀里 —— 摘要器看到的是**带工具结果原文**的
  那一段，工具结果由这一次摘要接管；
- 压缩落点受 `tool_chain_balanced` 约束，绝不切在悬空工具链上
  （`assistant.tool_calls` 与它的 `tool` 结果必须同进同出，否则模型 API 硬拒绝 400）。

`set_dialogue` 只做一件事：按 `covered_end` 丢掉已被摘要覆盖的前缀，其余原样装载。
每加一轮，上下文就是上一次的上下文**加上新消息**。

## 压缩触发

### `summary_token_threshold` 是什么

它是**请求体积的软上限**，不是模型窗口、也不是"压到多少"的目标：

```
估算体积 = 串起来发给模型的那份请求的估算 token
         = 系统提示词 + 插件各段 + 记忆摘要 + 未覆盖的对话 + 待并入的消息

估算体积 <= summary_token_threshold  →  放行，照原样发
估算体积 >  summary_token_threshold  →  先压既有历史，再用压缩后的上下文发
```

体积是**估算**（`approx_tokens_text` / `default_message_tokens`），不是精确计数。
它同时也是**分层视图的百分比基准**：`context_layout.budget_tokens` 就是它，
各段 `pct` 相对它算。默认 700000，按实际模型的窗口大小调。

超过阈值**不是错误**：超了就压，压完接着发。它是这套机制里唯一决定"该不该压"的数。

### 一次压缩的完整流程

`ContextCompactor.ensure_before_append()` 在拼入前跑：

```
1. 取未覆盖视图     view = messages[covered_end:]      ← 已压过的不再看
2. 组装压缩上下文   base = 整份装配结果 - 尾部（新输入 + 执行模式）
3. 估算并比较      total_token_estimate(base) + 待并入 > 阈值 ?
                   不超 → 返回 None（放行）
4. 取压缩区间      excerpt_by_target_tokens(view, keep_turns=full_user_rounds)
                   ├ 遮盖末尾 full_user_rounds 个用户轮（近场不压）
                   ├ 取遮盖起点之前的区间；那里没得压就连遮盖一起压
                   └ 落点退回轮边界（turn_boundary_floor）与工具链边界
                     （tool_chain_balanced）；退不回去就放弃本次压缩
5. 调摘要器        用 base 当前缀，末尾接压缩指令（前缀逐字节等于平常请求）
                   被压那一段（含工具结果原文）就在前缀里，不再另算素材
7. 记录            covered_end += 区间长度；摘要追加进 summaries
8. 立刻装回管线    set_summary_messages()：同一次请求随后就装配，
                   读到的必须是新摘要（晚一步就会用旧上下文发请求）
```

### 遮盖

末尾 `full_user_rounds` 个用户轮是**遮盖**：那是模型的近场，手里的活全在那里。

- 正常路径：遮盖不动，压它前面那一段；
- 遮盖前面压不出空间时（总共只剩 1 轮、或遮盖已盖住全部），**连遮盖一起压** ——
  极端情况压完整个上下文 **0 个用户轮**，摘要接管全部历史，剩下的只有头部；
- 遮盖是**偏好**，不是拒绝压缩的理由：压不动就是请求超上限直接失败。

系统提示词与插件各段都是 `system`、排在对话之前，所以"最后一个前置 system 之后"
这个区域**天然只覆盖对话**，不含任何系统设定。

### 区间怎么取

`excerpt_by_target_tokens(messages, keep_turns)` 给出要压掉的区间 `[0, cut)`：

- `cut` 是**遮盖起点**：区间不含被遮盖的那几轮；
- 遮盖前面没得压时 `cut` 落到末尾 —— 0 个用户轮是允许的结果；
- 落点已经过轮边界与工具链边界校验，退不回去就返回 `None`（本次不压）。

### 参数

| 参数 | 默认 | 含义 |
|---|---|---|
| `summary_token_threshold` | 700000 | 请求体积的软上限；超了才压，同时是分层百分比的基准 |
| `full_user_rounds` | 1 | 遮盖的末尾用户轮数（压不出空间时连它们一起压）|
| `summary_output_max_chars` | 5000 | 摘要篇幅上限（字） |
| 摘要前缀 | 固定复用 | 摘要请求带上与平常请求相同的前缀，这次调用才能命中已有缓存 |

**压缩是同步的**：没压完不接着发请求 —— 发出去的那一份必须是压缩后的。
**压缩是增强项，不阻断回合**：压缩器缺省、调用失败、返回空文本，都一律放行
（异常会记一条 stderr，不静默）。

`ContextCompactor.restore_from_events()` 从会话记录重放 `context_compacted` 事件重建
状态（幂等，`covered_end` 单调不减）。

## 摘要请求复用前缀

摘要也是一次模型调用，**结构与平常请求相同，只有尾巴不同**：

```
平常请求  系统提示词 + 插件各段 + 记忆摘要 + 对话 + 新输入 / 工具结果 + 执行模式
摘要请求  系统提示词 + 插件各段 + 记忆摘要 + 对话 + 压缩指令
```

前缀就是**同一份装配结果**剔除尾部，**逐字节等于上一次请求的前缀**，所以这一段命中
provider 的 KV 缓存，只按压缩指令那点新增内容付费。

**必须是整份**：中间挖掉一段就不再是"上次请求的前缀"，缓存会从挖掉的位置起全部失效。
四样东西必须一起对上，少一样整段缓存作废：

| 项 | 取法 |
|---|---|
| `system` 字段 | `context.system_text()` —— 与平常请求同一个值 |
| `tools` | 本次请求同一份 schema（`ModelModule` 传给 `ensure_before_append`） |
| 消息前缀 | 与平常请求**同一份**装配结果，末尾换成压缩指令 |
| 执行模式说明 | 本次的 `mode_note`，照平常请求补在前缀末尾 |

指令是**末尾一条 `system` 消息**，其中写明头部各段（系统提示词、插件各段、
记忆摘要）属于智能体的常驻设定、不是对话内容。

拿不到前缀时退回另一条路径：一条提问消息，
内容为指令 + 素材 JSON。

## 执行模式是请求尾部的临时后缀

执行模式（Auto / Plan / Execute）**不在系统提示词里**，也不进会话记录与事件：
`shell/prompts.py` 的 `resolve_mode_note()` 单独产出，组装请求时追加到**最后一条**。

模式若写在系统提示词里，切一次模式就会改动上下文最前面那一块，从该位置起整段前缀
缓存全部作废。放到末尾后，切换只改动最后一条。

```
系统提示词 + 插件各段 + 记忆摘要 + 对话 + 新输入 / 工具结果 + 执行模式
                                                                  ↑ 临时附加
```

`build_system_prompt()` 仍会产出模式段（供单独取用），`split_mode_section()` 负责把它
从系统提示词里切掉，只删模式段本身、保留其后的用户自定义规则与工具速查。
调用方显式给了系统提示词（mesh 的 `system`）时不再附加模式说明。

`_strip_mode_tail()` 在压缩前摘掉尾部模式，避免把它当对话内容压进摘要。

## 多段插件

一个插件可以注册**多条**注入源，它们共用段 key（插件名）、在分层里各占一行。
`plugins/skills` 就是这种形态：清单一条、常驻正文一条，两条各自带段名与抬头。

多条注入属于**同一个来源组**：组装位次由插件在清单里的位置决定，组内按注册顺序。
分段统计也按同一顺序逐段上报。

Skills 本身的分层做法见 [skills.md](skills.md)。

## 图片进请求的限制

图片按原样内联进请求体，所以带多少张要自己管（两道闸都在 `[context]` 里）：

| 参数 | 默认 | 含义 |
|---|---|---|
| `image_turns` | 3 | 只带**最近这么多轮用户发言**里的图片；更早的转文本占位。负数 = 不限 |
| `image_max` | 10 | 这几轮里最多带几张图；**最近一轮优先保**，超量的从最老的那一轮开始砍。负数 = 不限 |

按**轮**计数而不是按张：一轮里发三张算一轮。问"这张图"时指的是刚发的那一轮，
老图连带价值低，留在请求里却是实打实的体积。

被剥掉的图只从**发给模型的这一份**里消失 —— 事实流里的 base64 不动，
历史回显与重新提问都还能拿到原图。判定与占位文本在 `image_embed.strip_old_images()`。

## 摘要生成

`make_provider_summarizer(provider)` 返回一个 `fn(material) -> str`：把待压缩素材
序列化后与固定的摘要系统提示词组成一次**单轮、无工具**的模型请求，收集返回文本。

摘要提示词要求输出分节（背景 / 关键结论 / 约束与约定 / 未完成与待确认 / 风险与注意点），
并明确"禁止编造记录中未出现的内容"。

`max_chars` **只写进提示词作为篇幅约束，代码不做强制截断**，实际长度由模型遵守程度决定。

退化判定 `_is_degenerate_summary_body()`：空串，或长度不足 10 且只含占位文本，都算失败。

## 估算

估算器 `approx_tokens_text()` 按字符分区算：**CJK 每字 1 token，其余每 4 字符 1 token**，
`tool_calls` 的 `arguments` 也算进去。整体按 `len // 4` 会把中文正文低估约四倍 ——
实测一条会话估出 17 万而真实 prompt 100 万，阈值因此形同虚设、压缩永远晚触发。

压缩判定另外加上工具声明与模式说明的固定开销（它们不在 messages 里，却是请求体的一部分）。

`reasoning_content` 按 `reasoning_replay_tokens` 裁过之后还剩多少就计多少 ——
回传多少就花多少，估算与请求同一份。

分段浮层显示的是**估算**（对装配后的 messages 求和），与用量条里的 `prompt_tokens`
不是同一个数：后者是 API 回来的真值。两者差着工具声明与分词差异。

token 数是**估算**而非精确计数：

- `approx_tokens_text()`：按字符类型估算文本；
- `default_message_tokens()`：按消息结构估算；
- 图片按固定值 `IMAGE_TOKENS_PER_IMAGE` 计（固定 384，不读配置）。

## 延伸阅读

- [architecture.md](../architecture.md)：模块链与端口
- [plugins.md](plugins.md)：插件怎么注册注入源
- [skills.md](skills.md)：Skills 插件的三层披露
- [core.md](core.md)：`CompressModule` 在链上的位置
- [guide/config.md](../guide/config.md)：完整配置项
