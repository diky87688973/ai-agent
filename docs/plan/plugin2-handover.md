# 插件 2.0 重构 · 完整交接文档

状态：已完成。八条灵魂全部落地，全量 2419 例 0 红，CI 24 项门禁全绿。
本文用于交接给任何接手者，读完应能独立判断「现在是什么状态、为什么这样、边界在哪」。

- 协议正文：`docs/plan/plugin-slots-protocol.md`（1715 行，权威）
- 本文定位：状态报告 + 决策记录 + 等价覆盖表。协议正文不复述。

---

# 第 0 章 背景：为什么要重构

## 0.1 重构前的三套并行机制

改动前，插件能力有三条互不相通的通道，同一个「工具」可能同时存在于三处：

```text
通道一  代码注册
  plugins/<名>/plugin.py 暴露 register(ctx)
  加载器执行它，通过 ctx.add_tool / add_route / add_ui_item 等往宿主注册表塞条目

通道二  旧装配树
  agent/boot/slot_tree.json（733 行）声明 67 个节点
  agent/core/slot_tree.py（379 行）负责 load / materialize / assemble
  插件用 plugin-assembly.json 提供 AssemblyOverlay.nodes 覆盖

通道三  后端路径表
  agent/capabilities/backend_paths.py 的 BASE_BACKEND_SLOTS 23 条
  agent/capabilities/path_registry.py 与 slot_registry.py 各持一份绑定账
```

## 0.2 具体病症（全部实测，非推测）

```text
一 同一事实多份
  slot_tree.json 的 backend_slots 与 backend_paths.py 的 BASE_BACKEND_SLOTS
  是同一份路径清单的两个副本。改一处、另一处不变即为双写。

二 声明与实现分离
  slot_tree.json 说「app/boot/tools/echo 由 make_echo 实现」
  但 plugins/*/plugin.py 的 register(ctx) 又在运行期往注册表加条目
  → 「树里有什么」与「运行期实际有什么」可以不一致，且没人能说出哪个对

三 装配不可替换
  slot_tree 的节点只有「实现一次」的能力，没有覆盖（override）通道
  slot_registry.py 的 _subtree_override 把主插口的 implementation 摊给子树每个节点
  → 一份 factory 冒充 N 个子插口，是一对多映射，不是可替换性

四 插件侵入宿主
  插件的 UI / 路由 / 设置要写进宿主文件，或依赖宿主里的插件名分支

五 无轮次边界
  插件启停立刻生效，轮次进行中可能改变可用工具集合
```

## 0.3 重构目标（用户原话归纳）

> 找回灵魂：运行时只有一棵插口树，由静态片段与动态片段在内存合并而成，每轮取一次只读快照。

八条判据见第 1 章。

---

# 第 1 章 插件 2.0 的初衷与灵魂

## 1.1 一句话

**功能 → 路径 → 契约 → 依赖 → 归属** 的唯一映射，运行期只有一棵树。

## 1.2 两来源一结果

```text
静态片段   仓库根 plugin-slots.json —— 内置核心：kernel / host / boot / shell
           随代码发布，91 个节点
动态片段   plugins/<名>/plugin-slots.json —— 每个插件自己携带
           11 个插件，合计 146 个节点

扫描 plugins/ → 收集片段 → 校验冲突 → 内存合并成一棵（247 节点）→ 每轮取快照
```

合并是一次性内存操作，**不写盘、不生成中间文件**。磁盘上是多份片段，运行时只有一棵树。

## 1.3 八条灵魂（判据，不是口号）

### 一 唯一实体

运行期只有一棵插口树，不存在「插件」与「树」两套并行结构。

```text
判据  任意时刻取「已声明路径的集合」，有且只有一个来源
      装配、绑定、快照、查询读到的节点集合逐项相同（路径集合相等，不是数量相等）
      删除任一插件目录后，树上不再出现它的任何路径
```

### 二 两个来源，一个结果

```text
判据  两类片段的解析走同一个函数；字段、校验、报错文案逐条相同
      一个路径的声明方由 origins 回答，与它来自哪个文件无关
      合并只在启动期发生一次；运行期不再读片段文件
```

### 三 轮次快照

```text
判据  同一轮内多次取快照返回同一对象
      轮内新增节点、换实现、改 requires 一律不生效
      启停与片段改动在下一轮可见
      快照对象不可写（写操作抛 TypeError）
```

### 四 零侵入

```text
判据  新增插件目录后，不改动 plugins/ 之外的任何文件，插件能力即完整可用
      宿主代码里不出现任何具体插件名作为分支条件
      去掉该目录后，宿主启动、装配、门禁全部照常通过
```

### 五 全在包内

```text
判据  该插件的声明、实现、资源、界面文件路径全部以 plugins/<名>/ 为前缀
      包外不出现该插件的任何文件
      包外不出现只在「该插件存在时」才被使用的宿主分支
```

### 六 唯一权威

```text
判据  注册表、白名单、绑定表都能由树现算得到；删掉它们再算，结果相同
      不存在第二处保存「某路径由谁实现」的地方
      同一事实不在两个容器里各存一份（改一处而另一处不变，即为双写）
```

### 七 声明即构造

```text
判据  节点声明里写有什么，就构造什么；代码里不存在第二份清单来补充或删减
      声明为 declarative 的节点返回声明本身，不另存副本
      构造结果与声明逐节点对应
```

### 八 可替换性（用户特别强调，最初被我漏掉）

> 任何插口，只要非冻结状态，就允许被更换实现。
> 做成插口，结果不能提供更换实现，就是丢了灵魂，不能替换的插口就是假的插口。
> 替换实现不只是作用于插件，内核也一样。任何模块的主插口被替换，则所有子插口都应该跟随失效。任何主插口都能被更换实现，任何子插口也都能被独立更换实现。

拆成六个子判据：

```text
8.1   非冻结 ⇒ 可换实现。冻结是唯一例外，且冻结必须真的生效
8.1.1 冻结作用于整棵子树：自身 + 全部后代不可覆盖，判定在装配主干之前
8.2   内核与插件一视同仁，不存在「只有插件能换」
8.3   主插口被替换 ⇒ 其子树全部跟随失效（旧后代不出现在有效视图，不被构造）
8.3.1 覆盖只换实现，不产生节点；覆盖 row 不许出现后代 path
8.4   子插口可独立替换 ⇒ 父与兄弟不变，父只构造一次
8.5   替换发生在树上（覆盖合并进树求值），不是另建一套绑定表
8.6   声明为插口却不能换实现 = 不是插口（用注桩门禁机检）
```

## 1.4 三个概念，各只占一个位置（曾经被一个词指三件事搞乱）

```text
主插口        独立模块子树的根插口 = 该路径存在后代
              纯拓扑事实，可派生，零字段
              唯一实现 has_descendants(specs, path)

关键插口      失败策略：致命 ⇒ 上抛；不致命 ⇒ 留痕后丢弃这一条
              意图，不可派生。节点层无字段；旧贡献 API 已删除，
              故当前装配期失败策略统一致命

能持有子级    kind ∈ {container, module, ui-slot} 或 children ≠ none
              结构能力，可派生，零字段
              唯一实现 holds_children(spec)
```

**通用条款：可派生者不得有字段。** 两个来源声明同一事实就是第二本账。

历史教训：原字段 `master: bool` 同时被读成「主插口」「关键」「拥有子树」三种意思。
实测 `plugin-slots.json` 里 63 处 `master=true`，其中 56 处挂在叶子节点上（无后代），
纯噪音 —— 这就是一词多义的直接后果。已整体删除该字段。

---

# 第 2 章 现阶段做到了什么

## 2.1 一句话现状

八条灵魂全部落地，第 8 条验收 a~f 全过；门禁全绿；
全量 2419 例测试 0 红（failures=0 errors=0 skipped=2）。

## 2.2 模块地图（磁盘实测行数）

```text
agent/core/slot_spec.py        278  SlotSpec / SettingDecl / holds_children / has_descendants
                                    parse_spec / parent_path / sort_key / label_of
agent/core/slot_config.py      166  SlotConfig / SlotConfigError / load_config / topo_order
agent/core/slot_problems.py    148  spec / requires / order / event / ownership 五类校验
agent/core/slot_factory.py      97  resolve_factory / plugin_factory / resolver_for / plugin_env
agent/core/slot_override.py    209  SlotBinding / ResolvedBindings / frozen_paths /
                                    resolve_bindings / effective_view / 三条覆盖校验
agent/core/slot_assembly.py    287  SlotAssembly / SessionAssembly / BuildContext
agent/core/slot_fragments.py   352  load_merged：静态 + 动态 → 一棵配置
agent/core/slot_snapshot.py    193  轮次快照（三层只读冻结）
agent/capabilities/slot_binder.py   308  装配后把节点登记进既有注册表
agent/capabilities/plugin_events.py  25  publish_plugin_event（旧 plugin_context 唯一活函数）
agent/boot/bootstrap.py        163  boot_app / _build_boot_config / _assemble / _bind
agent/boot/components.py       153  make_facade / make_plugins / apply_model_policy 两次调用
agent/boot/tool_components.py  230  37 个工具工厂
agent/boot/tool_components_media.py  74  12 个媒体与网络工具工厂
```

数据流：

```text
plugin-slots.json + plugins/<名>/plugin-slots.json
  ↓ load_merged            校验冲突、补齐祖先、记 origins
SlotConfig（声明 + overrides）
  ↓ effective_view         frozen 向子树传播 / 结构字段拒 / 覆盖不得声明后代
有效视图（唯一产物，覆盖求值后即弃）
  ↓ SlotAssembly           只读有效视图构造（config.specs 退为求值输入）
  ↓ SlotBinder             登记进注册表（按有效 spec 分派 kind）
  ↓ apply_model_policy     绑定后再算一次（模型目录来源此刻才建立）
```

## 2.3 删除的旧机制（附行数）

```text
agent/core/slot_tree.py                    379 行   0 引用死代码
agent/boot/slot_tree.json                  733 行   与 backend_paths 同一事实两份
SlotSpec.master 字段                       13 → 12 字段
SPEC_FIELDS 手写副本                        → frozenset(fields(SlotSpec))，全仓字段名单份
agent/capabilities/plugin_context.py       395 行   代码注册通道
agent/capabilities/plugin_ui_context.py    228 行   同上
plugins/*/plugin.py 的 register(ctx)       11 个插件，41 处 ctx.add_*，共 2300 → 1874 行
  auto_update / web_ui 的 plugin.py 整个删除（身份仍在 plugin-meta.json）
MODEL_CONFIG_CONFIG 档                     无输入来源的死分支（详见 2.9）
tests/test_slot_tree.py                    152 行
tests/test_plugin_slots_equivalence.py     148 行
tests/test_plugin_bind.py / test_plugin_context_replace.py  整文件删除
```

## 2.4 新增机制（附行数）

```text
agent/core/slot_override.py        209  有效视图 + 三条覆盖校验
scripts/check_slot_view.py         113  门禁 e：装配路径只读有效视图（AST 扫描）
scripts/check_slot_stub.py         203  门禁 f：逐节点注桩验可替换性
scripts/check_slot_fields.py       178  门禁：节点字段闭合白名单，从字段表现算
scripts/check_retired_fields.py     82  门禁：已删字段名回潮清扫
scripts/check_network_isolation.py 125  门禁：patch urlopen，非环回请求必须为 0
agent/capabilities/plugin_events.py 25  publish_plugin_event 的新归属
```

## 2.5 第 8 条验收 a~f 逐项对账

```text
a  内核 service 主插口 replace_subtree → 后代全消失
   test_slot_replaceable::test_every_descendant_disappears_from_effective_view
   （逐个子节点断言，不是只看一个）
   test_slot_replaceable::test_descendants_are_not_constructed
   test_slot_replaceable::test_no_node_receives_the_replaced_implementation

b  子插口 replace → 父与兄弟不变，父只构造一次
   test_slot_replaceable::test_child_replacement_keeps_parent_and_siblings

c  frozen 自身与后代覆盖全拒，文案含路径 + frozen
   test_slot_replaceable::FrozenSubtreeTest（3 例）
   test_slot_replaceable::test_frozen_paths_include_descendants
   test_slot_replaceable::test_non_frozen_sibling_still_replaceable

d  内核与插件各测一遍（不是只测插件）
   KernelReplaceSubtreeTest / KernelReplaceChildTest / PluginSideReplaceTest

e  AST 门禁：装配路径出现直读 config.specs 构造要被测出来
   scripts/check_slot_view.py 退 0，扫描 259 文件，
   受管类 SlotAssembly / SessionAssembly / SlotBinder / SlotBinderMixin

f  逐非冻结节点注桩验可替换性
   scripts/check_slot_stub.py 退 0，受检 193 个节点全部可单独换掉
```

补充覆盖：

```text
test_slot_replaceable::StructuralFieldTest       结构字段（kind/scope/children/fixed）不可经覆盖修改
test_slot_replaceable::DescendantDeclarationTest 覆盖不得声明后代
test_slot_replaceable::EffectiveViewTest         有效视图不携带 overrides，禁用覆盖后有可重算性
test_slot_replaceable::RealRepoReplaceTest       真实仓库配置上，插件 tool 节点可被替换
```

## 2.6 门禁现状（CI 24 项，逐项实测 exit 0）

按 `scripts/ci.py --list` 的 24 项门禁逐个跑，全部退出码 0：

```text
依赖方向          check_imports.py                   通过，cycles() = []
架构约束          check_architecture_hygiene.py      11 项全过，同层私有导入存量 0
CI 工作流一致      check_ci_workflow.py               门禁 24 / 验收 10，逐字节一致
配置一致性        check_config_drift.py              无漂移
密钥扫描          check_secrets.py                   无命中
单测文档一致       gen_unit_tests_md.py --check       files=137 cases=2419
静态检查          ruff check                          All checks passed
Python 下限       check_python_floor.py              通过
UI JS 自检        check_ui_js.py                     通过
静默异常          check_silent_except.py             无静默 except
README 一致性      check_readme.py                    用例 2419、门禁 24、验收 10
确认文案无歧义       check_confirm_wording.py           通过
注释文案          check_comment_style.py             通过
注册表一致性        check_catalog.py                   69 工具，无漂移
插口配置一致性       check_slots.py                     91 静态 / 合并 247 / 宿主工厂 85
插口字段白名单       check_slot_fields.py               516 文件，只校验节点字段 12 项
有效视图          check_slot_view.py                 259 文件，装配路径只读有效视图
插口可替换（注桩）    check_slot_stub.py                 193 个非冻结节点全部可单独换掉
字段回潮清扫        check_retired_fields.py            556 文件，无残留
复杂度阈值         check_complexity.py               无超阈值文件/函数
复杂度文档一致       gen_complexity_md.py --check       与代码一致
适用性登记         check_applicability.py             通过
准则清单一致        check_standards_manifest.py        通过
并发争用          tests.test_concurrency             通过
```

两项专项自检（不在 24 项内，改动插口相关代码时必跑）：

```text
check_slot_fields.py --self-check   集合内放行 / 随机串被抓（含别名导入）/
                                    同名非权威类不误判 / 白名单加随机字段后门禁不改即跟随
check_network_isolation.py          全量 2419 例，非环回 urlopen 请求 0 次
```

`ci_steps.py` 共 28 条 CiStep（24 门禁 + 单元测试 + 10 验收 + 2 覆盖率收尾）。

## 2.7 计数实测

```text
静态片段                  91 节点
  container 8 / module 5 / service 31 / tool 47
插件片段                  11 个插件，合计 146 节点
  ai_cosplay 9 / auto_update 1 / base_settings 25 / knowledge 9 / multi_model 5
  rules 4 / skills 7 / theme_style 4 / visual_operator 13 / visual_operator_2 28 / web_ui 41
合并后                    247 节点
宿主工厂可解析            85
非冻结可换实现的节点      193
节点字段                  12（path kind factory requires owner order scope frozen children fixed props method）
事件名契约                26（agent/core/event_name.py）
插件                      11 个目录（均含 plugin-meta.json）
改动总量                  80 files changed, +4526 / −18850（含附录 A 的 13288 行删除）
```

## 2.8 插件身份判据的变更（重要）

```text
旧   discover() 判 <name>/plugin.py 存在
新   discover() 判 <name>/plugin-meta.json 存在（唯一身份来源）

依据 plugins.py:82 原本就写着「plugin-meta.json 是唯一来源」，
     但 discover:291 与 load_manifest:325 的判据却看 plugin.py —— 代码自相矛盾

配套 _load_one 修改
  entry 缺失 ⇒ 不 load_plugin_module、不写 _modules、照常写 _plugin_roots
  版本一律读 plugin-meta.json，不读模块属性
  实测：11 个插件 meta 均有 version（visual_operator_2 为 2.0，其余 1.0）
       ⇒ 判据改动行为零变化

效果：纯声明插件（只有片段 + meta，无 Python 入口）成为合法形态
     auto_update / web_ui 的 plugin.py 已据此删除，仍是合法插件
```

## 2.9 MODEL_CONFIG_CONFIG 档的删除（重要决策）

```text
现象  有 provider、零模型时：model_config_state = "config"，degraded = False，
      但 available_models / default_model / allowed_models 全为空

取证  全库无任何赋值点填 BootConfig.available / HostBootConfig.available
      config.ini 历史上从未有过 [model_reasoning] 节（git log -S 命中 0 次）
      adapter.py:218 那条注释描述的配置项从不存在

后果  这个档唯一可观测效果是谎报：把「没模型」伪装成「没降级」

处置  a 填 available：要凭空发明一个 config.ini 模型节格式，
        而真实现网唯一模型来源是插件 provider(target=model-catalog)，
        再造并列通道 = 第二本账（违反第六条）→ 不选
      b 删掉 config 档 → 选中
      c 只改注释：谎报仍在 → 不选

实现  删 MODEL_CONFIG_CONFIG 常量与 __all__ 导出
      apply_model_policy 三档 → 两档（catalog 权威 / 空）
      make_facade 三元改统一初值 MODEL_CONFIG_NONE
      adapter.py:218-219 描述不存在实现的注释一并删除

时序  apply_model_policy 必须在 binder 之后被再调一次：
      模型目录来源（provider target=model-catalog）由 SlotBinder 在绑定阶段建立，
      第一次调用（make_plugins 内）时 catalog 尚未权威，只能落空档。
      这不是重复，是「信息变了重算一次」。docstring 已写明这条约束。

位置  apply_model_policy 归属 agent/app_model_policy.py，不是 boot/components.py
      原因：boot/components.py 已 import agent.app（make_facade 内构造 App），
           bootstrap → components 再加边会成环
           （实测 cycles() = ['agent.app','agent.boot.bootstrap','agent.boot.components']）
```

## 2.10 旧贡献通道的收束（最后一批改动）

```text
发现  全库 PluginContext(...) 构造点 12 处，全部在 tests，生产代码 0 处
      register(ctx) 调用方全库 0 处（plugins.py:369 明写不执行）
      PluginUiContextMixin 只被 plugin_context 自己 + check_slot_fields 引用
      ⇒ 623 行死代码，且是「代码注册」与「片段声明」两条通道并存 = 第二本账

处置  publish_plugin_event（唯一活函数，被 visual_operator_2 引用）
        → 迁到 agent/capabilities/plugin_events.py
      两个模块整体删除
      check_slot_fields 收缩为只校验节点字段（去掉贡献 API 半边）

效果  插件贡献的唯一通道 = 片段声明 + SlotBinder 登记
```

## 2.11 测试基础设施修复

```text
问题  testkit.no_plugins 只 patch agent.config.DEFAULT_PLUGINS_PATH（装载清单）
      但 bootstrap.py 是 from-import default_plugins_root，插件根走 APP_HOME/plugins
      slot_fragments._fragments 只排除 plugins.ini 里 enabled=0 的，未列出默认启用
      ⇒ 清单清空、片段照样合并 ⇒ 测试拿到本机 multi_model 真实模型，甚至出网

实测  修前：test_protocol_contract 的 as-is 组出现 4 条 anthropic 真实调用警告
      修后：0 条，耗时 12.3s → 0.26s

修法  testkit.isolate_plugins(case) 同时 patch 两处：
        agent.config.DEFAULT_PLUGINS_PATH → 空清单
        agent.boot.bootstrap.default_plugins_root → 空目录
      20 个 build_app 的测试文件全部改用，断言一字未改

新增门禁  scripts/check_network_isolation.py
      patch urllib.request.urlopen 为「记录 + 抛错」桩，跑全量，
      非环回请求数必须为 0（环回放行：test_web_shell / test_plugin_http 真连本机服务）
      当前：2417 例，非环回 0 次
```

## 2.12 边界（非缺陷，但接手必须知道）

```text
一 静态资产不进树
   agent/shell/web/web_plugin.py::_plugin_asset
   从 host.plugins_dir/<插件>/rel 直读文件，不查该插件是否在树里
   ⇒ manifest 为空、插件未装载时，只要目录在，js/css/html 仍能服务出去
   进树：route / tool / ui / setting / prompt / event（运行期能力）
   不进树：插件目录下静态资产文件
   不违反第五条（资产在包内）与第六条（静态文件非运行期注册表）

二 4 个集成测试依赖仓库 plugins/ 可装载
   test_plugin_asset_delivery / test_slot_binder /
   test_visual_app_integration / test_write_path_keys_lifecycle
   它们断言的就是真实装配结果，隔离等于拆掉被测对象
   属集成测试，要求仓库处于可装载状态

三 BASE_BACKEND_SLOTS 不是第二本账（已核实）
   agent/capabilities/backend_paths.py 23 条里 8 条带 <参数> 模板
   登记的是 PathRegistry 的路径匹配协议（owner='*'），不是装配节点
   与插口树不构成同一事实两份
```

---

# 第 3 章 收口记录（本轮已完成）

## 3.1 本轮收口四件事

```text
A  3 条测试红 → 已清零
   1 test_plugin_contributions.test_data_dir_none_without_host_root
     原用已删的 PluginContext；改走 plugin_env + dataclasses.replace
     （HostBootConfig 是冻结 dataclass，直接赋值会 FrozenInstanceError）
   2 test_write_path_keys_lifecycle 整模块导入失败
     改为 ToolRegistry().register + dispose() 直连；
     断言两半：注册后 reg.get() 非空、撤销后为空
   3 test_plugins.PluginGateTest.test_gate_rollback_on_register_error
     被测机制（装载期 register 抛错回滚）随 plugin_context 一并删除 → 删用例
     等价覆盖：test_slot_loader 三条 + test_slot_binder.BinderFailureTest

B  文档漂移 → 已同步
   docs/complexity.md      gen_complexity_md.py 重新生成
   docs/unit-tests.md      gen_unit_tests_md.py（files=137 cases=2419）
   README.md / README.zh.md  用例数 2433 → 2419

C  过时内容 → 已清理
   docs/plan/plugin-slots-protocol.md 附录 A（13288 行代码索引）已移除，
   文件 15010 → 1715 行。理由：索引会漂移，且其中 6 个文件已删除；
   需要清单时从代码现算（complexity_scan / gen_unit_tests_md / check_imports）。

D  用例数 2431 → 2419（净减 12）
   删除：test_plugin_bind 3、test_plugin_context_replace 1、
        contributions 6、test_plugins 1、model_catalog 2
   新增：test_slot_binder 1、test_slot_registry 1
   改写 10 条（断言对象随 ctx 消失而迁到下一层，断言本身不动）
```

## 3.2 已删除机制的等价覆盖表（接手时不要重复怀疑）

```text
装载期 register 抛错 → 装载失败 + 逆序回滚
  机制随 plugin_context 删除
  等价覆盖：test_slot_loader::test_failure_releases_built_nodes_in_reverse
           test_slot_loader::test_session_failure_releases_partial_and_keeps_app_clean
           test_slot_loader::test_dispose_is_idempotent_and_continues_after_failure
           test_slot_binder::BinderFailureTest（单条失败不停其余）
           test_plugins::test_register_is_not_executed（register 不再被执行）
  结论：现在失败只有两种 —— 装载失败（缺 meta / 版本不符 / 模块 import 失败）
        与装配失败（构造抛错）。「装载期 register 抛错」这个概念已不存在

插件侧 pipeline 门控（pre-gate / post-observer）
  机制：PROVIDER_TARGETS 只有 context-source / prompt-section / mode-tail /
        assembly-hook / model-catalog，无 pipeline 目标
        旧通道 PluginContext.add_pre_gate 已删
        12 份片段 target 取值中无一个 gate / observer；git grep HEAD plugins/ 命中 0
  等价覆盖：内核侧 build_pipeline_gate 由 tests/test_quality_pipeline.py 覆盖
  结论：插件侧没有 pipeline 申请通道，PROVIDER_TARGETS 就是可声明面

非权威 config 档（MODEL_CONFIG_CONFIG）
  处置：删常量与分支（详见 2.9）
  等价覆盖：test_model_provider（目录权威 / 降级两档）+
           test_classic_adapter 的 health 取值

ctx 贡献 API（_contribute / ctx.add_*）
  底层直连：ContributionRegistry.add_route、ContextSources.add、
           ModelCatalog.set_source、ToolRegistry.register、plugin_env、safe_dir_name
  · ui replace → test_ui_registry::test_item_replace_and_restore
  · catalog 第二来源留痕不抛 → test_slot_binder::test_model_catalog_conflict_is_reported_and_rest_binds
  · data_dir → test_ctx_capabilities::test_data_dir_for_three_owner_kinds

critical 失败策略
  节点层本就没有 critical 字段（协议文档已写明）；
  装配期失败策略统一致命，由 test_slot_loader 三条覆盖
```

## 3.3 常态验收命令（改动后必跑）

```text
python -m unittest discover -s tests -p "test_*.py" -t tests   # 2419 / 0 / 0 / 2
python scripts/check_complexity.py
python scripts/check_architecture_hygiene.py
python scripts/check_imports.py
python scripts/check_slots.py --resolve          # 91 / 247 / 85
python scripts/check_slot_stub.py                # 193 全过
python scripts/check_slot_view.py                # 259 文件
python scripts/check_slot_fields.py              # 516 文件 / 节点 12 项
python scripts/check_slot_fields.py --self-check
python scripts/check_retired_fields.py           # 556 文件
python scripts/check_network_isolation.py        # 非环回 0
python scripts/check_ci_workflow.py
python scripts/check_readme.py
python -m ruff check agent plugins scripts tests # 只 --check，绝不 --fix
```

---

# 第 4 章 收口明细：旧贡献通道的收束

## 4.1 旧贡献通道已收，贡献唯一通道 = 片段声明

```text
删除  agent/capabilities/plugin_context.py     395 行
删除  agent/capabilities/plugin_ui_context.py  228 行
合计  623 行

迁出  publish_plugin_event → agent/capabilities/plugin_events.py
      函数体与错误上报不改，只把「register(ctx) 与插口 factory 两条路径」
      的过时 docstring 改成「插口 factory 都要推事件」
      report_error 的 tag 随归属改为 plugin_events.publish_event
      消费方：plugins/visual_operator_2/plugin.py:9

删除前取证：PluginContext( 共 13 处命中 = 类定义 1 + 实例化 12，实例化全在 tests，
          生产代码 0 处；register(ctx) 调用方全库 0 处
删除后验收：agent/ plugins/ scripts/ tests/ 搜 plugin_context 与 plugin_ui_context，命中 0
```

贡献现在只有一条通道：插件的 `plugin-slots.json` 片段声明节点，装配期由
`SlotBinder` 登记进既有注册表。「代码注册」与「片段声明」两本账并存的结构已消失。

## 4.2 插件身份判据 = plugin-meta.json，入口可选

```text
discover / load_manifest  判 <插件目录>/plugin-meta.json 是否存在（META_FILE）
plugin.py                 降为可选入口（ENTRY_FILE）；不存在时不加载模块，
                          仍照常写 _plugin_roots，静态资产照常可取
PluginInfo                字段为 name / root / entry；entry 可为 None
register(ctx)             装载器不执行（调用点为 0）
```

纯声明型插件（`auto_update`、`web_ui`）已无 `plugin.py`，仅靠片段与身份文件工作。

## 4.3 静态资产不进树：按目录直读，校验不出插件根

```text
_handler._plugin_asset(plugin, rel)
  → host.plugin_root(plugin) / rel 直读文件系统
  不经装配树、不落节点

越界校验：解析后必须仍在插件根内；
         plugin_tree_only / AI_AGENT_PLUGIN_TREE_ONLY 开启时，外部 path= 插件
         越出 plugins/ 树即报错
覆盖：tests/test_plugin_asset_delivery.py::ExternalPluginRootAssetTest
      （外部 path= 插件能送资产、默认目录下无同名目录、越界被拒）
```

## 4.4 四个测试是集成测试，依赖仓库 plugins/ 可装载

下列 4 个文件的断言对象就是真实装配结果，插件层不能隔离：

```text
tests/test_plugin_asset_delivery.py     片段节点数 ↔ 绑定器登记资产数逐类相等
tests/test_slot_binder.py               真实 route/setting 在 contributions / settings 里
tests/test_visual_app_integration.py    视觉插件被装载、按钮节点存在
tests/test_write_path_keys_lifecycle.py skills 工具存在再卸载消失
```

实测：强行清空插件层后它们分别红 3 / 3 / 1 / 1 条（隔离即拆掉被测对象）。

边界要求：

```text
- 跑之前仓库必须处于可装载状态（plugins/ 下 11 个插件目录与 plugin-meta.json 完整）
- 它们是集成测试，不是单元测试；不计入「不依赖环境」那一类
- 以后若要并发/沙箱运行，需要给它们专用片段夹具，届时另立议题
- 其余 build_app 用例一律走 tests/testkit.py::isolate_plugins（清单 + 插件根两道入口）
```

## 4.5 已删机制与等价覆盖表（明细）

```text
已删机制                                替代覆盖在哪
装载期 register 抛错 → 回滚             ① tests/test_plugins.py::test_register_is_not_executed
  （register 无调用点，概念已不存在）      （register 抛错不影响装载，状态恒为 loaded）
                                        ② tests/test_slot_binder.py::BinderFailureTest
                                        ③ tests/test_slot_loader.py 构造失败逆序释放三条

插件侧 pipeline 门控                    内核门控等价覆盖：
  （add_pre_gate / add_post_observer     tests/test_quality_pipeline.py
  无装配通道）

非权威 config 档                        tests/test_model_provider.py 的目录权威/降级两档
  （MODEL_CONFIG_STATES 只剩                + tests/test_classic_adapter.py 的 health 取值
   none / catalog 两个值）

ctx 贡献 API（_contribute / ctx.add_*）  底层直连：ContributionRegistry.add_route、
                                        ContextSources.add、ModelCatalog.set_source、
                                        ToolRegistry.register、plugin_env、safe_dir_name
                                        · ui replace → test_ui_registry
                                          .test_item_replace_and_restore
                                        · catalog 第二来源留痕不抛 → test_slot_binder
                                          .test_model_catalog_conflict_is_reported_and_rest_binds
                                        · data_dir → test_ctx_capabilities
                                          .test_data_dir_for_three_owner_kinds

critical 失败策略                       节点层本就没有 critical 字段（协议文档已写明）；
                                       装配期失败策略统一致命，由 test_slot_loader 覆盖
```

门禁变更：`check_slot_fields` 现在只校验节点字段（`SlotSpec` 白名单），
不再校验贡献 API 的参数名——贡献 API 已不存在。

---

# 第 5 章 收口记录：抢锁噪音与测试数据根隔离（已完成）

## 5.1 问题与根因

```text
现象
  data/logs/errors.log 里 agent.mechanisms.wake_scheduler.lock_busy 堆积。
  同期读数：总 4944 条中 lock_busy 3670 条（74.2%），把真错误淹掉。

根因（实测）
1  agent/boot/shell_components.py:122  finalizer 里调 wake_scheduler.start()
   ⇒ 每次 boot_app 都尝试抢 data/wake/scheduler.lock
2  tests 下多个 build_app/boot_app 调用点未传 data_root
   ⇒ 走 default_data_root() = 仓库 data/，与运行中的主进程抢同一把锁
3  抢锁失败原先按 error 记 errors.log ⇒ 噪音来源
```

## 5.2 修复一：抢锁失败不再记 error

```text
agent/mechanisms/wake_scheduler.py  start() 抢锁失败分支
  删  report_error("agent.mechanisms.wake_scheduler.lock_busy", ...)
  改  write_stderr("[info] 唤醒调度器未启动：锁由 PID N 持有（路径）；...")
  新增 _SchedulerProcessLock.holder_pid() 只读访问器（读不到返回 0）
  返回值语义不变：True = 成为 owner 并起线程；False = 没抢到

agent/boot/shell_components.py:122  finalizer
  读取 start() 返回值；抢不到时打一行 [boot] info，不抛错
  register 仍无条件（服务总要能取到对象）

仍保留为 error 的四处（真异常，未动）
  lock_reclaim 清残留锁失败 · lock_write 写 holder.json 失败
  lock_cleanup 上述清理也失败 · lock_release 删锁目录失败

SERVICE_WAKE_SCHEDULER 三个消费点在非 owner 下的行为（逐个核过）
  app.py:79 dispose        _thread 为 None 不 join、_owner False 不 release
                           ⇒ 不会误删别人持有的锁
  shell_components.py      register 无条件 + start 返回值被读取
  tasks/wake.py            注册/取消在非 owner 时 raise，list 仍可用
  没有 is_running / health 读取点 ⇒ 不存在「取到对象 = 调度在跑」的误判
```

## 5.3 修复二：测试数据根隔离

```text
tests/testkit.py::isolate_data(case) -> Path（第 70 行起）
  建临时目录 → patch agent.boot.bootstrap.default_data_root 为 <tmp>/data
  挂 addCleanup；传类时 addClassCleanup（与 isolate_plugins 同款）
  返回数据根

patch 点经三组对照实测确认（不是读源码推断）
  [不 patch]                              临时根未创建 · 子项 []          · 未成锁 owner
  [patch agent.boot.bootstrap.…]          临时根已创建 · plugin/session/wake · 成锁 owner
  [patch agent.config.…]                  临时根未创建 · 子项 []          · 未成锁 owner
  ⇒ 生效符号是 agent.boot.bootstrap.default_data_root（:16 from-import，:50 调用）
    只 patch agent.config 里的同名函数对已 from-import 的引用无效

入口层（entry/cli.py:18→:27、entry/headless.py:14→:22、entry/web.py:18→:40 与 :132、
shell/web/server.py:30→:169）各自 from-import 同上函数，但测试均不经过：
  tests 里只有 test_entry_layer 引用 agent.entry，它自设 AI_AGENT_DATA_ROOT
  并给 build_shell_app 显式传 data_root；该文件不在未隔离清单内
  ⇒ 入口层不动

另外修掉一处隐蔽泄漏（首次验收时才暴露）
  test_catalog 不直接调 build_app，而是经 gen_catalog.collect_schemas() /
  collect_display() 内部 build_app() 落仓库 data/
    修法：加 _IsolatedCatalogTest 基类，三个类继承
  test_session_tools 的 RunnerE2ETest 未继承 _MeshBase、自带 setUp
    修法：setUp 补 isolate_data
  逐文件定位（每文件独立跑、数仓库锁路径出现次数）：修前 test_catalog 17 次、
  test_session_tools 1 次；修后命中文件 0 个、行数 0

覆盖范围
  tests 下 55 个 build_app/boot_app 调用点全部处于隔离上下文：
  40 个在文件级 isolate_data / AI_AGENT_DATA_ROOT 之下，
  20 个显式传 data_root（有重叠），两者都无的 = 0
  三处不用 isolate_data 但已隔离：test_error_log（setUp 设 AI_AGENT_DATA_ROOT，
  断言绑 elog.path 到该根）、test_plugin_http / test_plugins（显式传 data_root）
```

## 5.4 验收（判据能区分「做了」与「没做」）

```text
a  data/logs/errors.log 的 lock_busy 计数：跑前 3670 → 跑后 3670，相等
   （不用「新增为 0」——非 owner 已不写 errors.log，那条没有鉴别力）
b  data/wake/scheduler.lock 的 holder pid 全程采样 18 次，集合 = [43536]
   即主进程，测试从未成为 owner
c  「[info] 唤醒调度器未启动」共 12 条，其中指向仓库 data/wake 的 = 0 条
d  CI 24 项门禁全绿 + ruff --check
e  全量：Ran 2419 / failures=0 / errors=0 / skipped=2
```

## 5.5 已知但本次不改的两项

```text
一 非 owner 时用户看到的是工具报错，而非友好的「只读模式」提示
  属于既有设计，若要改文案另立议题

二 anthropic provider 的 stop_reason 只经 stderr 直写 + 绕过 warnings 模块
  ⇒ grep stderr 与 catch_warnings 都读不到，只能给 _warn 打桩定位
  这是出网门禁改用 patch urlopen 数调用次数的原因（见第 6 章第 7 条）
```
---

# 第 6 章 本次重构的过程教训（写给接手者，避免重复）

```text
1  把「函数存在」当「机制已实现」
   resolve_bindings 曾存在且有用例，但装配主干从不调用，chains 无消费者
   ⇒ 真插口变成假插口。判据：结论必须给出调用点；只有测试调用 = 未实现

2  把「计划」写成「已执行」
   两次：批 3、批 6-C，报告里写了还没落盘的模块名与数字
   一次：看到 send 返回 run_id 为空（投递未生效）仍在正文写「裁定已下发」
   判据：写进报告前先跑一次命令或看一眼磁盘；投递类操作要看 run_id 是否非空

3  用具体词证明闭合规则
   写「primary 报错」「master 报错」等于把白名单当黑名单，承认这两个词特殊
   闭合性只能这样证：集合内放行、集合外随机串被拒、加字段白名单自动跟随

4  给扫描开豁免
   为让门禁通过而给某个词、某个文件开白名单 = 给门禁加漏洞
   要么让它不存在于字段表，要么改代码

5  先拆复杂度再修边界违规
   拆分会把跨层私有导入藏进新模块。顺序是先修边界违规，再按其结论拆

6  数字凑账
   报「合计 26 → 去重后 22」这种中间步骤，会掩盖上游重复计入
   宁可报「对不上」，不许加一步凑平

7  用字符串当出网判据
   anthropic 警告既经 stderr 直写（core.stderr.write_stderr 持原始引用）、
   又绕过 warnings 模块 ⇒ grep 与 catch_warnings 都读不到
   可靠判据是 patch urlopen 数调用次数

8  未获授权自行新建子智能体
   任务分配方式属于委托方的决定，不是执行方的技术选择
   曾因此造成两个执行者可能同时改同一批文件（本次未实际冲突：新会话零落盘）

9  改实现去迎合测试
   test_slot_binder 新用例断言 binder.failures，但实现是 report_error 留痕后 return None
   正确处置是改断言，不是改实现写 failures
```

---

# 第 7 章 红线（写代码前必读）

```text
不因当前用例方便破坏既有边界
不先加字段再补职责解释
不留旧入口的再导出与别名层
不让门面承担业务规则
不为文案改数据结构（例如给 CiStep 加 description）
不把未运行说成通过
数字必须能从命令输出直读，不许去重折算，加总逐项列清
测试允许红，但不许改断言凑绿；改断言必因设计变更且补正向对照
改实现去迎合测试 = 把设计改坏，禁止
ruff 只 --check，绝不 --fix（--fix 会绕过写盘链路）
临时脚本用完清理，不留在项目目录
```

---

# 附录 A 关键文件索引

```text
协议正文（权威）      docs/plan/plugin-slots-protocol.md   1715 行
本文                  docs/plan/plugin2-handover.md
片段（静态）          plugin-slots.json                     91 节点
片段（插件）          plugins/*/plugin-slots.json           146 节点
装配器                agent/core/slot_assembly.py
覆盖求值              agent/core/slot_override.py
片段合并              agent/core/slot_fragments.py
轮次快照              agent/core/slot_snapshot.py
绑定器                agent/capabilities/slot_binder.py
启动路径              agent/boot/bootstrap.py::boot_app
门禁                  scripts/check_slot_{slots,fields,stub,view}.py
                      scripts/check_retired_fields.py
                      scripts/check_network_isolation.py
```

# 附录 B 插件清单（11 个）

```text
插件                  片段节点   plugin.py   说明
ai_cosplay               9        156 行    角色扮演、语音播报
auto_update              1        已删除     纯声明（nav/buttons/update）
base_settings           25        111 行     设置面板 4 + 条目 10
knowledge                9        515 行     知识库
multi_model              5        310 行     模型目录（唯一模型来源）
rules                    4        194 行     rules/*.md 注入
skills                   7        127 行     skills 目录
theme_style              4         83 行     主题样式
visual_operator         13        116 行     视觉操作 v1（plugins.ini 里 enabled=0）
visual_operator_2       28        262 行     视觉操作 2.0
web_ui                  41        已删除     纯声明（18 ui-slot + 11 ui-action + 11 ui-control + 1 ui-tool-shell）
```
