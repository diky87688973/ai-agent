# 插件系统设计复核

## 1. 结论

```text
方向正确
7 个 P1 设计约束已补齐
可以进入实现
实现前先落契约测试
```

## 2. 复核范围

```text
插件系统总体架构
前端路径注册
后端路径注册
插口协议
设置契约
生命周期
资产归属
迁移方案
```

依据：

```text
docs/plan/plugin-system-ui-registry.zh.md
docs/plan/plugin-system-final-design.zh.md
docs/plan/plugin-system-migration.zh.md
agent/capabilities/plugin_context.py
agent/capabilities/plugins.py
agent/capabilities/settings_registry.py
agent/shell/settings_panel.py
plugins/web_ui/ui/classic/agent-ui.html
plugins/*/plugin.py
```

## 3. 已通过

```text
路径命名空间统一
插口协议决定可注册性
前端区域和后端能力分层
设置单路径
插件系统承担注册、分发、广播
宿主不识别插件业务
工具、上下文、提示词、事件、HTTP、模型都有路径归属
```

## 4. P1 问题

### P1-1 前端 extension 槽位（已关闭）

问题：

```text
允许前端注册 web-ui/<region>/extensions/<plugin>/<id>
但哪些区域声明 children=extension 没有最终表
```

风险：

```text
前端能登记路径，后端 catalog 没有对应父协议
动作无法分发
```

修正：

```text
在区域协议表明确 extension 槽位
未声明的区域一律拒绝
前端 extension 注册必须返回失败原因
```

### P1-2 路径 owner 与渲染器 owner（已关闭）

问题：

```text
web-ui/chat/messages/tools/<tool_name> 路径 owner 是 WEB-UI
工具专用渲染器可能来自工具插件
```

风险：

```text
一个字段同时表示路径归属和内容归属，生命周期清理会错
```

修正：

```text
path_owner        路径和插槽所有者
renderer_owner    渲染内容提供者
action_owner      动作处理者
```

三者在注册项中分别声明，插口协议决定是否允许分离。

### P1-3 基础设置依赖（已关闭）

问题：

```text
base_settings 通过 agent.shell.settings_panel 读写配置
```

风险：

```text
插件层直接依赖宿主实现
宿主设置存储变更会破坏插件
```

修正：

```text
插件系统暴露 HostSettingsPort
端口方法：
  read(section, key)
  write(section, key, value)
  apply()
基础设置插件只依赖端口
```

### P1-4 后端路径协议（已关闭）

问题：

```text
backend/* 列出了路径，但缺少 protocol_version、参数格式、handler 签名、冲突策略
```

修正：

```text
每个后端路径声明：
  path
  kind
  protocol_version
  handler signature
  owner
  priority
  dispose
```

### P1-5 设置事务（已关闭）

问题：

```text
多个 owner 的设置条目一次提交时，没有明确验证、提交、回滚顺序
```

修正：

```text
先全量 validate
→ 再逐 owner save
→ 任一失败调用已提交 owner 的 rollback
→ 返回逐项错误
```

### P1-6 Provider 契约（已关闭）

问题：

```text
backend/kernel/providers/* 没有接口定义、版本、默认 provider、失败回退
```

修正：

```text
ProviderSpec:
  port
  version
  factory
  priority
  replaces
  validate
```

约束：

```text
同 port 只能有一个 active provider
默认 provider 保留
失败回退默认
冲突显式报错
```

### P1-7 前端登记闭环（已关闭）

问题：

```text
前端注册 API 的行为、失败回滚、catalog 刷新没有定义完整
```

修正：

```text
POST /api/ui/register
  → 校验 manifest 白名单
  → 校验父插口协议
  → 校验 owner
  → 登记
  → 返回 catalog
失败：
  → 不写入 registry
  → 返回明确错误
卸载：
  → 按 owner 撤销全部前端 extension
```

## 5. P2 问题

```text
backend/events/publish 是动作，不是持久注册，不进入路径表
backend/runtime 是私有对象，不是公共扩展点
路径参数没有统一稳定标识规则
API catalog 和 action dispatch 的请求/响应 schema 需要补齐
UI 组件 props schema 需要补齐
旧 add_ui_item 需要定义退役期限
迁移测试需要覆盖卸载和重新启用
```

## 6. 架构判定

| 检查项 | 判定 |
|---|---|
| 宿主/插件系统/内核分层 | 通过 |
| 路径命名空间 | 通过 |
| 插口协议 | 有条件通过 |
| 前端注册 | 有条件通过 |
| 后端注册 | 有条件通过 |
| 设置归属 | 通过 |
| 生命周期 | 有条件通过 |
| Provider 替换 | 未完成 |
| 迁移可执行性 | 有条件通过 |

## 7. 必须补齐

```text
区域 extension 槽位表
path_owner / renderer_owner / action_owner
HostSettingsPort
后端路径协议版本和 handler 签名
设置事务 validate/commit/rollback
ProviderSpec 和默认回退
/api/ui/register、/api/ui/action、/api/ui/catalog
UI 组件 props schema
契约测试
```

## 8. 复核结论

```text
设计方向成立
P1 约束已在最终设计中补齐
可以拆分迁移阶段
P2 在实现阶段持续补齐
```
