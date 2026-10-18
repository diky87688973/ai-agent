# 质量门禁与预算

本文登记门禁与预算的当前值。数字的单一事实源是 `scripts/quality_budgets.py`；
预算常量调整后，本文与 `docs/complexity.md` 由生成器与校验器保持同步。

## 1. 预算总表

| 预算 | 常量 | 当前值 | 约束 | 备注 |
|---|---|---|---|---|
| 静默异常惯用法 | `SILENT_EXCEPT_IDIOM_BUDGET` | 119 | 只降不升 | 建表时按存量一次取齐；新增惯用法必须同时写明判据并调低别处 |
| 验收脚本跳过数 | `ACCEPTANCE_SKIP_BUDGET` | 1 | 只降不升 | 与白名单**分开**设置，白名单扩容不会自动放宽上限 |
| 覆盖率分包下限 | `COVERAGE_FLOORS` | 7 个包（60%–90%） | 只升不降 | `agent/core 85`、`agent/mechanisms 80`、`agent/capabilities 75`、`agent/shell 70`、`agent/entry 60`、`agent (top-level) 90`、`plugins 60` |
| 超阈值文件 | `FILE_COMPLEXITY` | 5 | 双向一致 | 登记项必须有承担者或拆分计划 |
| 超阈值函数 | `FUNCTION_COMPLEXITY` | 27 | 双向一致 | 键为 `相对路径::限定名`，类方法带类名，避免同名覆盖 |

`check_complexity.py` 的双向约束：

- 代码里超阈值、表里没有 → **失败**（新增债务）；
- 表里有、代码已不超阈值 → **失败**（登记过期，必须删）；
- 表与 `docs/complexity.md` 不一致 → **失败**（生成文档漂移）。

## 2. 门禁步骤

`python scripts/ci.py --list` 是清单的唯一事实源（`scripts/ci_steps.py`）；
`.github/workflows/ci.yml` 由 `scripts/gen_ci_workflow.py` 从同一清单**逐字节生成**。

| 步骤 | 脚本 | 拦截什么 |
|---|---|---|
| 依赖方向 | `check_imports.py` | 上层被下层导入；`--scc` 打印全包强连通分量（当前 0 组） |
| 架构约束 | `check_architecture_hygiene.py` | 跨层私有导入、内核插件名、单通路门控、`assert` 控制流 |
| CI 工作流一致 | `check_ci_workflow.py` | `ci.yml` 与 `ci_steps.py` 渲染结果不逐字节一致 |
| 配置一致性 | `check_config_drift.py` | `.example` ↔ `config_schema.py` 双向漂移；真实配置多键 |
| 单测文档一致 | `gen_unit_tests_md.py --check` | `docs/unit-tests.md` 与测试方法集合不一致 |
| 静态检查 | `ruff check` | 未用导入、导入顺序、明显缺陷 |
| Python 下限 | `check_python_floor.py` | 用了高于声明下限（3.10）的语法 |
| UI JS 自检 | `check_ui_js.py` | JS 语法、共享作用域、被调用但未定义的辅助函数 |
| 静默异常 | `check_silent_except.py --all-strict` | 未说明的静默 `except`；惯用法超预算 |
| README 一致性 | `check_readme.py` | 用例数、验收脚本数、`data/` 子目录与事实不符 |
| 确认文案无歧义 | `check_confirm_wording.py` | 写盘指引含糊、缺解锁工具、含解释性内容 |
| 注释文案 | `check_comment_style.py` | 注释残句、过程叙述、全角标点混排、Markdown 排版标记 |
| 注册表一致性 | `check_catalog.py` | 文档/注册表与代码不一致 |
| 复杂度登记 | `check_complexity.py` | 新增/过期复杂度债务 |
| 复杂度文档一致 | `gen_complexity_md.py --check` | `docs/complexity.md` 与登记表不一致 |
| 适用性登记 | `check_applicability.py` | 申报结构错误；编号与 `scripts/standards_rules.py` 双向比对，并打印 N/A 占比 |
| 并发争用 | `tests.test_concurrency`（`-X dev`） | 共享可变状态的线程争用（K4） |

### 2.1 覆盖率（post）

`ci.py` 读取 `coverage run` 产出的 `.coverage`，按顶层包校验 `COVERAGE_FLOORS`。
覆盖率数据的生成方式（CI 在 3.12 矩阵里执行）：

```bash
python -m coverage run --branch --source=agent,plugins --omit="*/web_assets/*" \
  -m unittest discover -s tests -p "test_*.py" -t tests
python scripts/check_coverage.py
```

没有 `.coverage` 时该步返回 `2`（SKIP），在 CI 输出里可见，不计为通过。

## 3. 漂移与回退

1. **常量先于文档**：`python scripts/gen_complexity_md.py`；只改 Markdown 会被 `--check` 打回。
2. **预算上调的记录**：PR 描述里逐条列出新增命中位置与理由；脚本输出即审计线索。
3. **登记项的删除**：代码拆到阈值以下后再删，提前删会先触发失败。
4. **负向用例**（`X2`）住在 `tests/test_gate_negative.py`：每个门禁至少一条"坏输入必须失败"，
   且都是纯函数调用（不为跑用例去改真实仓库文件）。

## 4. 未接入项

无。覆盖率、配置漂移、生成文档校验、生成式 `ci.yml`、并发争用均已进入
`scripts/ci_steps.py`；`python scripts/ci.py --list` 与 `ci.yml` 的步骤集合一致。
