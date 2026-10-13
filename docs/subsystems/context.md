# 上下文管理

上下文管线回答两个问题：**发给模型的请求体由哪些部分组成**，以及**历史太长时怎么压缩**。

实现在 `agent/mechanisms/context_pipeline.py`（组装）与 `context_compactor.py`（压缩）。

## 七块上下文

请求体按固定顺序拼装，空块跳过。

| 顺序 | 块 | 常量 | 内容 |
|---|---|---|---|
| 1 | 系统提示词 | `CHUNK_SYSTEM` | 基础提示词 + 工具速查 |
| 2 | Skills | `CHUNK_SKILL` | 技能库索引，随技能加载能力接入 |
| 3 | 知识库 | `CHUNK_KB` | 知识库文件片段，经注入源刷新 |
| 4 | 记忆文件 | `CHUNK_MEM` | 摘要生成后落在这里 |
| 5 | 远期记忆 | `CHUNK_PURE` | 较老的对话轮次，按原文保留 |
| 6 | 近期记忆 | `CHUNK_FULL` | 最新的对话轮次，始终按原文保留 |
| 7 | 模式 | `CHUNK_MODE` | 当前运行模式的尾注 |

顺序由 `CHUNK_ORDER` 固定。展平后末端统一过一遍 `sanitize_fn`。

## 轮与块

- **Round**：以一条 `user` 消息起轮，含其后的 assistant 与 tool 消息。
- **ContextChunk**：命名块，内含若干 Round。

对话段展平时按 **远期 → 近期** 的时序，即越老的在越前面。

## 保留窗口

两个参数决定对话段保留多少原文：

| 参数 | 默认 | 含义 |
|---|---|---|
| `full_user_rounds` | 10 | 近期记忆保留的轮数，**从不被摘要** |
| `pure_user_rounds` | 10 | 远期记忆额外缓冲的轮数 |

保留窗口宽度 = `full_user_rounds + pure_user_rounds`。

摘要取段的计算规则（`dialogue_summary_excerpt_half_open_for_messages`）：

- 设用户轮总数为 `k`，保留量 `reserve = full + pure`；
- `k <= full`：无需摘要，返回 `None`；
- `full < k <= reserve`：摘要区间为 `[首轮, 第 k-full 轮)`；
- `k > reserve`：摘要区间为 `[首轮, 第 k-reserve 轮)`。

取到区间后要做两步修正：**工具链完整性外扩**（`adjust_excerpt_range_half_open()`，不把一次工具调用拆到两段）与**素材切轮**（`excerpt_slice_to_rounds()`，按轮边界对齐）。

## 压缩触发

`agent/mechanisms/context_compactor.py` 的 `ContextCompactor` 在拼入前检查预算：

```
当前估算 token + 待并入 token <= summary_token_threshold
```

不超就放行；超了就调摘要函数，把越界的轮次压成一段摘要文本，落到"记忆文件"块。

| 参数 | 默认 | 含义 |
|---|---|---|
| `summary_token_threshold` | 700000 | 触发压缩的估算 token 阈值 |
| `summary_output_max_chars` | 5000 | 摘要篇幅上限（字） |

**压缩是增强项，不阻断回合**：压缩器缺省、调用失败、返回空文本，都一律放行。

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

`make_provider_summarizer(provider, max_chars=...)` 返回一个 `fn(material) -> str`：

1. 把待压缩素材序列化成 JSON；
2. 用固定的摘要系统提示词 + 该 JSON 组成一次**单轮、无工具**的模型请求；
3. 收集返回的文本增量作为摘要。

摘要提示词要求输出分节（背景 / 关键结论 / 约束与约定 / 未完成与待确认 / 风险与注意点），并明确"禁止编造记录中未出现的内容"。

`max_chars` **只写进提示词作为篇幅约束，代码不做强制截断**，实际长度由模型遵守程度决定。

退化判定 `_is_degenerate_summary_body()`：空串，或长度不足 10 且只含占位文本，都算失败。

## 估算

token 数是**估算**而非精确计数：

- `approx_tokens_text()`：按字符类型估算文本；
- `default_message_tokens()`：按消息结构估算；
- 图片按固定值 `IMAGE_TOKENS_PER_IMAGE` 计（`context_compactor.py` 的常量，固定取 384，不读配置）。

## 注入源

`ContextSources` 把外部内容（知识库、技能）刷进对应块。注册方式与其它扩展点一致：注册返回注销句柄。

## 延伸阅读

- [architecture.md](../architecture.md)：模块链与端口
- [core.md](core.md)：`CompressModule` 在链上的位置
- [guide/config.md](../guide/config.md)：完整配置项
