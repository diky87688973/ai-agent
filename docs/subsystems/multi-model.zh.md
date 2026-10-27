[English](multi-model.md) | **中文**

# 多模型（`multi_model` 插件）

`multi_model` 把模型条目声明成内核的模型目录来源：每个条目自带网关、协议与凭据，
内核按请求里的模型 id 路由到对应 provider 实例。插件同时提供输入区的模型下拉，
并声明设置页的「模型」入口。

插件机制本身见 [plugins.md](plugins.zh.md)；各协议的请求体与流式解析见 [llm.md](llm.zh.md)。

## 包结构

```
plugins/multi_model/
  plugin.py                  入口：解析配置、注册目录来源与端点、登记开屏脚本
  plugin-config.ini          真实配置（不入库）
  plugin-config.ini.example  配置模板（入库）
  plugin-meta.json           身份元数据（name / desc / icon / version / settings_tab）
  settings-schema.json       设置页的结构化表单声明
  ui/model-picker.js         输入区模型下拉
  ui/model-picker.css        下拉样式
```

## 配置

每个模型一节 `[model:<id>]`：

```ini
[model:model-a]
provider = anthropic
base_url =
api_key =
model =
label =
context_window =
compression_percent = 70
max_tokens =
thinking = 0
```

| 键 | 缺省 | 说明 |
|---|---|---|
| 节名 | 必填 | `[model:<id>]`；`id` 由表单顺序生成，不出现在界面 |
| `provider` | `openai` | 协议与端点拼法：`openai`（Chat Completions）或 `anthropic`（Messages）；未知值只让该条目无效 |
| `base_url` | 空 | 网关地址，必须持有这把密钥 |
| `api_key` | 空 | 鉴权密钥；模板占位符（如 `sk-请替换`）不算已配置 |
| `model` | 等于 `id` | 发给网关的线格式模型名 |
| `label` | 等于 `id` | 下拉与顶栏的显示名 |
| `context_window` | 必填 | 该模型的最大上下文窗口（token）；用于占用率和压缩阈值计算 |
| `compression_percent` | `70` | 压缩触发百分比，范围 10–90；阈值 = floor(窗口 × 百分比 / 100) |
| `default` | 无 | `1` 至多一条；都没标时取第一条有效条目 |
| `max_tokens` | `16000` | 仅 Messages 协议：**回复**的 token 上限，不是上下文长度 |
| `thinking` | `1` | 仅 Messages 协议：`1` 下发 `enabled`，`0` 显式下发 `disabled`；省略时适配器开启思考 |
| `thinking_budget_tokens` | `4096` | 仅 Messages 协议：思考预算，须 ≥ 1024 且小于 `max_tokens` |

条目无效只影响自身：缺 `api_key` / `base_url`、`provider` 值未知、数值写坏，该条从目录里
剔除，其余条目照常可用。重复 id 或同名节让整份文件作废。诊断写到 stderr，格式为
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

- `thinking = 0` 是显式关闭：请求体下发 `{"type":"disabled"}`。省略该键时适配器开启思考，
  预算取 `thinking_budget_tokens`。
- `thinking_budget_tokens` 必须 ≥ 1024 且小于 `max_tokens`。不满足时适配器写一条
  stderr 诊断并关闭本回合思考，请求照常发出。
- 思考深度：Messages 协议按 `budget_tokens`，Chat Completions 协议按请求里的
  `reasoning_effort`（由会话档位决定）。适配器不下发 `output_config`。
- 思考模式下部分网关忽略 `temperature`，Messages 适配器不下发该字段。
- 带工具的同一回合里，thinking 块必须随 `tool_use` 原样回传；缺块时网关返回 400。
  历史回合不要求回传。块缺失且无法补齐时，适配器关闭本回合思考并留诊断。
- 思考模式下密钥必须与 `base_url` 指向的网关匹配，否则会被网关拒绝。

## 目录权威

插件装载后，模型目录是唯一来源；没有有效条目时服务仍启动，主页面模型下拉为空。
插件配置保存后热重载，不需要重启。

`GET /api/plugin/multi_model/catalog` 返回目录快照，不含 `api_key` 与 `base_url`：

```json
{
  "ok": true,
  "models": [{"id": "1", "label": "Model A", "provider": "openai",
              "context_window": 1000000, "default": true}],
  "default": "1",
  "invalid": []
}
```

## 设置页

插件声明 `settings-schema.json`，设置页按 schema 渲染结构化表单：每个条目一张卡片，
可增删、可改字段，切换 `provider` 时就地显隐 `max_tokens` / `thinking` 等字段。
保存只重写 `[model:*]` 节，其它节逐字节保留；密钥字段只回显是否已配置，
留空表示沿用原值。

设置页不提供内核模型节；模型配置只在多模型插件的结构化表单里编辑。
插件在 `plugin-meta.json` 声明 `settings_tab` 为「模型」，启用后设置页左侧直接出现
「模型」入口；进入的是同一份多模型表单，不显示返回按钮。

## 模型下拉

插件用 `ctx.add_boot_script("ui/model-picker.js")` 登记开屏脚本，壳层只保留
`#modelPickerSlot` 容器。脚本经 `window.aiAgentPlugins.for()` 读 `/catalog` 取条目，
用 `window.aiAgentShell.models` 读取当前选择并写回；目录端点不可用时回落到
`shell.models.list()`。样式经 `window.aiAgentShell.styles.load()` 注入。
桥的契约见 [plugins.md](plugins.zh.md#壳层公共桥)。

按钮与下拉都不设宽度上限：模型名是唯一的辨识依据，同一网关的两个条目
（`model-a-openai` 与 `model-a-anthropic`）截成同一段前缀后就分不出选的是哪个。
菜单用 `width:max-content` 跟着条目走，只在视口边界（`100vw - 24px`）收口。

## 延伸阅读

- [plugins.md](plugins.zh.md)：插件包形态、扩展点、界面资产与生命周期
- [llm.md](llm.zh.md)：请求体、地址推导、流式解析与错误映射
- [../guide/config.md](../guide/config.zh.md)：宿主配置项
