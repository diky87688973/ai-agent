[English](context.md) | **中文**

# 上下文

## 1. 概览

上下文模块负责把一次模型请求组装成稳定的消息前缀：系统提示词、插件贡献的上下文段、摘要与对话。

它只处理通用能力，不识别具体插件、业务方或工具；插件通过上下文插口贡献内容，上下文模块按注册结果组装。

## 2. 流程图

```text
SessionRunner.build_engine
  ├─ session_prompt()
  ├─ ContextPipeline.append_system()  -> CHUNK_SYSTEM
  ├─ ContextSources.collect_segments() -> CHUNK_PLUGIN
  ├─ Compactor                         -> CHUNK_MEM
  ├─ SessionLog.derive_messages()      -> CHUNK_FULL
  └─ mode_note / request tail
```

## 3. 插口协议

### 3.1 暴露的插口

| 插口路径 | 暴露的能力 | 关键属性 | 可替换/覆盖方式 |
|---|---|---|---|
| `app/kernel/modules/compress` | 上下文压缩模块入口 | `scope=session`、`order=2`、`master=true`；实现 `ModuleBase.execute(ports)`，按模块链产出事件 | 同路径 `replace=true` 覆盖；卸载时恢复原插口 |
| `backend/context/sources` | 插件上下文正文段注册 | 注册函数 `fn(conversation_id) -> list[str]`；每项一条 `system` 消息；`SourceMeta(key,label,prefix,count,plugin_rank)`；按插件清单顺序；单来源异常隔离并记错；返回 disposer | 同路径 `replace=true` 覆盖；卸载时恢复原插口 |
| `backend/context/assembly-hooks` | 装配后的消息变换钩子 | `hook(messages, conversation_id) -> list[dict] or None`；按注册顺序执行；返回非法值或抛错时记错并跳过；返回 disposer | 同路径 `replace=true` 覆盖；卸载时恢复原插口 |
| `backend/context/usage-segments` | 分段用量观察 | 每段 `{key,label,tokens,pct}`，加 `{key:"remaining",...}`；只读统计，不参与请求组装 | 同路径 `replace=true` 覆盖；卸载时恢复原插口 |
### 3.2 依赖的插口

| 依赖路径 | 依赖的能力 | 提供者 | 为什么依赖 | 不可用时的影响 |
|---|---|---|---|---|
| `app/host/services/prompt_sections` | 渲染系统提示词章节 | 宿主服务 | 生成 `CHUNK_SYSTEM` 的正文 | 系统提示词缺失，请求头不完整 |
| `app/host/services/context_sources` | 收集插件正文段 | 宿主服务 | 生成 `CHUNK_PLUGIN` | 插件上下文段缺失 |
| `app/host/services/context_hooks` | 装配后消息变换 | 宿主服务 | 在最终消息列表上追加/修改内容 | 钩子贡献的内容缺失 |
| `app/host/services/prompt_tail` | 请求尾部片段 | 宿主服务 | 追加模式说明和插件尾部 | 请求尾部缺失 |
| `app/host/services/provider` | 模型调用 | 宿主服务 | 生成压缩摘要 | 压缩不可用，保留原对话 |
| `app/host/services/session_factory` | 创建每会话上下文管线 | 宿主服务 | 按 `conversation_id` 隔离上下文 | 会话无法获得上下文管线 |
| `app/host/services/compactor_factory` | 创建压缩器 | 宿主服务 | 触发压缩与摘要 | 不压缩，上下文可能超限 |

上下文模块只依赖能力接口，不依赖任何具体插件的实现或路径。

## 4. 插口能力

### 4.1 系统提示词：`app/host/services/prompt_sections`

依赖 `PromptSections` 渲染系统提示词章节，上下文只接收最终文本并放入 `CHUNK_SYSTEM`。

- 输入：章节贡献方提供的渲染函数。
- 输出：一段系统提示词文本。
- 边界：上下文模块不解释章节语义，也不拼接插件名称。

### 4.2 插件正文段：`backend/context/sources`

每个来源注册一个函数和 `SourceMeta`：

```python
def source(conversation_id: str) -> list[str]:
    ...
```

- `key`：段 key，前端按它找渲染锚点。
- `label`：段名。
- `prefix`：可选前缀。
- `count`：可选主体数量回调。
- `plugin_rank`：按 `plugins.ini` 的插件顺序排序。

每条正文独立成一条 `system` 消息；单来源失败不影响其它来源。

### 4.3 装配钩子：`backend/context/assembly-hooks`

钩子在消息列表装配完成后执行：

```python
def hook(messages: list[dict], conversation_id: str) -> list[dict]:
    ...
```

- 返回 `None` 表示不修改。
- 返回新消息列表则替换当前结果。
- 抛出异常或返回非法结构时记错并继续下一个钩子。

### 4.4 压缩模块：`app/kernel/modules/compress`

该插口暴露压缩模块本身：

```text
scope=session
order=2
master=true
```

模块按 `ModuleBase.execute(ports)` 读取上下文，产出事件；压缩策略由 `compactor_factory` 提供，摘要由 `provider` 生成。

### 4.5 用量观察：`backend/context/usage-segments`

布局输出按段统计：

```text
CHUNK_SYSTEM / CHUNK_PLUGIN / CHUNK_MEM / CHUNK_FULL
```

每段包含 `key`、`label`、`tokens`、`pct`，末尾追加剩余容量。它只读，不改变请求。

### 4.6 历史摘要：`app/host/services/compactor_factory`

历史摘要不是 system 常驻消息，而是一条 user 检查点消息：

```text
<compacted-summary>
九节摘要正文
</compacted-summary>
```

- 整个会话只保留一条当前摘要；每次压缩用新摘要整体替换旧摘要。
- 摘要消息位于系统/插件段之后、当前对话之前，只作为已建立背景。
- 摘要不是新用户请求；不得因 `Pending Jobs` / `Next Step` 自动执行。
- 压缩请求复用上一次正常请求的精确前缀，再追加一条 user 压缩指令。

## 5. 其他细节

### 补充

压缩请求复用同一份头部，只替换尾部指令；普通请求与压缩请求的头部逐段一致。



- `CHUNK_MODE` 是保留空块；运行模式走请求尾部。
- 模式说明不写入会话事实，也不进入系统提示词。
- 压缩前剥离尾部临时内容，避免摘要污染。
- 用户轮是原子单位；工具往返不跨轮拆分。
- 图片按 `[context]` 的 `image_turns` / `image_max` 进入请求；超出的图片只从本次请求移除。
- token 是估算：CJK 约 1 token/字，其余约 1 token/4 字符，图片固定 `IMAGE_TOKENS_PER_IMAGE`。
- 上下文构建失败按请求失败传播，不静默回退为空上下文。

## 6. 延伸阅读

| 主题 | 文档 |
|---|---|
| 架构 | [architecture.zh.md](../architecture.zh.md) |
| 核心 | [core.zh.md](core.zh.md) |
| 插件 | [plugins.zh.md](plugins.zh.md) |
| 配置 | [config.zh.md](../guide/config.zh.md) |
