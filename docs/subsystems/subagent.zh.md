# 子智能体

## 1. 概览

本模块的能力与边界见下文。

## 2. 流程图

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

## 3. 插口协议

### 暴露

| 插口路径 | 能力 | 关键属性 | 可替换/覆盖方式 |
|---|---|---|---|
| `app/host/services/subagents` | 宿主服务 | owner=模块；由 SlotTree 装配；失败按 master 规则 | 启动树节点按路径覆盖；运行时只读插口不替换 |
| `app/boot/tools/subagent` | 工具或执行器 | owner=模块；由 SlotTree 装配；失败按 master 规则 | 启动树节点按路径覆盖；运行时只读插口不替换 |
| `backend/tools/subagents/visibility/*` | 工具或执行器 | owner=插件；路径由声明给出；卸载时撤销 | 同路径 `replace=true` 覆盖；卸载时恢复原插口 |
### 依赖

| 依赖路径 | 能力 | 提供者 | 为什么依赖 |
|---|---|---|---|
| `app/host/services/store` | 宿主服务 | 宿主 | 装配前必须已就绪；不可用时按启动/请求失败传播 |
| `app/host/services/mesh` | 宿主服务 | 宿主 | 装配前必须已就绪；不可用时按启动/请求失败传播 |
| `app/host/services/queue` | 宿主服务 | 宿主 | 装配前必须已就绪；不可用时按启动/请求失败传播 |
| `app/host/services/event_bus` | 宿主服务 | 宿主 | 装配前必须已就绪；不可用时按启动/请求失败传播 |

## 4. 插口能力

### 数据归属
```text
data/batches/<parent_cid>/<batch>.json
  批次元数据、子智能体 id、label、context

data/subagent/sessions/<child_id>.raw
  子会话事实

data/subagent/sessions/<child_id>.raw.lock
  子会话锁
```

`data/batches` 是批次元数据的唯一入口。
子会话共享父存储的全局序号源；子会话不出现在主会话列表。

### 消息与完成
```text
父 → 子
  subagent.send
  → 子忙：入队并标记插入，下个安全插入点批量注入积压消息
  → 子闲：启动回合

子 → 父
  subagent_send
  → 父忙：入队并标记插入，下个安全插入点批量注入积压消息
  → 父闲：启动回合

子回合结束
  → 只取最近一个 turn_started 之后、当前任务轮次的非空 model_message
  → 纯系统通知输入的回合不自动汇报父会话
  → 普通任务轮次中途插入通知时，整个任务轮次仍只汇报一次
  → 无模型输出时投递固定提示
  → 已主动发送相同文本或同一 turn_ended 回调重复触发时不重复投递
```

父子消息在目标忙碌时强制插入，发送路径不提供非插入模式。在 `QueuedInputModule` 中批量认领插入消息，每条保留独立 `input_claimed` 事实。
普通排队消息仍按回合结束投递。

### 工具
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
`fork` 只复制父会话已结束的回合。`result` 返回子会话最近一次非空模型输出，不读取状态代替结果。

## 5. 其他细节

### 补充

没有持久化存储时不提供子智能体工具。
`subagent` 只用于父会话；`subagent_send` 只用于子会话。父/子工具视图由 `ToolRegistryView` 过滤，工具实现仍保留在同一个注册表。
单个工具是否对子智能体可见由插件在 `plugin-slots.json` 的 `subagent_tools` 声明：声明为 `[]` 表示该插件全部工具都不暴露，不声明该键才表示不加限制。



### 边界
```text
agent/subagent/
  models.py       数据对象与错误
  batches.py      批次元数据
  repository.py   子会话、批次、fork 播种
  lifecycle.py    创建、启动、状态、列表、结果
  messaging.py    父子消息投递
  manager.py      对外门面与完成通知
```

`agent/subagent` 只依赖 `agent/core` 与 `agent/mechanisms`。
`agent/boot/` 负责装配；`agent/shell/web` 只经 `SERVICE_SUBAGENTS` 调用，不直接持有仓库或批次文件。

### 失败与关闭
```text
创建批次失败：批次写入原子；失败批次不产生可见子智能体
首次启动失败：保留子智能体记录并抛出可重试错误
子会话存储失败：留痕，不伪造模型输出
管理器关闭：先退订事件，再 flush 子会话
```

## 6. 延伸阅读

| 主题 | 文档 |
|---|---|
| 架构 | [architecture.zh.md](../architecture.zh.md) |
| 插件 | [plugins.zh.md](plugins.zh.md) |
