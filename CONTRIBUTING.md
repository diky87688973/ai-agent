# 贡献指南

## 环境

- Python 3.10+
- Windows、Linux、macOS 均可运行内核与测试
- 界面验收需要 Playwright 与 Chromium

```bash
python -m pip install -e . -c constraints.txt
python -m pip install ruff coverage
```

## 开发规则

- 分层顺序为 `entry → shell → capabilities → mechanisms → core`，依赖方向由 `scripts/check_imports.py` 校验。
- `data/` 是运行时会话数据，测试与开发过程不得写入、移动或删除。
- `config.ini`、`plugins/*/plugin-config.ini`、`.env` 与密钥文件不进入提交。
- 工具声明变更后同步生成注册表：`python scripts/gen_catalog.py`。
- 测试变更后同步生成用例文档：`python scripts/gen_unit_tests_md.py`。
- CI 工作流由生成器维护：`python scripts/gen_ci_workflow.py --check`。
- 界面 JS 与 CSS 保持插件归属：插件界面资产放在对应插件的 `ui/` 目录。
- 注释解释代码约束与边界，不记录对话过程、评审过程或后续计划。

## 提交前检查

```bash
python -m ruff check agent tests scripts
python scripts/check_ui_js.py
python -m unittest discover -s tests -p "test_*.py" -t tests
python scripts/ci.py --fast
```

涉及验收行为时执行完整流水线：

```bash
python scripts/ci.py
```

## 提交规范

提交信息使用 `feat:`、`fix:`、`docs:`、`test:`、`refactor:`、`chore:` 前缀，正文说明行为变化与验证方式。

Pull Request 包含：

- 变更目的与影响范围
- 复现步骤或设计说明
- 实际执行的检查命令与结果
- 关联 Issue

## 文档

- 架构与子系统文档位于 `docs/subsystems/`。
- 方案文档位于 `docs/plan/`。
- 配置项位于 `docs/guide/config.md`。
- 安全问题按 [SECURITY.md](SECURITY.md) 的流程提交。
