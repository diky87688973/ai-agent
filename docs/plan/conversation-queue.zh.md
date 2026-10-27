[English](conversation-queue.md) | **中文**

# 会话消息队列

## 目标

会话忙时，用户输入和 Agent 投递进入同一个待发送队列。输入不被阻塞，消息和图片都不丢失。

队列提供：

- 回合结束时自动投递
- 在下一个安全模型趟插入
- 修改并还原到输入栏
- 取消
- Agent 来源标记

## 边界

- 队列不属于会话事实，不写 `data/sessions/*.raw`。
- 队列项只有投递后才产生 `INPUT_CLAIMED` 事实。
- 队列不改变模型上下文装配顺序。
- 队列不保存已投递消息。
- 用户输入和 Agent 投递共用一个队列，队列项有稳定 ID，共用一套状态机；不存在第二条待发送通道。

## 资产归属

| 资产 | 归属 |
|---|---|
| 队列存储、状态机、附件 | `agent/mechanisms/conversation_queue.py` |
| 服务注册 | `agent/core/context.py` 的 `SERVICE_CONVERSATION_QUEUE` |
| 回合结束调度 | `agent/shell/session/runner.py`、`agent/shell/session/queue.py` |
| 安全插入点注入 | `agent/core/modules/queued_input_mod.py` |
| 输入事实 | `agent/core/modules/input_mod.py` |
| HTTP 端点 | `agent/shell/web/web_routes.py`、`agent/shell/web/web_chat.py`、`agent/shell/web/web_api.py` |
| SSE 契约 | `agent/core/event_name.py`、`agent/shell/classic_adapter/` |
| UI | `agent/shell/web/web_assets/classic/js/chat/queue.js`、`agent/shell/web/web_assets/classic/css/chat-queue.css`、`agent/shell/web/web_assets/classic/agent-ui.html` |
| 队列数据 | `data/queues/<cid>/` |

`MeshState` 保留：

- Agent 注册表
- 运行占位与活跃集
- 会话存在性检查
- 通过 `submit` 原子投递

队列存储和队列状态归 `ConversationQueue`。

## 数据模型

```text
id              队列项 ID
cid             会话 ID
origin          user | agent | system
content         文本
attachments     附件元数据
sender          Agent 来源信息
delivery        after_turn | next_pass
state           queued | inserting | claimed | draft
seq             队列顺序
created_at
updated_at
payload         内部元数据：恢复结果、通知类型、来源、ID、批次
```

队列项本身不带 revision。每个会话有一个队列版本号（revision），保存在 `data/queues/<cid>/revision`，每次队列变化递增。

`sender`：

```text
cid
name
thread_id
requires_reply
```

`attachments`：

```text
id
mime
size
width
height
```

blob 路径只在内部使用，不返回前端。

后台任务通知和恢复结果属于内部 `system` 项。它们不出现在队列快照里，但保留投递顺序。

## 状态机

```text
queued
  ├─ 插入发送 → inserting
  ├─ 修改 → draft
  └─ 取消 → 移除

inserting
  ├─ 安全插入点 → claimed
  ├─ 回合提前结束 → 保持 inserting
  └─ 取消 → 移除

draft
  ├─ 重新提交 → 新的 queued 项
  └─ 丢弃 → 移除

claimed
  ├─ 发出输入事实（插入）→ 移除
  ├─ 回合结束（after_turn）→ 移除
  └─ 进程重启 → queued
```

队列行进入 `inserting` 后显示「已插入」，修改、取消和再次插入均禁用。

规则：

- `claimed` 后修改和取消返回 409。
- 取消后该项立即从队列视图移除。
- 已投递项从队列删除。
- 写盘失败返回错误，输入栏保持不变。
- 进程重启时，落盘为 `claimed` 的项回到 `queued`；`inserting` 项保持 `inserting`，在下一个安全插入点投递。

## 图片规则

队列不设置独立图片上限。

输入框、`/api/chat/send` 和队列使用同一套附件规则：

```text
agent/core/input_attachments.py
  MAX_IMAGES
  IMAGE_MIMES
  normalize_images()
```

- 输入框和队列接受的图片数量一致。
- 上限由 `MAX_IMAGES` 定义；UI 通过 `/health` 的 `max_images` 读取。
- 服务端请求体大小上限由 `MAX_BODY_BYTES` 控制。
- 队列只保存已通过输入校验的附件。
- 队列不额外增加上限或过滤，只沿用共享附件规则。
- 通过校验的附件完整保存，不静默丢弃。

附件落盘：

```text
data/queues/<cid>/
  revision
  <item_id>/
    meta.json
    <attachment_id>
```

`meta.json` 保存队列项及其附件元数据；每张原图作为独立 blob 保存，文件名为 `a0`、`a1` 等。

队列列表返回附件元数据，不返回整张 base64。修改时读取 blob，恢复为 `data_base64` 给输入栏。

## 投递策略

### 会话空闲

`POST /api/chat/send` 直接启动新回合，不入队。

### 会话忙

```text
POST /api/chat/send
→ 入队，delivery=after_turn
→ 返回 queue_item
→ 清空输入栏
→ 队列 UI 增加一行
```

回合结束：

```text
当前回合结束
→ SessionRunner 仍持有运行占位
→ ConversationQueue 取 after_turn 队首
→ 为下一回合续占占位
→ 启动新回合
→ 该回合结束后删除队列项
```

队列优先于目标和自主续跑。

`after_turn` 每回合消费一条，不合并多条消息。

### 停止

停止只结束当前回合：

- 不自动消费队列
- 队列项保持当前状态
- 用户仍可插入、修改、取消
- 只有下一次显式发送或插入才继续

## 插入发送

插入点是下一个安全模型趟：

```text
当前模型流结束
→ 当前批次工具全部结束
→ 工具结果落盘
→ 下一个 pass 开始
→ QueuedInputModule
→ CompressModule
→ ModelModule
```

不插入到：

- 模型流式输出中
- 工具执行中
- tool_call 与 tool_result 之间

会话空闲时，插入会立即启动新回合，该项作为该回合的输入。

在同一个安全插入点，所有 `inserting` 项按队列顺序认领，每项各自产生一条 `INPUT_CLAIMED` 事实。

回合提前结束时，`inserting` 项保持 `inserting`，在下一个安全插入点投递。

立即中断当前回合属于停止后开启新回合，不属于队列插入。

## Agent 消息

目标会话忙时，Agent 消息进入队列：

```text
origin=agent
sender={cid,name,thread_id,requires_reply}
delivery=after_turn
```

目标会话空闲时，消息直接启动回合，不入队。

已入队的子智能体对等消息标记为 `inserting`（`delivery=next_pass`），在下一个安全插入点投递。

展示：

```text
[#1] [🤖 AgentName] [协作消息...] [插入发送] [修改] [取消]
```

投递后按 Agent 消息渲染，不变成普通用户消息。

普通 Agent 消息不注入当前回合；已入队的子智能体对等消息走下一个安全插入点。

## 修改与来源保留

修改用户消息：

1. recall 队列项
2. 状态改为 `draft`，从队列视图移除
3. 文本和图片还原到输入栏
4. 重新提交时生成新队列项

修改 Agent 消息：

1. recall 返回 `origin=agent`、sender 元数据和 `draft_queue_id`
2. 输入栏显示来源标记
3. 重新提交携带 `draft_queue_id`
4. 服务端校验 draft 属于当前会话
5. 新队列项保留 `origin=agent` 和 sender

浏览器不能自行声明 Agent 身份。

## API

```text
POST   /api/chat/send
GET    /api/chat/queue?conversation_id=...
POST   /api/chat/queue/<item_id>/insert
POST   /api/chat/queue/<item_id>/recall
DELETE /api/chat/queue/<item_id>
```

队列操作携带 `conversation_id`：GET 与 DELETE 走 query，POST 走 body。

会话忙时 `POST /api/chat/send` 响应：

```json
{
  "ok": true,
  "conversation_id": "cid",
  "run_id": "",
  "queued": true,
  "queue_item": {"id": "<item_id>", "position": 1},
  "revision": 12
}
```

`recall` 响应：

```json
{
  "ok": true,
  "draft_queue_id": "<item_id>",
  "item": {
    "id": "<item_id>",
    "origin": "user",
    "content": "text",
    "sender": null,
    "attachments": [
      {"mime": "image/png", "data_base64": "..."}
    ]
  },
  "revision": 12
}
```

队列快照：

```json
{
  "conversation_id": "cid",
  "revision": 12,
  "items": [
    {
      "id": "<item_id>",
      "position": 1,
      "origin": "user",
      "content": "text",
      "state": "queued",
      "delivery": "after_turn",
      "attachments": [
        {"id": "a0", "mime": "image/png", "size": 1234}
      ]
    }
  ]
}
```

SSE：

```text
queue_updated
```

事件携带会话快照与 revision。前端用快照整体替换本地队列，不做增量合并。

## UI

位置：输入框上方左侧，宽度为输入框的一半；语音播放条位于队列下方。

用户消息：

```text
[#1] [帮我处理一下 xxxx] [插入发送] [修改] [取消]
```

Agent 消息：

```text
[#1] [🤖 AgentName] [协作消息...] [插入发送] [修改] [取消]
```

行为：

- 会话忙时不拦截发送
- 队列路径下，成功响应后才清空输入栏
- 队列项按 `position` 展示
- `inserting` 行不能重复点击
- 修改后恢复文本、图片和来源标记
- 取消后立即移除该行
- 队列为空时自动隐藏
- 每个会话 tab 有独立队列
- 刷新后从快照恢复队列

## 输入事实

用户消息和 Agent 消息使用同一输入事实形状：

```json
{
  "content": "text",
  "attachments": [],
  "_sender": "agent-cid",
  "_sender_name": "Agent Name"
}
```

用户消息不带 `_sender`。

两条输入路径都产生这一形状，附件都经过 `with_attachment_ids()`；任一路径新增字段时，另一条路径同步新增。

## 测试

### 队列机制

- 忙时入队，空闲直发
- 写盘失败不影响输入栏
- 队列顺序与 revision
- 图片保存与恢复
- 无队列独立图片上限，规则与输入框一致
- 修改与取消状态机
- claimed 拒绝修改和取消
- 重启恢复：claimed 回到 queued，inserting 保留
- 停止后不自动投递

### 回合调度

- after_turn 每回合一条
- 目标和自主续跑不抢占队列
- 插入在工具批次之后、下一次模型请求之前
- 回合提前结束时 inserting 项保持 inserting
- 多会话隔离
- Agent 消息投递后保留来源

### API 与 UI

- 忙时 send 返回 queued
- queue 快照与 revision
- recall 返回文本、图片和来源
- insert 生效
- cancel 生效
- SSE 整体替换快照
- 修改后发送保留 Agent 来源
- 图片预览恢复

### 回归

- `session_send`、`session_multisend`、`session_broadcast`
- `requires_reply`
- 确认轮与恢复轮
- 停止
- 目标与自主续跑
- 会话历史
