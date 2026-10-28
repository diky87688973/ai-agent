[English](cli-confirm-backlog.md) | **中文**

# CLI 两阶段确认 backlog

状态：未完成。

## 范围

`agent/shell/cli/interactive.py` 当前只处理写盘预览确认：

```text
write preview → _ask_confirm → gate.confirm(confirm_id) → commit_write
```

工具因 `user_confirm` 或 `approval_confirm` 发出 `tool_suspended` 时，CLI 只打印 `[工具等待确认]`，没有读取挂起信封和提交选择的入口。

## 需要补齐

```text
读取挂起信封
在终端展示 title / confirms / 审批选项
把用户选择写成原 call_id 的工具结果
启动续跑回合并清空 pending_confirm
```

## 验收

```text
user_confirm 首段挂起并记录 pending_confirm
CLI 接受选择并写成原调用的工具结果
下一回合收到选择，不伪造新的用户消息
取消、审批同意、审批驳回三条路径可用
不再通过隐藏的 confirm 参数直接调用工具
```
