# 插件 2.0 后续待办

状态：全部完成。

## 1. 模型请求 RemoteDisconnected 自动重试

状态：已完成。

实现：

```text
仅在尚未收到任何流式 chunk 时重试 RemoteDisconnected
首次请求加最多 5 次重试，总尝试次数最多 6 次
退避 0.1 / 0.2 / 0.4 / 0.8 / 1.6 秒
退避期间以 50ms 为粒度检查取消
每次重试都会由 provider.stream() 重新构造底层 HTTP 请求
llm_done / llm_failed / llm_ended / canceled 事件记录 retries
收到 chunk 后断流、其它异常、鉴权和参数错误不重试
```

测试覆盖：

```text
连续 5 次失败后第 6 次成功
连续 6 次失败只产生一个终态失败
收到 chunk 后断流不重试
退避期间取消立即停止
其它异常不重试
```

## 2. replace_in_file 单次替换上限 80 → 120 行

状态：已完成。

实现：

```text
MAX_DIFF_LINES = 120
替换内容行数和目标区间跨度分别检查，短内容不能绕过区间跨度限制
错误文案同步显示 120
中英文写入门控文档同步更新
```

测试覆盖 120 行放行、121 行拒绝、目标区间 120 行放行、121 行拒绝，以及错误文案中的上限。

## 3. 定时唤醒只携带本次任务

状态：已完成。

实现：

```text
唤醒输入携带当前 wake_job_id 和 due_at
模型输入渲染为当前 job_id、due_at、reminder
只投影最近一次唤醒之后的事实，以及本次唤醒产生的模型和工具链
保留系统提示与插件提示，排除历史对话和历史压缩摘要
唤醒请求不复用历史压缩 covered_end，也不更新普通请求的前缀快照
最近一次 input_claimed 是普通输入时恢复完整会话历史
task_wake_list 仍可显式查询全部任务
```

测试覆盖两个历史唤醒、当前唤醒、工具调用与结果、历史摘要排除，以及后续普通任务恢复完整历史。

## 4. 子智能体忙碌累计时长

状态：已完成。

实现：

```text
RunRegistry 从 claim 时记录 started_at，不新增持久化业务字段
InMemoryRunRegistry 与 FileRunRegistry 语义一致
插话续跑 renew(reset_started=False)，不重置当前连续忙碌段
新的普通任务轮次和目标轮次使用新的 started_at
create / list / result / status 返回 busy_since 和 busy_seconds
idle 时不返回 busy 时间字段
```

测试覆盖两类 registry 的保留/重置语义、插话不重置、新任务重置，以及忙碌与空闲生命周期响应。

## 5. 用量圆环改为上下文占用百分比

状态：已完成。

实现：

```text
圆环内部不再显示 usage-num 数字
圆环后显示 usage-pct：n%
百分比由当前 context_layout 的非 remaining 段计算并限制在 0..100
缺少布局数据时显示 0%，不会出现 NaN 或 undefined
深色、浅色主题均定义圆环与百分比颜色
```

## 6. 压缩摘要与最近轮次保留

状态：已完成。

实现：

```text
优先保留最近 full_user_rounds 个用户轮，值来自 [context] full_user_rounds
该宽度前没有可压轮次时逐级降低：n → n-1 → … → 1
最低保留 1 轮，单轮不压缩
摘要请求只包含系统/插件/旧摘要前缀和可压缩区间，不包含近期保留轮
压缩后上下文 = 单条新摘要 + 保留轮次原文
covered_end 只前移一次，连续压缩复用新摘要并从剩余视图重新切分
```

验收：

```text
配置值 5 时用带唯一标记的 8 轮消息，摘要请求只含前 3 轮，后 5 轮不进入请求
压缩后后 5 轮各出现一次，整份请求只有一条摘要检查点
总轮数不足以保留配置值时，从配置值逐级降到可用宽度
总轮数为 1 时不生成摘要，最近 1 轮保持原文
连续压缩两次时旧摘要进入新摘要请求，但已覆盖轮次和近期保留轮不重复累积
```

测试位于 `tests/test_compaction_retention.py`、`tests/test_context_assembly.py` 与
`tests/test_compaction_prefix.py`。

## 7. 后台任务完成通知改按插入消息处理

状态：已完成。

`BackgroundTaskManager` 在任务批次最后一次 settle 时生成一条 backlog 通知和稳定的 `notice_id`。通知处理器通过 `MeshState.submit_insert()` 在一个原子边界内完成消息入队和 `inserting` 标记，并提供相同 `notice_id` 的队列去重。

```text
会话忙碌：通知以 origin=system、delivery=next_pass 进入队列，保持 inserting
安全点：当前模型请求结束且当前工具批次收尾后，批量认领全部 inserting 消息
注入后：下一条模型请求看到全部通知，每条通知仍保留独立 input_claimed 事实
会话空闲：同一原子入口先持久化通知，再启动一个由队列驱动的运行回合
运行收尾：通知到达与运行位释放共用 MeshState 锁，迟到的通知由当前 runner 继续消费
```

通知不会中断已经发起的模型 HTTP 流，也不会插入正在流式输出的模型回复；它在安全点改变下一次模型请求的输入。新通知不应导致子智能体逐个通知回合向父会话连续自动汇报：

```text
只从最近一个 turn_started 之后读取当前任务轮次的模型输出
只有系统通知输入的回合不自动汇报父会话
普通任务轮次中途插入通知时，整个任务轮次仍只汇报一次
同一 turn_ended 回调重复触发或正文与主动汇报相同时不再重复投递
```

测试覆盖忙碌插入、空闲队列驱动、重复 notice_id 去重、runner 收尾竞态、通知元数据、纯通知回合不汇报，以及任务轮次内插入通知仍只汇报一次。截图验收使用隔离数据目录和临时 Web 端口，不触碰工程 `data/`。
