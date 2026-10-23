# 项目标准对齐优化方案

> 适用标准：`production-standards.md` v1.1（MUST / SHOULD 两级）
> 该方案只解决**存量工程债**；两个新需求的方案见 [history-paging.md](history-paging.md)、[multi-model.md](multi-model.md)。
> 结论：标准里的 **13 项 MUST、2 项 SHOULD** 均已达标，验收证据见 §0.4。

## 0. 结论先行

### 0.1 为什么必须先对齐

| 新需求 | 会被存量问题卡住的点 | 后果 |
|---|---|---|
| 历史分页 | `A2` 两个依赖环未清 | 环未清时无法证明新模块不在环上；先拆，新增依赖边才有判据 |
| 历史分页 / 多模型 | `X5` 覆盖率只统计 `agent/core` + `agent/mechanisms` | 新模块 `agent/shell/*`、`plugins/*` 不进任何下限，等于没测 |
| 多模型 | `K4` 无并发争用作业 | `ModelCatalog` 的锁只能靠人眼审，原子替换无机器证明 |
| 两者 | `Y1` `ci.yml` 与 `ci_steps.py` 不同源（覆盖率步骤只在 yml） | 本地全绿不代表 CI 全绿，反之亦然 |
| 两者 | `D3` `docs/unit-tests.md` 无漂移校验 | 新增测试后文档必然过期，且无人发现 |

### 0.2 缺陷总览

| # | 准则 | 缺陷 | 级别 | 阶段 |
|---|---|---|---|---|
| 1 | `C5` | `agent/` 下 4 处 `assert` 参与控制流 | MUST | P1 |
| 2 | `A2` | 2 组、11 个模块的循环依赖 | MUST | P1/P2 |
| 3 | `B1` | `PluginSegments.items/counts` 是可变 `list` | MUST | P1 |
| 4 | `X2` | 9 个门禁没有任何负向用例 | MUST | P4 |
| 5 | `X5`/`X6` | 覆盖率不在 `ci_steps`、无分包下限、口径漏 shell/plugins | MUST | P3 |
| 6 | `X7` | 验收 skip 上限恒等于白名单长度，永远不可触发 | MUST | P3 |
| 7 | `E2a` | 静默异常惯用法无数量、无预算、无递减约束 | MUST | P3 |
| 8 | `R1` | 超阈值文件与函数无登记表 | MUST | P0 |
| 9 | `T4` | 配置漂移且无校验；`web-ui-config.ini` 正本入库、无样例文件 | MUST | P0/P2 |
| 10 | `D3` | `docs/unit-tests.md` 已漂 14 个用例，生成器无 `--check` | MUST | P3 |
| 11 | `K4` | 无并发/争用检测作业 | MUST | P4 |
| 12 | `0.5` | 无 `docs/applicability.md` | MUST | P0 |
| 13 | `Y1` | yml 有覆盖率步、`ci_steps` 没有；校验器靠 `_ALLOWED_EXTRA` 放行 | MUST | P3 |
| 14 | `B3` | `agent/core/ports.py` 21 处 `Any` | SHOULD | P5 |
| 15 | `R2` | `agent-ui.js:744-746` 注释残句 + 重复 | SHOULD | P1 |

### 0.3 顺序

```
P0 登记表与门禁骨架   → P1 小范围硬伤（assert/不可变/注释/quality 环）
→ P2 拆 shell↔app 环（引入 entry 层）  ← 新需求在此之后可开工
→ P3 门禁增强（覆盖率/skip/预算/漂移/生成式 yml）
→ P4 负向用例 + 并发作业 → P5 收尾（B3/全量验收）
```

### 0.4 落地状态

| 阶段 | 状态 | 落地内容 | 遗留项 |
|---|---|---|---|
| P0 | ✅ 完成 | `scripts/quality_budgets.py`、`check_complexity.py`、`gen_complexity_md.py`、`docs/complexity.md`、`check_applicability.py`、`docs/applicability.md`、`docs/quality-gates.md`；三道新门禁进 `ci_steps.py` 与 `ci.yml` | 无 |
| P1 | ✅ 完成 | 4 处 `assert` 移除；`PluginSegments` 入口即冻结（含单测）；`quality` 包导入改为 `import a.b.c`；`agent-ui.js` 残句注释清理；`check_imports.py --scc` 落地 | 无 |
| P2 | ✅ 完成 | 新增 `agent/entry/{web,cli,headless}.py`；`shell` 不再导入 `agent.app`；`_date_group` 抽到 `agent/shell/timefmt.py`；`LAYERS` 加 `entry`；启动脚本/README/子系统文档同步 `python -m agent.entry.*`；SCC 0 组 | 无 |
| P3 | ✅ 完成 | 覆盖率进 `ci_steps`（`--source=agent,plugins` + 7 个分包下限）；`ACCEPTANCE_SKIP_BUDGET` 独立；静默异常预算 119；`config_schema.py` + `check_config_drift.py`；`gen_unit_tests_md.py --check`；`gen_ci_workflow.py` 逐字节生成 `ci.yml` | 无 |
| P4 | ✅ 完成 | `tests/test_gate_negative.py`（每个门禁正/负例）、`tests/test_concurrency.py`（8 条争用用例）、`tests/test_import_graph.py`；CI 增 `-X dev` 并发争用步 | 无 |
| P5 | ✅ 完成 | `agent/core/ports.py` 协议化（`ProviderPort` / `RegistryPort` / `PipelinePort` / `SessionsPort` / `ProgressSink` / `CancelCheck`）；`docs/architecture.md` 补 `entry` 层；README 文档索引 | 无 |

验收：`python scripts/ci.py` **29 步全绿**（门禁 17 + 单测 + 验收 10 + 覆盖率）；
`python scripts/check_imports.py --scc` 输出 **0 组**环；`python scripts/ci.py --list`
与 `.github/workflows/ci.yml` 的步骤集合由 `check_ci_workflow.py` 逐字节比对。

## 1. 审计口径（可复现）

以下命令均在仓库根执行；结论中的数字由这些命令直接得出。

```bash
# 依赖环：只算运行期导入，跳过 `if TYPE_CHECKING:` 体内的导入
python scripts/check_imports.py --scc

# assert
rg -n "assert " agent --glob "*.py"

# 复杂度
python scripts/check_complexity.py --list

# 静默异常
python scripts/check_silent_except.py --all-strict

# 覆盖率 / 工作流漂移
python scripts/check_ci_workflow.py
git ls-files "*.ini"
```

`--scc` 与 `--list` 已随 P0/P1 落地；这里的数字取自它们的输出，可直接复跑复核。

### 1.1 依赖图的解析规则（必须先定死，否则环数会随实现者口味变化）

| 写法 | 边指向 | 理由 |
|---|---|---|
| `import a.b.c` | `a.b.c` | 直接模块依赖 |
| `from a.b.c import name` | `a.b.c`；若 `a.b.c.name` 是模块再加一条到它 | 名字可能是子模块 |
| `from a.b import sub` 且 `a/b/sub.py` 存在 | `a.b.sub` | Python 会导入子模块，不依赖包属性 |
| `from a.b import symbol` | `a.b`（即包 `__init__`） | 运行时真的执行包初始化 |
| `if TYPE_CHECKING:` 体内 | **不建边** | 类型专用，运行期不加载；但必须真的只用于注解 |
| `try: import x\nexcept ImportError:` | 建边 | 可选依赖也是依赖方向 |

> 按此规则，`classic_adapter/__init__.py → adapter.py` 与 `adapter.py → contract.py` 都是单向，不构成环。当前真实环只有 2 组。

### 1.2 测量结果

第一组（`mechanisms` 层内，3 模块）：

```
agent.mechanisms.quality (__init__)
agent.mechanisms.quality.gate
agent.mechanisms.quality.pipeline_bridge
```

第二组（`shell` 与装配根，8 模块）：

```
agent.app
agent.shell.classic_adapter (__init__)
agent.shell.classic_adapter.adapter
agent.shell.classic_adapter.inbound
agent.shell.classic_adapter.outbound
agent.shell.web
agent.shell.web.web_api
agent.shell.web.web_routes
```

## 2. MUST 缺陷逐项方案

### 2.1 `C5` 禁止用 `assert` 做控制流

**证据**

| 位置 | 代码 | 问题 |
|---|---|---|
| `agent/core/host.py:164` | `assert result is not None` | `-O` 下断言消失，`None` 被写进 `_last_result`，错误推迟到属性访问才暴露 |
| `agent/core/host.py:231` | `assert self.last_result is not None` | 同上，`-O` 下 `None` 继续往下走 |
| `agent/core/chain.py:95` | `assert isinstance(outcome, Outcome)` | 前一行 `_require_outcome` 已校验，属重复断言 |
| `agent/core/chain.py:133` | `assert self.result is not None` | `-O` 下 `result` 为 `None` 时返回错误类型 |

**根因**：把"内部不变量"当成输入校验，且默认解释器不开 `-O`。

**改法**

1. `host.py`：先落局部变量再判空，抛 `RuntimeError("step 结果为空：<step id>")`；属性 getter 保留"未执行即访问"的独立错误，不依赖 `assert`。
2. `chain.py:95`：删除（保留 `_require_outcome`）。
3. `chain.py:133`：改为
   ```python
   if self.result is None:
       raise RuntimeError("chain 已结束但没有结果：缺少终态 step")
   ```
4. `check_architecture_hygiene.py` 增加规则 `assert_in_agent`：`agent/**/*.py` 出现 `ast.Assert` 即失败（`tests/` 不受限）。
5. 负向用例进 `tests/test_architecture_hygiene.py`（P4 建）：临时目录写一个含 `assert` 的包，断言检查器返回违规。

**验证**：`python -O -m unittest tests.test_core_chain tests.test_core_host` 通过；`rg "assert " agent` 零命中。

**风险**：低。`-O` 下行为从"静默继续"变为"明确抛错"，属预期修正。

### 2.2 `A2` 消除循环依赖

#### 环一：`quality` 包

**根因**：`agent/mechanisms/quality/gate.py:10-11`

```python
from agent.mechanisms.quality import checks as _checks
from agent.mechanisms.quality import diagnose as _diagnose
```

`from 包 import 子模块` 会先执行包 `__init__`，而 `__init__` 第 28 行又导入 `gate`。`pipeline_bridge` 因 `__init__` 再入被卷进同一个强连通分量。

**改法**（只改 2 行，语义不变）：

```python
import agent.mechanisms.quality.checks as _checks
import agent.mechanisms.quality.diagnose as _diagnose
```

`checks.py` / `diagnose.py` 对 `QualityGate` 的引用已在 `TYPE_CHECKING` 内，保持现状。

**验证**：`python scripts/check_imports.py --scc` 只剩第二组；`python -c "import agent.mechanisms.quality"` 正常；质量门控单测全绿。

#### 环二：`shell` ↔ `app`

**根因**（三条边，缺一不成环）

| 边 | 位置 | 用途 |
|---|---|---|
| `shell.web → app` | `web.py:20` `from agent.app import App, build_app` | `build_shell_app()` 与 `__main__` 启动 |
| `web_api → app` | `web_api.py:14` `from agent.app import App` | 仅类型注解 |
| `inbound → shell.web` | `inbound.py:558`（函数体内延迟导入） | 复用 `_date_group` |
| `app → shell` | `app.py:86-88` | 装配根，方向正确 |

`inbound.py` 的延迟导入是**用函数内导入掩盖环**，标准明令禁止；`_date_group` 在 `web_api.py:884` 有实现，`inbound.py:553-560` 只是转发，转发本身也是重复实现。

**改法（引入 `entry` 层）**

1. 新增顶层 `agent/entry/`，只做"装配 + 进程入口"，允许依赖 `agent.app` 与 `agent.shell`，**不允许被任何层反向导入**。
   ```
   agent/entry/__init__.py
   agent/entry/web.py      # 装配 app 后调用 agent.shell.web.serve(app, ...)；含 build_shell_app / main
   agent/entry/cli.py      # 装配 app 后调用 agent.shell.cli.cli.main(argv, app_factory=...)
   agent/entry/headless.py # 装配 app 后调用 agent.shell.cli.headless.main(argv, app_factory=...)
   ```
2. `agent/shell/web.py`：删除 `from agent.app import ...`（`web.py:20`）与 `build_shell_app`/`main`/`__main__`；保留 `serve(app, ...)`（只负责壳怎么跑）与 `create_server(app, ...)`。`create_server` 签名不变（`scripts/acceptance_web.py:33` 与 `scripts/retired/acceptance_ui.py:49` 在用）。
3. `agent/shell/web_api.py`：`App`（`web_api.py:14`）改为 `TYPE_CHECKING` + 字符串注解；若实施时发现存在运行期 `isinstance(x, App)`，改用协议判断，不允许为了去掉导入而保留运行期依赖。
4. `agent/shell/classic_adapter/inbound.py`：`_date_group` 抽到 `agent/shell/timefmt.py`（纯函数，零内部依赖），`web_api.py:884` 与 `inbound.py` 都从那里导入；删除 `inbound.py:553-560` 的转发与 558 的延迟导入，同时删掉 `web.py:43` 对 `_date_group` 的再导出（私有名字，不保留兼容层）。
5. `agent/shell/chat.py` / `agent/shell/headless.py`：删除顶部 `from agent.app import build_app` 与 `__main__`；入口改为接收现成 app —— `chat.main(argv, app_factory=...)` / `chat.build_session(argv, app=...)`，`headless.run(app, text)` / `headless.main(argv, app_factory=...)`，由 `agent/entry/*` 负责构造 app。`tests/test_chat_shell.py:22` 的导入路径保持不变（`build_session` 等辅助函数留在原模块）。
6. `LAYERS` 扩为 `("core", "mechanisms", "capabilities", "shell", "entry")`，同步 `check_imports.py:12` 与 `check_architecture_hygiene.py:12`；`entry` 只能向下。
7. 启动命令改 `python -m agent.entry.web`；同步 `start.bat`、`start.sh`、README、`docs/subsystems/shell.md:185-186`。

**为什么不是"函数内 import"**：标准 `A2` 要求环可机器证明为零；函数内导入只是把边藏起来，SCC 检查若按运行期调用图建模仍会命中。`entry` 层是真实的分层修正。

**验证**

- `python -m agent.entry.web --host 127.0.0.1 --port 8765` 起服务，首页与 `/api/chat/history` 正常。
- `python scripts/check_imports.py --scc`：0 组。
- `python -m agent.entry.headless` 冒烟；`acceptance_web` 全绿。
- `python -c "import agent.shell.web"` 不触发 `agent.app` 导入（可用 `sys.modules` 断言）。

**风险**：中。入口路径是用户可见行为（`start.bat`）。按 `R5` 不保留旧命令兼容层：脚本、README、子系统文档在同一个 PR 一并改。

### 2.3 `B1` `PluginSegments` 深不可变

**证据**：`agent/mechanisms/context_pipeline.py:540-549`

```python
@dataclass(frozen=True)
class PluginSegments:
    items: List[Tuple[str, str, str]] = field(default_factory=list)
    counts: List[int] = field(default_factory=list)
```

`frozen=True` 只冻结字段绑定，`items.append(...)` 仍可改；这正是标准点名的"表面 tuple"。

**改法**

1. 字段类型改 `Tuple[Tuple[str, str, str], ...]` / `Tuple[int, ...]`，默认 `()`。
2. 构造点 `:660` 改 `PluginSegments(items=tuple(items), counts=tuple(counts))`。
3. 消费点 `:1011` 已是 `list(segments.counts)`，无需改；全仓搜 `segments.items` 确认无 `append`/下标赋值。
4. 单测：`segments.items.append(...)` 抛 `AttributeError`；`segments.counts[0] = 9` 抛 `TypeError`。

**验证**：`tests/test_context_assembly.py` 新增 2 条断言；`python scripts/ci.py` 全绿。

### 2.4 `X2` 门禁负向用例

现状：只有 `tests/test_catalog.py`、`tests/test_architecture_hygiene.py` 有负向用例；以下 9 个门禁没有任何"输入坏数据必须失败"的证明。

| 门禁 | 现有形状 | 需要暴露的入口 |
|---|---|---|
| `check_imports.py` | 全仓扫描，无参数 | `check(root) -> list[str]` + `--scc` |
| `check_silent_except.py` | 已有 `--all-strict` | 输出里加预算计数（见 2.7） |
| `check_readme.py` | `main()` 内联 | 拆 `check(readme_text, facts) -> list[str]` |
| `check_comment_style.py` | `main()` 内联 | 拆 `check(text) -> list[str]` |
| `check_ci_workflow.py` | 读真实 yml | 拆 `check(yml_text, steps) -> list[str]` |
| `check_python_floor.py` | 扫描全仓 | `check(root)` |
| `check_ui_js.py` | `main()` 内联 | `check(js_text)` |
| `check_confirm_wording.py` | `main()` 内联 | `check(text)` |
| `check_acceptance_skips.py` | 读 `ACC_SKIP_FILE` | `evaluate(names, budget) -> list[str]` |

**统一约定**：每个门禁模块提供纯函数 `check(...)`，`main()` 只负责读写文件与退出码。负向用例在临时目录构造最小坏样本，断言"返回非空且信息含定位（文件:行）"。

**验收**：`tests/test_gate_negative.py` 覆盖上表 9 项，用例数 ≥ 18（每项正、负各一）。

### 2.5 `X5` / `X6` 覆盖率

**证据**

- `ci.yml:217-226` 有覆盖率步：`--source=agent/core,agent/mechanisms`、`--include="agent/core/*,agent/mechanisms/*"`、`--fail-under=80`。
- `scripts/ci_steps.py` 的 `catalog()` 里**没有**这一步；本地 `ci.py` 从不跑覆盖率。
- 口径缺 `agent/capabilities`、`agent/shell`、`plugins/*`，新需求代码全在缺口里。
- 只有一个总下限，无分包下限（`X6`）。

**改法**

1. `scripts/ci_steps.py` 增加 `kind="post"` 的覆盖率步，与 yml 生成器同源（见 2.10）。
2. `--source=agent,plugins`，`--omit="*/web_assets/*"`；JS 不计入 Python 覆盖率，由 `check_ui_js.py` 负责。
3. 新增 `scripts/check_coverage.py`：
   - 读 `.coverage`，按顶层包（`agent/core`、`agent/mechanisms`、`agent/capabilities`、`agent/shell`、`plugins`）分别算行覆盖率；
   - 下限表写在 `scripts/quality_budgets.py`（单一事实源），低于下限即失败并打印"包 / 测得值 / 下限 / 缺口行号前 10 条"；
   - 同时输出总覆盖率，供人看趋势。
4. **下限的确定方式**：全量测量后把测得值向下取整到整数个百分点作为初始下限，与测量结果同一个 PR 提交；此后只上调，下调需在 PR 描述里写原因并附新增测试，避免留下与真实覆盖率脱节的低阈值。
5. `pyproject.toml` 只保留 `[tool.coverage.run]` 的 `branch = true`，不再写 `fail_under`（避免双处阈值）。

**验收**：`python scripts/ci.py` 末尾出现分包覆盖率表；把任意包的 `coverage report` 人为降到下限以下，`check_coverage.py` 退出码 1（负向用例用伪造的 `.coverage` 文件，不跑真单测）。

### 2.6 `X7` 验收 skip 上限不可触发

**证据**：`scripts/ci_steps.py:18-21`

```python
ALLOWED_ACCEPTANCE_SKIPS = frozenset({"acceptance_mvp3"})
MAX_ACCEPTANCE_SKIPS = len(ALLOWED_ACCEPTANCE_SKIPS)
```

`check_acceptance_skips.py:125-132` 先拒绝白名单外的名字，再比较 `len(uniq) > MAX`。白名单只有 1 项时，上限恒为 1 且 `uniq` 最大也是 1，**永远不可能触发**。

**改法**

1. 预算独立：`scripts/quality_budgets.py` 定义 `ACCEPTANCE_SKIP_BUDGET = 1`，`ci_steps` 只引用。
2. 顺序调整：先比预算、再验白名单。这样即使白名单扩到 3 项，预算仍是硬约束。
3. 负向用例：直接调用 `evaluate(["a", "b"])`，断言在 `BUDGET=1` 下失败；再断言 `["a"]` 通过。

**为什么不是把预算设成 0**：当前 `acceptance_mvp3` 在 CI 上确实按设计跳过（依赖 `edge-tts` 不安装），设 0 会让 CI 常红。1 是"已知且唯一"的诚实值。

### 2.7 `E2a` 静默异常预算

**证据**：`python scripts/check_silent_except.py --all-strict` 输出

```
静默 except 共 164 处
  · 已说明（惯用法）：119 处
  · 内核路径未说明：0 处
  · 旁路未说明：    0 处
```

没有数量上限，也没有"只能降不能升"的约束；新增第 120 处惯用法不会有任何阻力。

**改法**

1. `scripts/quality_budgets.py`：`SILENT_EXCEPT_IDIOM_BUDGET = 119`。
2. 脚本输出改为 `惯用法 119/119（预算 119）`，超预算打印新增命中位置并退出 1。
3. 上限只降不升：PR 降低预算时同步改常量；提高预算必须在 PR 里逐条列出新增理由（脚本打印的定位就是审计线索）。
4. 记录历史：`docs/quality-gates.md`（P0 新建）列"预算 / 当前值 / 最近一次变化 / 原因"。

**验收**：负向用例在临时树里放 120 处惯用法，断言失败；真实仓库保持 119 通过。

### 2.8 `R1` 复杂度登记表

**测量**（`agent/` + `scripts/`，排除 `scripts/retired/`）

| 文件 | 行数 |
|---|---|
| `agent/mechanisms/context_pipeline.py` | 1165 |
| `agent/shell/classic_adapter/inbound.py` | 1054 |
| `agent/mechanisms/session_store.py` | 936 |
| `agent/shell/web_api.py` | 909 |

超 80 行的函数：27 个（`check_complexity.py --list` 生成清单）。

**改法**

1. `scripts/quality_budgets.py` 维护 `FILE_COMPLEXITY` / `FUNCTION_COMPLEXITY` 两张表，每项必须带 `reason` 与 `owner`（承担者）或 `split_plan`（拆分计划）。
2. `docs/complexity.md` 由 `scripts/gen_complexity_md.py` 从表生成；`check_complexity.py` 同时做三件事：
   - 实际超阈值但不在表里 → 失败（新增债务）；
   - 在表里但实际已不超阈值 → 失败（登记过期，必须删）；
   - 表里的登记行数与 `docs/complexity.md` 不一致 → 失败（`D3` 漂移）。
3. 登记表里的每一项都必须有明确归属。新文件需 <800 行、函数 <80 行；超过阈值时进表并同时给出拆分计划，由 PR 审 + 门禁保证。

**验收**：`python scripts/gen_complexity_md.py --check` 零差异；临时把某文件加 1 行到 801，门禁失败。

### 2.9 `T4` 配置漂移

**证据**

| 问题 | 证据 |
|---|---|
| 正本入库、无样例文件 | `git ls-files web-ui-config.ini` 命中；不存在 `web-ui-config.ini.example` |
| 本地正本多出键 | `config.ini` 有 `[context] summary_prefix_reuse`，schema 未登记 |
| 无 schema，真实配置无法双向校验 | `plugins.ini` 的 `plugin:*` 节是"启用集合"，与插件配置天然不同，直接比键集会误报 |

**改法**

1. 新增 `agent/config_schema.py`：`SCHEMA: dict[str, dict[str, str]]`（节 → 键 → 默认值），`agent/config.py` 的 `get_*` 改为按 schema 取键；未登记的键读取即报错（带节、键、文件）。
2. `web-ui-config.ini` 入库；不提供样例文件；加载器在文件缺失时使用 schema 默认值（不报错）。
3. `scripts/check_config_drift.py`：
   - 真实配置 ↔ `SCHEMA` 比对（未登记键失败）；
   - 若真实文件存在，额外检查"真实键 ⊆ schema"，多出的键失败并给出行号（`configparser` 不给行号，用文本扫描定位节）；
   - 真实文件不存在只打印 `[SKIP] 未找到 config.ini（干净克隆）`，不失败——这是 `E5` 要求的可见跳过。
4. 删除 `config.ini` 里 schema 未登记的 `summary_prefix_reuse`，或在 schema 中登记该键。

**验收**：给 `config.ini` 或 `web-ui-config.ini` 加一个未登记键 → 门禁失败；无真实配置时跳过并通过。

### 2.10 `D3` 生成文档漂移

**证据**

- `docs/unit-tests.md` 写 1146 个用例，实际 1160 个；14 个测试方法在文档里完全找不到。
- 生成器 `scripts/_gen_unit_tests_md.py` 只能"写"，没有 `--check`。
- `ci.yml` 与 `ci_steps.py` 都不跑它。

**改法**

1. 生成器加 `--check`：在内存里生成全文，与磁盘比对，不同则打印首处差异并退出 1。
2. 生成器改为可导入 `build() -> str`，`main()` 只做写/比对；文件更名
   `_gen_unit_tests_md.py` → `gen_unit_tests_md.py`（去掉"内部脚本"前缀，纳入门禁）。
3. `ci_steps` 增加 `门禁 生成文档一致`（`gen_unit_tests_md --check`、`gen_complexity_md --check`）。
4. 生成与校验的先后：先重生成 `docs/unit-tests.md`，再开门禁（反序会先红）。

**验收**：删掉文档里任意一行 → 门禁失败；重生成 → 通过。

### 2.11 `K4` 并发争用作业

**现状**：`tests/` 里没有以并发为主题的用例；CI 不开 `-X dev`。

**改法**

1. 新增 `tests/test_concurrency.py`，只放"同一对象被多线程同时读写"的用例，每条都有确定断言，不靠 sleep 制造时序：
   - `PendingStore`：8 线程 × 200 次 `put/get`，断言"同一路径只留最新快照"且计数不超上限；
   - `ContextSources`：注册/收集并发，断言 `version` 单调、收集结果不撕裂；
   - `LiveState`：写者/读者并发，断言读到的永远是完整快照；
   - `ModelCatalog`（多模型落地后）：`set_source` 与 `snapshot` 并发，断言快照里的模型集合要么全旧、要么全新，不出现混合。
2. CI 单设一步 `并发争用`：`PYTHONDEVMODE=1 python -X dev -m unittest tests.test_concurrency`，超时 3 分钟。
3. 该文件不进入常规单测循环的重复执行（常规循环会跑到它，但不带 `-X dev`；两者都要绿）。

**验收**：本地连跑 20 次不 flake；故意去掉 `ModelCatalog` 的锁，用例必须失败（这是它的负向证明）。

### 2.12 `0.5` 适用性声明

**改法**

1. 新增 `docs/applicability.md`，逐条列标准 ID：`适用` / `不适用` + 理由 + 风险承担者 + 证据路径。不适用项必须有≥20 字理由和可点击证据。
2. `scripts/check_applicability.py`：
   - 校验表结构（四列齐全）、ID 不重复；
   - 编号集合在 `scripts/standards_rules.py`（手册 v1.1 的 95 条可申报准则），CI 不依赖外部路径；
   - 表里出现集合外的编号 → 失败；集合内的编号未申报 → 继续适用；
   - 输出打印准则版本与"申报 N 条 / 标准 M 条（N/A x%）"。
3. 负向用例：拿真实编号集合比对一条不存在的编号 → 退出 1；申报表原因过短 → 退出 1；申报表缺失 → 退出 1。

### 2.13 `Y1` CI 单一事实源

**证据**：`check_ci_workflow.py:24-31` 的 `_ALLOWED_EXTRA` 直接把 `coverage` 放进放行名单；校验逻辑只检查"清单里的步骤在 yml 里出现"和"yml 里的 `scripts/check_*.py` 不超清单"，**不检查 yml 多出来的执行步骤**。于是覆盖率步在 yml 里存在、在 `ci_steps` 里缺失，两边都"通过"。

**改法**

1. 新增 `scripts/gen_ci_workflow.py`：由 `ci_steps.catalog()` 渲染完整 yml（固定头 + 矩阵 + 每步的 `name/if/timeout/run`），`--check` 与磁盘比对。
2. `CiStep` 增加 `kind`（`gate` / `unit` / `acceptance` / `post`）、`timeout`、`condition`、`shell` 字段；验收步的 skip 包装由渲染器生成，不再手写 10 段重复 yml。
3. 删除 `_ALLOWED_EXTRA` 与所有"按脚本名猜"的逻辑；`check_ci_workflow.py` 改为"重渲染并逐字节比对"，差异用 `difflib` 打印。
4. 迁移顺序：先让生成器产出与现 yml 等价的内容（人工 diff 确认），再替换；替换后 `coverage` 自然回到清单里。

**验收**：手改 yml 任意一行 → 门禁失败并给出 diff；`python scripts/ci.py` 与 CI 执行的步骤集合完全一致（脚本打印步骤清单）。

## 3. SHOULD 缺陷

### 3.1 `B3` `ports.py` 的 `Any`

`agent/core/ports.py` 21 处 `Any`，集中在 `ProviderPort` / `ToolRegistry` 的入参。改法：

1. 为 `provider`、`request`、`registry` 定义 `Protocol`（只含端口实际调用的方法），放在 `ports.py` 内。
2. 确实无法命名的"用户自定义载荷"保留 `object`，并在旁注明为什么不是 `Any`。
3. `dict[str, Any]` 这类 JSON 形状保留 `Any`（`json` 的真实类型就是任意），不计入本次范围。

**验证**：`rg -c "\bAny\b" agent/core/ports.py` 从 21 降到个位数；`mypy` 不在 CI 里，不引入新工具。

### 3.2 `R2` 注释残句

`agent/shell/web_assets/classic/js/agent-ui.js:742-744`：

```js
/* 通用面板容器：标签与面板都按 `data-pane` 驱动，新增面板不必改这里。
   面板要能被插件注入，所以标签与面板都按 `data-pane` 数据驱动，加面板不必改这里。
   就必须是**按数据**遍历而不是按名字写死。
```

第三行是没有主语的残句，第二行与第一行重复。改为两句，说清"为什么必须按数据遍历"即可。

**验证**：`python scripts/check_comment_style.py` 通过；人工读一遍。

## 4. 目标结构决定

### 4.1 分层（P2 完成后）

```
agent/entry/      进程入口与装配（可依赖 app、shell）
agent/app.py      装配根（可依赖 capabilities、mechanisms、core、shell）
agent/shell/      HTTP / SSE / 适配器（可依赖 capabilities、mechanisms、core）
agent/capabilities/ 工具与插件宿主（可依赖 mechanisms、core）
agent/mechanisms/ 机制（可依赖 core）
agent/core/       内核（不依赖上层）
plugins/          仅在包外向下依赖 agent
```

允许边只有"向下"；`entry` 是最上层。`app.py` 不在 `LAYERS` 里，但由 SCC 检查单独约束：`app` 可以导入任何层，任何层不得导入 `agent.app` 或 `agent.entry`。

### 4.2 预算与登记表单一事实源

`scripts/quality_budgets.py` 一处存放：覆盖率下限、静默异常预算、验收 skip 预算、复杂度登记。所有门禁与生成文档都从这里取数，禁止在各脚本里再写常量。

### 4.3 门禁的"可测试形状"

每个 `scripts/check_*.py` 必须导出纯函数 `check(...)`，`main()` 只做 I/O。这不是风格要求，是 `X2` 的前提：不能为了写负向用例去起子进程、改真实仓库文件。

## 5. 分阶段实施

> 下表保留最初的工作分解，便于核对每项落在哪个文件；**实际交付一次完成**，
> 没有延后到后续阶段的遗留，最终验收见 §0.4。

### P0 登记表与门禁骨架（0.5 人日）

| 动作 | 文件 |
|---|---|
| 预算单一事实源 | `scripts/quality_budgets.py`（新增） |
| 复杂度登记与生成 | `scripts/check_complexity.py`、`scripts/gen_complexity_md.py`、`docs/complexity.md` |
| 适用性表 | `docs/applicability.md`、`scripts/standards_rules.py`、`scripts/check_applicability.py` |
| 门禁清单文档 | `docs/quality-gates.md` |
| 接入 CI | `ci_steps.py` + 生成式 `ci.yml`（逐字节校验） |

**退出条件**：新门禁全绿；`rg -c "Any"`、行数等数字与这里一致。

### P1 小范围硬伤（0.5 人日）

`assert` 4 处、`PluginSegments` 不可变、`quality` 包 2 行导入、`agent-ui.js` 注释。

**退出条件**：`python -O -m unittest tests.test_core_chain tests.test_core_host tests.test_context_assembly` 通过；SCC 从 2 组降到 1 组。

### P2 拆 `shell` ↔ `app` 环（1.5–2 人日）

新增 `agent/entry/`、抽 `timefmt.py`、`TYPE_CHECKING` 收口、改启动脚本与文档、`LAYERS` 加 `entry`。

**退出条件**：SCC 0 组；`acceptance_web` 全绿；`python -m agent.entry.web` 可起。

**此阶段完成 = 两个新需求可以开工。**

### P3 门禁增强（1.5 人日）

覆盖率进清单 + 分包下限、skip 预算独立、静默异常预算、配置 schema 与漂移、生成文档 `--check`、`gen_ci_workflow` 替换手写 yml。

**退出条件**：`python scripts/ci.py` 全绿；`check_ci_workflow --check` 与磁盘零差异；`ci.py` 打印的步骤与 yml 完全一致。

### P4 负向用例 + 并发（1.5 人日）

`tests/test_gate_negative.py`（≥18 条）、`tests/test_concurrency.py`（≥4 条）、`tests/test_import_graph.py`（环检测正/负）。

**退出条件**：`python scripts/ci.py` 全绿；把任一被保护的行为改坏，对应用例必红（逐条演示记录进 PR）。

### P5 收尾（0.5 人日）

`ports.py` 协议化、全仓注释抽检、`docs/architecture.md` 补 `entry` 层、README 文档索引。

**退出条件**：`docs/applicability.md` 所有 `不适用` 项有原因与风险承担者，编号与 `scripts/standards_rules.py` 双向对齐，`ci.py` 全绿。

合计约 **6–7 人日**。

## 6. 负向测试矩阵（`X2` 落地清单）

| 门禁 | 负向输入 | 期望 |
|---|---|---|
| `check_imports` | 临时包 `a -> b -> a` | 报 SCC 成员，退出 1 |
| `check_architecture_hygiene` | 临时 `agent/core/x.py` 含 `assert`；跨层私有导入 | 各报一条，带 `文件:行` |
| `check_python_floor` | 含 `match` 语句的文件 + floor 3.9 | 报语法特性与文件 |
| `check_comment_style` | 含全角标点混排/残句样本 | 报规则名与行号 |
| `check_ui_js` | 语法错误 JS / 缺 `;` 的共享作用域 | 报文件与错误 |
| `check_readme` | 用例数写错、文档提到不存在的 `data/` 子目录 | 报期望值与实际值 |
| `check_ci_workflow` | yml 多一步、少一步 | 打印 diff |
| `check_config_drift` | 真实配置多键 | 报节、键 |
| `check_applicability` | 缺列、未知 ID、原因过短、申报表缺失 | 各报一条 |
| `check_complexity` | 801 行文件未登记 | 报出文件与行数 |
| `gen_*_md --check` | 文档少一行 | 打印首处差异 |
| `check_silent_except` | 120 处惯用法 | 报超预算数与新增位置 |
| `check_acceptance_skips` | 2 个 skip、预算 1 | 报数量与白名单 |

所有负向用例都构造临时目录/临时文本，**不修改仓库真实文件**。

## 7. 验收命令

```bash
python -O -m unittest tests.test_core_chain tests.test_core_host
python scripts/check_imports.py --scc          # 期望：0 组
python scripts/check_architecture_hygiene.py
python scripts/check_config_drift.py
python scripts/check_complexity.py
python scripts/check_applicability.py
python scripts/gen_unit_tests_md.py --check
python scripts/gen_complexity_md.py --check
python scripts/check_ci_workflow.py
python scripts/ci.py                            # 全绿
```

`scripts/ci.py` 是唯一总入口；任何"只在 CI 跑、本地不跑"的步骤都算 `Y1` 未修完。

## 8. 与两个新需求的关系

| 新需求动作 | 前置条件 | 状态 |
|---|---|---|
| 新建 `agent/shell/classic_adapter/history_page.py`、`agent/shell/web_assets/classic/js/history-paging.js` | P2（层与入口已定） | 已满足 |
| 新建 `plugins/multi_model/*` | P2；插件目录不进 `LAYERS`，由 `check_imports` 的包外规则约束 | 已满足 |
| 新增测试文件 | P3（覆盖率口径包含新文件）后才有下限意义 | 已满足 |
| 合并 PR | P4 完成（负向用例与并发作业已就位） | 已满足 |

新需求方案里原本"项目既存缺口不在本方案修"的段落，已改为引用该方案；两份方案不再重复描述存量债。

## 9. 风险与回退

| 风险 | 触发点 | 缓解 |
|---|---|---|
| 入口迁移导致用户启动失败 | P2 改 `start.bat/sh` | 同 PR 改 README、`docs/subsystems/shell.md`；发布说明置顶 |
| 覆盖率下限把 CI 打红 | P3 第一次跑全量 | 下限由测得值向下取整生成，先提交基线再开 `--fail-under` |
| 复杂度登记表变成"合法欠债清单" | P0 建表 | 每项必须写承担者或拆分计划；新文件一律不得入表 |
| 生成式 yml 与 GitHub 语义不一致 | P3 | 先渲染与现 yml 等价内容，人工 diff 后再替换；保留 `workflow_dispatch` 手动跑一次 |
| `config_schema` 改动影响所有读取方 | P2/P3 | 先加 schema 与门禁（P0），再改 `get_*`；每步跑全量单测 |

## 10. 结论

- 13 项 MUST 中，影响架构的是 `A2`（2 组环）与 `X5`（覆盖率口径）；其余是门禁可信度与登记缺失。
- P0–P5 已全部落地：改动范围不含新功能与协议变更，界面行为不变（启动命令迁移到 `agent.entry` 除外）。
- 两个新需求的前置条件（P2 层与入口、P3 覆盖率口径、P4 负向与并发）已满足，可按 `history-paging.md` 与 `multi-model.md` 开工。
