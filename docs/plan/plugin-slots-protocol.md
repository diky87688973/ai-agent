# 插件 2.0 插口协议配置

状态：待审查。本文定义协议、路径、依赖、配置与合并规则。

## 术语

三个概念各只占一个位置，不许串。下面每条例明定义、是否可派生、承载字段、判据。

### 主插口

```text
定义    独立模块子树的根插口：该路径存在后代
可派生  是。纯拓扑事实，不需要任何字段
承载    无字段。禁止另设布尔声明同一件事
判据    有后代 ⇒ 是主插口；无后代 ⇒ 不是。没有第三种
        与 kind、owner、关键性均无关
```

补一句边界：有后代但 kind 不允许持有子级，是**两条独立断言同时成立**——
它在拓扑上是主插口，同时它违反「能持有子级」。前者成立不豁免后者。

### 关键插口

```text
定义    失败策略：该节点构造失败时是致命还是可丢弃
        致命 ⇒ 抛错上抛，让父装配一起失败
        不致命 ⇒ 留痕后丢弃这一条
可派生  否。是意图：同一 kind 在 A 模块里致命、在 B 模块里可丢，结构上看不出来
承载    节点层当前无字段（见下方说明）；贡献 API 层由 critical 参数承载
判据    构造失败时的行为可观测：上抛，或留痕后跳过
```

节点层为何暂无字段：现役装配的失败策略是统一的——任一节点构造失败即抛
`SlotAssemblyError` 并逆序释放已构造节点，不存在「按节点区分致命与否」的需求。
给 `SlotSpec` 加 `critical` 属新增能力，需单独走新增能力检查，不得顺手加。
因此这里写明：节点层**没有**字段承载「关键」，不得用任何含义含糊的布尔冒充。

### 能持有子级

```text
定义    该节点能不能挂子节点
可派生  是。结构能力，不需要任何字段
承载    无字段
判据    kind ∈ {container, module, ui-slot} 或 children ≠ none
        唯一权威函数 holds_children(spec)，定义在 agent/core/slot_spec.py
```

### 通用条款：可派生者不得有字段

凡能由路径或 kind 现算得到的，不许另给字段再声明一遍。
两个来源声明同一事实，就是 0.6 禁止的第二本账。

判据：

```text
新增字段前先回答：该值能否由路径 / kind / children 算出
能算出 ⇒ 不得加字段，加一个算一个违反
算不出（意图、外部输入）⇒ 才允许字段，且名字必须专指该意图
```

## 0. 灵魂

运行时只有一棵插口树，由两个来源在内存合并而成。

```text
静态片段   内置核心：kernel / host / boot / shell / tools
           仓库内固定，随代码发布
动态片段   plugins/<插件名>/ 各自携带
           插件自己声明暴露什么、依赖什么

扫描 plugins/ → 收集片段 → 校验冲突 → 内存合并成一棵 → 每轮取快照
```

下面八条是判据，不是原则声明。每条给出可检验的说法；不满足判据即违反。

### 0.1 唯一实体

运行期只有一棵插口树，不存在「插件」与「树」两套并行结构。

判据：

```text
任意时刻取「已声明路径的集合」，有且只有一个来源
装配、绑定、快照、查询读到的节点集合逐项相同（路径集合相等，不是数量相等）
删除任一插件目录后，树上不再出现它的任何路径
```

### 0.2 两个来源，一个结果

静态片段与动态片段是同一种数据，只在磁盘位置不同。

判据：

```text
两类片段的解析走同一个函数；字段、校验、报错文案逐条相同
一个路径的声明方由 origins 回答，与它来自哪个文件无关
每个装配代只合并一次；运行期仅在显式热插拔或重载请求时读取片段，构造候选代
当前回合继续使用原有代；文件变动本身不修改已建成的树
```

### 0.3 轮次快照

每轮取一次快照，轮内只读。

判据：

```text
同一轮内多次取快照返回同一对象
轮内新增节点、换实现、改 requires 一律不生效
启停与片段改动在下一轮可见
快照对象不可写（写操作抛 TypeError）
```

热插拔的读取租约覆盖回合和插件 HTTP 请求。存在活跃读取者时延迟发布，空闲时立即应用。
候选构造与登记失败时恢复旧身份、模块和登记，旧代继续有效。实现与回归见
[插件 2.0 热插拔](plugin2-hotplug.md)。宿主服务的启动覆盖沿用 §0.8，状态型宿主服务的在线迁移不由插件热插拔执行。

### 0.4 零侵入

加一个插件 = 加一个目录。

判据：

```text
新增插件目录后，不改动 plugins/ 之外的任何文件，插件能力即完整可用
宿主代码里不出现任何具体插件名作为分支条件
去掉该目录后，宿主启动、装配、门禁全部照常通过
```

### 0.5 全在包内

插件能力全部落在 plugins/<名>/。

判据：

```text
该插件的声明、实现、资源、界面文件路径全部以 plugins/<名>/ 为前缀
包外不出现该插件的任何文件
包外不出现只在「该插件存在时」才被使用的宿主分支
```

### 0.6 唯一权威

运行期不许有与树并行的第二本账。

判据：

```text
注册表、白名单、绑定表都能由树现算得到；删掉它们再算，结果相同
不存在第二处保存「某路径由谁实现」的地方
同一事实不在两个容器里各存一份（判据：改一处而另一处不变，即为双写）
```

白名单必须从声明派生，不得手写第二份：`SPEC_FIELDS` 由 `fields(SlotSpec)` 现算，
声明类里那个字段定义是字段名的唯一出处；能派生的值一旦写成字面量集合，
加字段时两处就会分叉（解析器拒、门禁放）。

### 0.7 声明即构造

声明是唯一事实源。

判据：

```text
节点声明里写有什么，就构造什么；代码里不存在第二份清单来补充或删减
声明为 declarative 的节点返回声明本身，不另存副本
构造结果与声明逐节点对应：每个声明路径都有值，或明确不参与本作用域
```

### 0.8 可替换性

任何非冻结插口都必须能被换实现。声明为插口却不能换实现，它就不是插口。

#### 8.1 非冻结 ⇒ 可换实现

判据：

```text
对树上任一非冻结节点注入替换实现，装配成功，且该位置取到的是替换后的实现
冻结是唯一例外，且冻结必须真的生效（见 8.1.1）
不存在「某些 kind 能换、某些 kind 不能换」的白名单
```

8.1.1 冻结作用于整棵子树：

```text
frozen 节点自身与其全部后代都不可被覆盖
对冻结子树内任一节点的覆盖一律拒绝，报错含该节点路径与 frozen 字样
判定在装配主干之前完成，不依赖调用方自觉
```

#### 8.2 内核与插件一视同仁

判据：

```text
覆盖求值不读声明方；__host__ 节点与插件节点走同一分支
覆盖一个内核 service 节点与覆盖一个插件节点，行为与报错文案同构
```

#### 8.3 主插口被替换 ⇒ 子树跟随失效

判据：

```text
主插口以 replace_subtree 覆盖后，其全部后代不再出现在有效视图里
这些路径不被构造：查询逐个报「不存在」，且没有任何节点拿到覆盖方实现
失效凭路径前缀一次算完，与 disable 的级联同一算法
```

8.3.1 覆盖不得声明后代：

```text
覆盖只换实现，不产生节点；覆盖 row 的 path 就是被覆盖路径本身
row 里出现被覆盖路径的后代 path ⇒ 拒绝，报错含「覆盖不得声明后代：<path>」
要在子树下增加节点，走片段 slots / provides（声明层），不走覆盖
```

#### 8.4 子插口可独立替换

判据：

```text
子节点以 replace 覆盖后，父节点与它的兄弟节点实现不变
父节点照常构造一次，且读到的是子的新值
替换只改实现；改 path / kind / scope / children 属结构变更，装配期拒绝并指明
该字段属于结构变更，须走下一轮快照
```

#### 8.5 替换发生在树上

判据：

```text
有效视图 = 声明 + 覆盖 现算得到；不落盘、不进全局、同输入同输出
覆盖在求值后被丢弃：除求值函数外没有任何读取点
装配、绑定、快照只读有效视图；读原始声明做构造只允许存在于有效视图构造内部
```

#### 8.6 插口判据

判据：

```text
对每个非冻结节点注入可识别桩并跑装配，任一节点装配失败即判「假插口」
该检查是门禁的一部分，不靠人工抽查
```

字段白名单门禁通过不等于本条成立：它只证明「节点字段集合闭合」，
不证明任何节点可被换实现。不得把「门禁绿了」当成第 8 条的证据。

### 0.9 反例

以下每一条都构成对第 8 条的违反：

```text
声明了插口，但装配直接读原始声明做构造，不走有效视图
  → 覆盖声明写了也不生效，8.5 与 8.6 同时被破坏

只有插件能换实现，内核节点覆盖被拒或被忽略
  → 违反 8.2；可替换性退化为插件特权

主插口被替换，子插口仍拿旧实现继续构造
  → 违反 8.3；旧实现与替换方并存，等于两套实现同时活着

覆盖声明里写后代节点，把覆盖当声明用
  → 违反 8.3.1；声明层与实现层混同，provides 与 mode 退化成两套并行机制

把同一份实现摊给子树每个节点以表达「跟随替换」
  → 违反 8.3；凭空造出一对多映射，正是 0.6 禁止的第二本账

frozen 只冻自己、不冻子树
  → 违反 8.1.1；冻结一个容器等于形同虚设，子节点照样被换

替换机制存在但无调用方，装配主干从不使用
  → 违反 8.6；插口不可换实现即为假插口
```

合并是一次性的内存操作，不写盘、不生成中间文件。磁盘上是多份片段，运行时只有一棵树。

## 1. 协议约定

插口是「功能 → 路径 → 契约 → 依赖 → 归属」的唯一映射。功能落成一条 `path`；`path` 绑定一份契约；契约由 `owner` 的实现满足；装配先后只由 `requires` 与 `order` 决定。

### 1.1 字段与收敛

目标配置只保留 9 个字段，见 2.14。下表列出三处实现当前实际持有的全部字段，以及它们在目标态的去向。

| 字段 | 现状持有处 | 目标态 |
| --- | --- | --- |
| `path` | 全部 | 保留：唯一身份 |
| `kind` | SlotSpec / PathSlot / UI 插口 | 保留：决定装配方式 |
| `factory` | slot_tree.json | 保留：实现引用 |
| `requires` | slot_tree.json | 保留：依赖边 |
| `owner` | 全部 | 保留：回滚键 |
| `order` | slot_tree metadata / Binding / UI / 设置 | 保留：同层顺序 |
| `scope` | SlotSpec / 内核模块 metadata | 保留：`app` / `session` |
| `contract` | SlotSpec | 并入 `kind`：类型已隐含返回值形状 |
| `contract_version` | SlotSpec / Binding | 删除：单一配置下无跨版本并存 |
| `children` | SlotSpec / PathSlot / UI 插口 | 并入 `kind`：子路径策略由类型决定 |
| `fixed_children` | PathSlot / UI 插口 | 并入 `kind` |
| `allowed_kinds` | PathSlot / UI 插口 | 并入 `kind` |
| `subtree` | SlotSpec | 删除：路径前缀已表达子树 |
| `default` | SlotSpec | 并入 `factory`：默认实现就是一个 factory |
| `default_owner` | SlotSpec | 并入 `owner` |
| `implementation` | Binding | 并入 `factory` |
| `dependencies` | SlotSpec | 并入 `requires` |
| `priority` | SlotSpec / Binding | 删除：同一插口多实现即冲突，按 mode 显式声明 |
| `mode` | Binding | 保留在插件侧覆盖声明里，不进主配置 |
| `enabled` | SlotSpec / 插件清单 | 保留在 `plugins.ini`，不进主配置 |
| `lifecycle` | SlotSpec | 删除：由 `scope` 与 `kind` 推出 |
| `cache` | 文档约定 | 删除：由段的位置决定 |
| `phase` | 文档约定 | 删除：由路径决定 |
| `exposed` | 文档约定 | 删除：等于 `frozen` 取反 |
| `master` | slot_tree.json | 删除：等于「该路径有后代」，纯拓扑派生，见术语表 |
| `frozen` | slot_tree.json | 保留：装配后是否可覆盖 |
| `metadata` | 全部 | 删除：附加声明应成为显式字段；粒度不够就加 kind，不用 metadata 补 |
| `version` | slot_tree.json / `plugin-meta.json` | 保留在文件根，不进节点 |

删掉 12 项，理由分三类：一类是路径与 `kind` 已经表达（`children`、`subtree`、`phase`、`cache`），一类是同一个概念有两个名字（`default`/`implementation`、`dependencies`/`requires`、`exposed`/`frozen`），一类是没有第二个来源就不需要（`contract_version`、`priority`、`metadata`）。

保留 `mode` 与 `enabled` 但移出主配置：前者是覆盖声明的一部分，写在覆盖方；后者属于启停清单，写在 `plugins.ini`。主配置只描述「有什么」，不描述「谁改它」与「开不开」。

### 1.2 `kind` 取值（16 种）

```text
container       纯容器，只组合子节点
module          内核阶段模块
service         宿主服务
provider        提供值（上下文源、提示词段、模型目录等）
tool            工具插件
route           HTTP 端点
event           事件订阅
setting         设置面板或条目
http-route      插件端点（PluginContext.add_route）
assembly-hook   上下文拼装钩子
executor        提交执行器
runtime         插件持有的运行时对象
ui-slot         UI 插口：可被控件填，持子级
ui-action       UI 动作声明
ui-control      UI 控件声明（按钮 / 面板 / 段）
ui-tool-shell   工具卡外壳声明
```

四种 `ui-*` 都无 factory。`ui-slot` 属容器类，另三种纯声明。

旧 `ui` 已取消。粒度不够就新增 kind 补齐，不得用 `metadata` 装子类，因此 `metadata.ui-kind` 已退役，出现即报错并指向对应新 kind。

### 1.3 kind 与 factory 签名

每种 `kind` 对应一种 factory 形式。`ctx` 是装配上下文，由装配器传入。

| kind | factory 签名 | 返回 | 说明 |
| --- | --- | --- | --- |
| `container` | `factory(ctx, children)` | 任意容器对象 | 不给 factory 时用默认容器：按 order 遍历子节点收集返回值 |
| `module` | `factory(ctx, children)` | 阶段对象，需有 `run(pass_ctx)` | `scope=session` 时每会话构造一次 |
| `service` | `factory(ctx, **requires)` | 服务对象 | 参数名由 `requires` 的键决定 |
| `provider` | `factory(ctx, **requires)` | 契约值 | 同上 |
| `tool` | `factory(ctx, **requires)` | 工具对象，需有 `name` 与 `execute` | 同上 |
| `route` | `factory(ctx, **requires)` | `(status, payload)` 函数 | HTTP 方法由节点 `method` 字段给出 |
| `http-route` | `factory(ctx, **requires)` | `(status, payload)` 函数 | 与 `route` 同形；身份由 `route_slot_path(method, path)` 生成 |
| `event` | `factory(ctx, **requires)` | `(event, payload) -> None` | 订阅的事件名由路径段给出 |
| `assembly-hook` | `factory(ctx, **requires)` | `(messages, conversation_id) -> Any` | 在完整上下文拼装后调用，可改写消息序列 |
| `executor` | `factory(ctx, **requires)` | `(args) -> result` 函数 | 提交执行器；由 `commit_write` 按工具名查表取用 |
| `setting` | `factory(ctx, **requires)` | `SettingDecl` | 面板与条目带 `save` / `load` 回调，函数无法写进 JSON，故必须有 factory；面板类可在 `props` 里只给标题 |
| `ui-slot` | 无 factory | 纯声明 | 插口只有形状、`children` / `fixed` 与 `props`；属容器类，持子级 |
| `ui-action` / `ui-control` / `ui-tool-shell` | 无 factory | 纯声明 | 只有 `props`；不持子级 |
| `runtime` | `factory(ctx)` | 进程内对象 | 不进序列化，只在本次装配内有效 |

三条注入规则：

```text
ctx 永远是第一个参数，由装配器传入，不从 requires 里声明
requires 的键就是 factory 的其余参数名，缺一个即装配失败
factory 抛错即节点构造失败，触发已构造节点逆序释放
```

`service` 与 `provider` 的差别只在生命周期：`service` 全局一份；`provider` 可随 `scope=session` 每会话一份，并允许被同路径的其他实现按 `mode` 替换。

### 1.4 装配算法

```text
load(config)
  ├─ 解析 slots / provides / overrides
  ├─ 校验：路径全局唯一、requires 指向存在、同容器 order 不重复
  ├─ 校验：覆盖不得声明后代、冻结子树不可覆盖、结构字段不可经覆盖修改
  └─ 校验失败 → 不进入构造，直接报配置错误

nodes = effective(config)       # 有效视图：声明 + 覆盖求值；覆盖求值后即丢弃
                                # 冻结子树内的覆盖已在上面被拒，此处不再有例外

order = topo_sort(nodes)        # 按 requires 求值，与声明顺序无关
for path in order:
    node = nodes[path]           # 只读有效视图，不回头读原始声明
    args = {k: built[v] for k, v in node.requires.items()}
    children = [built[c] for c in children_of(node) sorted by (order, path)]
    built[path] = node.factory(ctx, **args, children=children)
    ledger.push(path, dispose_of(built[path]))
```

失败与释放：

```text
任一节点构造抛错
  ├─ 停止后续节点
  ├─ ledger 逆序调用已构造节点的 dispose
  ├─ dispose 自身失败只上报，继续释放其余
  └─ 抛 SlotAssemblyError，带失败路径与原始异常
```

`frozen` 作用于整棵子树：冻结节点自身与其全部后代都拒绝覆盖，判定发生在装配主干之前；能否持有子级由 `holds_children` 判定；出现环时拓扑排序失败并报出参与环的路径。

异常分两个：配置期（解析、校验、依赖缺失、成环、mode 冲突）抛 `SlotConfigError`，此时尚未构造任何节点；装配期（factory 抛错、依赖未就绪）抛 `SlotAssemblyError`，此时已构造的节点会被逆序释放。

### 1.5 mode 行为

覆盖方在声明里写 `mode`，决定它和默认实现的关系。

| mode | 对绑定的效果 | 对子树的效果 | 回滚 |
| --- | --- | --- | --- |
| `replace` | 默认实现不再被调用，覆盖方接管 | 子树保持，父节点不变 | 恢复默认实现 |
| `extend` | 默认实现保留，覆盖方在其后追加 | 子树保持 | 移除追加部分 |
| `wrap` | 默认实现被包一层，覆盖方决定调用前后 | 子树保持 | 移除包装层 |
| `disable` | 默认实现与所有覆盖都不调用 | 整棵子树不可用 | 恢复原状 |
| `replace_subtree` | 与 `replace` 同 | 整棵子树失效：旧后代不再出现在有效视图，也不被构造 | 恢复原子树 |

同一插口出现两个 `replace`，或 `disable` 与任何其他模式并存，均为配置冲突，装配期报错。`extend` 与 `wrap` 可叠加，叠加后的调用顺序按 `order`。

容器的默认实现按 `(order, path)` 遍历子节点；`container` 与 `module` 两类都遵循这一条。容器被 `wrap` 时，由包装方决定是否调用默认遍历。

### 1.6 `scope` 与生命周期

装配分两段：`scope=app` 的节点在进程启动时构造一次；`scope=session` 的节点不进进程装配结果，而是登记成模板，由会话在创建时实例化。

```text
启动装配
  ├─ scope=app      直接构造，进 App 门面
  └─ scope=session  只校验声明与依赖，记录 (path, factory, requires) 模板

会话创建
  ├─ 新建 SessionContext
  ├─ 按 order 依次实例化该会话的 session 节点
  │    依赖从本会话的实例表取，取不到才回退到 app 级服务
  └─ 实例表挂在 SessionContext 上，不写回全局

会话结束
  ├─ 逆序释放本会话全部实例
  ├─ 释放失败只上报，其余继续
  └─ 实例表清空，全局状态不受影响
```

三条硬约束：

```text
session 节点的依赖解析顺序：本会话实例 → app 级节点 → 报错，绝不跨会话取
session 节点不得持有 app 级可变对象的引用后自行改写它
同一会话内同一路径只构造一次，重复取用返回同一实例
```

`module` 默认 `scope=session`：每个会话一套模块实例，回合之间复用，会话结束才释放。`service` 默认 `scope=app`：全局一份。`provider` 的 `scope` 必须显式写，不写按 `app` 处理。

失败传播：会话创建时任一步抛错，该会话的实例表整体释放并让创建失败，不影响其他会话与 app 级节点。

### 1.7 归属与回滚

```text
插件装载
  ├─ register(ctx) 返回 disposer 列表
  ├─ 每个 ctx.add_* 同时写插口账本与既有机制
  ├─ disposer 记入 plugin_ledger
  └─ 任一步抛错 → 已登记 disposer 逆序执行

插件卸载
  ├─ 按 owner 取回该插件的全部账本条目
  └─ 逆序调用 disposer，插口恢复默认实现或消失
```

`owner` 是回滚的唯一键。同一插口允许多个 owner 各持一份绑定，回滚只清自己的那份。`plugin_ledger.merge_disposers` 按对象身份去重，同一 disposer 只撤销一次。

### 1.8 声明式外壳

插件目录可放四份声明文件，宿主按文件名识别。

| 文件 | 内容 | 消费方 |
| --- | --- | --- |
| `plugin-meta.json` | 名称、描述、图标、版本、`settings_tab`、`config`、`auto_load` | `agent/capabilities/plugins.py` 的 `load_manifest` |
| `plugin-ui.json` | `ui-paths` 段取 `paths`；`ui` 段取 `slots`/`actions`/`items`/`tool_shells`；`settings` 段取 `panels`/`fields`/`ui_items` | `plugin_paths.py`、`plugin_ui_tree.py`、`plugin_settings_tree.py` |
| `settings-schema.json` | `kind=fields` 或 `kind=sections` 两型字段声明 | `agent/shell/plugin_editor.py` |
| `plugin-assembly.json` | `{kind: "assembly", nodes: [{path, factory, metadata, requires}]}` | `agent/boot/plugin_assembly.py` |

`plugin-assembly.json` 的 `factory` 写成插件内相对模块名时，解析结果必须落在插件目录内，越出即报错；写成 `agent.*` 前缀时按宿主模块解析。声明文件存在即自动装载该插件，`plugins.ini` 里 `enabled = 0` 仍然优先。

同一份 `plugin-ui.json` 由三个读取方各取一段，段名互不重叠；`ui-paths` 型只有 `paths`，不带 `ui` 与 `settings`。

### 1.9 只有一棵树

现状是三套并存，各自以路径字符串对齐、互不共享数据结构：

```text
SlotTree          agent/core/slot_tree.py       启动装配，67 节点 + 23 条 backend_slots
SlotRegistry      agent/capabilities/…          运行期绑定，priority 决定生效者
PathRegistry      agent/capabilities/…          路径白名单，只校验不装配
```

目标态只留一棵树。判定一条实现是否属于「第二套账本」只需一个问句：**它是否用同一批路径另存了一份状态，需要与树对齐才能工作。** 是，则必须合并进树，不做桥接。

由此推出两条具体结论：

```text
路径白名单       合并进节点：一条路径要么是树上的节点，要么不存在
                 不接受「存在但不在树上」的声明，也就不存在对齐问题
运行期绑定       合并进节点的 mode 与 frozen：替换在树上声明，不在树上另立表
```

子级策略（`children` / `fixed`）是节点自身的属性，不是一张独立的表。原先 `paths` 段那种「声明一条路径允许什么子级、但自身不是节点」的做法，正是第二套账本的雏形：它必须与树对齐才说得清哪些路径真实存在。取消它，改成节点字段。

## 2. 全工程插口树

插口分三层呈现：装配期（`agent/boot/slot_tree.json` 的 `nodes`，67 节点）、后端路径（同文件 `backend_slots`，23 条）、插件声明（11 个插件目录的 JSON 与 `register(ctx)`）。

### 2.1 装配期树：kernel 与 host

```text
app                                  root
├─ kernel                            container
│  └─ modules                        kernel_group
│     ├─ input                       order=0  scope=session
│     ├─ queued_input                order=1  scope=session
│     ├─ assemble                    order=2  scope=session
│     ├─ compress                    order=3  scope=session
│     ├─ model                       order=4  scope=session
│     └─ tool                        order=5  scope=session
├─ host                              container
│  └─ services                       22 个服务节点
│     ├─ event_bus
│     ├─ error_log                   requires event_bus
│     ├─ live_state
│     ├─ queue                       requires event_bus
│     ├─ mesh                        requires queue
│     ├─ registry
│     ├─ background_tasks
│     ├─ context_sources
│     ├─ context_hooks
│     ├─ prompt_tail
│     ├─ prompt_sections
│     ├─ contributions
│     ├─ model_catalog
│     ├─ update
│     ├─ session_factory             requires context_sources
│     ├─ compactor_factory           requires provider
│     ├─ provider                    requires model_catalog
│     ├─ contexts                    requires registry, live_state
│     ├─ pipeline                    requires registry, contexts, live_state
│     ├─ plugin_host                 requires 9 项
│     ├─ store
│     └─ subagents                   requires store, mesh, queue, event_bus
```

### 2.2 装配期树：boot 与 shell

```text
├─ boot                              container
│  ├─ files
│  ├─ facade                         requires 上表 22 个服务
│  ├─ plugins                        requires facade
│  ├─ tools                          24 个工具节点，每个 requires facade
│  │  ├─ background_task  echo  read_file  grep_files  glob_files
│  │  ├─ write_file  edit  fs  command  tasks  session  subagent
│  │  ├─ locate  text_data  system  web  ocr  image  archive  geo
│  │  ├─ review_conclusion  present
│  │  ├─ executors                   requires facade, files
│  │  └─ commit_write                requires facade, executors
│  └─ shell                          container
│     ├─ classic_adapter             requires facade
│     ├─ plugin_events               requires classic_adapter
│     ├─ runner                      requires facade
│     ├─ wake_scheduler              requires facade
│     └─ finalizer                   requires 4 项
└─ auth                             无子级  frozen=true
```

### 2.3 后端路径树（`backend_slots`，23 条）

```text
backend/tools                                   keyed
backend/tools/<tool>                            fixed: executor, post-write
backend/tools/subagents/visibility              keyed
backend/tools/pipeline/pre-gates                keyed
backend/tools/pipeline/pre-gates/<plugin>       keyed
backend/tools/pipeline/post-observers           keyed
backend/tools/pipeline/post-observers/<plugin>  keyed
backend/context/sources                         keyed
backend/context/sources/<plugin>                keyed
backend/context/assembly-hooks                  keyed
backend/context/assembly-hooks/<plugin>         keyed
backend/context/usage-segments                  keyed
backend/prompt/sections                           keyed
backend/prompt/sections/<section>                 keyed
backend/prompt/mode-tails                         keyed
backend/events/subscriptions                      keyed
backend/events/subscriptions/<event>              keyed
backend/http/routes                               keyed
backend/models/catalog                            keyed
backend/models/providers                          keyed
backend/models/routing                            keyed
backend/runtime                                   keyed
```

`backend/http/routes` 下挂插件端点，路径身份由 `route_slot_path(method, path)` 生成：`f"{method}:{path}".encode().hex()`。`backend/runtime` 下挂插件持有的运行时对象，由 `ctx.set_runtime` 登记。

### 2.4 插件声明（11 个目录）

| 插件 | `plugins.ini` | 声明文件 | 工具 | 后端路径 |
| --- | --- | --- | --- | --- |
| `base_settings` | `enabled=1` | meta / ui（settings 型）/ — | 0 | 0 |
| `web_ui` | `enabled=1` | meta / ui（ui 型） | 0 | 0 |
| `skills` | `enabled=1` | meta / ui / settings-schema | 1 | 3 |
| `rules` | `enabled=1` | meta / ui | 0 | 2 |
| `knowledge` | `enabled=1` | meta / ui / settings-schema | 0 | 5 |
| `multi_model` | `enabled=1` | meta / ui / settings-schema | 0 | 1 |
| `theme_style` | `enabled=1` | meta / ui | 0 | 1 |
| `auto_update` | `enabled=1` | meta / ui | 0 | 0 |
| `ai_cosplay` | 无 `enabled` | meta / ui / settings-schema | 1 | 6 |
| `visual_operator` | `enabled=0` | meta / ui（`paths: {}`） | 12 | 0 |
| `visual_operator_2` | `enabled=1` | meta / ui | 20 | 6 |

### 2.5 UI 树（`plugins/web_ui/plugin-ui.json`，18 插口）

```text
app/shell/web-ui                      fixed: nav, chat, input, left-panel, right-panel, runtime, settings
├─ nav                                fixed: buttons
│  └─ buttons                          keyed
├─ chat                               fixed: messages
│  └─ messages                        fixed: user_msg, ai_msg, tools
│     └─ tools                        keyed
├─ actions                            keyed
├─ input                              fixed: textarea, buttons, right-buttons
│  ├─ buttons                         keyed
│  └─ right-buttons                   keyed
├─ left-panel                        fixed: sessions, context_usage
│  ├─ sessions                        fixed: new, list
│  └─ context_usage                   keyed
├─ right-panel                        keyed
├─ runtime                           fixed: left-panel, right-panel
│  ├─ left-panel                      keyed
│  └─ right-panel                     keyed
└─ settings                          none
```

`actions` 段声明 11 个动作，注册路径由动作 ID 的点号换成下划线：`settings.open` → `app/shell/web-ui/actions/settings_open`。`tool_shells` 段声明 1 条工具壳：`chat/messages/tools/diff`（`renderer=diff`），挂在 keyed 的 `tools` 下。`items` 段声明 11 个控件，各带 `order`：

```text
right-panel/steps            order=0
right-panel/open_file        无 order
input/buttons/image_btn      order=10
input/buttons/mode_btn       order=20
input/buttons/thinking_btn   order=30
input/right-buttons/goal_btn order=10
input/right-buttons/send_btn order=20
input/right-buttons/stop_btn order=30
runtime/left-panel/inbox     order=0
runtime/right-panel/background_task  order=0
runtime/right-panel/subagent 无 order
```

插件在 `plugin-ui.json` 的 `paths` 段声明自己的挂载点，共 13 条：

| 插件 | 键 | 路径 |
| --- | --- | --- |
| `ai_cosplay` | panel | `app/shell/web-ui/runtime/left-panel/ai_cosplay` |
| `auto_update` | button | `app/shell/web-ui/nav/buttons/update` |
| `knowledge` | button / panel / segment | `.../input/buttons/kb_btn`、`.../right-panel/kb`、`.../left-panel/context_usage/kb` |
| `multi_model` | button / settings_panel | `.../input/buttons/model_switch_btn`、`app/settings/model` |
| `rules` | segment | `.../left-panel/context_usage/rules` |
| `skills` | segment / tool | `.../left-panel/context_usage/skills`、`.../chat/messages/tools/skill` |
| `theme_style` | panel / button | `app/settings/interface`、`.../nav/buttons/style` |
| `visual_operator_2` | button | `.../input/buttons/visual_btn` |

`visual_operator` 的 `paths` 是空对象，不挂任何 UI。

### 2.6 装配顺序与冻结边界

```text
读 slot_tree.json
  ├─ nodes：67 条，按 requires 求值后构造
  ├─ backend_slots：23 条，注入 SlotRegistry 作为父插口
  └─ 合并 plugins/*/plugin-assembly.json 的 nodes（存在即覆盖同路径节点）

冻结边界
  ├─ app/auth            frozen=true，覆盖请求直接拒绝
  └─ 其余节点           frozen 缺省为 false，允许替换或新增子树
```

`requires` 的值是目标节点路径，键是该节点 factory 接收的参数名。装配按依赖求值，不按 JSON 数组顺序；任一节点构造失败时，已构造节点逆序释放。

### 2.7 运行期写入点

`PluginContext` 上向插口写入的方法与落点如下。

| 方法 | 落的插口 | 使用者 |
| --- | --- | --- |
| `add_route(method, path, handler)` | `backend/http/routes/<插件>-<名>` | `ai_cosplay`、`knowledge`、`multi_model`、`theme_style`、`visual_operator_2` |
| `add_context_source(fn)` | `backend/context/sources/<插件>/<名>` | `knowledge`、`rules`、`skills` |
| `add_context_assembly_hook(fn)` | `backend/context/assembly-hooks/<插件>/<名>` | `visual_operator_2` |
| `add_prompt_section(section, fn)` | `backend/prompt/sections/<section>` | `knowledge`、`rules`、`skills`、`visual_operator_2` |
| `add_mode_tail(fn)` | `backend/prompt/mode-tails/<插件>-<名>` | `ai_cosplay` |
| `subscribe(event, fn)` | `backend/events/subscriptions/<event>/<插件>-<名>` | `ai_cosplay` |
| `add_pre_gate(fn)` | `backend/tools/pipeline/pre-gates/<插件>` | 当前无插件使用 |
| `add_post_observer(fn)` | `backend/tools/pipeline/post-observers/<插件>` | 当前无插件使用 |
| `register_tool(tool)` | `app/boot/tools/<插件>` | `ai_cosplay`、`skills`、`visual_operator`、`visual_operator_2` |
| `add_executor(name, fn)` | `backend/tools/<tool>/executor` | 当前无插件使用 |
| `set_runtime(obj)` | `backend/runtime/<插件>` | `visual_operator_2` |
| `add_model_catalog(entries)` | `backend/models/catalog` | `multi_model` |
| `add_settings_panel(id, title)` | `app/settings/<id>` | `multi_model` |
| `add_settings_item(parent, id)` | `app/settings/<parent>/<id>` | `theme_style` |
| `add_ui_slot(path, ...)` | `app/shell/web-ui/...` | `web_ui` |
| `add_ui_item(path, ...)` | `app/shell/web-ui/...` | `web_ui` 与 8 个插件 |

绑定既有的插口不走 `add_*`，走 `bind(path, impl)` 与 `bind_route(method, path, impl)`；两者要求插口已声明，否则抛 `ValueError`。

### 2.8 路由全量表

`agent/shell/web/web_routes.py` 分发 36 个 `/api` 路径与 13 个非 `/api` 路径；`agent/shell/web/auth/policy.py` 决定免鉴权集合：`PUBLIC_GET = {/login, /desktop-login, /healthz, /auth/status}`，`PUBLIC_POST = {/auth/login, /auth/desktop}`。

| 方法 | 路径 | 处理 |
| --- | --- | --- |
| GET | `/` | 首页 HTML |
| GET | `/favicon.ico` | 图标 |
| GET | `/assets/<rel>` | 静态包（`ui_bundle`） |
| GET | `/workspace/<rel>` | 工作区文件 |
| GET | `/health` | 存活 |
| GET | `/healthz` | 存活（含 auth 回退信息） |
| GET | `/login` | 登录页 |
| GET | `/desktop-login` | 桌面令牌登录页 |
| GET | `/auth/status` | 身份状态与 Cookie 续期 |
| GET | `/auth/csrf` | CSRF 令牌 |
| GET | `/api/backend/catalog` | 后端插口目录 |
| GET | `/api/ui/catalog` | UI 插口目录 |
| GET | `/api/settings`、`/api/settings/<name>` | 设置读取 |
| GET | `/api/chat/queue` | 待发队列 |
| GET | `/api/chat/attachment` | 附件内容 |
| GET | `/api/chat/history` | 会话历史 |
| GET | `/api/chat/sessions` | 会话列表 |
| GET | `/api/chat/ui-state` | 界面状态 |
| GET | `/api/events/stream` | SSE 事实流 |
| GET | `/api/usage-accumulator` | 用量累计 |
| GET | `/api/fs/list`、`/api/fs/read` | 文件浏览与读取 |
| GET | `/api/dir-browse` | 目录选择 |
| GET | `/api/media` | 媒体内容 |
| GET | `/api/plugins/loaded` | 已装载插件名 |
| GET | `/api/tool-labels` | 工具标签 |
| GET | `/api/reasoning-effort` | 推理档位 |
| GET | `/api/subagents`、`/api/subagents/history` | 子智能体状态与历史 |
| GET | `/api/background/tasks` | 后台任务列表 |
| GET | `/api/update/status`、`/api/update/logs` | 更新状态与日志 |
| GET | `/api/plugin/<插件>/<路径>` | 插件端点 |
| POST | `/auth/login` | 密码登录 |
| POST | `/auth/desktop` | 桌面令牌登录 |
| POST | `/auth/logout` | 登出 |
| POST | `/api/chat/send` | 发送消息 |
| POST | `/api/chat/stop` | 停止回合 |
| POST | `/api/chat/title` | 重命名会话 |
| POST | `/api/chat/goal` | 目标设置 |
| POST | `/api/chat/autonomous` | 自主模式开关 |
| POST | `/api/chat/command-input` | 命令输入 |
| POST | `/api/chat/user-confirm` | 确认答复 |
| POST | `/api/chat/queue/<id>` | 队列项操作 |
| POST | `/api/settings`、`/api/settings/<name>` | 设置保存 |
| POST | `/api/subagents/send` | 向子智能体发消息 |
| POST | `/api/background/tasks/create`、`/cancel` | 后台任务创建与取消 |
| POST | `/api/update/check`、`/download`、`/apply` | 更新三阶段 |
| POST | `/api/plugin/<插件>/<路径>` | 插件端点 |
| PUT | `/api/chat/ui-state` | 界面状态写入 |
| PUT | `/api/reasoning-effort` | 推理档位写入 |
| PUT | `/api/usage-accumulator` | 用量记账 |
| PUT | `/api/plugin/<插件>/<路径>` | 插件端点 |
| DELETE | `/api/chat/sessions` | 删除会话 |
| DELETE | `/api/chat/queue/<id>` | 删除队列项 |
| DELETE | `/api/plugin/<插件>/<路径>` | 插件端点 |

`/api/plugin/*` 只经 `ContributionRegistry.match` 分派，未命中返回 404 并列出全部已注册端点；`GET /api/plugin/<插件>/_asset/<相对路径>` 单独取插件静态资产，不进匹配表。

### 2.9 事件全量表

`agent/core/event_name.py` 定义 26 个事件名，全部是常量字符串，改动即破坏订阅兼容。

| 事件 | 归属 | 语义 |
| --- | --- | --- |
| `turn_started` | 宿主 | 回合开始 |
| `turn_ended` | 宿主 | 回合结束，唯一回合边界判据 |
| `input_started` | 输入模块 | 输入环节开始 |
| `input_claimed` | 输入模块 | 认领到内容 |
| `input_ended` | 输入模块 | 输入环节结束 |
| `compress_started` | 压缩模块 | 压缩环节开始 |
| `context_compacted` | 压缩模块 | 真发生压缩才发 |
| `compress_ended` | 压缩模块 | 压缩环节结束 |
| `context_segments` | 共享 | 请求装配的分段快照 |
| `llm_started` | 模型模块 | 模型调用开始 |
| `llm_done` | 模型模块 | 模型调用成功 |
| `llm_failed` | 模型模块 | 模型调用失败 |
| `llm_ended` | 模型模块 | 模型调用结束，三种结果共用出口 |
| `assistant_delta` | 模型模块 | 正文流式增量 |
| `reasoning_delta` | 模型模块 | 思维链流式增量 |
| `model_message` | 共享 | 模型消息事实 |
| `tool_started` | 工具模块 | 工具调用开始 |
| `tool_done` | 工具模块 | 工具成功，带 `data` |
| `tool_failed` | 工具模块 | 工具失败，带 `error` |
| `tool_canceled` | 工具模块 | 工具被取消 |
| `tool_suspended` | 工具模块 | 工具挂起等确认 |
| `tool_ended` | 工具模块 | 工具调用结束，只带 `status` 与 `elapsed_ms` |
| `tool_progress` | 共享 | 工具流式进度 |
| `usage` | 共享 | token 用量 |
| `error` | 共享 | 错误事实 |
| `queue_updated` | 共享 | 待发队列变化，只推 UI 不落事实 |

`TOOL_EVENTS` 是常量元组，固定六个工具生命周期事件，供适配层与测试遍历，不另写清单。`tool_ended` 不带结果：结果在同一次调用先发的 `tool_done` 或 `tool_failed` 里，派生模型消息时必须按 `call_id` 回查。

### 2.10 设置全量表

设置面板与条目由 `SettingsRegistry` 落账，插件用 `ctx.add_settings_panel` / `add_settings_item` 注册，`save` / `load` 回调由插件实现。

| 面板 | 标题 | 声明方 | 条目 |
| --- | --- | --- | --- |
| `app/settings/agent` | Agent | `base_settings` | `reasoning_effort`（select：low/high/max，默认 high）、`max_passes`（number，默认 512）、`backup_retention_days`（number，默认 7） |
| `app/settings/context` | 上下文 | `base_settings` | `full_user_rounds`（number，默认 5）、`summary_output_max_chars`（number，默认 5000）、`reasoning_replay_tokens`（number，默认 8000）、`image_turns`（number，默认 1）、`image_max`（number，默认 8） |
| `app/settings/interface` | 界面 | `base_settings` + `theme_style` | `display_tool_items`（checkbox，默认 1）、`display_tool_steps`（checkbox，默认 0）、`theme_style`（select：dsh / minimal） |
| `app/settings/plugin` | 插件设置 | `base_settings` | 由各插件的 `settings_tab` 与 `settings-schema.json` 展开 |
| `app/settings/model` | 模型设置 | `multi_model` | `sections` 型，`section_prefix` 为 `model:`，每个模型一组字段 |

共 5 个面板、11 条固定条目。`multi_model` 的模型条目按配置条数动态展开，不在此表计数。

`base_settings` 另注册 1 个 UI 控件：`app/shell/web-ui/nav/buttons/settings`（order=-1）。

### 2.11 工具全量表

工具注册进 `ToolRegistry`，装配期每个工具组占一个 `app/boot/tools/<组>` 节点。

内置 47 个，按模块归属：

| 模块 | 工具 | 插口 |
| --- | --- | --- |
| `builtin/archive_tool.py` | `archive` | `app/boot/tools/archive` |
| `builtin/background_task.py` | `background_task` | `app/boot/tools/background_task` |
| `builtin/command_tools.py` | `python_inline`、`run_command` | `app/boot/tools/command` |
| `builtin/commit_write.py` | `commit_write` | `app/boot/tools/commit_write` |
| `builtin/echo.py` | `echo` | `app/boot/tools/echo` |
| `builtin/edit_tools.py` | `apply_patch`、`read_write`、`replace_in_file` | `app/boot/tools/edit` |
| `builtin/fs_tools.py` | `delete_file`、`file_ops`、`file_undo` | `app/boot/tools/fs` |
| `builtin/geo_weather_tools.py` | `ip_geolocate`、`open_meteo_weather` | `app/boot/tools/geo` |
| `builtin/glob_files.py` | `glob_files` | `app/boot/tools/glob_files` |
| `builtin/grep_files.py` | `grep_files` | `app/boot/tools/grep_files` |
| `builtin/image_tool.py` | `read_image` | `app/boot/tools/image` |
| `builtin/locate_tools.py` | `file_search`、`find_in_file`、`regex_locate` | `app/boot/tools/locate` |
| `builtin/ocr_tool.py` | `image_ocr` | `app/boot/tools/ocr` |
| `builtin/present_tool.py` | `present` | `app/boot/tools/present` |
| `builtin/read_file.py` | `read_file` | `app/boot/tools/read_file` |
| `builtin/review_conclusion.py` | `review_conclusion` | `app/boot/tools/review_conclusion` |
| `builtin/session_tools.py` | `session_broadcast`、`session_create`、`session_list`、`session_multisend`、`session_send` | `app/boot/tools/session` |
| `builtin/subagent_tools.py` | `subagent`、`subagent_send` | `app/boot/tools/subagent` |
| `builtin/system_tools.py` | `git_workspace`、`unified_diagnose` | `app/boot/tools/system` |
| `builtin/text_data_tools.py` | `data_table`、`text_diff` | `app/boot/tools/text_data` |
| `builtin/web_tools.py` | `web_fetch`、`web_fetch_render` | `app/boot/tools/web` |
| `builtin/write_file.py` | `write_file` | `app/boot/tools/write_file` |
| `tasks/confirm.py` | `approval_confirm`、`user_confirm` | `app/boot/tools/tasks` |
| `tasks/goal.py` | `goal` | 同上 |
| `tasks/run_type.py` | `run_type` | 同上 |
| `tasks/todo.py` | `todo_list` | 同上 |
| `tasks/wake.py` | `task_schedule`、`task_sleep`、`task_wake_cancel`、`task_wake_list` | 同上 |

`commit_write` 另有装配依赖：`requires` 同时列出 `facade` 与 `executors`，执行器表由 `make_executors` 先填好，`commit_write` 再取。

### 2.12 插件工具表

插件工具 34 个，由 `ctx.register_tool` 注册，插口都是 `app/boot/tools/<插件>`。

| 插件 | 工具 | 默认启用 |
| --- | --- | --- |
| `ai_cosplay` | `ai_speek` | 是 |
| `skills` | `skills` | 是 |
| `visual_operator_2` | `vision_request_open`、`vision_start`、`vision_focus`、`vision_move`、`vision_move_point`、`vision_move_focus`、`vision_click`、`vision_click_sequence`、`vision_key`、`vision_stop` | 是 |
| `visual_operator_2` | `vision_app`、`vision_window`、`vision_eye`、`vision_type_into`、`vision_keyboard`、`vision_wait`、`vision_find`、`vision_click_text`、`vision_mouse`、`vision_open` | 是 |
| `visual_operator` | `desktop_act`、`desktop_app`、`desktop_click_region`、`desktop_click_text`、`desktop_eye`、`desktop_find`、`desktop_keyboard`、`desktop_mouse`、`desktop_open`、`desktop_type_into`、`desktop_wait`、`desktop_window` | 否 |

合计：内置 47 + 插件 34 = 81 个声明；`visual_operator` 在 `plugins.ini` 里 `enabled=0`，实际启用 69 个。

`visual_operator_2` 的 20 个工具分两批构建：`tools.py` 定义 10 个视觉链工具（`vision_request_open` 至 `vision_stop`），`desktop.py` 定义 10 个桌面辅助工具（`specs` 列表），后者统一包一层授权检查，未授权时直接返回错误而不进入底层工具。

### 2.13 片段：插件的唯一声明入口

插件对树的贡献全部写在 `plugins/<插件名>/plugin-slots.json`。扫描插件目录即自动收集，不需要改任何其他文件。

片段有两个段，分工不可混：

```text
slots      自己拥有的插口：path 必须在本插件前缀内
provides   落到别人插口里的贡献：path 是「目标插口 + 子级键」，不是自己的前缀
```

```json
{
  "version": 1,
  "root": "app",
  "slots": [
    {
      "path": "app/plugins/example/tools/example_tool",
      "kind": "tool",
      "factory": "tools:build",
      "order": 0
    },
    {
      "path": "app/plugins/example/events/turn_ended",
      "kind": "event",
      "factory": "plugin:on_turn_ended"
    }
  ],
  "provides": [
    {
      "path": "app/kernel/modules/assemble/prompt/messages/example",
      "kind": "provider",
      "factory": "plugin:context_lines",
      "order": 40
    },
    {
      "path": "app/shell/web-ui/input/buttons/example_btn",
      "kind": "ui",
      "props": {"label": "示例"}
    }
  ],
  "subagent_tools": ["example_tool"],
  "paths": []
}
```

约束：

```text
slots[].path      必须以 app/plugins/<本插件名>/ 开头，越界报错
provides[].path   必须以某个已声明插口的路径为父，末段是子级键
parent 插口要求   children 必须是 keyed 或 fixed；none 不接受贡献
fixed 父插口      末段必须在该插口的 fixed 列表里
order             同父不重复；provides 与 slots 同层混排比较
subagent_tools    可选，本插件工具对子智能体的可见清单
存在即装载        片段文件存在即视为该插件参与装配
启停              plugins.ini 里 enabled=0 优先，整个片段跳过
祖先容器          不必声明，加载器按 path 前缀补齐
```

为什么需要 `provides`：插口的意义就是被人填。宿主声明 `app/shell/web-ui/input/buttons`，插件往里放一个按钮；base_settings 声明 `app/settings/interface`，theme_style 往里放一条设置项。这些落点不在插件自己前缀内，但它们不是「越界」，而是插口契约的正常使用。把两者混成一个 `slots` 段，只会逼着要么放宽前缀规则、要么把挂载点塞进 `metadata` 变成隐式约定。

`provides` 与 `slots` 的区别只有一条：`slots` 的节点归插件所有，卸载随子树消失；`provides` 的节点归目标插口的 owner 所有，卸载时只摘掉自己那一条。

祖先补齐是加载器职责，不是插件作者职责。插件只声明自己实际贡献的叶子路径，`app/plugins`、`app/plugins/<插件名>`、`app/plugins/<插件名>/tools` 这类中间容器由加载器按需生成。

补齐节点的 owner 按层级二分，不能一律归插件：

```text
app/plugins/<本插件名>/... 及以下   → owner = 该插件名
app/plugins 本身、以及插件前缀之上   → owner = __host__
```

理由：`app/plugins` 是所有插件共用的一级容器，若归某个插件，该插件卸载时会把整棵插件子树连根拔掉，其他插件随之失效。因此共享祖先必须宿主持有，只有落在本插件前缀内的补齐节点才归该插件，卸载时随子树一起消失。

`plugin-assembly.json` 是这套机制的前身，两种配置并存会让人不知道写哪个。目标态只保留 `plugin-slots.json` 一种，`plugin-assembly.json` 删除，其能力由本节覆盖。

### 2.14 静态片段

仓库根 `plugin-slots.json`，内容只有内置核心：kernel / host / boot / shell / tools。

```json
{
  "version": 1,
  "root": "app",
  "slots": [
    {
      "path": "app/host/services/plugin_host",
      "kind": "service",
      "factory": "agent.boot.host_factories:make_plugin_host",
      "requires": {"facade": "app/boot/facade"},
      "order": 0
    }
  ],
  "paths": [
    {"path": "backend/http/routes", "children": "keyed", "fixed": []}
  ]
}
```

静态片段**不包含任何 `app/plugins/` 下的路径**。插件相关的东西一律由插件自己的片段提供，这是「能力在包内」的判据。

### 2.14.1 归属授权

有些插件拥有不在 `app/plugins/` 下的子树：`web_ui` 拥有整个 `app/shell/web-ui`，`base_settings` 拥有四个设置面板，`multi_model` 拥有 `app/settings/model`。这类子树由静态片段用 `owners` 段授权，不由插件自己声明。

```json
{
  "version": 1,
  "root": "app",
  "owners": {
    "app/shell/web-ui": "web_ui",
    "app/settings/agent": "base_settings",
    "app/settings/context": "base_settings",
    "app/settings/interface": "base_settings",
    "app/settings/plugin": "base_settings",
    "app/settings/model": "multi_model"
  },
  "slots": [],
  "paths": []
}
```

规则：

```text
默认归属        未被任何授权覆盖的路径归 __host__
前缀归属        owners 的键是前缀，命中最长的那条
互斥            两条授权不得重叠，重叠即报错并指出双方
插件片段可声明   app/plugins/<本插件名>/ 之下，或 owners 授权给本插件的前缀之下
其余            报错，指出「缺少该前缀的归属授权」
```

授权写在静态片段，不是插件自己写。理由：归属是宿主判断，插件不能自称拥有别处的一棵子树；授权集中一处，谁的边界在哪一目了然，不散在 11 个目录里。

`provides` 段不受授权约束：它填的是别人的插口，落点由目标插口决定，不需要事先授权。

片段字段（`slots` 与 `provides` 共用）：

| 字段 | 含义 |
| --- | --- |
| `path` | 插口路径，全局唯一 |
| `kind` | 插口类型，决定装配方式 |
| `factory` | 实现引用，`module:attr`；缺省表示纯容器 |
| `requires` | 声明的依赖边，键是 factory 的参数名 |
| `owner` | 归属，卸载时按它逆序回滚；插件片段由目录名填入 |
| `order` | 同层顺序；同 order 视为配置冲突 |
| `scope` | `app` 或 `session` |
| `frozen` | 装配完成后是否可覆盖（作用于整棵子树） |
| `children` / `fixed` | 仅 `paths` 段：子级策略与固定子名 |

三处不写进配置的字段，理由如下：

```text
cache      缓存策略由段的位置决定，不由字段决定
exposed    等于 frozen 取反，不需要两个字段
lifecycle  由 scope 与 kind 推出，单例或按会话
```

一条路径只允许出现在一处：`slots` 与 `paths` 重名即加载失败，不静默择一。`requires` 指向不存在的路径、两个节点同容器同 `order`、`factory` 无法解析，三种情况都在装配期报错。

### 2.15 合并规则

启动时合并，产物只有一个内存对象。

```text
1  读仓库根 plugin-slots.json            → 静态片段
2  扫 plugins/ 下每个目录
     ├─ 读 plugin-slots.json             → 动态片段
     ├─ plugins.ini 里 enabled=0         → 整个片段跳过
     └─ 目录名即 owner，写入该片段 slots 段全部节点
3  收 provides 段（必须在 2 之后、4 之前）
     ├─ 父路径必须已由 slots/paths 声明
     ├─ 父插口 children 必须是 keyed 或 fixed；none 拒接贡献
     ├─ fixed 父插口的末段必须在 fixed 列表里
     └─ owner 取父插口的 owner，不是贡献方插件名
4  校验
     ├─ 路径全局唯一：两条片段出现同一 path → 报错，指出两处来源
     ├─ 同父同 order 重复（slots 与 provides 同层混排）→ 报错
     ├─ requires 指向不存在的路径 → 报错
     ├─ frozen 节点被任何片段覆盖 → 报错
     ├─ slots 段出现非自身前缀的 path → 报错
     └─ provides 段的父插口未声明或不接受贡献 → 报错
5  合并成一个 SlotConfig，进入装配
```

为什么 `provides` 段要在静态与动态 `slots` 都收完之后才能校验：贡献的合法性取决于父插口是否存在、是否可填。先收 `slots` 再收 `provides`，才能对插口的最后一个填法给出确定结论；反过来就会把「父还没到」误判成「父不存在」。

冲突一律报错并指出两处来源，不做优先级仲裁。优先级是隐式规则，谁都不会记得谁压谁。

### 2.16 轮次快照

树在启动时合并一次，运行期不变更结构。每轮开始取快照，轮内只读。

```text
启动        合并 → 装配 → 树定型
每轮开始    取快照：节点、依赖边、已构造实例的引用
轮内        只读快照，不再查树、不再改树
插件启停    记入待生效清单，下一轮重建快照时生效
```

快照只复制结构与引用，不复制已构造对象本身。轮内不允许新增节点、不允许换实现、不允许改 `requires`。

### 2.17 新增一个插件的完整清单

四条铁律的验收样本，只做这些，不做别的：

```text
1  建目录 plugins/<插件名>/
2  写 plugin-slots.json        暴露什么、依赖什么
3  写实现（可选）               目录内模块，片段里 factory 指过来
4  plugins.ini 加一行 enabled=1
```

一个都不能碰：仓库根 `plugin-slots.json`、其他插件目录、`agent/` 下任何文件、任何测试。

### 2.18 字段表

节点：

| 字段 | 含义 |
| --- | --- |
| `path` | 插口路径，全局唯一 |
| `kind` | 插口类型，决定装配方式 |
| `factory` | 实现引用，`module:attr`；缺省表示纯容器 |
| `requires` | 声明的依赖边，键是 factory 的参数名 |
| `owner` | 归属，卸载时按它逆序回滚；插件片段由目录名填入 |
| `order` | 同层顺序；同 order 视为配置冲突 |
| `scope` | `app` 或 `session` |
| `frozen` | 装配完成后是否可覆盖（作用于整棵子树） |
| `children` / `fixed` | 子级策略：`none` / `keyed` / `fixed`；`fixed` 时给出允许的子名 |
| `props` | 声明式载荷：UI 的标签、动作、绑定、脚本、样式；仅声明类节点使用 |

`props` 是显式字段，不是 `metadata`。理由：声明类节点不构造对象，声明本身就是产物，载荷必须原样保留到渲染侧；塞进 `metadata` 等于把它当万能袋，正是 §1.1 要消灭的形态。

未知字段一律报错，不许静默丢弃：解析时出现上述之外的键，指名路径与键名后拒绝。理由：静默丢弃会让「配置写了但没生效」伪装成「配置正确」，比报错危险得多。

子级策略属于节点，不再是单独的 `paths` 段。理由见 §1.9：一张只声明路径、自身不是节点的表，必然要与树对齐，那正是要消灭的第二套账本。

判定一条插口能否接受贡献只看它自己的 `children`：

```text
none      不接受，provides 或被当作父级即报错
keyed     接受任意子名，每个子名一条节点
fixed     只接受 fixed 列表里的子名，其余报错
```

`children` / `fixed` 任何 kind 都能写。实际会写该字段的只有两类：装配类（`container` / `module` / `ui-slot`）与需要持子项的声明类（如 `setting` 面板）。其余 kind 写了 `children≠none` 就会被当作可填插口。

「可持子级」判定必须**只有一处实现**，供两处调用：

```text
父插口判定      provides 的父能否接受贡献
祖先判定        path 前缀缺失的中间节点能否由加载器补齐成父
```

两处若各写一份，就会出现「补出了容器祖先，provides 却认它不可填」这类自相矛盾。判据本身是：`kind` 属装配类，或 `children != none`。

`master` 已删除。它曾有两种读法（拥有子树 / 关键），现分别由 `holds_children` 与贡献 API 的 `critical` 承担，术语见开头的术语表。

`metadata.ui-kind` 已退役：出现即报错并指出路径与应改成的 kind。

三处不写进配置的字段：

```text
cache      缓存策略由段的位置决定，不由字段决定
exposed    等于 frozen 取反，不需要两个字段
lifecycle  由 scope 与 kind 推出，单例或按会话
```

### 2.19 加载时机

| 片段 | 何时读 | 频率 |
| --- | --- | --- |
| 静态片段 | 进程启动 | 一次 |
| 插件片段 | 进程启动，扫 `plugins/` | 一次 |
| 合并结果 | 启动后定型，运行期只读 | 每轮取快照 |

运行期不再重读片段文件。`slots` 与 `paths` 重名、`requires` 悬空、同容器同 `order`、`factory` 无法解析、插件片段越界，五种情况都在合并或装配期报错。

## 3. Kernel / Agent Loop

```text
暴露插口:
- 内核容器     app/kernel
- 子模块容器   app/kernel/modules

依赖插口（默认实现）:
- app/kernel/modules -- 实现自己暴露的插口：按 order 遍历子模块并依次执行

主要逻辑:
- 拿到所有子模块：tree.children(app/kernel/modules)
- 按子模块的 order 排序执行
```

子模块插口，全部平铺在 `modules` 容器下：

```text
- .../modules/input         -- 实现自己暴露的插口
- .../modules/queued_input
- .../modules/assemble
- .../modules/compress
- .../modules/model
- .../modules/tool
```

每个子模块的形态与容器同构：暴露自己的插口，默认实现绑回自己，别人的实现可以替换或修改它。

`assemble` 与 `compress` 是两个阶段，不复用同一节点：`assemble` 每轮都跑，产出请求的提示词形状；`compress` 只在超预算时跑，把旧上下文换成摘要。两者的变更轴不同，合成一个节点会让「改提示词结构」牵动「改压缩逻辑」。

现状对照：这六个位置在 `agent/boot/slot_tree.json` 里只落了五个 —— `app/kernel/modules/{input,queued_input,compress,model,tool}`，装配职责目前混在 `compress` 里（`compress_module` 同时接收 `compactor` 与若干提示词相关参数）。目标态把它拆成 `assemble` 与 `compress` 两个平级节点，order 依次为 0 到 5。

## 4. Context / Prompt

提示词由 `assemble` 阶段的 `prompt` 子树独占，没有第二条注入路径。

### 4.1 装配阶段

```text
暴露插口:
- 阶段主插口   .../modules/assemble
- 提示词       .../modules/assemble/prompt
- 系统骨架     .../prompt/system
- 系统追加     .../prompt/system-appends
- 系统消息     .../prompt/messages
- 用户消息     .../prompt/user-messages
- 尾部追加     .../prompt/tail

依赖插口（默认实现，各自绑回自己暴露的插口）:
- .../modules/assemble   每轮执行：取 prompt 的产物，挂到请求上
- .../prompt             组装 = system + system-appends，再接 messages 与 user-messages
- .../prompt/system      固定骨架，不随插件变化
- .../prompt/system-appends  按 order 遍历子插口，拼接文本
- .../prompt/messages        按 order 遍历，每条成为独立系统消息
- .../prompt/user-messages   按 order 遍历，每条成为用户消息
- .../prompt/tail            按 order 遍历，拼在请求最末

主要逻辑:
- 空文本跳过，不产生空段落
- tail 只允许出现在请求最后
- 子插口按 order 遍历，同一 order 报装配冲突
```

### 4.2 压缩阶段

```text
暴露插口:
- 阶段主插口   .../modules/compress
- 摘要提取     .../modules/compress/extract

依赖插口（默认实现，各自绑回自己暴露的插口）:
- .../modules/compress   超预算时触发
- .../extract            读旧上下文，产出摘要后的新上下文

主要逻辑:
- 触发条件来自模型配置的压缩阈值，不看提示词结构
- 与装配阶段无数据依赖，只共享上下文对象
```

### 4.3 谁往哪里写

| 插口 | 使用方 |
| --- | --- |
| `system-appends` | 回复语言、动手指令、资源目录、环境信息、编码准则、术语、工具使用纪律、可用工具、视觉帧描述 |
| `messages` | skills、rules、知识库、记忆摘要 |
| `user-messages` | 视觉帧注入的图片信息 |
| `tail` | 执行模式、AI 说话、todolist |

### 4.4 现状对照

| 现状动作 | 目标落点 | 使用者 |
| --- | --- | --- |
| `add_prompt_section(section, fn)` | `prompt/*` 下按语义归位 | `skills`、`rules`、`knowledge`、`visual_operator_2` |
| `add_mode_tail(fn)` | `prompt/tail` | `ai_cosplay` |
| `add_context_source(fn)` | `prompt/messages` 或 `prompt/system-appends` | `knowledge`、`rules`、`skills` |
| `add_context_assembly_hook(fn)` | `prompt/user-messages` | `visual_operator_2` |

四条旧路径合并到一处：`assemble` 阶段的 `prompt` 子树。`ContextSources`、`PromptSections`、`PromptTail` 不再作为插件注册入口，只保留为容器默认实现。

现状与目标的差异有两处要说清：一是现在 `compress` 同时做装配与摘要，目标拆成两个平级阶段；二是现在有四条并列的提示词写入路径，目标只有 `prompt` 下面五个子插口。

## 5. Host / Boot / Tool / Shell

### 5.1 Host services

```text
暴露插口:
- 服务容器   app/host/services
- 每个服务   app/host/services/<服务名>

依赖插口（默认实现）:
- app/host/services/<服务名> -- 各自绑回自己，builder 写在节点上

主要逻辑:
- 按 requires 求值，无依赖的先构造
- 服务只能在构造时拿到自己声明的依赖，不读全局
```

22 个服务及其依赖：

| 服务 | requires |
| --- | --- |
| `event_bus` | — |
| `error_log` | event_bus |
| `live_state` | — |
| `queue` | event_bus |
| `mesh` | queue |
| `registry` | — |
| `background_tasks` | — |
| `context_sources` | — |
| `context_hooks` | — |
| `prompt_tail` | — |
| `prompt_sections` | — |
| `contributions` | — |
| `model_catalog` | — |
| `update` | — |
| `session_factory` | context_sources |
| `compactor_factory` | provider |
| `provider` | model_catalog |
| `contexts` | registry、live_state |
| `pipeline` | registry、contexts、live_state |
| `plugin_host` | registry、event_bus、context_sources、pipeline、contributions、context_hooks、model_catalog、prompt_tail、prompt_sections |
| `store` | — |
| `subagents` | store、mesh、queue、event_bus |

现状对照：路径是 `app/host/services/<服务名>`，`factory` 统一为 `agent.boot.components:service_component`，实际 builder 在节点 `metadata.builder` 里，例如 `agent.boot.host_factories:make_event_bus`。目标态把 `metadata.builder` 提升为节点的实现声明，不再包一层 `service_component`。

### 5.2 Boot

```text
暴露插口:
- 启动容器   app/boot
- 文件资源   app/boot/files
- 门面       app/boot/facade
- 插件装载   app/boot/plugins

依赖插口（默认实现）:
- app/boot/files    -- 实现自己暴露的插口
- app/boot/facade   -- 依赖 5.1 的全部服务
- app/boot/plugins  -- 依赖 facade

主要逻辑:
- files 先于工具，因为 executors 要拿 backups 与 recycle
- facade 只转发与转换形状，不含业务规则
- plugins 最后装载，失败时按已登记的回滚清单逆序撤销
```

`facade` 的 `requires` 是 5.1 的 22 条服务，一一对应，不新增服务；它把这些服务转给工具与壳层。现状对照：`app/boot/{files,facade,plugins}` 与实测节点一致，`facade` 的 `requires` 在 `slot_tree.json` 里正好 22 项。

### 5.3 Tools

```text
暴露插口:
- 工具容器   app/boot/tools
- 每个工具   app/boot/tools/<组名>

依赖插口（默认实现）:
- app/boot/tools/<组名>  -- 各自绑回自己，一个节点注册该组的全部工具

主要逻辑:
- 每个工具节点 requires facade；一组工具共用一个节点
- 工具只声明名字、参数与 execute，不碰装配
- executors 与 commit-write 另加依赖：前者要 files 的 backups 与 recycle，后者要 executors 表
```

24 个工具节点，与 2.11 的模块归属表一一对应：

```text
background_task  echo  read_file  grep_files  glob_files  write_file
edit  fs  command  tasks  session  subagent  locate  text_data
system  web  ocr  image  archive  geo  review_conclusion  present
executors  commit_write
```

现状对照：路径是 `app/boot/tools/<组名>`，`factory` 为 `agent.boot.tool_components:make_*`，节点名用下划线（`read_file`），与工具名同名时直接复用。目标态把 24 个节点换成 81 个工具级插口，每个工具一条路径，可单独替换。

### 5.4 Shell

```text
暴露插口:
- 壳层容器       app/shell
- 界面根         app/shell/web-ui
- 界面各挂载点   app/shell/web-ui/<区域>
- 鉴权           app/auth

依赖插口（默认实现）:
- app/boot/shell/classic_adapter   -- 依赖 facade
- app/boot/shell/plugin_events     -- 依赖 classic_adapter
- app/boot/shell/runner            -- 依赖 facade
- app/boot/shell/wake_scheduler    -- 依赖 facade
- app/boot/shell/finalizer         -- 依赖上述四项

主要逻辑:
- 壳层不拥有插件子树，只提供挂载点
- 适配器按 facade 取服务，不直接摸 host
- 最终化节点最后执行，负责收尾与会话落盘
```

`app/auth` 是唯一带 `frozen=true` 的节点：它不拥有子级，装配完成后不许覆盖。

界面挂载点见 2.5 的 18 个插口，不在此重列。现状对照：`app/boot/shell/{classic_adapter,plugin_events,runner,wake_scheduler,finalizer}` 五个节点与实测一致，`finalizer` 的 `requires` 为四项，见 `slot_tree.json` 第 66 节点。原文虚构的 `app/shell/web-ui/sidebar`、`composer`、`app/shell/http`、`app/shell/events`、`app/shell/adapters/*` 全部不存在，已删。

### 5.5 Entry

Entry 不在装配树内。它是装配的调用方，不是被装配对象：`entry → boot_app() → shell`。把入口也做成被装配节点会形成「装配根需要先装配自己」的循环。

```text
暴露插口:
- 无。入口是进程边界，不向树内暴露任何插口。

依赖插口:
- app/boot/facade        取装配结果
- app/boot/shell/*       把控制权交给对应壳层

主要逻辑:
- 选运行方式：CLI 交互、无头单回合、Web
- 调 boot_app() 拿到装配好的 app
- 把 app 交给壳层，自己不再干预
```

三种运行方式的插件清单：

| 清单 | 作用 |
| --- | --- |
| `plugins.ini` | 基础清单，三种方式共用 |
| `plugins.cli.ini` | CLI 覆盖层，`[profile] base = plugins.ini` |
| `plugins.headless.ini` | 无头覆盖层，同样继承基础清单 |

装配期内与入口相关的只有壳层侧五个节点，见 5.4；`slot_tree.json` 里没有任何 `app/entry/*` 节点，因为入口在树外调用装配根。

覆盖层当前有一处失效：`plugins.cli.ini` 与 `plugins.headless.ini` 都写着：

```ini
[plugin:ai_speak]
enabled = 0
```

但插件目录名是 `ai_cosplay`，清单按目录名匹配，所以这一节匹配不到任何插件，等于没禁用。要真正在 CLI 与无头模式关掉语音，节名必须改成 `[plugin:ai_cosplay]`。

### 5.6 主插口规则

```text
一个独立模块 = 一个主插口
一个插件 = 一个主插口
一个工具 = 一个主插口
所有子插口路径必须以主插口路径为前缀
主插口禁用/卸载 = 整个子树不可用
替换主插口 = 整个子树替换
```

四类主插口前缀：

| 对象 | 主插口 | 子插口 |
| --- | --- | --- |
| 模块 | `app/kernel/modules/<名>` | 无，叶子节点 |
| 插件 | `app/plugins/<插件名>` | `tools/`、`routes/`、`prompt/`、`ui/`、`runtime/` |
| 内置工具 | `app/tools/<工具名>` | `schema`、`executor`、`ui/tool-shell` |
| 插件工具 | `app/plugins/<插件名>/tools/<工具名>` | 同上 |

全量清单不在此重复：模块见 §3 与 5.1–5.4，插件见 2.4，内置工具 47 个见 2.11，插件工具 34 个见 2.12。

插件主插口下的子插口按职责分四类：

```text
app/plugins/<插件名>
├─ tools/<工具名>       工具，每个一条
├─ routes/<端点名>      HTTP 端点
├─ prompt/<段名>        提示词贡献，落在 4.3 的四条插口上
├─ ui/<挂载点>          UI 控件与面板
└─ runtime              插件持有的运行时对象
```

替换粒度：绑定插件主插口即替换整个子树，不必逐个替换子插口。视觉插件的 20 个工具、提示词、图片注入与界面按钮都挂在 `app/plugins/visual_operator_2` 下，一次替换全生效。

工具壳挂在工具主插口下，不挂在界面侧：

```text
app/tools/<工具名>/ui/tool-shell
app/plugins/<插件名>/tools/<工具名>/ui/tool-shell
```

界面侧 `chat/messages/tools` 只是解析器：拿工具名拼出「工具主插口 + `/ui/tool-shell`」再去查，不是全部工具壳的父插口。所以不存在 `chat/messages/tools/<工具名>` 这类路径。

工具壳契约四项：`title`、`summary`、`mount`、`fill`。定制只改这四项，不改工具本身。

### 5.7 主模块索引

主模块按同一格式在上文逐节展开，本节只给索引，不重复内容。

| 主模块 | 主插口 | 见 |
| --- | --- | --- |
| 主循环 | `app/kernel/modules` | §3 |
| 输入 | `app/kernel/modules/input` | §3 |
| 排队输入 | `app/kernel/modules/queued_input` | §3 |
| 装配 | `app/kernel/modules/assemble` | §4.1 |
| 压缩 | `app/kernel/modules/compress` | §4.2 |
| 模型 | `app/kernel/modules/model` | §3 |
| 工具 | `app/kernel/modules/tool` | §3 |
| 宿主服务 | `app/host/services` | 5.1 |
| 启动 | `app/boot` | 5.2 |
| 工具 | `app/boot/tools` | 5.3 |
| 壳层 | `app/shell` | 5.4 |
| 入口 | 树外 | 5.5 |
| 插件 | `app/plugins/<插件名>` | 5.6 与 2.4 |

每个主模块都必须满足：子插口以主插口路径为前缀；替换主插口即替换整个子树；主插口不可用时子树整体不可用。

## 6. 插件协议

### 6.1 插件清单

11 个插件，每个一个主插口 `app/plugins/<插件名>`，子插口按职责分五类（见 5.6）。下表是各插件实际暴露与依赖的插口，数字与 §2 各表一致。

| 插件 | 暴露 | 依赖 | 启用 |
| --- | --- | --- | --- |
| `ai_cosplay` | 工具 1、路由 3、事件订阅 2、提示词尾 1、UI 1、运行时 1 | `prompt/tail` | 是 |
| `visual_operator_2` | 工具 20、路由 4、拼装钩子 1、提示词段 1、UI 1、运行时 1 | `prompt/system-appends`、`prompt/user-messages` | 是 |
| `visual_operator` | 工具 12 | 无 | 否 |
| `skills` | 工具 1、上下文源 2、提示词段 1、UI 2 | `prompt/messages`、`prompt/system-appends` | 是 |
| `rules` | 上下文源 1、提示词段 1、UI 1 | `prompt/messages`、`prompt/system-appends` | 是 |
| `knowledge` | 上下文源 1、提示词段 1、路由 3、UI 3 | `prompt/messages`、`prompt/system-appends` | 是 |
| `multi_model` | 模型目录 1、设置面板 1、路由 1、UI 1 | `backend/models/catalog` | 是 |
| `theme_style` | 设置条目 1、路由 1、UI 2 | `app/settings/interface` | 是 |
| `auto_update` | UI 1 | `app/shell/web-ui/nav/buttons` | 是 |
| `base_settings` | 设置面板 4、设置条目 10、UI 1 | `app/settings` 根 | 是 |
| `web_ui` | UI 插口 18、动作 11、控件 11、工具壳 1 | 无 | 是 |

### 6.2 两类插件的写法差异

插件分两种，写法不同：

```text
纯数据插件
  ├─ base_settings、web_ui、auto_update
  ├─ 全部能力由 plugin-ui.json 声明
  └─ plugin.py 只调一次声明解析，不含业务逻辑

带业务插件
  ├─ ai_cosplay、visual_operator_2、skills、rules、knowledge、multi_model、theme_style
  ├─ 声明文件给路径与形状
  └─ plugin.py 给实现，运行时对象经 set_runtime 登记
```

`ai_cosplay` 是典型的跨层插件：一边暴露 `ui/panel`（界面长相可替换），一边依赖 `prompt/tail`（尾部文本）。两层只靠路径对齐，插件之间不互相 import。

`visual_operator_2` 是最大的插件：20 个工具、4 条路由、1 个拼装钩子、1 段提示词。替换时绑定主插口 `app/plugins/visual_operator_2` 一处即可，不必逐个替换工具。

`visual_operator` 是待淘汰的旧实现，`plugins.ini` 里 `enabled=0`，只在需要对比时启用；它的 12 个工具与 `visual_operator_2` 的 20 个工具并存会撞名，不能同时开。

### 6.3 已删除的虚构插件

`ai_writing` 在旧文档里有一节 6.5，但 `plugins/` 下没有该目录，`plugins.ini` 里也没有该节。它不是待实现项，是不存在的条目，已从全文档删除。

## 7. 从当前实现迁移

现状是两套路径规则并存：装配树用 `app/kernel`、`app/host`、`app/boot`，插件贡献用 `app/backend/*`。目标只有一套：`app/*` 之下按层分段，`backend/*` 前缀整体消失。

| 现状路径 | 目标路径 | 依据 |
| --- | --- | --- |
| `app/backend/http/routes/<插件>-<名>` | `app/plugins/<插件名>/routes/<名>` | 端点属于插件 |
| `app/backend/events/subscriptions/<事件>/<插件>-<名>` | `app/plugins/<插件名>/events/<事件>` | 订阅属于插件 |
| `app/backend/context/sources/<插件>/<名>` | `app/plugins/<插件名>/prompt/messages/<名>` | 落到 4.3 的 messages |
| `app/backend/context/assembly-hooks/<插件>/<名>` | `app/plugins/<插件名>/prompt/user-messages/<名>` | 落到 4.3 的 user-messages |
| `app/backend/prompt/sections/<段名>` | `prompt/system-appends/<段名>` 或 `prompt/messages/<段名>` | 按语义二选一 |
| `app/backend/prompt/mode-tails/<名>` | `prompt/tail/<名>` | 尾部追加 |
| `app/backend/models/catalog` | `app/plugins/multi_model/models/catalog` | 模型目录归属插件 |
| `app/backend/runtime/<插件>` | `app/plugins/<插件名>/runtime` | 运行时归属插件 |
| `app/backend/tools/<tool>/executor` | `app/tools/<tool>/executor` | 执行器属工具 |

装配期四层路径保持不变：`app/kernel`、`app/host`、`app/boot`、`app/shell`。它们已经在 `slot_tree.json` 里，只是 `metadata` 要提升为显式字段。

迁移顺序：先删 `backend/*` 的写入方（插件侧），再删路径声明，最后删 `PathRegistry` 里的 `BACKEND_SLOTS` 种子。三步都完成前，两套路径并存。

每一步的完成判据：

| 步骤 | 完成判据 | 验证方式 |
| --- | --- | --- |
| 一 · 插件侧改写 | 11 个 `plugin.py` 里搜不到 §8 的 15 个 API | `grep -r "ctx\.add_\|ctx\.register_tool\|ctx\.subscribe" plugins/` 无命中 |
| 二 · 删路径声明 | `plugins/` 下搜不到 `app/backend/` | `grep -rn "app/backend" plugins/` 无命中 |
| 三 · 删种子 | `backend_paths.py` 不再读 `backend_slots` | 删文件后所有测试通过，`slot_tree.json` 里 `backend_slots` 段删掉 |

三步任一未完成，`docs/subsystems/plugins.zh.md` 的「内核不认任何具体插件」都不成立，因为插件仍在运行期调用注册接口。

## 8. 要删除的常规 API

14 个 `add_*` 与 `register_*` 全部删除，能力改为声明：

```text
register_tool          → app/plugins/<插件名>/tools/<工具名>
set_subagent_tools     → app/plugins/<插件名>/tools/<工具名>/visibility
add_executor           → app/tools/<工具名>/executor
subscribe              → app/plugins/<插件名>/events/<事件>
add_context_source     → app/plugins/<插件名>/prompt/messages/<名>
add_mode_tail          → app/plugins/<插件名>/prompt/tail/<名>
add_prompt_section     → app/plugins/<插件名>/prompt/system-appends/<名>
add_ui_item            → app/plugins/<插件名>/ui/<挂载点>
add_ui_slot            → plugin-ui.json 的 slots 段
add_settings_panel     → app/settings/<面板>
add_settings_item      → app/settings/<面板>/<条目>
add_model_catalog      → app/plugins/multi_model/models/catalog
add_route              → app/plugins/<插件名>/routes/<名>
add_context_assembly_hook → app/plugins/<插件名>/prompt/user-messages/<名>
```

三处例外必须留代码，因为它们是运行期行为而非数据：

| API | 为什么不能声明 |
| --- | --- |
| `set_runtime(obj)` | 运行时对象是进程内实例，无法用 JSON 表达 |
| `add_pre_gate(fn)` | 安全门控要在工具执行前拦截，是有副作用的函数，不是返回值 |
| `add_post_observer(fn)` | 观察者在工具执行后读取结果，同上 |

这三处只对确实需要的插件开放，且必须登记在插件的 `plugin-meta.json` 里说明用途；不允许当通用扩展点用。

`PromptTail`、`PromptSections`、`ContextSources` 不再是插件注册入口，只保留为容器默认实现。

### 8.1 插件侧写法

`register(ctx)` 保留，但只剩三件事可做；做别的立即报错，不留兼容窗口。

```text
register(ctx) 允许的动作
  ├─ 返回 set_runtime(obj)         进程内运行时对象
  ├─ 返回 add_pre_gate / add_post_observer   确有需要的门控与观察者
  └─ 返回空                        纯数据插件，全部能力由声明描述
```

插件不再调用的东西：`ctx.add_*`、`ctx.register_tool`、`ctx.subscribe`、`ctx.bind`。这些改由声明里的 `factory` 与路径表达。插件若仍调用，宿主在 `register` 返回后校验账本，发现非常规条目即卸载该插件并报错。

实现怎么交出来：写在声明的 `factory` 里，指向插件目录内的模块函数。

```json
{
  "path": "app/plugins/knowledge/prompt/messages/knowledge",
  "kind": "provider",
  "factory": "plugin:knowledge_lines",
  "order": 30
}
```

`factory` 只有两种写法：

```text
宿主实现   agent.<点分模块>:<属性>      例：agent.boot.host_factories:make_plugin_host
插件实现   <点分相对模块>:<属性>        例：plugin:knowledge_lines（插件目录下 plugin.py）
                                        例：components:make_example（插件目录下 components.py）
```

插件实现的模块名是相对插件目录的点分名：点换成目录分隔符、补 `.py`，落在本插件目录内，越出即报错。因此它不带 `plugins.` 前缀、不带斜杠、不带 `.py`。`plugin:` 不是特殊语法，它只是相对模块名恰好叫 `plugin` 的情形，于是解析到插件目录下的 `plugin.py`。

写法由路径决定：`path` 在 `app/plugins/<名>/` 下时两种都可用（宿主实现可被插件引用），其他路径只允许宿主实现。`plugins.*` 前缀与含斜杠、带 `.py` 的写法都不接受。

注入：factory 拿到的参数只有 `ctx` 与 `requires` 声明的依赖。需要配置、数据目录这类环境能力时从 `ctx` 取：

```text
ctx.config        本插件 plugin-meta.json 的 config 段
ctx.data_dir      data/plugin/<插件名>/，由宿主创建
ctx.requires      已构造的依赖对象，键与声明一致
```

以 `knowledge` 为例，改后 `plugin.py` 只剩一个函数与一次 `set_runtime`；它的 3 条路由、1 个上下文源、1 段提示词、3 个控件全部由声明描述。`base_settings` 与 `web_ui` 这类纯数据插件，`register` 直接返回空列表。

## 9. 审查清单

铁律（违反即架构事故，逐条对 §0）：

```text
[ ] 新增一个插件只新增了 plugins/<名>/ 目录与 plugins.ini 一行
[ ] 该插件的能力全部落在自身目录内，包外无任何其资产
[ ] 静态片段里没有任何 app/plugins/ 路径
[ ] 运行期只有一棵树，无并行注册表、白名单或第二份账本
[ ] 轮内不新增节点、不换实现、不改 requires；变更下一轮生效
```

装配期：

```text
[ ] 每个 requires 指向真实存在的插口
[ ] 同一容器内 order 不重复
[ ] 只有 app/auth 带 frozen=true
[ ] 每条路径只在一处声明，slots 与 paths 不重名
[ ] 每个节点的 factory 可解析为 module:attr
[ ] 插件片段的每个 path 都以 app/plugins/<本插件名>/ 开头
[ ] 补齐节点的 owner：本插件前缀下归插件，前缀之上归 __host__
```

提示词：

```text
[ ] 装配阶段只有 prompt 一处权威
[ ] prompt/tail 只出现在请求最末
[ ] system-appends 与 system 同段，不进 tail
[ ] messages 与 user-messages 不混用
[ ] 空文本跳过，不产生空段落
```

插件：

```text
[ ] 11 个插件各有 plugin-slots.json，内容自洽
[ ] 所有子插口以主插口路径为前缀
[ ] plugin.py 不再调用 §8 的 14 个常规 API
[ ] 卸载时插口、路由、UI、设置全部回滚
[ ] visual_operator 与 visual_operator_2 不同时启用
```

数量：

```text
[ ] 内置工具 47 个、插件工具 34 个，合计 81 个声明
[ ] 启用状态扣掉 visual_operator 的 12 个，实际 69 个
[ ] 插件 11 个，与 plugins/ 目录一致
[ ] 事件 26 个，与 event_name.py 常量数一致
```

模式：

```text
[ ] CLI 与无头模式的覆盖层节名是 [plugin:ai_cosplay]
[ ] CLI 与无头模式不注入 UI 与语音尾部
[ ] 旧 backend/* 路径没有残留
```

### 9.1 实现期再定

以下四项本轮不定，实现时按实际需要补，但补完必须回写本文档，不允许只留在代码里。

| 项 | 现状 | 何时定 |
| --- | --- | --- |
| `ui` 与 `setting` 纯声明的渲染契约 | 只有形状与 `props`，字段集未定 | 改前端时定，落到 `plugin-ui.json` 的 schema |
| 错误码与上报格式 | 未定义 | 写装配器时定，先在 `SlotConfigError` / `SlotAssemblyError` 上按类加分类 |
| 是否加 `check_slots.py` 配置自检脚本 | 已实现：`scripts/check_slots.py`，已进 CI 门禁 | 装配器落地后定；若加，进 `scripts/ci.py --list` |
| `plugin-slots.json` 迁移期与 `slot_tree.json` 的并存策略 | 本文写「新优先、旧补缺、日志报出补齐项」 | 开工前定；若改硬切，§2.15 同步改 |