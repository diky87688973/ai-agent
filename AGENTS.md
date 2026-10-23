# 项目 Agent 约定

## 入口

- 项目说明：`README.md`
- 架构：`docs/architecture.md`
- 模块边界：`docs/engineering-standards.md`
- 门禁与预算：`docs/quality-gates.md`
- 配置：`docs/guide/config.md`
- 用户提交规则：`rules/USER_RULES.md`
- 项目复核流程：`rules/PROJECT_CHECK.md`

## 必须执行

- 修改前读取文件当前内容，修改前备份到 `D:\FanFiles\deepseek-harness-bak\`。
- 后端改动运行对应 `python -m unittest tests.<module>`。
- 提交前按 `rules/USER_RULES.md` 完成复核；需要全量门禁时运行 `python scripts/ci.py`。
- 测试使用临时 `AI_AGENT_DATA_ROOT`，测试数据当场清理。

## 项目边界

- `data/` 只读：不删除、不移动、不覆盖用户会话与运行态数据。
- 未经明确要求不 commit、不 push、不重启进程、不改远端配置。
- 不引入项目外 Skills、外部配置、模拟开关或临时旁路。
- 不把密钥、真实配置、运行态数据、截图或临时文件放入源码树。

## 冲突处理

1. `production-standards`
2. `audit-procedure`
3. 项目文档与 `rules/`
4. 当前代码与门禁
