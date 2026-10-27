[English](subagent.md) | **中文**

# 子智能体能力

## 目标

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

## 决策

| 项目 | 决策 |
|---|---|
| 批次归属 | 批次属于当前父会话。 |
| 不传批次 | 自动创建批次并返回。 |
| 单批上限 | 10 个子智能体。 |
| `fork` | 复制父会话截至最后一个已完成回合的存储事件；进行中的回合不复制。 |
| `fresh` | 空历史；沿用共享模型策略与工作目录，工具视图按子会话角色过滤。 |
| 重启 | 子会话保留；状态恢复为空闲；不重跑回合。 |
| 消息 | 父子双向；子与子拒绝；跨批次父子仍可通讯。 |
| 强制插入 | 在目标忙碌时插入当前回合的下一个安全点；不提供非插入模式。 |
| 图片 | 复用现有附件与图片输入链路。 |
| 存储 | 子会话事实放 `data/subagent/sessions`；其他数据仍在 `data` 根。 |
| 密钥 | 与主会话共用 `data/cache/session_encryption.key`。 |
| UI | 静默创建；子智能体出现在列表；只从列表打开标签。 |
| 插件边界 | 生命周期归核心服务，不整体做成插件。 |

## 设计取舍

采用：

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

fork 的边界只到最后一个 `turn_ended`，子会话不会看到父会话进行中的半截回合。

## 领域模型

### 子智能体

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

### 批次

```text
batch          sb-<随机串>
parent_cid     所属父会话
children       子智能体记录
created_at     创建时间
```

批次不写全局 registry。
每个父会话一个目录，每个批次一个 JSON 文件，单文件最多 10 条子智能体记录。

约束：

```text
一个批次只属于一个父会话
同一父会话可有多个批次
同一批次最多 10 个子智能体
同一父会话的子智能体可分布在多个批次
```

### 父子关系

```text
父 → 任意自己的子智能体
子 → 自己的直属父会话
子 → 子：拒绝
子 → 其他父会话：拒绝
```

跨批次不影响父子通讯。
子会话的发送路径把目标固定为直属父会话，不暴露 target 参数。

## 总体架构

```text
agent/subagent/
  manager.py      门面：组合各边界并处理子会话回合结束通知
  lifecycle.py    创建、首回合启动、状态、列表、结果
  messaging.py    父子消息、强制插入、图片
  repository.py   子会话路径、批次记录、fork 播种、历史与结果读取
  batches.py      批次元数据文件读写
  seed.py         fork 已完成回合的会话前缀
  models.py       数据类与错误

agent/capabilities/builtin/subagent_tools.py
  父会话工具：subagent
  子会话工具：subagent_send

agent/shell/web/web_subagents.py
  列表、历史、发送动作

agent/shell/web/web_assets/classic/js/chat/subagents.js
  子智能体列表与标签打开

agent/shell/web/web_assets/classic/css/subagents.css
  右侧堆叠面板样式
```

职责边界：

| 模块 | 唯一职责 | 不负责 |
|---|---|---|
| `manager.py` | 门面、公开用例、子会话回合结束通知 | 文件读写、运行态计算 |
| `lifecycle.py` | 创建、首回合启动、状态、列表、结果 | 直接读写批次文件 |
| `messaging.py` | 父子消息、强制插入、图片 | 管理子会话 |
| `repository.py` | 子会话路径、批次记录、fork 播种、历史与结果读取 | 启动回合、发送消息 |
| `batches.py` | 批次文件原子读写 | 运行态判断 |
| `seed.py` | fork 前缀构造 | 路径与权限 |

依赖方向：

```text
app 装配
  → SubagentManager（门面）
    → SubagentRepository → BatchStore / SessionStore / seed
    → SubagentLifecycle → SubagentRepository / SubagentMessenger
    → SubagentMessenger → SubagentRepository / MeshState / ConversationQueue
    → EventBus（回合开始 / 回合结束）
```

工具可见性：

```text
父视图：注册表全部工具，排除 subagent_send 与会话工具
会话工具：session_send / session_multisend / session_broadcast / session_create / session_list
子视图：注册表全部工具，排除 subagent、上述会话工具，以及插件声明对子智能体隐藏的工具
子会话保留：subagent_send
父会话保留：subagent
```

服务注册：

```text
SERVICE_SUBAGENTS
```

`build_app()` 将其与后台任务管理器、`SessionRunner` 一同注册；`SubagentManager` 接收 `MeshState` 与会话队列。
没有父会话存储时，不创建管理器，也不创建两个工具。

## 会话存储

### 目录

```text
data/
  sessions/
    <cid>.raw                     主会话事实
  cache/
    session_encryption.key        父子会话共用
  batches/
    <parent_cid>/
      <batch_id>.json             子智能体批次元数据，最多 10 条
  subagent/
    sessions/
      <child_id>.raw              子会话事实
```

资产归属：

| 资产 | 归属 | 说明 |
|---|---|---|
| 子会话事实 | `data/subagent/sessions/` | 唯一进入 subagent 目录的会话数据。 |
| 批次元数据 | `data/batches/` | 属于父会话，不属于子会话。 |
| 待发送消息 | `data/queues/` | 现有队列，按 child cid 分键。 |
| Agent 身份 | `data/mesh/agents.json` | 现有协作网格。 |
| 加密密钥 | `data/cache/session_encryption.key` | 父子共用。 |
| 工具产物 | 项目目录或 `data/` 现有归属 | 不为子智能体新建旁路。 |

约束：

```text
data/subagent/sessions 只放子会话事实
data/batches 按父会话和批次分文件；批次属于父会话，不属于子会话目录
不存在全局 registry.json
不复制主会话的 title、日志文件、附件存储和队列
子会话工具产生的文件仍在项目目录或 data/ 现有归属
```

单个批次文件最多 10 条子智能体记录，文件大小受子智能体上限与 120 字标题上限约束。
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
进程内单锁串行化批次写入
批次文件只重写当前批次的记录（最多 10 条）
```

子会话自身的第一条 `subagent/created` 事件同时记录：

```text
parent_cid
batch
label
context
```

批次文件是成员关系的权威来源。批次文件丢失时，不从子会话元数据重建；该子会话仍在磁盘上，但不出现在列表里。

### SessionStore 配置

`SessionStore` 默认把会话事实解析到 `data_root/sessions/<cid>.raw`，密钥解析到 `data_root/cache/session_encryption.key`。

可选参数：

```text
sessions_dir     自定义会话目录
key_path         自定义密钥路径
sequence_source  外部序列分配器
scan_dirs        额外扫描目录
```

`add_scan_dir(path)` 可在构造后追加扫描目录。

子会话 store：

```text
sessions_dir = data/subagent/sessions
key_path = 父 store 的密钥路径
sequence_source = 父 store
```

父 store 的扫描范围：

```text
data/sessions
data/subagent/sessions
```

保证 SSE 全局 `seq` 不重复。

### 会话历史路由

主会话列表：

```text
SessionActions.sessions()
  只扫描 data/sessions
  不读取 data/subagent
```

子会话历史：

```text
GET /api/subagents/history?conversation_id=<parent>&child_id=<child>
  通过 SubagentManager 解析子会话 store
  返回子会话历史
```

未注册的 `child_id` 返回 404；父会话不匹配返回 403。

## 运行链路

### 创建

父会话工具调用：

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
校验父会话 id；调用方是子智能体时拒绝
校验 label：非空，最长 120 字
解析或创建批次；校验归属与容量
生成 child_id
按 context 写入子会话初始事实
把子智能体写入批次文件
注册到 MeshState
启动首条 prompt
返回 ok + batch + child_id + label + status + queued
不打开 UI 标签
```

`label` 必填，是 UI 列表和子会话标签的展示标题；缺省或空白直接拒绝创建。

`prompt` 是首条任务。创建完成后立即以该 prompt 激活子会话，状态变为 busy，不等待用户再次发送。
批次文件写入失败时不启动首条回合。首条回合启动失败时保留子会话和批次记录，抛出可重试错误，子会话状态为 idle。

接口返回：

```json
{
  "ok": true,
  "batch": "sb-...",
  "child_id": "...",
  "label": "任务标题",
  "status": "busy",
  "queued": false
}
```

### fork 播种

```text
追加 subagent/created，记录 parent_cid、batch、label、context
读取父会话事件
找到最后一个 turn_ended
取到该事件为止的前缀（含该事件）
过滤前缀中的 subagent/* 事件
把前缀写入子会话 store
分配新的全局 seq
```

子会话只有一条 `subagent/created` 事件，不额外写入 fork 标记。

不复制父会话的运行态：

```text
父会话进行中的回合
父会话待发送队列
父会话待确认状态
父会话 UI 临时状态
```

没有已完成回合时退化为 `fresh`。

### fresh

```text
不复制父会话事件；created 标记是唯一初始事实
同一套系统提示词装配，工具与提示词尾部按角色可见性过滤
模型按子会话 id 从共享策略解析
子会话角色工具视图
同一工作目录
```

### 激活

复用：

```text
MeshState.submit
SessionRunner
ConversationQueue
RunRegistry
```

`SessionRunner` 按会话解析 store：

```text
store_for(cid)
  主会话 → 主 store
  子会话 → 子 store
```

`App.session(..., store=...)` 接受显式传入的子 store。
工具、上下文、事件总线、队列和 SessionContexts 仍共用同一装配。

## 消息

### 父 → 子

父会话工具调用：

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
空闲：启动子会话
忙碌：进入子会话队列
强制插入：队列项标记 inserting，在下一个安全点注入
批量注入：全部积压的 inserting 项，包括系统通知、Agent 消息和用户主动插入
每条消息保持独立的 input 事实，不合并
返回 ok、target_id、queued、inserted、run_id
```

父子消息在目标忙碌时强制插入；发送路径不提供非插入模式。目标空闲时直接启动回合。
目标忙碌时消息进入其队列，下一安全插入点由 `QueuedInputModule` 批量注入全部积压插入消息。

### 子 → 父

子会话工具调用：

```json
{
  "msg": "消息",
  "images": []
}
```

目标固定为直属父会话，不暴露 target 参数。
行为与父 → 子对称：

```text
父空闲：启动父会话
父忙碌：进入父队列
强制插入父会话当前回合
回合结束：子会话最近一次非空模型输出直接投递父 inbox
```

### 消息来源

提交的消息载荷携带：

```text
_sender            发送方 cid
_sender_name       子智能体 label 或父会话名
_sender_role       subagent / parent
_agent_peer_message true
_message_kind      peer
```

排队与输入链路保留发送方 cid 和名称。

复用现有 `peer_message` 事件与 `addPeerMessage()`：

```text
inbox 显示来源头像、来源名称、会话短 id
气泡样式与 session_send 一致
```

### 图片

沿用：

```text
normalize_images
ConversationQueue attachments
Engine.start_turn(attachments=...)
```

父 → 子、子 → 父都支持图片。
无文字、只有图片视为有效消息。

## 状态与列表

### 状态

```text
busy = mesh.is_running(child_id)
idle = 其他情况
```

队列中有待发送消息但当前未运行，状态仍为 idle；列表额外返回 `pending` 数。
不存在 `stopped` 状态。

### 列表

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
      "created_at": 0,
      "children": [
        {
          "child_id": "...",
          "label": "任务标题",
          "context": "fork",
          "created_at": 0,
          "status": "busy",
          "pending": 0
        }
      ]
    }
  ],
  "counts": {"busy": 0, "idle": 1}
}
```

排序：

```text
批次按 created_at 倒序
同批次内按创建顺序
不按状态重排
```

### 重启恢复

构造时：

```text
读取 data/batches/ 下的全部批次文件
按 child_id 建立 parent / batch 索引
不启动任何回合
不打开子会话文件
```

状态由运行注册表推导，重启后子智能体为空闲。

重启不检查子会话的最后一条事件：

```text
保留已有事实不变
不追加 interrupted 结束事实
不伪造模型输出
```

下一条消息到达时启动新回合，`SessionRunner` 从子 store 加载历史并运行。

## 工具与 API

### 父会话工具

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
label       必填；UI 列表和标签标题；非空；最长 120 字
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

`status` 和 `result` 接收 `child_id`。

### 子会话工具

```text
subagent_send
  msg
  images
```

目标固定为父会话。
子会话工具视图排除 `subagent`，因此子会话不能创建新的子会话；生命周期也会拒绝调用方为子智能体的创建请求。

### HTTP

```text
GET  /api/subagents
GET  /api/subagents/history
POST /api/subagents/send
```

`POST /api/subagents/send` 只服务 UI 子会话标签的输入。
工具调用走 `SubagentManager`，不依赖 HTTP。

## UI

### 布局

```text
[左侧控件区域 50%] [右侧控件区域 50%]
[inbox 队列]       [子智能体面板]
[队列草稿]         [后台任务面板]
[AI 说话]
[输入框 --------------------------------------------------]
```

右侧列：

```text
.composer-right-col
  .subagent-panel
  .bg-task-panel
```

左侧列：

```text
.composer-left-col
  #chatQueue
  #queueDraft
  #aiSpeakSlot
```

### 子智能体面板

折叠头：

```text
子智能体
[0 已完成] [0 进行中]
```

展开行：

```text
[状态点] [批次号] [标题] [打开会话]
```

点击行或“打开会话”：

```text
打开子会话标签
不切换主会话列表
不自动打开新创建的子智能体
```

面板轮询：

```text
每 3 秒读取父会话列表
窗口卸载时清理定时器
```

父会话没有子智能体时隐藏面板；子会话标签激活时也隐藏。
动态列表使用事件委托，不逐行绑定。

### 子会话标签

标签元数据：

```text
subagent: true
parentCid
batch
title
```

标签行为：

```text
可输入
忙碌时发送走强制插入
可发图片
关闭标签只释放 UI 运行态，不删除子会话
忙碌的标签不能关闭
主会话列表不显示该子会话
```

### inbox 来源

复用现有 peer 气泡：

```text
来源名称 = 子智能体 label
来源短 id = child_id 前 8 位
```

发送方角色在消息载荷中，不在 inbox 气泡中渲染。

## 插件边界

子智能体生命周期不做成可热插拔插件。

原因：

```text
子智能体可能正在执行长任务
卸载插件不能撤销已接受的运行
热插拔会让创建、消息和状态查询出现半可用状态
生命周期、容量、权限和持久化必须由核心服务统一持有
```

核心：

```text
SubagentManager
批次文件存储
session store 路由
MeshState / SessionRunner 集成
fork 播种
权限与状态
```

可插件化：

```text
外部 Provider（ACP / 远程 Agent）
工具 schema 的可选扩展
UI 面板
```

外部执行后端可以卸载；卸载只禁止新建，已接受的运行必须继续完成。插件不能拥有正在运行的子智能体生命周期。

## 测试范围

### 单元

```text
批次创建、自动批次、10 个上限
批次只属于一个父会话
fork 只取已完成回合
fresh 空历史
busy/idle 状态
父 → 子 / 子 → 父
sibling 拒绝
跨批次父子允许
强制插入标记 inserting
图片消息
重启恢复 idle
子会话不进入主会话列表
序列不冲突
```

### Web

```text
列表轮询
折叠/展开
打开子会话标签
子会话输入
inbox 来源显示
不存在一次性模式
```

### 验收

```text
父会话创建 2 个子智能体，同一批次
两个子智能体分别执行
父会话收到两个来源消息
子智能体之间发送被拒绝
重启应用后两个子智能体仍列出，状态 idle
父会话继续向子智能体发消息
```

## 风险

| 风险 | 处理 |
|---|---|
| 全局 `seq` 冲突 | 共享序列分配器，扫描两个会话目录。 |
| 子会话污染主列表 | 主列表只扫 `data/sessions`。 |
| 密钥分裂 | 父子共用父 store 的密钥路径。 |
| 子智能体递归 | 子视图排除 `subagent`；生命周期拒绝子智能体调用方。 |
| sibling 越权 | 消息按父子关系校验；子会话工具不暴露目标参数。 |
| 热插拔中断运行 | 生命周期核心化。 |
| 重启残留半回合 | 不自动重跑；保留已有事实，不伪造模型输出。 |
| 标签关闭误删数据 | 关闭只释放运行态，不删除 `.raw`。 |
