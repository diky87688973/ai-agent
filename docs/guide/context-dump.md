# 上下文导出（开发者 CLI）

`scripts/dump_context.py` 按生产装配读取某个会话的事实，重建最近一次请求的完整上下文；只读，不调用模型，不注册为模型工具。

## 用法

```bash
python scripts/dump_context.py --cid <会话ID>
python scripts/dump_context.py --cid <会话ID> --format json --out context.json
python scripts/dump_context.py --cid <会话ID> --format json --include-tools --out context.json
```

可选参数：

| 参数 | 含义 |
|---|---|
| `--data-root` | 数据根；默认使用工程配置 |
| `--plugins-dir` | 插件根；默认使用工程配置 |
| `--plugins-path` | 插件清单；默认使用工程配置 |
| `--out` | 输出文件；默认 stdout |
| `--format` | `text` / `json` |
| `--include-tools` | JSON 中带完整工具 schema |

## 装配边界

```text
build_app() 读真实 config.ini / plugins.ini
→ SessionStore 读取会话事实
→ SessionRunner 提供系统提示词与模式尾部
→ ContextCompactor 恢复摘要与 covered_end
→ ContextPipeline 装配头部、对话与尾部
```

输出包含：

```text
messages          真实请求消息
system_prompt     系统提示词
mode_note         执行模式 + Todo-List + 插件请求尾部
segments          插件段名与数量
event_count       事实条数
covered_end       已压缩覆盖点
tools_count       工具数量
```

不写会话事实，不调用模型。上下文可能含用户数据，默认只落本地文件。

该脚本不注册为模型工具。模型侧的入口是内置 Skill：

```text
skills/context-dump.md
```

用户要求导出上下文时，模型先读取该 Skill，再按其中命令通过 `run_command` 执行脚本。Skill 规定当前会话 ID、输出目录、JSON/TXT 双份导出与验收摘要。
