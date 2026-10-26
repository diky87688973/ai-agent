# 子智能体能力方案

## 1. 目标

在现有会话体系内增加可持久化的多轮子智能体。

核心能力：

```text
父会话创建子智能体
子智能体独立会话
父子双向消息
按批次发现
后台列表与详情标签
跨应用重启保留
```

范围边界：

```text
只做多轮子智能体
不做一次性子智能体
不做子智能体再创建子智能体
不做 sibling 互通
不做子智能体插件热插拔
```

## 2. 已确认决策

| 项目 | 决策 |
|---|---|
| 批次归属 | 属于当前父会话 |
| 不传批次 | 自动创建批次并返回 |
| 单批上限 | 10 个子智能体 |
| fork | 父会话最后一个已完成回合，不含进行中回合 |
| fresh | 空历史，沿用父会话模型、工具和工作目录 |
| 重启 | 子会话保留，状态恢复为空闲，不自动重跑 |
| 消息 | 父子双向；子与子禁止；跨批次父子仍可通讯 |
| insertSend | 强制插入当前回合，不提供 false 选项 |
| 图片 | 复用现有附件与图片输入链路 |
| 存储 | 子会话事实放 `data/subagent/sessions`，其他仍在 `data` 根 |
| 密钥 | 与主会话共用 `data/cache/session_encryption.key` |
| UI | 静默创建，只在子智能体列表出现；点详情才开标签 |
| 插件化 | 生命周期归核心服务，不整体插件化 |

## 3. 设计取舍

本方案采用：

```text
本地持久多轮子智能体
显式批次分组
子会话独立存储
生命周期由核心服务持有
fork 只复制已完成回合
父会话持有子智能体成员关系
```

不采用：

```text
一次性子智能体
子智能体再创建子智能体
子会话混入主会话列表
把正在运行的生命周期交给可热插拔插件
```

fork 的边界只到最后一个 `turn_ended`，避免子会话看到父会话进行中的半截回合。

## 4. 领域模型

### 4.1 子智能体

```text
child_id       子会话 id
parent_cid     父会话 id
batch          批次 id
label          任务标题，必填
context        fork / fresh
created_at     创建时间
```

状态不持久化：

```text
busy = 子会话当前有运行中的回合
idle = 没有运行中的回合
```

### 4.2 批次

```text
batch_id       sb-<随机串>
parent_cid     所属父会话
children       子智能体列表
created_at     创建时间
```

批次不写全局 registry。
每个父会话一个目录，每个批次一个 JSON 文件，单文件最多 10 条子智能体元数据。

约束：

```text
一个批次只属于一个父会话
同一父会话可有多个批次
同一批次最多 10 个子智能体
子智能体可属于不同批次，但父会话相同
```

### 4.3 父子关系

```text
父 → 任意自己的子智能体
子 → 自己的直属父会话
子 → 子：拒绝
子 → 其他父会话：拒绝
```

跨批次不影响父子通讯。

## 5. 总体架构

```text
agent/subagent/
  manager.py      门面：组合三个边界，不持有实现
  lifecycle.py    创建、首回合启动、状态与列表
  messaging.py    父子消息、insertSend、图片
  repository.py   子会话路径、批次记录、fork 播种
  batches.py      批次元数据文件读写
  seed.py         fork 已完成回合的会话前缀
  models.py       数据类、错误与状态枚举

agent/capabilities/builtin/subagent_tools.py
  父会话工具：subagent
  子会话工具：subagent_send

agent/shell/web/web_subagents.py
  列表、历史、发送路由

agent/shell/web/web_assets/classic/js/chat/subagents.js
  子智能体列表与标签打开

agent/shell/web/web_assets/classic/css/subagents.css
  右侧堆叠面板样式
```

职责边界：

| 模块 | 唯一职责 | 禁止 |
|---|---|---|
| `manager.py` | 门面组合与公开用例 | 读写文件、拼消息、算状态 |
| `lifecycle.py` | 创建、启动、状态、列表 | 直接读写批次文件 |
| `messaging.py` | 父子消息与 insertSend | 管理 child 会话 |
| `repository.py` | 子会话路径、批次记录、fork 播种 | 激活回合、发消息 |
| `batches.py` | 批次文件原子读写 | 运行态判断 |
| `seed.py` | fork 前缀构造 | 路径与权限 |

依赖方向：

```text
app 装配
  → SubagentManager（门面）
    → SubagentLifecycle
      → SubagentRepository → BatchStore / SessionStore / seed
      → SubagentMessenger → MeshState / ConversationQueue
```

工具可见性：

```text
父会话工具视图：完整工具集，排除 subagent_send
子会话工具视图：排除 subagent / session_create / session_multisend / session_broadcast
子会话保留：subagent_send / session_send（session_send 仍按父子权限校验）
```

服务注册：

```text
SERVICE_SUBAGENTS
```

由 `build_app()` 装配，和 `BackgroundTaskManager`、`MeshState`、`SessionRunner` 同级。

## 6. 会话存储

### 6.1 目录

```text
data/
  sessions/                         主会话，保持现状
  cache/session_encryption.key      主会话与子会话共用
  sessions/                          主会话
  batches/
    <parent_cid>/
      <batch_id>.json                子智能体批次元数据，最多 10 条
  subagent/
    sessions/
      <child_id>.raw                 子会话事实（唯一进入 subagent 的数据）
```

资产归属：

| 资产 | 归属 | 说明 |
|---|---|---|
| 子会话事实 | `data/subagent/sessions/` | 唯一进入子目录的会话数据 |
| 批次元数据 | `data/batches/` | 属于父会话，不属于子会话 |
| 待发送消息 | `data/queues/` | 现有队列，按 child cid 分键 |
| Agent 身份 | `data/mesh/agents.json` | 现有协作网格 |
| 加密密钥 | `data/cache/session_encryption.key` | 父子共用 |
| 工具产物 | 项目目录或 `data/` 现有归属 | 不为子智能体新建旁路 |

约束：

```text
data/subagent/sessions 只放子会话事实
data/batches 按父会话和批次分文件；批次属于父会话，不属于子会话目录
不存在全局 registry.json
不复制主会话的 title、logs、attachments、queue
子会话工具产生的文件仍在 data 根或项目工作目录
```

单个批次文件最多 10 个子智能体，文件大小有上限。
父会话的批次数量增长表现为目录内文件数量增长，不会形成永久追加的单文件。

批次文件：

```json
{
  "schema": 1,
  "batch": "sb-...",
  "parent_cid": "...",
  "created_at": 0,
  "children": [
    {
      "child_id": "...",
      "label": "任务标题",
      "context": "fork",
      "created_at": 0
    }
  ]
}
```

写入方式：

```text
临时文件 + os.replace
按父会话目录加锁
批次文件只重写当前批次的 10 条元数据
```

子会话自身的第一条 `subagent/created` 事件同时记录：

```text
parent_cid
batch
label
context
```

批次文件丢失时可以从子会话恢复父子关系，但不能恢复完整批次列表。

### 6.2 SessionStore 改造

当前 `SessionStore` 固定：

```text
data_root/sessions/<cid>.raw
data_root/cache/session_encryption.key
```

增加可选参数：

```text
sessions_dir    自定义会话目录
key_path        自定义密钥路径
sequence_source 外部序列分配器
scan_dirs       额外扫描目录
```

子会话 store：

```text
sessions_dir = data/subagent/sessions
key_path     = data/cache/session_encryption.key
sequence_source = 主 store
```

主 store 的序列扫描包含：

```text
data/sessions
data/subagent/sessions
```

保证 SSE 全局 `seq` 不重复。

### 6.3 会话历史路由

主会话列表：

```text
SessionActions.sessions()
  只扫描 data/sessions
  不读取 data/subagent
```

子会话历史：

```text
GET /api/subagents/history?conversation_id=<parent>&child_id=<child>
  通过 SubagentManager 找到 child store
  返回子会话事件
```

未注册的 child_id 不返回。

## 7. 运行链路

### 7.1 创建

父会话调用 `subagent`：

```json
{
  "action": "create",
  "prompt": "任务内容",
  "batch": "可选，回传上次返回的批次号",
  "label": "必填，UI 展示标题",
  "context": "fork",
  "images": []
}
```

流程：

```text
校验父会话
校验 label 非空且长度不超过 120
校验 batch 归属、父会话匹配与容量
生成 child_id
创建子会话 store
按 context 写入初始事实
写入当前批次文件
注册到 MeshState
激活首条 prompt
返回 batch + child_id + label
不打开 UI 标签
```

`label` 必填，是 UI 列表和子会话标签的唯一展示标题；缺省或空白直接拒绝创建。

`prompt` 是首条任务。创建完成后立即以该 prompt 激活子会话，状态变为 busy，不等待用户再次发送。
批次文件写入失败时不启动首条回合；首条回合启动失败时保留子会话和批次记录，抛出可重试错误，子会话状态为 idle。

接口返回：

```json
{
  "ok": true,
  "batch": "sb-...",
  "child_id": "...",
  "label": "任务标题",
  "status": "busy"
}
```

### 7.2 fork 播种

```text
读取父会话事件
找到最后一个 turn_ended
只取该事件之前的完整回合
过滤父会话的 subagent 专属元数据
写入子会话 store
分配新的全局 seq
追加 subagent/forked 元数据事件
```

不复制：

```text
父会话进行中的回合
父会话待发送队列
父会话待确认状态
父会话 UI 临时状态
```

没有已完成回合时退化为 fresh。

### 7.3 fresh

```text
空事件日志
同一系统提示词
同一模型策略
同一工具集合，但移除 subagent 创建工具
同一工作目录
```

### 7.4 激活

复用现有：

```text
MeshState.submit
SessionRunner
ConversationQueue
RunRegistry
```

`SessionRunner` 增加 store 解析：

```text
store_for(cid)
  主会话 → 主 store
  子会话 → 子 store
```

`App.session(..., store=...)` 允许显式传入子 store。
工具、上下文、事件总线、队列、SessionContexts 仍共用同一装配。

## 8. 消息

### 8.1 父 → 子

父会话工具：

```json
{
  "action": "send",
  "child_id": "...",
  "msg": "消息",
  "images": []
}
```

行为：

```text
校验 child 属于当前父会话
空闲：正常激活子会话
忙碌：进入子会话队列
强制插入：队列项标记 inserting，下一安全插入点批量注入
批量范围：系统通知 / Agent 消息 / 用户主动插入
每条消息保持独立 rule=user 事实，不合并
返回 accepted / queued / inserted
```

父子消息强制使用打断式插入。父会话忙碌时消息进入队列，下一安全插入点由 `QueuedInputModule` 批量注入全部积压插入消息。

### 8.2 子 → 父

子会话工具：

```json
{
  "msg": "消息",
  "images": []
}
```

目标固定为直属父会话，不允许指定任意 target。
行为与父 → 子对称：

```text
父空闲：激活父会话
父忙碌：进入父队列
强制插入父当前回合
回合结束：本轮最终模型输出直接投递父 inbox
```

### 8.3 消息来源

投递消息统一写入：

```text
_sender       发送方 cid
_sender_name  子智能体 label 或父会话名
_sender_role  subagent / parent
_agent_peer_message = true
_message_kind = peer
```

复用现有 `peer_message` 事件与 `addPeerMessage()`：

```text
inbox 队列显示来源头像、来源名称、会话短 id
气泡样式与 session_send 一致
```

### 8.4 图片

沿用：

```text
normalize_images
ConversationQueue attachments
Engine.start_turn(attachments=...)
```

父 → 子、子 → 父都支持图片。
无文字、只有图片视为有效消息。

## 9. 状态与列表

### 9.1 状态

```text
busy  = mesh.is_running(child_id)
idle  = 其他情况
```

队列中有待发送消息但当前未运行，状态仍为 idle，列表额外返回 `pending` 数。
不引入 `stopped`。

### 9.2 列表

父会话查询：

```text
GET /api/subagents?conversation_id=<parent>&batch=<可选>
```

返回：

```json
{
  "ok": true,
  "batches": [
    {
      "batch": "sb-...",
      "children": [
        {
          "child_id": "...",
          "label": "任务标题",
          "status": "busy",
          "pending": 0,
          "created_at": 0
        }
      ]
    }
  ],
  "counts": {"busy": 0, "idle": 1}
}
```

排序：

```text
busy 在前
同状态按创建时间倒序
批次按最近创建倒序
```

### 9.3 重启恢复

启动时：

```text
扫描 data/batches/<parent_cid>/*.json
校验子会话文件
建立内存 child → parent/batch 索引
不启动任何回合
所有子智能体状态为 idle
```

如果子会话最后事件不是 `turn_ended`：

```text
追加 interrupted 结束事实
保留已有消息和工具结果
不伪造模型输出
```

下次父/子消息到达时，`MeshState` 正常激活，`SessionRunner` 从子 store 恢复历史并开始新回合。

## 10. 工具与 API

### 10.1 父会话工具

```text
subagent
  action=create
  action=list
  action=status
  action=result
  action=send
```

创建参数：

```text
prompt
batch
label       必填，UI 列表和标签标题，非空，最长 120 字
context=fork|fresh
images
```

列表参数：

```text
batch
```

发送参数：

```text
child_id
msg
images
```

### 10.2 子会话工具

```text
subagent_send
  msg
  images
```

目标固定为父会话。
子会话不注册 `subagent` 创建工具，避免递归。

### 10.3 HTTP

```text
GET  /api/subagents
GET  /api/subagents/history
POST /api/subagents/send
```

`POST /api/subagents/send` 只服务 UI 子会话标签的输入。
工具调用走 `SubagentManager`，不依赖 HTTP。

## 11. UI

### 11.1 布局

```text
[左侧控件区域 50%] [右侧控件区域 50%]
[ai说话]           [后台子智能体]
[inbox队列]        [后台任务]
[输入框 ----------------------------]
```

右侧列：

```text
.composer-right-col
  .subagent-panel
  .bg-task-panel
```

左侧列保持：

```text
.composer-left-col
  aiSpeakSlot
  chatQueue / queueDraft
```

### 11.2 子智能体面板

折叠头：

```text
后台子智能体
[busy 数] [idle 数]
```

展开列表行：

```text
[状态 icon] [批次号] [标题] [打开会话]
```

点击行或“打开会话”：

```text
打开子会话标签
不切换主会话列表
不自动打开新创建的子智能体
```

面板轮询：

```text
每 1.5 秒读取父会话列表
窗口卸载时清理定时器
```

动态列表使用事件委托，不逐行绑定。

### 11.3 子会话标签

标签新增元数据：

```text
subagent: true
parentCid
batch
label
```

标签行为：

```text
可输入
可插入发送
可发图片
关闭标签只释放 UI 运行态，不删除子会话
主会话列表不显示该标签
```

### 11.4 inbox 来源

复用现有 peer 气泡：

```text
来源名称 = 子智能体 label
来源短 id = child_id 前 8 位
来源角色 = subagent
```

## 12. 插件化结论

不建议把子智能体生命周期做成可热插拔插件。

原因：

```text
子智能体可能正在执行长任务
插件卸载不能撤销已接受的运行
热插拔会让创建、消息、状态查询出现半可用状态
生命周期、容量、权限、持久化必须由核心服务统一持有
```

推荐边界：

```text
核心：
  SubagentManager
  批次文件存储
  session store 路由
  MeshState / SessionRunner 集成
  fork 播种
  权限与状态

可插件化：
  未来外部 Provider（ACP / 远程 Agent）
  工具 schema 的可选扩展
  UI 面板
```

外部执行后端可以卸载；卸载只禁止新建，已接受运行必须继续完成。插件不能拥有正在运行的子智能体生命周期。

## 13. 测试

### 13.1 单元

```text
批次创建、自动批次、10 个上限
批次只属于父会话
fork 只取已完成回合
fresh 空历史
busy/idle 状态
父 → 子 / 子 → 父
sibling 拒绝
跨批次父子允许
强制插入，标记 inserting
图片消息
重启恢复 idle
子会话不进入主会话列表
序列不冲突
```

### 13.2 Web

```text
列表轮询
折叠/展开
打开子会话标签
子会话输入
inbox 来源显示
一次性模式不存在
```

### 13.3 验收

```text
父会话创建 2 个子智能体，同一批次
两个子智能体分别执行
父会话收到两个来源消息
子智能体之间发送被拒绝
重启应用后两个子智能体仍列出，状态 idle
父会话继续向子智能体发消息
```

## 14. 实施顺序

```text
1. SessionStore 可配置 sessions_dir / key_path / sequence_source
2. BatchStore 与 SubagentManager
3. fork 播种与子会话 store
4. SessionRunner store_for 与 App.session(store=...)
5. 父子消息与 insertSend
6. 工具与 HTTP
7. 右侧 UI 与子会话标签
8. 测试与验收
```

## 15. 风险

| 风险 | 处理 |
|---|---|
| 全局 seq 冲突 | 共享序列分配器，扫描两个会话目录 |
| 子会话污染主列表 | 主列表只扫 `data/sessions` |
| 密钥分裂 | 共用主密钥路径 |
| 子智能体递归 | 子会话不注册创建工具 |
| sibling 越权 | 消息按 parent/child 关系校验 |
| 热插拔中断运行 | 生命周期核心化 |
| 重启残留半回合 | 追加 interrupted 结束事实，不自动重跑 |
| 标签关闭误删数据 | 关闭只释放运行态，不删除 `.raw` |
