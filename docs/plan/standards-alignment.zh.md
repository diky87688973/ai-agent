[English](standards-alignment.md) | **中文**

# 标准对齐

> 适用标准：`production-standards.md`（MUST / SHOULD）。
> 范围：只处理存量工程债；两个新需求见 [history-paging.md](history-paging.md)、[multi-model.md](multi-model.md)。
> 审计发现的 **13 项 MUST、2 项 SHOULD** 全部由下述设计处理；门禁与预算的当前值见 §0.4。

## 0. 结论先行

### 0.1 为什么先做对齐

| 新需求 | 依赖的性质 | 缺失时的后果 |
|---|---|---|
| 历史分页 | `A2`：依赖环为零 | 存在环时无法证明新模块不在环上；拆干净后，每一条新增依赖边才有判据 |
| 历史分页 / 多模型 | `X5`：覆盖率只统计 `agent/core` 与 `agent/mechanisms` | `agent/shell` 与 `plugins` 下的新模块落在所有下限之外，等于没测 |
| 多模型 | `K4`：没有并发争用作业 | `ModelCatalog` 的锁只能靠人眼审，原子替换没有机器证明 |
| 两者 | `Y1`：`ci.yml` 与 `ci_steps.py` 不同源（覆盖率步骤只写在 yml 里） | 本地全绿不代表 CI 全绿，反之亦然 |
| 两者 | `D3`：`docs/unit-tests.md` 没有漂移校验 | 新增测试后文档必然过期，且无人发现 |

### 0.2 缺陷与设计落点

| # | 准则 | 缺陷 | 级别 | 设计落点 |
|---|---|---|---|---|
| 1 | `C5` | `agent/` 下 4 处 `assert` 参与控制流 | MUST | `agent/core/host.py`、`agent/core/chain.py` 抛显式 `RuntimeError`；`agent/` 已无 `assert` |
| 2 | `A2` | 2 组、11 个模块的循环依赖 | MUST | `agent/entry/` 层；`check_imports.py`；`tests/test_import_graph.py` |
| 3 | `B1` | 冻结数据类 `PluginSegments` 仍暴露可变 `list` | MUST | `__post_init__` 复制为元组；`tests/test_context_assembly.py` |
| 4 | `X2` | 9 个门禁没有任何负向用例 | MUST | `tests/test_gate_negative.py`；静默异常与依赖图门禁另有专项用例 |
| 5 | `X5` / `X6` | 覆盖率不在 `ci_steps`、无分包下限、口径漏 shell 与 plugins | MUST | `scripts/run_coverage.py`、`scripts/check_coverage.py`、`COVERAGE_FLOORS` |
| 6 | `X7` | 验收 skip 上限恒等于白名单长度，永远不可触发 | MUST | `ACCEPTANCE_SKIP_BUDGET` 独立；`acceptance_skip_problems()` |
| 7 | `E2a` | 静默异常无数量、无预算、无递减约束 | MUST | `scripts/check_silent_except.py` 的结构化门禁；按设计不设预算 |
| 8 | `R1` | 超阈值文件与函数靠豁免登记表放行 | MUST | `check_complexity.py` 超过任一项即失败；没有豁免表 |
| 9 | `T4` | 配置漂移且无校验；入库的真实配置没有 schema | MUST | `agent/config_schema.py`；`scripts/check_config_drift.py` |
| 10 | `D3` | `docs/unit-tests.md` 已漂移，生成器没有 `--check` | MUST | `scripts/gen_unit_tests_md.py --check` |
| 11 | `K4` | 没有并发争用作业 | MUST | `tests/test_concurrency.py`；`-X dev` CI 步骤 |
| 12 | `0.5` | 没有 `docs/applicability.md` | MUST | `docs/applicability.md`；`scripts/check_applicability.py` |
| 13 | `Y1` | `ci.yml` 与 `ci_steps.py` 不同源；校验器放行多出的覆盖率步骤 | MUST | `scripts/gen_ci_workflow.py`；`scripts/check_ci_workflow.py` |
| 14 | `B3` | `agent/core/ports.py` 的接口用 `Any` 标注 | SHOULD | `Protocol` 端口；剩余 `Any` 只用于 JSON 载荷与不透明句柄 |
| 15 | `R2` | 面板容器注释残句且重复 | SHOULD | `agent/shell/web/web_assets/classic/js/panels/panes.js` 的两句话注释；`check_comment_style.py` |

### 0.3 顺序

```text
P0 复杂度门禁骨架 → P1 小范围硬伤（assert / 不可变 / 注释 / quality 环）
→ P2 拆 shell↔app 环（引入 entry 层）  ← 此阶段完成后新需求可开工
→ P3 门禁增强（覆盖率 / skip / 预算 / 漂移 / 生成式 yml）
→ P4 负向用例 + 并发作业 → P5 收尾（B3 / 全量验收）
```

### 0.4 当前值

| 项目 | 当前值 | 命令 |
|---|---|---|
| 流水线步骤 | 30 步：18 项门禁、单测、10 个验收脚本、分包覆盖率 | `python scripts/ci.py --list` |
| 依赖环 | 0 组 | `python scripts/check_imports.py --scc` |
| 静默异常 | 0 处（扫描 400 个文件、698 个 except） | `python scripts/check_silent_except.py` |
| 适用性申报 | 95 条准则中申报 0 条（N/A 0.0%） | `python scripts/check_applicability.py` |
| 用例数 | 1918 | `python scripts/check_readme.py` |
| 配置漂移 | 真实配置是 schema 的子集 | `python scripts/check_config_drift.py` |
| 覆盖率下限 | 10 个包 | `scripts/quality_budgets.py` |
| 生成的工作流 | 与渲染结果逐字节一致 | `python scripts/check_ci_workflow.py` |

## 1. 审计口径（可复现）

以下命令均在仓库根执行；给出的数字取自这些命令。

```bash
# 依赖环：只算运行期导入，跳过 `if TYPE_CHECKING:` 内的导入
python scripts/check_imports.py --scc

# assert
rg -n "\bassert\b" agent --glob "*.py"

# 复杂度
python scripts/check_complexity.py --list

# 静默异常
python scripts/check_silent_except.py

# 生成文档与工作流
python scripts/gen_unit_tests_md.py --check
python scripts/gen_complexity_md.py --check
python scripts/check_ci_workflow.py

# 入库的配置文件
git ls-files "*.ini" "*.example"
```

### 1.1 依赖图的解析规则

规则先定死，否则环数会随实现者口味变化。

| 写法 | 边指向 | 理由 |
|---|---|---|
| `import a.b.c` | `a.b.c` | 直接模块依赖 |
| `from a.b.c import name` | `a.b.c`；若 `a.b.c.name` 是模块，再加一条到它 | 名字可能是子模块 |
| `from a.b import sub` 且 `a/b/sub.py` 存在 | `a.b` 与 `a.b.sub` | Python 会导入子模块，包的 `__init__` 也会执行 |
| `from a.b import symbol` | `a.b`（即包 `__init__`） | 包初始化在运行期真的执行 |
| `if TYPE_CHECKING:` 体内 | **不建边** | 类型专用，运行期不加载；但必须真的只用于注解 |
| `try: import x` / `except ImportError:` | 建边 | 可选依赖也是依赖方向 |

按此规则，`classic_adapter/__init__.py → adapter.py` 与 `adapter.py → contract.py` 都是单向，不构成环。

### 1.2 测量结果

审计发现两组环：`quality` 包（`__init__`、`gate`、`pipeline_bridge`）与 shell / 装配根组（`agent.app`，经典适配层的 `__init__` / `adapter` / `inbound` / `outbound`，以及 Web 壳的 `web`、`web_api`、`web_routes`）。两组都不存在；`--scc` 现在报告 **0 组**。消除这两组环的设计见 §2.2。

## 2. MUST 缺陷

### 2.1 `C5` 禁止用 `assert` 做控制流

**规则**：`assert` 是开发期不变量，不得承担运行期控制流；`python -O` 会把断言删掉。

| 写法 | 为什么不行 |
|---|---|
| `assert result is not None`，随后保存 `result` | `-O` 下检查消失，`None` 被保存，错误推迟到属性访问才暴露 |
| 返回前 `assert self.last_result is not None` | 同上；`-O` 下 `None` 继续往下走 |
| 校验器已检查后再 `assert isinstance(outcome, Outcome)` | 重复断言；校验器会抛 `TypeError` 并带上模块名 |
| 返回前 `assert self.result is not None` | `-O` 下会返回错误类型 |

根因是把内部不变量当成输入校验，并默认解释器不开 `-O`。

**设计**：

1. `agent/core/host.py` 在迭代结束后判空，抛 `RuntimeError` 并带上会话与趟数；消费者中途放弃迭代时，`run_iter` 在 `finally` 里记下 `abandoned` 结果，迭代结束必有结论。
2. `agent/core/chain.py` 通过 `_require_outcome` 校验模块返回值，不符合即抛 `TypeError`；`drain()` 在链已结束但没有 `Outcome` 时抛 `RuntimeError`。
3. `agent/` 不含 `assert`。架构约束门禁没有单独的 `assert` 规则；该不变量由审计命令与 `-O` 下的测试运行守住。

**验证**：`rg -n "\bassert\b" agent --glob "*.py"` 零命中；`python -O -m unittest tests.test_core` 通过。

**风险**：低。`-O` 下行为从“静默继续”变为“明确抛错”，属预期修正。

### 2.2 `A2` 消除循环依赖

标准要求环可机器证明为零。函数内导入只是把边藏起来，并没有消除：若依赖图按调用期建模，强连通分量里仍然有它。修法是真实的分层修正。

#### 环一：`quality` 包

**根因**：`from 包 import 子模块` 会先执行包的 `__init__`，而 `__init__` 又导入 `gate`，于是 `gate` 自己的导入闭上环；`pipeline_bridge` 因 `__init__` 再入被卷进同一个强连通分量。

**设计**：按模块绝对路径导入子模块，不经过包命名空间：

```python
import agent.mechanisms.quality.checks as _checks
import agent.mechanisms.quality.diagnose as _diagnose
```

这样绑定子模块时不会重跑包初始化。`checks.py` / `diagnose.py` 对 `QualityGate` 的引用已在 `TYPE_CHECKING` 内，保持现状。

**验证**：`check_imports.py --scc` 不列出该组；`python -c "import agent.mechanisms.quality"` 正常；质量门控单测全绿。

#### 环二：`shell` ↔ `app`

**根因**：三条向上边闭合成环；第四条是装配根正确的向下边。

| 边 | 用途 |
|---|---|
| 壳层 web → `agent.app` | `build_shell_app()` 与 `__main__` 启动 |
| `web_api` → `agent.app` | 仅类型注解 |
| 经典适配层 inbound → 壳层 web（函数内延迟导入） | 复用 `date_group` |
| `app` → shell | 装配根，方向本身正确 |

函数内延迟导入掩盖了环，标准明令禁止。适配层为复用 `date_group` 而导入 Web API 的私有函数；这个函数本可以是零依赖的纯函数，转发本身也是重复实现。

**设计（引入 `entry` 层）**：

1. 新增顶层 `agent/entry/`，只做“装配 + 进程入口”。它允许依赖 `agent.app` 与 `agent.shell`，下层不得导入它。
   ```text
   agent/entry/web.py       # 装配 app 后调用 agent.shell.web.server.serve(app, ...)
   agent/entry/cli.py       # 装配 app 后启动交互式 CLI
   agent/entry/headless.py  # 装配 app 后启动 headless
   ```
2. `agent/shell/web/server.py` 保留 `serve(app, ...)` 与 `create_server(app, ...)`，不导入装配根。
3. `agent/shell/web/web_api.py` 把 `App` 改为 `TYPE_CHECKING` 内的字符串注解。壳层不做 `isinstance(x, App)`；运行期判断走协议，不允许为了注解保留运行期导入。
4. `date_group` 归到 `agent/shell/timefmt.py`（纯函数，零内部依赖）。经典适配层的会话模块与 Web 会话列表都从那里导入；适配层不再转发 Web API 的私有函数，也不保留私有名再导出。
5. 交互式 CLI 与 headless 接收现成 app：`agent/shell/cli/interactive.py` 提供 `build_session(argv, app=...)` 与 `main(argv, app_factory=...)`；`agent/shell/cli/headless.py` 提供 `run(app, text)` 与 `main(argv, app_factory=...)`。app 由 `agent/entry/*` 构造。
6. `LAYERS` 扩为 `("core", "mechanisms", "capabilities", "shell", "entry")`，同步 `check_imports.py` 与 `check_architecture_hygiene.py`；`entry` 只能向下。`COMPOSITION_ROOTS` 为 `{"app", "entry"}`：`app` 可以导入任意层，下层不得在运行期导入这两个根。
7. 启动命令改为 `python -m agent.entry.web`；`start.bat`、`start.sh`、README 与 `docs/subsystems/shell.md` 同一步改动。

**验证**：

- `python -m agent.entry.web --host 127.0.0.1 --port 8765` 起服务，首页与 `/api/chat/history` 正常。
- `python scripts/check_imports.py --scc`：0 组。
- `python -m agent.entry.headless` 冒烟；Web 验收脚本全绿。
- 导入 `agent.shell.web.server`、`agent.shell.cli.interactive` 与 `agent.shell.cli.headless` 不会加载 `agent.app`（用 `sys.modules` 断言）；`tests/test_import_graph.py` 双向钉住。

**风险**：中。入口路径是用户可见行为（`start.bat`）。按 `R5` 不保留旧命令兼容层：脚本、README、子系统文档在同一个变更里一起改。

### 2.3 `B1` `PluginSegments` 深不可变

**规则**：冻结数据类不得暴露可变容器。

**反例**：

```python
@dataclass(frozen=True)
class PluginSegments:
    items: List[Tuple[str, str, str]] = field(default_factory=list)
    counts: List[int] = field(default_factory=list)
```

`frozen=True` 只冻结字段绑定，`items.append(...)` 仍能改对象。这正是标准点名的“表面 tuple”。

**设计**：字段类型改为 `Tuple[Tuple[str, str, str], ...]` 与 `Tuple[int, ...]`，默认 `()`。`__post_init__` 逐项复制为元组，并校验 `(key, 段名, 正文)` 形状，形状不符抛 `ValueError`。调用方可以传 list，落成对象后总是元组；正文元素保持原样，由装配侧再展开。

**验证**：`tests/test_context_assembly.py`（`PluginSegmentsImmutableTest`）：构造后修改原 list 不影响对象；`segments.items.append(...)` 抛 `AttributeError`；`segments.counts[0] = 9` 抛 `TypeError`；只有两段的条目抛 `ValueError`。

**风险**：低。只有构造后的修改行为变化，构造参数的形状不变。

### 2.4 `X2` 门禁负向用例

只在干净的仓库上跑通的门禁，等于没测：把检查器写成永远返回 `[]` 也能过。因此每个门禁都要有一个必须失败的最小输入，以及一个合法输入。

**设计**：每个门禁模块把判定与 I/O 分开：判定落在接收路径、文本或测量数据的函数里；`main()` 只负责读写文件与设置退出码。函数名随输入形状变化，但契约一致：

| 门禁 | 可测试入口 |
|---|---|
| `check_imports.py` | `check(package_root)`；`cycles()` 支撑 `--scc` |
| `check_architecture_hygiene.py` | `check(...)`，以及每条规则一个函数（`check_cross_layer_private_imports`、`check_kernel_plugin_names` 等） |
| `check_silent_except.py` | AST 判据（`_broad`、`_only_pass_continue`、`_reports`、`_transforms`、`_broad_suppress`）与可替换扫描根目录的 `main()` |
| `check_readme.py` | `check(readme, acceptance, tests, data_dirs, steps, gates)` |
| `check_comment_style.py` | `scan_text(text, suffix, rules)` |
| `check_ci_workflow.py` | `check()` |
| `check_python_floor.py` | `_violations(tree)` |
| `check_ui_js.py` | `_undefined_called(text)`、`model_id_literals(text)` |
| `check_confirm_wording.py` | `check_texts(texts)` |
| `check_acceptance_skips.py` | `ci_steps.py` 的 `acceptance_skip_problems(names)` |
| `check_config_drift.py` | `compare_subset`、`compare_plugin_model_real`、`compare_model_example` |
| `check_applicability.py` | `check(text, known_ids)` |
| `check_complexity.py` | `check(root, docs, ...)` |
| `check_coverage.py` | `check(measured, floors)` |
| `check_catalog.py` | `check(catalog_path)` |
| `check_secrets.py` | `scan_text(text)` |
| 生成文档 | `gen_unit_tests_md.main(["--check"])`、`gen_complexity_md.build()` / `main(["--check"])` |

负向用例在 `tests/test_gate_negative.py`，另有 `tests/test_catalog.py`、`tests/test_silent_except_gate.py`、`tests/test_import_graph.py`。用例只构造临时目录或临时文本，从不修改仓库文件；断言要求结果非空，并在门禁输出定位时要求信息带定位。

**验收**：每个被覆盖的门禁至少有一个失败输入和一个通过输入。`check_secrets.py` 扫描版本库跟踪的文件，不在 §6 的负向矩阵内。

### 2.5 `X5` / `X6` 覆盖率

**规则**：覆盖率按顶层包分别设下限，口径覆盖全部交付的 Python 代码，阈值只有一处来源。

**设计**：

1. `scripts/run_coverage.py` 以 `--branch --source=agent,plugins --omit=*/web_assets/*` 跑单测，先写 `.coverage.tmp.<pid>`，再持 `.locks/coverage.lock` 用 `os.replace` 发布 `.coverage`。读侧只会看到完整的旧文件或完整的新文件。
2. `scripts/check_coverage.py` 按路径前缀把测量文件归入 10 个包，逐包对比 `scripts/quality_budgets.py` 的 `COVERAGE_FLOORS`。
3. 缺少 `.coverage`、未安装 `coverage`、校验期间数据文件被改写，都返回退出码 `2`（SKIP）。SKIP 在 CI 输出里可见，不计为通过。某个包没有任何测量数据是失败，不是跳过。
4. `check_coverage.py` 打印分包表；失败时给出包、测得值、下限与语句数。覆盖率只在 3.12 矩阵测一次，HTML 报告也从那里上传。
5. JS 与 CSS 不计入 Python 覆盖率，由 `check_ui_js.py` 负责。
6. 任何地方都不写 `fail_under`。阈值只存在于 `quality_budgets.py`；下限只许上调，下调必须在同一个变更里给出原因并补测试。

下限表：

| 包 | 下限 |
|---|---|
| `agent/core` | 85% |
| `agent/mechanisms` | 80% |
| `agent/capabilities` | 75% |
| `agent/shell` | 70% |
| `agent/entry` | 60% |
| `agent/gui` | 25% |
| `agent/update` | 60% |
| `agent/subagent` | 85% |
| `agent (top-level)` | 90% |
| `plugins` | 60% |

`agent/gui` 下限低，是因为桌面壳依赖平台绑定的内嵌浏览器，CI 只覆盖与平台无关的分支。

**验证**：先 `python scripts/run_coverage.py`，再 `python scripts/check_coverage.py`；`--print` 只打印测得值、不判下限。低于下限或某个包没有数据即失败；`.coverage` 不存在则按 SKIP 处理。`tests/test_gate_negative.py`（`CoverageGateTest`）直接喂测量字典构造负向用例。

### 2.6 `X7` 验收 skip 上限

**规则**：验收脚本的跳过上限与白名单独立；白名单扩容不得自动放宽上限。

**设计**：`scripts/quality_budgets.py` 定义 `ACCEPTANCE_SKIP_BUDGET = 1`，`ci_steps.py` 的 `MAX_ACCEPTANCE_SKIPS` 引用它。白名单为 `{"acceptance_mvp3"}`。`acceptance_skip_problems(names)` 先去重（去掉 BOM 与空白），**先**比预算、再验白名单，每个问题返回一条文案。`check_acceptance_skips.py` 从 `ACC_SKIP_FILE` 读名单；变量未设置时只打印白名单与上限并通过，避免本地残留临时文件造成假失败。

**上限取 1 的理由**：`acceptance_mvp3` 在 CI 上按设计跳过，因为真实模型验收需要显式开启。设 0 会让 CI 常红；1 是“已知且唯一”的跳过。

**验证**：负向用例覆盖：预算 1 下出现 2 个跳过即失败；白名单外的名字失败；1 个白名单名字通过；重复名字不重复计数。

### 2.7 `E2a` 静默异常

**规则**：每处失败都有明确归属并留下痕迹。吞异常不是可选设计，因此不设预算，也不设惯用法白名单。

| 形式 | 判定 |
|---|---|
| `except Exception:` 后只有 `pass`，或只有 `continue` | 失败 |
| 裸 `except:` | 失败 |
| 宽捕获（`Exception` / `BaseException` 或含二者的元组）既不上报也不转换 | 失败 |
| 宽捕获后返回或赋值常量默认值（`None`、空容器）且不上报 | 失败 |
| `suppress(Exception)` / `suppress(BaseException)` | 失败 |
| 窄捕获 + 明确返回 | 允许 |
| `suppress(具体异常)` | 允许 |
| 隔离边界上的宽捕获：上报并返回确定状态、转成 `ToolResult(...)`，或原样重抛 | 允许 |

**设计**：`scripts/check_silent_except.py` 对 `agent/`、`tests/`、`scripts/`、`plugins/` 下的 `.py` 做 AST 结构检查，跳过 `__pycache__` 与 `retired`。它不读正则表、不读预算，注释不构成豁免。上报指 `report_error(...)`（至少两个位置参数）、`write_stderr(...)` 或 `print(..., file=sys.stderr)`；转换指 `raise`，或赋值右值是 `ToolResult(...)` 调用。完整判据见 [silent-exceptions.md](../silent-exceptions.md)。

**验证**：`python scripts/check_silent_except.py` 扫描 400 个文件、698 个 except，0 违规；`tests/test_silent_except_gate.py` 覆盖 `pass`、多语句中的 `pass`、窄捕获返回、`suppress(Exception)`、缺少载荷的上报，以及替换扫描根目录后的 `main()`。

**风险**：行为风险低——被上报的失败本来就有明确结果，门禁只拒绝静默形式。维护成本在于合法的清理分支必须写明具体异常类型。

### 2.8 `R1` 复杂度阈值

**规则**：阈值是硬上限——单文件 800 行、单函数 80 行、单文件 40 个函数；没有豁免登记表。

**设计**：`scripts/quality_budgets.py` 存放 `MAX_FILE_LINES`、`MAX_FUNCTION_LINES`、`MAX_FILE_FUNCTIONS`。`scripts/check_complexity.py` 扫描 `agent/`、`scripts/`、`plugins/`（跳过 `__pycache__` 与 `retired`），任一文件或函数超阈值即失败；`docs/complexity.md` 与扫描结果不一致同样失败。`scripts/gen_complexity_md.py` 生成该文档；`--list` 打印当前超阈值项。

| 项目 | 当前值 |
|---|---|
| 扫描文件 | 303 个 |
| 扫描函数 | 2527 个 |
| 超过 800 行的文件 | 0 个 |
| 超过 80 行的函数 | 0 个 |
| 超过 40 个函数的文件 | 0 个 |

超过阈值就拆分，不登记。

**验证**：`python scripts/gen_complexity_md.py --check` 零差异；给一个 800 行文件再加一行即失败；`tests/test_gate_negative.py`（`ComplexityGateTest`）覆盖超阈值文件与生成文档漂移。

### 2.9 `T4` 配置漂移

**规则**：真实配置文件只允许使用已登记的节与键。缺键回落到默认值；多键失败。

**设计**：

1. `agent/config_schema.py` 是节与键的唯一清单：`SCHEMA` 对应 `config.ini`，`WEB_UI_SCHEMA` 对应 `web-ui-config.ini`，`MULTI_MODEL_SCHEMA` 对应多模型插件的 `[model:*]`。值是用于文档与模板对照的默认值；读取仍在 `config.py`，缺键回落到调用方默认值。
2. 两个主配置文件都入库，因此不需要另设样例：默认值就在 schema 里。只有多模型插件配置含凭据，真实文件留在本地，但必须有入库的 `plugin-config.ini.example`。
3. `scripts/check_config_drift.py` 把真实文件按子集与 schema 比对：未登记的节或键失败，键的行号由文本扫描定位。多模型插件的真实 `[model:*]` 键按子集校验；样例与 schema 双向比对，缺键与多键都失败。
4. 真实文件不存在时打印 `[SKIP]` 说明（用代码默认值，或插件未配置），并通过。这是 `E5` 要求的可见跳过。

**验证**：给 `config.ini` 或 `web-ui-config.ini` 加未登记键，失败并给出节、键与行号；未登记的节失败；样例缺少 schema 键失败；真实文件缺失则跳过并通过。`tests/test_gate_negative.py`（`ConfigDriftGateTest`、`ConfigModelExampleGateTest`）覆盖各情形。

### 2.10 `D3` 生成文档漂移

**规则**：生成文档必须与来源一致；可读的测试目录不靠手工维护。

**设计**：`scripts/gen_unit_tests_md.py` 从发现的 `unittest` 用例渲染 `docs/unit-tests.md`（`render()`），`--check` 把渲染文本与文件比对，不一致即报告并退出 1。`docs/unit-tests.md` 当前列出 1918 个用例。`scripts/gen_complexity_md.py` 提供 `build()`，对 `docs/complexity.md` 采用同一形状。两项校验各占一个门禁步骤。变更时先重新生成，再跑校验。

**验证**：删掉文档任意一行即失败；重新生成即通过。`tests/test_gate_negative.py`（`GeneratedArtifactDriftTest`、`GeneratedComplexityDocGateTest`）覆盖漂移、文件缺失与多余内容。

### 2.11 `K4` 并发争用

**规则**：共享可变状态必须用真线程并断言不变量，不能只观察“没崩”。

**设计**：`tests/test_concurrency.py` 含 11 条用例，覆盖五类对象：预览快照仓库（`PendingStore`）、上下文注入源注册表（`ContextSources`）、会话实时状态（`LiveState`）、模型目录（`ModelCatalog`）与 AI 说话运行时。每条用例让 8 个线程在同一个屏障后开跑，断言一条确定性质：上限不被击穿、同一路径只留最新快照、取用恰好一次、收集看到一致快照、原子替换不出现混合、provider 缓存按条目指纹分键。断言只针对不变量；唯一的 sleep 是有上限的轮询，用于等待异步队列排空，不用来制造时序。

CI 把该模块单列为门禁步骤，带 `-X dev`（开发模式暴露 `ResourceWarning` 与未回收线程），超时 3 分钟。常规单测步骤也会跑到它，但不带 `-X dev`；两者都要绿。

**验证**：去掉 `ModelCatalog` 的锁，争用用例必须失败，这是它的负向证明。`python -X dev -m unittest tests.test_concurrency` 通过。

### 2.12 `0.5` 适用性申报

**规则**：标准条目缺省即适用；只有申报的条目才不适用，且必须给出原因与风险承担者。

**设计**：`docs/applicability.md` 是一张四列表：准则、申报、原因、风险由谁承担。只申报不适用项，未申报的继续适用。`scripts/check_applicability.py` 校验结构与内容：

- 恰好四列；编号符合准则编号格式且不重复；
- 申报值为 `Not applicable`；
- 原因至少 20 字；
- 风险承担者非空；
- 编号必须在 `scripts/standards_rules.py` 的集合内（95 条可申报的 MUST / SHOULD 编号）；集合外的编号是过期申报，失败。

校验器打印手册版本与申报数 / 准则总数及 N/A 占比，占比上升即可被发现。当前表不申报任何条目：95 条中 0 条，N/A 0.0%。

**验证**：未知编号、原因过短、申报表缺失，各报一条并失败；合法行与英文表头的申报表都通过。用真实编号集合跑一遍是端到端用例。

### 2.13 `Y1` CI 单一事实源

**规则**：`scripts/ci_steps.py` 是唯一步骤清单，工作流由它生成，不手工修改。

**设计**：

1. `CiStep(label, kind, script_key, argv, timeout_minutes)` 描述一步；`kind` 取 `gate`、`unittest`、`acceptance`、`post`。`catalog(fast)` 安排门禁、单测、验收脚本与覆盖率后置步；`--fast` 去掉后两段。
2. `scripts/gen_ci_workflow.py` 渲染整份工作流。门禁块与验收块来自步骤记录（名称、超时、命令、跳过包装）；固定部分——检出与安装、逐文件单测循环、验收跳过文件的前置步、覆盖率步骤（只在 3.12 矩阵）、报告上传、`data/` 检查——是生成器里的模板。
3. `scripts/check_ci_workflow.py` 重新渲染并逐字节比对；不一致时打印首个差异行及实际值与期望值。代码里不存在 `_ALLOWED_EXTRA`，也没有按脚本名猜步骤的逻辑。
4. 当前清单是 30 步：18 项门禁、1 个单测步、10 个验收脚本、1 个覆盖率后置步。`python scripts/ci.py --list` 可打印。

**验证**：手改 `ci.yml` 任意一行即失败并指出行号；`python scripts/ci.py --list` 与工作流包含同一组步骤。`tests/test_gate_negative.py`（`GeneratedArtifactDriftTest`）给渲染结果追加一行并断言失败。

## 3. SHOULD 缺陷

### 3.1 `B3` `ports.py` 的类型

**规则**：模块可见能力用 `Protocol` 标注；`Any` 只留给真正是 JSON 形状或不透明的值。

**设计**：`agent/core/ports.py` 定义 `ProviderPort`（`model`、`stream`）、`RegistryPort`（`schemas`）、`PipelinePort`（`execute`）、`SessionsPort`（`resolve_sync`）、`ProgressSink` 与 `CancelCheck`。`ModelPort`、`ToolPort` 依赖这些协议。除导入行外，剩余 11 处 `Any` 都属于三类：JSON 载荷形状（`Dict[str, Any]`、消息与工具声明列表）、进程级 app / 会话句柄、事件载荷。CI 不引入新的类型检查器。

**验证**：`rg -c "\bAny\b" agent/core/ports.py` 报告 12 行：1 行导入加 11 处使用，全部落在上述类别；协议类由现有的内核用例覆盖。

### 3.2 `R2` 注释文案

**规则**：注释解释代码为什么这样写，不复述代码在做什么；残句与重复都算失败。

**设计**：面板容器的注释是两句话：标签与面板都由 `data-pane` 驱动；插件注入的面板只带这一条身份线索，因此遍历必须按数据走。这说的是“新增面板不必改这里”的原因，而不是把循环再描述一遍。

**门禁**：`scripts/check_comment_style.py` 拒绝遗留备忘、对读者下指令或指路、纠错史、版本口吻、设计辩护与注释里的 Markdown 强调。它只读注释与文档串，不读字符串字面量与代码；干净的注释通过。

**验证**：`python scripts/check_comment_style.py` 通过；`tests/test_gate_negative.py`（`CommentStyleGateTest`）覆盖 TODO 备忘、指令式注释、Markdown 强调、不应命中的字符串字面量与干净注释。

## 4. 目标结构

### 4.1 分层

```text
agent/entry/       进程入口与装配（可依赖 app、shell）
agent/app.py       装配根（可依赖 capabilities、mechanisms、core、shell）
agent/shell/       HTTP / SSE / 适配器（可依赖 capabilities、mechanisms、core）
agent/capabilities/ 工具与插件宿主（可依赖 mechanisms、core）
agent/mechanisms/  机制（可依赖 core）
agent/core/        内核（不依赖上层）
plugins/           在包外向下依赖 agent
```

只允许向下的边；`entry` 是最上层。`app.py` 不在 `LAYERS` 里，但单独受约束：它可以导入任意层；下面四层不得在运行期导入 `agent.app` 或 `agent.entry`。`if TYPE_CHECKING:` 的注解运行期不加载，不受此限。`plugins/` 不进 `LAYERS`，它对 `agent` 的向下依赖是包约定，不是依赖图规则。

### 4.2 预算单一事实源

`scripts/quality_budgets.py` 是数字的唯一存放处：覆盖率下限、验收 skip 预算、同层私有导入预算、复杂度阈值。门禁与生成文档都从这里取数；门禁脚本不得自己定义阈值。静默异常门禁按设计不设预算。

### 4.3 门禁的可测试形状

每个 `scripts/check_*.py` 把判定放在接收路径、文本或测量数据的函数里，由 `main()` 驱动 I/O。扫描真实目录的门禁把根目录或目标文件暴露为模块级参数，测试可以替换（`ROOT`、`DOCS`、`WORKFLOW`、`SCAN_DIRS`）。契约一致：返回问题列表，干净时为空。这是 `X2` 的前提：负向用例可以导入函数并传入临时目录或临时文本，不必起子进程，也不碰真实仓库。

## 5. 工作分解

各阶段按依赖排序：每个阶段替下一个阶段移除阻塞，P2 完成后新需求即可开工。所有阶段都已在当前代码里实现。

### P0 门禁骨架

| 动作 | 文件 |
|---|---|
| 预算单一事实源 | `scripts/quality_budgets.py`（新增） |
| 复杂度阈值与生成 | `scripts/check_complexity.py`、`scripts/gen_complexity_md.py`、`docs/complexity.md` |
| 适用性表 | `docs/applicability.md`、`scripts/standards_rules.py`、`scripts/check_applicability.py` |
| 门禁清单文档 | `docs/quality-gates.md` |
| 接入 CI | `scripts/ci_steps.py` 与生成的 `ci.yml`（逐字节校验） |

### P1 小范围硬伤

4 处 `assert`、`PluginSegments` 不可变、`quality` 包的 2 行导入、面板注释。

### P2 拆 `shell` ↔ `app` 环

新增 `agent/entry/`，抽出 `timefmt.py`，用 `TYPE_CHECKING` 收口，改启动脚本与文档，`LAYERS` 加入 `entry`。P2 完成后 SCC 为 0，两个新需求可以开工。

### P3 门禁增强

覆盖率进步骤清单并带分包下限、skip 预算独立、静默异常改为严格门禁、配置 schema 与漂移校验、生成文档加 `--check`、生成式工作流替换手写 yml。

### P4 负向用例与并发

`tests/test_gate_negative.py`、`tests/test_concurrency.py`、`tests/test_import_graph.py`。

### P5 收尾

`ports.py` 协议化、全仓注释抽检、`docs/architecture.md` 补 `entry` 层、README 文档索引。

## 6. 负向测试矩阵

| 门禁 | 负向输入 | 期望 |
|---|---|---|
| `check_imports` | 临时 `agent/core` 模块导入 `agent.shell` | 报出文件与两个层 |
| `check_architecture_hygiene` | 跨层私有导入；`agent/core` 出现插件名；导入 `quality_gate` 兼容模块；同层私有导入超预算 | 每个违规一行 `文件:行` |
| `check_silent_except` | `except Exception: pass`；裸 `except`；`suppress(Exception)`；上报缺少载荷 | 文件、行号与原因 |
| `check_python_floor` | 在 3.10 下限下解析 PEP 695 泛型 | 报语法特性与文件 |
| `check_comment_style` | TODO 备忘；指令式注释；注释里的 Markdown 强调 | 规则名与行号 |
| `check_ui_js` | 调用未定义的辅助函数；模型 ID 字面量 | 文件与行号 |
| `check_readme` | 步骤数、门禁数、验收数或用例数写错；`data/` 子目录不存在 | 期望值与实际值 |
| `check_ci_workflow` | 工作流多出一个字节 | 首个差异行及实际值与期望值 |
| `check_config_drift` | 真实配置多键；未登记的节；插件 `[model:*]` 多键；样例缺键 | 节、键与行号 |
| `check_applicability` | 未知编号；原因过短；申报表缺失 | 每个问题一条 |
| `check_complexity` | 801 行文件；`docs/complexity.md` 漂移 | 文件与行数，或漂移说明 |
| `gen_*_md --check` | 文档少一行 | 报告不一致并退出 1 |
| `check_coverage` | 测得值低于下限；某包无数据 | 包、测得值、下限 |
| `check_acceptance_skips` | 预算 1 下出现 2 个跳过；白名单外的名字 | 数量与白名单 |
| `check_catalog` | 注册表缺失、损坏或漂移 | 文件与原因 |

所有负向用例都构造临时目录或临时文本，不修改仓库真实文件。

## 7. 验收命令

```bash
python -O -m unittest tests.test_core
python scripts/check_imports.py --scc          # 期望：0 组
python scripts/check_architecture_hygiene.py
python scripts/check_silent_except.py
python scripts/check_config_drift.py
python scripts/check_complexity.py
python scripts/check_applicability.py
python scripts/gen_unit_tests_md.py --check
python scripts/gen_complexity_md.py --check
python scripts/check_ci_workflow.py
python scripts/run_coverage.py                 # 发布 .coverage
python scripts/check_coverage.py               # 分包下限
python scripts/ci.py                           # 全部步骤
```

`scripts/ci.py` 是唯一总入口；任何“只在 CI 跑、本地不跑”的步骤都算 `Y1` 未修完。

## 8. 与两个新需求的关系

| 新需求动作 | 前置条件 | 由什么提供 |
|---|---|---|
| 新建 `agent/shell/classic_adapter/history_page.py` 与 `agent/shell/web/web_assets/classic/js/history-paging.js` | P2：层与入口已定 | `agent/entry/`；依赖环 0 组 |
| 新建 `plugins/multi_model/*` | P2；插件目录不进 `LAYERS` | 层清单；插件的向下依赖约定 |
| 新增测试文件 | P3：覆盖率口径包含新文件 | `COVERAGE_FLOORS` 与 `agent,plugins` 统计口径 |
| 交付新需求 | P4：负向用例与并发作业已就位 | `tests/test_gate_negative.py`、`tests/test_concurrency.py` |

两份新需求方案不再重复描述存量债。

## 9. 风险与回退

| 风险 | 触发点 | 缓解 |
|---|---|---|
| 入口迁移导致用户启动失败 | `start.bat` / `start.sh` 改动 | README、`docs/subsystems/shell.md` 与发布说明同一步改；不保留旧命令兼容层 |
| 覆盖率下限把 CI 打红 | 第一次全量测量 | 下限取测得值向下取整；先落基线再启用判定 |
| 复杂度阈值被当成“合法欠债清单” | 没有豁免表 | 超阈值就拆分，不建登记表 |
| 生成式工作流与远端 CI 语义不一致 | 替换手写 yml | 先渲染等价内容并人工 diff，再替换；保留 `workflow_dispatch` |
| schema 改动影响所有读取方 | `get_*` 默认值 | 先加 schema 与门禁；每一步跑受影响单测 |

## 10. 结论

- 13 项 MUST 里影响架构的是 `A2`（依赖环）与 `X5`（覆盖率口径）；其余是门禁可信度与登记缺失。
- 所有阶段均已实现。变更范围不含新功能与协议变更；界面行为不变，只有启动命令迁到 `agent.entry`。
- 两个新需求的前置条件已满足：层与入口结构（P2）、覆盖率口径（P3）、负向与并发覆盖（P4）。
