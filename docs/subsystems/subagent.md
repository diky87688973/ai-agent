# 子智能体

## 边界

```text
agent/subagent/
  models.py       数据对象与错误
  batches.py      批次元数据
  repository.py   子会话、批次、fork 播种
  lifecycle.py    创建、启动、状态、列表、结果
  messaging.py    父子消息投递
  manager.py      对外门面与完成事件
```

`agent/subagent` 只依赖 `agent/core` 与 `agent/mechanisms`。
`agent/app.py` 负责装配；`agent/shell/web` 只经 `SERVICE_SUBAGENTS` 调用，不直接持有仓库或批次文件。

## 注册与生命周期

```text
build_app(store=None)
  → 不创建 SubagentManager
  → 不注册 subagent / subagent_send

build_app(store=...)
  → 创建 SubagentManager
  → 注册父视图 subagent
  → 子视图 subagent_send
  → 注册 SERVICE_SUBAGENTS
  → App.dispose() 调用 shutdown
```

没有持久化存储时不提供子智能体工具。
`subagent` 只用于父会话；`subagent_send` 只用于子会话。父/子工具视图由 `ToolRegistryView` 过滤，工具实现仍保留在同一个注册表。

## 数据归属

```text
data/batches/<parent_cid>/<batch>.json
  批次元数据、子智能体 id、label、context

data/subagent/sessions/<child_id>.raw
  子会话事实

data/subagent/sessions/<child_id>.raw.lock
  子会话锁
```

`data/batches` 是批次元数据唯一入口。旧路径 `data/subagent/batches` 不再读取，也不再写入。
子会话共享父存储的全局序号源；子会话不出现在主会话列表。

## 消息与完成

```text
父 → 子
  subagent.send
  → 强制插入
  → 子忙：进入队列，下个安全 pass 批量注入
  → 子闲：启动回合

子 → 父
  subagent_send
  → 强制插入
  → 父忙：进入队列，下个安全 pass 批量注入
  → 父闲：启动回合

子回合结束
  → 读取本轮最终 model_message
  → 作为 Agent 消息直接投递父 inbox
  → 已主动发送相同文本时不重复投递
```

插入消息在 `QueuedInputModule` 中批量认领，每条保留独立 `input_claimed` 事实。
普通排队消息仍按回合结束投递。

## 失败与关闭

```text
创建批次失败：批次写入原子；失败批次不产生可见子智能体
首次启动失败：保留子智能体记录并抛出可重试错误
子会话存储失败：留痕，不伪造模型输出
管理器关闭：先退订事件，再 flush 子会话
```

## 工具

父工具：

```text
subagent
  create
  list
  status
  result
  send
```

子工具：

```text
subagent_send
```

`create` 的 `label` 必填；批次最多 10 个子智能体；`context` 为 `fork` 或 `fresh`。
`fork` 只复制父会话已结束的回合。`result` 返回子会话最近一次模型输出，不读取状态代替结果。
