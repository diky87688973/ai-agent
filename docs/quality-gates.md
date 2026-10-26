# 质量门禁与预算

门禁与预算的当前值如下。数字的单一事实源是 `scripts/quality_budgets.py`；
预算常量调整后，`docs/complexity.md` 由生成器与校验器保持同步。

## 1. 预算总表

| 预算 | 常量 | 当前值 | 约束 | 备注 |
|---|---|---|---|---|
| 验收脚本跳过数 | `ACCEPTANCE_SKIP_BUDGET` | 1 | 只降不升 | 与白名单**分开**设置，白名单扩容不会自动放宽上限 |
| 覆盖率分包下限 | `COVERAGE_FLOORS` | 10 个包（25%–90%） | 只升不降 | `agent/core 85`、`agent/mechanisms 80`、`agent/capabilities 75`、`agent/shell 70`、`agent/entry 60`、`agent/gui 25`、`agent/update 60`、`agent/subagent 85`、`agent (top-level) 90`、`plugins 60` |
| 复杂度超阈值 | `MAX_FILE_LINES` / `MAX_FUNCTION_LINES` / `MAX_FILE_FUNCTIONS` | 800 / 80 / 40 | 硬失败 | 无豁免表；超过任一项即失败 |
| 同层私有导入 | `SAME_LAYER_PRIVATE_BUDGET` | 0 | 只降不升 | 同层跨模块 `_` 符号导入；超过预算失败 |

`check_complexity.py` 的约束：

- 任一文件、函数或函数数超过阈值 → **失败**；
- `docs/complexity.md` 与当前扫描结果不一致 → **失败**（生成文档漂移）。

## 2. 门禁步骤

`python scripts/ci.py --list` 是清单的唯一事实源（`scripts/ci_steps.py`）；
`.github/workflows/ci.yml` 由 `scripts/gen_ci_workflow.py` 从同一清单**逐字节生成**。

| 步骤 | 脚本 | 拦截什么 |
|---|---|---|
| 依赖方向 | `check_imports.py` | 上层被下层导入；`--scc` 打印全包强连通分量（当前 0 组） |
| 架构约束 | `check_architecture_hygiene.py` | 跨层私有导入、内核插件名、单通路门控、`assert` 控制流 |
| CI 工作流一致 | `check_ci_workflow.py` | `ci.yml` 与 `ci_steps.py` 渲染结果不逐字节一致 |
| 配置一致性 | `check_config_drift.py` | 真实配置多键 / 未登记节 |
| 密钥扫描 | `check_secrets.py` | 高置信度密钥、私钥、令牌模式 |
| 单测文档一致 | `gen_unit_tests_md.py --check` | `docs/unit-tests.md` 与测试方法集合不一致 |
| 静态检查 | `ruff check` | 未用导入、导入顺序、明显缺陷 |
| Python 下限 | `check_python_floor.py` | 用了高于声明下限（3.10）的语法 |
| UI JS 自检 | `check_ui_js.py` | JS 语法、共享作用域、被调用但未定义的辅助函数 |
| 静默异常 | `check_silent_except.py` | `pass`/`continue`、裸 `except`、宽捕获无上报、`suppress(Exception)`；判据见 [silent-exceptions.md](silent-exceptions.md) |
| README 一致性 | `check_readme.py` | 用例数、验收脚本数、`data/` 子目录与事实不符 |
| 确认文案无歧义 | `check_confirm_wording.py` | 写盘指引含糊、缺解锁工具、含解释性内容 |
| 注释文案 | `check_comment_style.py` | 注释残句、过程叙述、全角标点混排、Markdown 排版标记 |
| 注册表一致性 | `check_catalog.py` | 文档/注册表与代码不一致 |
| 复杂度阈值 | `check_complexity.py` | 任一文件或函数超阈值 |
| 复杂度文档一致 | `gen_complexity_md.py --check` | `docs/complexity.md` 与扫描结果不一致 |
| 适用性登记 | `check_applicability.py` | 申报结构错误；编号与 `scripts/standards_rules.py` 双向比对，并打印 N/A 占比 |
| 并发争用 | `tests.test_concurrency`（`-X dev`） | 共享可变状态的线程争用（K4） |

`docs/unit-tests.md` 是生成的可读测试目录，不是事实源；事实源是 `tests/`。

### 2.1 覆盖率（post）

`ci.py` 读取 `run_coverage.py` 发布的 `.coverage`，按顶层包校验 `COVERAGE_FLOORS`。
覆盖率数据的生成方式（CI 在 3.12 矩阵里执行）：

```bash
python scripts/run_coverage.py        # 跑全量单测并发布 .coverage
python scripts/check_coverage.py
```

`run_coverage.py` 把 `coverage run` 的产物先写到 `.coverage.tmp.<pid>`，再持锁
`os.replace` 成 `.coverage`：读侧只会看到完整的旧文件或完整的新文件，不会读到
并行采集写了一半的数据。同一份产物的写者与读者通过 `.locks/coverage.lock` 串行。

没有 `.coverage` 时该步返回 `2`（SKIP），在 CI 输出里可见，不计为通过；
校验期间数据文件被外部进程改写时同样返回 `2`，不拿半份数据出结论。

### 2.2 本地 JS 事件审计

**初衷**：重渲染的列表——每次刷新都重建节点的那种——不给每个列表项单独绑事件。
事件只在顶层 `document` 上绑一次，靠冒泡加 `closest()` / `contains()` 认目标。
逐项绑的代价是每次重建都新建一批监听，节点移除后监听若被闭包引用就一起泄漏。

`scripts/scan_js_events.py` 扫描 `agent/` 与 `plugins/` 下的 JS/HTML，把每条
`addEventListener`、`onXxx=` 属性赋值与内联 HTML 事件按静态依据分级：

| 分级 | 含义 | 需复核 |
|---|---|---|
| `per-item` | 落在循环体内（按花括号配平判，不看缩进） | 是 |
| `leak-risk` | 渲染路径上的全局监听，且无配对摘除 | 是 |
| `render-path` | 渲染函数内绑在持久目标上 | 是 |
| `inline` | 内联 HTML 事件，无法委托 | 是 |
| `delegated-ok` | 容器根 + `closest` / `contains` 目标识别 | 否 |
| `global-once` | 模块级或一次性初始化的全局监听 | 否 |
| `guarded-ok` | 同函数内有 `_xxxDelegated` / `dataset.bound` 守卫 | 否 |
| `ephemeral` | 目标由 `createElement` / `el()` 工厂新建，随节点销毁 | 否 |
| `ok` | 其余元素自身绑定 | 否 |

只输出清单，不自动失败。判准是静态近似，`render-path` 与 `leak-risk` 仍需
模型确认（例如 `ensureXxx()` 若有早退守卫，实际只绑一次）。

两个字段的含义容易混淆：

- **配对摘除**要求同目标 + 同事件 + 同回调 + 同 capture。任一不同都解绑不了，
  仍按无摘除计——具名回调只说明「能摘」，不等于「已摘」。
- **匿名**只在报告里展示，不参与分级。

单独运行：

```bash
python scripts/scan_js_events.py                    # 全部
python scripts/scan_js_events.py --only per-item    # 只看某一类
python scripts/scan_js_events.py --path composer    # 只看某目录
```

`scripts/ci.py` 在本地流水线末尾自动调用它。远端 CI 不执行这一项——
判断要读业务语义，CI 上没有模型；脚本自身也在 `GITHUB_ACTIONS=true` 时直接
跳过，属有意为之，不是漏配。

### 2.3 并行 CI

同一仓库同时只允许一条 `ci.py`：入口先拿 `.locks/ci.lock`（`mkdir` 原子创建），
被占用时按 `--lock-wait` 秒等待后报错，持有进程被强杀留下的锁按 PID 存活判定回收。
`--force-lock` 用于确认对方已失联后强拆。锁目录 `.locks/` 不进版本库。

## 3. 漂移与回退

1. **常量先于文档**：`python scripts/gen_complexity_md.py`；只改 Markdown 会被 `--check` 打回。
2. **预算上调的记录**：PR 描述里逐条列出新增命中位置与理由；脚本输出即审计线索。
3. **超阈值项**：拆分到阈值以内；不存在登记项。
4. **负向用例**（`X2`）住在 `tests/test_gate_negative.py`：每个门禁至少一条"坏输入必须失败"，
   且都是纯函数调用（不为跑用例去改真实仓库文件）。

## 4. 未接入项

无。覆盖率、配置漂移、生成文档校验、生成式 `ci.yml`、并发争用均已进入
`scripts/ci_steps.py`；`python scripts/ci.py --list` 与 `ci.yml` 的步骤集合一致。
