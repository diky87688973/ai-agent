# 多模型（`multi_model` 插件）

`multi_model` 把模型条目声明成内核的模型目录来源：每个条目自带网关、协议与凭据，
内核按请求里的模型 id 路由到对应 provider 实例。插件同时提供输入区的模型下拉，
并在目录权威时接管设置页的模型配置入口。

插件机制本身见 [plugins.md](plugins.md)；各协议的请求体与流式解析见 [llm.md](llm.md)。

## 包结构

```
plugins/multi_model/
  plugin.py                  入口：解析配置、注册目录来源与端点、登记开屏脚本
  plugin-config.ini          真实配置（不入库）
  plugin-meta.json           身份元数据（name / desc / icon / version）
  settings-schema.json       设置页的结构化表单声明
  ui/model-picker.js         输入区模型下拉
  ui/picker.css              下拉样式
```

## 配置

每个模型一节 `[model:<id>]`：

```ini
[model:model-a]
provider = openai
base_url =
api_key =
model =
label =
context_window =
max_tokens =
thinking = 0
```

| 键 | 缺省 | 说明 |
|---|---|---|
| 节名 | 必填 | `[model:<id>]`；`id` 由表单顺序生成，不出现在界面 |
| `provider` | `openai` | 协议与端点拼法；未知值只让该条目无效 |
| `base_url` | 空 | 网关地址，必须持有这把密钥 |
| `api_key` | 空 | 鉴权密钥；模板占位符（如 `sk-请替换`）不算已配置 |
| `model` | 等于 `id` | 发给网关的线格式模型名 |
| `label` | 等于 `id` | 下拉与顶栏的显示名 |
| `context_window` | 空 | 该模型的上下文窗口（token），界面按它算占用率；它是物理上限，与 `[context]` 的压缩阈值不是一回事 |
| `default` | 无 | `1` 至多一条；都没标时取第一条有效条目 |
| `max_tokens` | 无 | 仅 Messages 协议：**回复**的 token 上限，不是上下文长度 |
| `thinking` | 无 | 仅 Messages 协议：`1` 下发 `enabled`，`0` 显式下发 `disabled`；省略时由网关取默认 |
| `thinking_budget_tokens` | 无 | 仅 Messages 协议：思考预算，须 ≥ 1024 且小于 `max_tokens` |

条目无效只影响自身：缺 `api_key` / `base_url`、未知厂商、数值写坏，该条从目录里剔除，
其余条目照常可用。重复 id 或同名节让整份文件作废。诊断格式为
`[plugin:multi_model] <文件> [model:<id>] <键> 无效：<原因>`。

配置用 `utf-8-sig` 读取，带 BOM 的文件可正常解析。

### 同一网关、两套协议

`provider` 决定协议与端点拼法，`model` 只决定发给网关的模型名。同一网关同时走两套
协议时，用不同 id 各写一节：

```ini
[model:chat]
provider = openai
base_url =
api_key  =
model    =

[model:messages]
provider = anthropic
base_url =
api_key  =
model    =
max_tokens =
```

INI 的节名必须唯一，因此两套协议不能共用一个 id。

### 思考模式

- `thinking = 0` 是显式关闭：请求体下发 `{"type":"disabled"}`。省略该键时由网关决定。
- `thinking_budget_tokens` 必须 ≥ 1024 且小于 `max_tokens`。不满足时适配器写一条
  stderr 诊断并关闭本轮思考，请求照常发出。
- 思考深度：Messages 协议按 `budget_tokens`，Chat Completions 协议走 `output_config.effort`。
  适配器不下发 `output_config`（官方端点拒绝未知字段），Chat Completions 侧取服务端默认档位。
- 思考模式下部分网关忽略 `temperature`，适配器因此不下发该字段。
- 带工具的同一轮里，thinking 块必须随 `tool_use` 原样回传；缺块时网关返回 400。
  历史轮不要求回传。块缺失且无法补齐时，适配器关闭本轮思考并留诊断。
- 思考模式下密钥必须与 `base_url` 指向的网关匹配，否则会被网关拒绝。

## 目录权威

插件装载后，模型目录是唯一来源；没有有效条目时服务仍启动，主页面模型下拉为空。
插件配置保存后热重载，不需要重启。

`GET /api/plugin/multi_model/catalog` 返回目录快照，不含 `api_key` 与 `base_url`：

```json
{
  "ok": true,
  "default": "model-a",
  "models": [{"id": "1", "label": "Model A", "provider": "openai",
              "context_window": 0, "default": true}],
  "invalid": []
}
```

## 设置页

插件声明 `settings-schema.json`，设置页按 schema 渲染结构化表单：每个条目一张卡片，
可增删、可改字段，协议切换时就地显隐 `max_tokens` / `thinking` 等字段。保存只重写
`[model:*]` 节，其它节逐字节保留；密钥字段只回显是否已配置，
留空表示沿用原值。

设置页不提供内核模型节；模型配置只由多模型插件的结构化表单维护。

## 模型下拉

插件用 `ctx.add_boot_script("ui/model-picker.js")` 登记开屏脚本，壳层只保留
`#modelPickerSlot` 容器。脚本通过 `window.aiAgentShell.models` 读取清单并写回选择，
样式经 `window.aiAgentShell.styles.load()` 按需注入。桥的契约见
[plugins.md](plugins.md#壳层公共桥)。

按钮与下拉都不设宽度上限：模型名是唯一的辨识依据，`model-a-openai` 与
`model-a-messages` 截断成同一个 `model-a-mess...` 后就分不出选的是
哪个版本。菜单用 `width:max-content` 跟着条目走，只在视口边界（`100vw - 24px`）
收口。

## 延伸阅读

- [plugins.md](plugins.md)：插件包形态、扩展点、界面资产与生命周期
- [llm.md](llm.md)：请求体、地址推导、流式解析与错误映射
- [../guide/config.md](../guide/config.md)：宿主配置项
