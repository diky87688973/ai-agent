# 项目复核接入

## 触发

- 按用户规则做项目核查
- 项目准入
- 项目复核
- 工程复核
- 交付前检查

## 执行

1. 检查上下文是否已有 `audit-procedure` 全文。
   - 已有：直接使用，不调用 `skills`。
   - 没有：执行 `skills action=read name=audit-procedure`。

2. 检查上下文是否已有 `production-standards` 全文。
   - 已有：直接使用，不调用 `skills`。
   - 没有：执行 `skills action=read name=production-standards`。

3. 读取项目自身声明的适用性申报。
4. 读取项目自身文档、配置、测试、CI。
5. 按 `audit-procedure` 执行。

读取失败时停止复核，标记 `BLOCKED`。

## 项目边界

- 项目适用性由项目自身声明，通用规则不写死路径
- `production-standards` 是独立标准，不复制进项目规则
- 复核流程、检查矩阵、证据规则、报告模板只由 `audit-procedure` 提供

## 输出

按 `audit-procedure` 的报告模板输出。

## 边界

默认只读。

只有同时明确要求修复时才写文件；修复前备份，修复后重跑受影响门禁。
