# 会话消息队列方案

## 目标

会话忙时，用户输入和 Agent 投递进入同一个待发送队列，不阻塞输入，不丢消息，不丢图片。

队列提供：

- 回合结束自动投递
- 下一个安全模型轮次插入
- 修改并还原到输入栏
- 取消
- Agent 来源标记

## 边界

- 队列不属于会话事实，不写 `data/sessions/*.raw`
- 队列项只有投递后才产生 `INPUT_CLAIMED` 事实
- 队列不改变模型上下文装配顺序
- 队列不保存已投递消息
- 旧 inbox 不迁移、不读取、不兼容，直接移除

## 现有 inbox 冲突

现有 inbox 同时承担 Agent 间传输和回合续跑：

```text
agent/mechanisms/mesh.py
  data/mesh/inbox/<cid>.jsonl
  无队列项 ID
  无修改/取消状态

agent/core/modules/inbox_mod.py
  每个模型 pass 前自动抽干
  直接注入当前回合

agent/shell/session_runner.py
  回合结束后从 mesh inbox 取队首

agent/shell/web_api.py
  忙时返回 409

chat/send.js
  忙时弹窗阻止发送
```

冲突：

- 用户消息会被当作 Agent 消息在 pass 中途注入
- Agent 消息可能在 UI 操作前被消费
- 没有稳定 ID，无法精确修改/取消
- 来源、排序、图片、状态无法统一
- 旧 inbox 自动抽干与用户控制的队列语义互斥

结论：删除旧 inbox 职责，新增统一 `ConversationQueue`。

## 资产归属

| 资产 | 归属 |
|---|---|
| 队列存储、状态机、附件 | `agent/mechanisms/conversation_queue.py` |
| 服务注册 | `agent/core/context.py` 的 `SERVICE_CONVERSATION_QUEUE` |
| 回合结束调度 | `agent/shell/session_runner.py` |
| 安全插入点注入 | `agent/core/modules/queued_input_mod.py` |
| 输入事实 | `agent/core/modules/input_mod.py` |
| HTTP 端点 | `agent/shell/web_api.py`、`agent/shell/web_routes.py` |
| SSE 契约 | `agent/core/event_name.py`、classic adapter |
| UI | `agent/shell/web_assets/classic/js/chat/queue.js`、CSS、`agent-ui.html` |
| 队列数据 | `data/queues/<cid>/` |

`MeshState` 只保留：

- Agent 注册表
- 运行占位与活跃集
- Agent 发现

`MeshState` 删除：

- `_inboxes`
- inbox 持久化
- inbox 出队
- `end_run` 的队列续占逻辑

## 数据模型

```text
id              队列项 ID
cid             会话 ID
origin          user | agent
content         文本
attachments     附件元数据
sender          Agent 来源信息
delivery        after_turn | next_pass
state           queued | inserting | claimed | delivered | cancelled | draft
seq             队列顺序
created_at
updated_at
revision        队列版本
```

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
blob            内部存储路径，不返回前端
```

## 状态机

```text
queued
  ├─ 插入发送 → inserting
  ├─ 修改 → draft
  └─ 取消 → cancelled

inserting
  ├─ 安全插入点 → claimed → delivered
  ├─ 回合提前结束 → queued
  └─ 取消 → cancelled

draft
  ├─ 重新提交 → queued / inserting
  └─ 丢弃 → cancelled

claimed
  禁止修改、禁止取消
```

规则：

- `claimed` 后修改/取消返回 409
- 取消立即从队列视图移除
- 投递成功后从队列删除
- 写盘失败返回错误，不清空输入栏

## 图片规则

队列不设置独立图片上限。

输入框、`/api/chat/send`、队列使用同一套附件规则：

```text
agent/core/input_attachments.py
  MAX_IMAGES
  IMAGE_MIMES
  normalize_images()
```

- 输入框接受多少张，队列就能存多少张
- 图片数量限制只改这一处
- 服务端请求体大小上限仍由 `MAX_BODY_BYTES` 控制
- 队列只保存已通过输入校验的附件
- 不截断、不再过滤、不静默丢图
- UI 的最大图片数由 `/health` 下发，JS 不写死 `4`

附件落盘：

```text
data/queues/<cid>/<item_id>/
  meta.json
  attachments/<attachment_id>
```

`meta.json` 只存附件元数据；原图独立存 blob。

队列列表返回附件元数据，不返回整张 base64。修改时读取 blob，恢复为 `data_base64` 给输入栏。

## 投递策略

### 会话空闲

`POST /api/chat/send` 直接启动新回合，不入队。

### 会话忙

```text
POST /api/chat/send
→ 入队，delivery=after_turn
→ 返回 queue_item
→ 输入栏清空
→ 队列 UI 增加一行
```

回合结束：

```text
当前回合结束
→ SessionRunner 仍持有运行占位
→ ConversationQueue 取 after_turn 队首
→ 续占下一轮
→ 启动新回合
→ 队列项删除
```

队列优先于目标和自主续跑。

一条消息一轮，不合并多条消息。

### 停止

停止只结束当前回合：

- 不自动消费队列
- 队列项保持原状态
- 用户可以继续插入、修改、取消
- 下一次显式发送或插入后才继续

## 插入发送

插入点是下一个安全模型轮次：

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

插入中的条目在回合提前结束时回到 `queued`，下一回合继续处理。

立即中断当前回合属于“停止 + 新回合”，不属于队列插入。

## Agent 消息

Agent 消息统一入队：

```text
origin=agent
sender={cid,name,thread_id,requires_reply}
delivery=after_turn
```

展示：

```text
[#1] [🤖 AgentName] [消息内容] [插入发送] [修改] [取消]
```

投递后按 Agent 消息渲染，不变成普通用户消息。

Agent 消息默认不自动注入当前回合。

## 修改与来源保留

修改用户消息：

1. recall 队列项
2. 状态改为 `draft`，从队列视图移除
3. 文本和图片还原到输入栏
4. 重新提交时生成新队列项

修改 Agent 消息：

1. recall 返回 `origin=agent`、sender 元数据、`draft_queue_id`
2. 输入栏显示来源标记
3. 重新提交携带 `draft_queue_id`
4. 服务端校验 draft 属于当前会话
5. 新队列项保留 `origin=agent` 与 sender

浏览器不能自行声明 Agent 身份。

## API

```text
POST   /api/chat/send
GET    /api/chat/queue?conversation_id=...
POST   /api/chat/queue/<item_id>/insert
POST   /api/chat/queue/<item_id>/recall
DELETE /api/chat/queue/<item_id>
```

`POST /api/chat/send` 忙时响应：

```json
{
  "ok": true,
  "queued": true,
  "conversation_id": "cid",
  "queue_item": {"id": "q_...", "position": 1},
  "revision": 12
}
```

`recall` 响应：

```json
{
  "ok": true,
  "draft_queue_id": "q_...",
  "item": {
    "id": "q_...",
    "origin": "user",
    "content": "text",
    "sender": null,
    "attachments": [
      {"mime": "image/png", "data_base64": "..."}
    ]
  }
}
```

队列快照：

```json
{
  "ok": true,
  "conversation_id": "cid",
  "revision": 12,
  "items": [
    {
      "id": "q_...",
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

携带会话快照与 revision。前端按 revision 覆盖，不做增量猜测。

## UI

位置：输入框上方左侧，宽度为输入框的一半；语音播放条在队列上方。

用户消息：

```text
[#1] [帮我处理一下 xxxx] [插入发送] [修改] [取消]
```

Agent 消息：

```text
[#1] [🤖 AgentName] [协作消息...] [插入发送] [修改] [取消]
```

行为：

- 忙时不再拦截发送
- 发送成功后才清空输入栏
- 队列项按 `position` 展示
- `插入中` 禁止重复点击
- 修改后恢复文本、图片和来源标记
- 取消立即移除
- 队列为空自动隐藏
- 按会话 tab 独立
- 刷新后通过快照恢复

## 输入事实

用户消息和 Agent 消息走同一输入事实形状：

```json
{
  "content": "text",
  "attachments": [],
  "_sender": "agent-cid",
  "_sender_name": "Agent Name"
}
```

用户消息不带 `_sender`。

`InputModule` 和 `QueuedInputModule` 共用同一个 payload 构造函数，避免两条输入路径漂移。

## 删除范围

直接删除，不保留兼容层：

- `agent/core/modules/inbox_mod.py`
- `MeshState` 的 inbox 字段与持久化
- `MeshState.enqueue` / `pop` / `inbox_size`
- `MeshState.end_run` 的队列出队
- `INBOX_DEQUEUED` 旧事件
- `inbox_queued` 旧 SSE 提示
- 旧 inbox 测试

旧 `data/mesh/inbox/*.jsonl` 不读取、不迁移、不删除。

## 测试

### 队列机制

- 忙时入队、空闲直发
- 写盘失败不清空输入
- 队列顺序与 revision
- 图片完整保存与恢复
- 无队列图片数量上限，规则与输入框一致
- 修改/取消状态机
- claimed 拒绝修改/取消
- 重启恢复
- 停止后不自动投递

### 回合调度

- 回合结束一条一轮
- 目标/自主续跑不抢占队列
- 插入在工具批次后、下一次模型请求前
- 插入中回合结束回队
- 多会话隔离
- Agent 消息按来源投递

### API / UI

- 忙时 send 返回 queued
- queue 快照与 revision
- recall 返回文本、图片、来源
- insert 生效
- cancel 生效
- SSE 快照覆盖
- 修改后发送保留 Agent 来源
- 图片预览恢复

### 回归

- `session_send` / `session_multisend` / `session_broadcast`
- `requires_reply`
- 确认与恢复轮
- 停止
- 目标与自主续跑
- 现有会话历史

## 实施顺序

1. `agent/core/input_attachments.py` 统一附件规则
2. `ConversationQueue` 与持久化
3. 删除 MeshState inbox
4. `QueuedInputModule` 与 `SessionRunner` 调度
5. Web API / SSE
6. 队列 UI 与图片还原
7. 测试、文档、验收
