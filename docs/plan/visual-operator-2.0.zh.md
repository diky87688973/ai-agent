**中文**

# 视觉操作 2.0 预研与设计

## 0. 文档范围

本文覆盖视觉操作 2.0 的预研结论、能力边界、详细设计与验收标准。

2.0 是独立插件，不读取旧视觉插件的配置、工具或运行态，也不与其共享代码路径。

```text
输入：屏幕像素
输出：键盘、鼠标事件
```

插件不做应用级后台调用：

```text
不使用 UIA
不使用窗口控件树
不使用 OCR
不使用游戏内部接口
不使用 HTTP 业务接口
不使用 shell 命令驱动目标应用
```

屏幕采集和 HID 注入属于平台能力，不属于目标应用的业务后台。

## 1. 预研结论

验证环境：

```text
Windows
管理员权限
QQ 已登录
QQ 欢乐斗地主
一局完整对局
```

验证结果：

```text
截图可见
鼠标可移动、可点击
游戏可启动、可进入牌桌
一局可开始并结束
```

同时确认了四个约束：

| 约束 | 结果 |
|---|---|
| 图片输入 | DeepSeek 支持图片，但只允许放在 `user` 消息 |
| system 图片 | 返回 `400`，不能作为上下文尾部图片载体 |
| 单张截图校验 | 点击后立即取图会得到旧画面，不能作为动作成功依据 |
| 动作往返延迟 | 单次工具往返可跨越游戏倒计时，超时后游戏进入托管 |

预研中的对局最终胜利，但相当一部分出牌由游戏托管完成。这个结果不能作为 2.0 的操作验收，只说明：

```text
视觉和输入通道存在
按需截图 + 单次点击的链路不满足连续操作
模型决策延迟必须与视觉注入解耦
```

2.0 的验收对象是：

```text
持续视觉是否稳定
画面变化是否能注入模型
键鼠动作是否能形成连续操作
动作后的画面变化是否能被模型观察到
```

不是：

```text
能否赢游戏
能否绕过反作弊
能否替代游戏客户端
```

## 2. 目标与非目标

### 2.1 目标

```text
启用视觉会话后持续采集画面
保留最新帧和上一帧
按固定采样率向模型提供当前画面
每次观察提供完整帧和聚焦局部图
视觉资源全局唯一，同一时间只允许一个会话持有
其他会话申请睁眼时驳回，并提示眼睛正被其他会话使用
模型通过 vision_request_open 发起授权请求
用户通过固定文案确认后，vision_start 才能睁眼
模型可以自主闭眼
睁眼后持续注入，闭眼后停止注入
模型可以设置聚焦区域
键鼠动作与视觉采集相互独立
动作不触发截图
画面变化通过 SSE 推送到前端，不自动唤醒模型
模型通过完整图像坐标定位后点击
```

### 2.2 非目标

```text
不做 OCR
不做控件树定位
不做游戏专用策略
不做视频流逐帧入上下文
不做多帧历史图片长期保存
不做反作弊绕过
不做后台业务命令
```

游戏只作为压力和连续性验证环境。

## 3. 不变量

1. 模型只通过图片观察屏幕，不通过结构化控件或应用接口获取状态。
2. 模型只通过键盘、鼠标改变桌面。
3. 当前观察只在 `user` 消息中携带图片。
4. `system` 只承载静态规则，不携带图片。
5. 每次模型请求只携带最新帧生成的完整图与聚焦局部图，不携带历史截图。
6. 视觉采集独立于模型请求，模型空闲时画面仍持续更新。
7. 点击不产生截图，动作只返回动作回执。
8. 鼠标锚点使用截图时刻的坐标，不使用发送时刻的实时坐标。
9. 鼠标移动前恢复到观察帧记录的起点，再执行相对位移。
10. 不绑定动作到旧帧；当前只保留两帧。
11. 视觉模块不依赖旧视觉插件。
12. 输入使用真实 HID 事件；权限不足时明确失败，不自动提权。
13. 聚焦区域只控制第二张局部图，不替代完整图。
14. 鼠标不在聚焦区域内时，观察必须标记，不能静默裁掉鼠标位置。
15. `vision_request_open` 发起睁眼确认，确认文案由眼睛工具提供；模型不能写入标题、正文或选项。
16. `vision_start` 必须携带眼睛工具签发的一次性 `consent_id`；没有凭证不得睁眼。
17. `consent_id` 绑定会话、用途、请求与选项，只能消费一次；当前不做自动过期。
18. `vision_stop` 是闭眼，由模型自主调用，不需要用户确认；关闭后停止采集与注入。
19. 宿主不自动改变模型的眼睛状态；模型忙碌只丢弃变化通知，不关闭眼睛。
20. 眼睛关闭时禁止截图；关闭动作必须清空帧队列与待注入观察。
21. 注入前必须同时检查眼睛开关和队列；关闭或空队列不注入视觉帧。
22. 视觉资源全局唯一，采集、帧队列、眼睛状态与 owner 会话共用同一份实例。
23. 同一时间只允许一个 owner 会话；其他会话申请睁眼时驳回并提示占用会话。
24. 每个会话拼装观察时检查该会话是否持有当前视觉资源。
25. 插件拥有眼睛、队列、授权等可写状态；宿主不保存这些插件状态的副本。
26. 宿主提供上下文拼装钩子：输入完整上下文，返回新完整上下文；插件注册后由内核按序调用。
27. 宿主提供工具恢复钩子：插件确认端点通过内核恢复挂起调用，插件不直接写会话事实。
28. 已发出的模型请求不追回；闭眼后从下一次请求开始不再携带视觉帧。

## 4. 总体架构

```text
┌────────────────────────────────────────────────────────────┐
│ CaptureSource                                              │
│  5 FPS 定时采集 + 动作触发采集                             │
│  原始帧、鼠标位置、时间戳                                  │
└───────────────────────┬────────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────────┐
│ FrameRing                                                  │
│  最新帧 + 上一帧                                           │
│  最多 2 帧                                                 │
└───────────────┬───────────────────────────────┬────────────┘
                │                               │
                ▼                               ▼
┌──────────────────────────────┐   ┌──────────────────────────┐
│ DiffNotifier                 │   │ ObservationBuilder       │
│ 原始帧差异                   │   │ 完整帧 + 聚焦局部图      │
│ 变化区域                     │   │ 绘制鼠标锚点             │
│ 1 秒最多 1 次通知            │   │ 缩放、编码               │
│ 模型忙时丢弃                 │   │ 生成观察包               │
└──────────────┬───────────────┘   └────────────┬─────────────┘
               │                                │
               ▼                                ▼
┌──────────────────────────────┐   ┌──────────────────────────┐
│ SessionCoordinator           │   │ ContextAssemblyHook      │
│ 全局 owner 与会话独占        │   │ 完整上下文 → 新上下文    │
│ 单飞请求                     │   │ 尾部 user 双图           │
│ 变化推送 SSE                 │   │ 不写入历史               │
│ 不自动创建回合               │   │ 插件注册即调用           │
└──────────────┬───────────────┘   └────────────┬─────────────┘
               │                                │
               └──────────────┬─────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────┐
│ 模型                                                       │
│ 读取当前画面，输出鼠标/键盘动作                            │
└───────────────────────┬────────────────────────────────────┘
                        ▼
┌────────────────────────────────────────────────────────────┐
│ ActionExecutor                                             │
│ 输入锁、起点恢复、HID 注入、动作回执                       │
│ 不截图                                                     │
└───────────────────────┬────────────────────────────────────┘
                        │
                        ▼
                 CaptureSource 继续采集
```

组件职责：

| 组件 | 职责 | 不负责 |
|---|---|---|
| `CaptureSource` | 采集屏幕、记录截图时刻鼠标位置 | 图片入上下文、动作判断 |
| `FrameRing` | 保留新旧两帧 | 长期历史 |
| `DiffNotifier` | 原始帧差异、变化通知、忙时丢弃 | 修改画面、决定动作 |
| `FocusController` | 保存聚焦区域、判断鼠标是否在区域内 | 截图、缩放图片 |
| `ObservationBuilder` | 绘制锚点、生成完整图和聚焦局部图、缩放、编码、生成观察 JSON | 发送模型请求 |
| `ContextAssemblyHook` | 内核钩子：输入完整上下文，返回新完整上下文；插件注册后注入双图 | 保存截图、触发动作 |
| `ConsentResumeHook` | 内核钩子：插件确认端点恢复挂起调用、写回工具结果并续跑回合 | 保存插件眼睛/队列状态 |
| `ActionExecutor` | 完整图像坐标、绝对移动、点击、按键、回执 | 截图、语义判断 |
| `SessionCoordinator` | 全局视觉 owner、会话生命周期、单飞、停止 | 平台输入细节 |

### 4.1 全局视觉资源

采集、帧队列、眼睛状态和授权属于同一份全局资源：

```text
vision_resource
  owner_conversation_id
  eyes_open
  consent
  frame_queue
```

同一时间只允许一个会话持有：

```text
会话 A 持有
会话 B 请求 vision_start
  → 返回“眼睛正被其他会话使用”
  → B 不获得帧
```

只有 owner 会话能：

```text
设置聚焦区域
读取帧
拼装视觉观察
执行视觉动作
```

owner 闭眼后释放资源，其他会话才可重新申请。

### 4.2 内核钩子

上下文拼装钩子：

```text
context = assemble(messages, tools, ...)
for hook in registered_context_hooks:
    context = hook(context)
provider(context)
```

钩子输入完整上下文，返回新完整上下文。插件可以据此：

```text
注入完整图和聚焦局部图
修剪上下文
增加自定义压缩
```

内核保证：

```text
工具调用与工具结果的顺序
user / assistant / tool 角色合法
历史图片不累积
钩子按注册顺序执行
```

工具恢复钩子：

```text
插件确认端点
→ kernel.resume_suspended(call_id, result)
→ 内核写回 tool_result
→ 内核恢复回合
```

插件不直接写会话事实。

## 5. 视觉采集

### 5.1 采样率

默认：

```text
FPS = 5
定时间隔 = 200ms
```

动作触发截屏：

```text
每次鼠标或键盘动作完成后，立即请求一帧
动作帧不受下一次定时帧的 200ms 限制
动作帧之后，下一次定时帧从动作帧时间往后推 200ms
```

因此允许瞬时超过平均 5 FPS，不做严格 1 秒窗口限帧。

```text
平均目标：5 FPS
动作帧：可插入
动作帧后的下一次定时帧：+200ms
```

### 5.2 帧记录

每帧至少包含：

```json
{
  "frame_id": "f-000123",
  "captured_at": 123456.789,
  "screen": {"x": 0, "y": 0, "width": 1920, "height": 1080},
  "cursor": {"x": 940, "y": 450},
  "image": "raw-frame-reference"
}
```

鼠标位置在截图前后各读取一次：

```text
截图前 cursor_before
截图后 cursor_after
```

如果两次坐标不同，视为该帧鼠标位置不稳定：

```text
优先重新截图
无法重截时标记 cursor_stale=true
```

不把发送时刻的实时鼠标位置画到旧图上。

### 5.3 采集区域

支持：

```text
整个虚拟桌面
指定显示器
指定矩形
```

视觉操作 2.0 默认使用整个虚拟桌面，避免弹窗、菜单落在目标窗口外时漏采。多显示器场景保留每个显示器的坐标原点与 DPI 信息。

### 5.4 帧环

```text
容量：2
内容：current、previous
新帧入队时淘汰最旧帧
```

队列只服务当前观察和差异检测，不是历史录像。

### 5.5 动作触发采集

动作结束后请求一帧：

```text
mouse_down / mouse_up / click
key_down / key_up
组合键完成
```

动作帧用于让模型看到动作后的当前画面，不通过动作返回值携带图片。

## 6. 差异与通知

### 6.1 差异检测

使用原始帧比较，不使用已绘制鼠标锚点的图。

```text
previous_raw
current_raw
  → 计算变化比例
  → 计算变化包围盒
  → 与阈值比较
```

鼠标锚点不能参与差异检测，否则鼠标移动本身会持续触发变化通知。

### 6.2 变化通知

```text
变化比例 > 阈值
  → 生成变化通知
  → 最多每秒 1 次
  → 发送 vision_change SSE
  → 不创建模型回合
```

通知内容只包含变化摘要，不携带图片：

```json
{
  "type": "visual_change",
  "frame_id": "f-000123",
  "captured_at": 123456.789,
  "diff_ratio": 0.18,
  "rect": {"x": 800, "y": 300, "width": 400, "height": 200}
}
```

图片只通过尾部观察进入模型。

### 6.3 变化通知

```text
原始帧差异超过阈值
  → 发送 vision_change SSE
  → 不创建模型回合
  → 最新帧继续保留
```

变化通知只用于前端展示和诊断，不代替模型请求。

### 6.4 帧回显节流

只在真正组装模型请求时发送 `vision_frame`，不在 5 FPS 采集循环里发送。

同一帧只随一次模型请求回显；帧不写入会话历史。

## 7. 图像编码与鼠标锚点

### 7.1 处理顺序

```text
原始帧
  → 差异检测
  → 复制完整图
  → 按聚焦区域裁出局部图
  → 在完整图绘制鼠标锚点
  → 在局部图绘制鼠标锚点（鼠标在区域内时）
  → 缩放、编码
  → 两张图放入尾部观察
```

差异检测必须在绘制锚点之前。

### 7.2 完整图与聚焦局部图

每次观察固定提供两张图：

```text
完整图：整个采集区域的全景
聚焦局部图：聚焦区域的放大视图
```

完整图不因聚焦区域而裁剪。聚焦区域只决定第二张图的内容。

默认聚焦区域：

```text
以当前鼠标位置为中心
宽高取配置值
```

模型可以显式设置聚焦区域：

```text
区域坐标：屏幕坐标
区域最小尺寸：64×64
区域超出屏幕：裁剪到屏幕边界
```

聚焦区域持续生效，直到模型重新设置或停止会话。

如果鼠标不在聚焦区域内：

```text
观察字段 cursor_in_focus = false
完整图仍绘制鼠标锚点
局部图不绘制鼠标锚点
```

不得静默裁剪掉鼠标位置而不标记。

模型可以在设置聚焦区域时要求：

```text
center_cursor = true
```

执行器把鼠标移动到聚焦区域中心后再采集下一帧。

### 7.3 鼠标锚点

完整图和局部图都使用截图时刻的鼠标坐标。

要求：

```text
清晰可见
不遮挡目标内容
位置来自截图时刻
```

推荐绘制：

```text
细十字线
小圆环
中心点
半透明描边
```

不使用大面积实心指针。

局部图中鼠标不在聚焦区域时，不绘制局部锚点，只在完整图显示。

### 7.4 编码

完整图默认：

```text
最长边：1920
格式：WebP
质量：80
```

聚焦局部图默认：

```text
从原始帧裁剪
放大倍数：2
最长边：1280
格式：WebP
质量：80
```

可选：

```text
JPEG quality 80
PNG 无损
原图
```

不默认使用 GIF 255 色。GIF 对文字和按钮边缘不友好，且不保证体积更小。

特殊场景可配置原图：

```text
绘图
精细文字
小尺寸控件
```

### 7.5 体积与 token

图片字节数只影响传输和请求体大小。

视觉 token 由尺寸决定。DeepSeek 会把大图缩放到约 1300×1300，每张图片最多约 1024 tokens。

一次观察两张图，单次请求最多约 2048 个图片 tokens。

因此控制成本的主要手段是：

```text
每轮只带最新帧生成的两张图
不保留历史截图
控制完整图最长边
控制局部图放大倍数
```

## 8. 上下文注入

### 8.1 角色约束

DeepSeek 官方限制：

```text
图片仅支持 user 消息
system 或 assistant 消息携带图片返回 400
```

因此：

```text
system：静态执行模式、动作协议、停止规则
user：尾部当前观察 + 完整图 + 聚焦局部图
```

不使用 system 承载截图。

### 8.2 尾部观察结构

```json
{
  "type": "vision_observation",
  "frame_id": "f-000123",
  "captured_at": 123456.789,
  "age_ms": 42,
  "screen": {"x": 0, "y": 0, "width": 1920, "height": 1080},
  "cursor": {"x": 940, "y": 450},
  "cursor_stale": false,
  "cursor_in_focus": true,
  "focus": {
    "x": 720,
    "y": 300,
    "width": 440,
    "height": 300,
    "source": "model",
    "zoom": 2
  },
  "image_order": ["full", "focus"],
  "change": {
    "diff_ratio": 0.18,
    "rect": {"x": 800, "y": 300, "width": 400, "height": 200}
  },
  "recent_action": {
    "action_id": "act-001",
    "type": "mouse_move",
    "t_end": 123456.700
  }
}
```

`source` 为 `auto` 时表示聚焦区域以鼠标为中心自动生成；为 `model` 时表示模型通过 `vision_focus` 设置。

实际请求内容为：

```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "FULL FRAME\n<vision_observation>...</vision_observation>"},
    {
      "type": "image_url",
      "image_url": {
        "url": "data:image/webp;base64,...",
        "detail": "low"
      }
    },
    {"type": "text", "text": "FOCUS FRAME\ncursor_in_focus=true"},
    {
      "type": "image_url",
      "image_url": {
        "url": "data:image/webp;base64,...",
        "detail": "original"
      }
    }
  ]
}
```

完整图和局部图都使用 `user` 消息中的图片块，顺序固定为完整图在前、局部图在后。

`detail` 可按场景配置为 `low`、`high` 或 `original`。桌面文字和按钮较小时，`low` 的 512×512 处理可能丢失细节，需要用实际截图验证。局部图默认使用 `original`，完整图默认使用 `low`。

鼠标不在聚焦区域时：

```text
cursor_in_focus = false
文本明确写出“鼠标不在聚焦区域”
完整图仍有鼠标锚点
局部图没有鼠标锚点
```

### 8.3 只保留最新观察

```text
每次模型请求重新构造尾部观察
两张图都来自最新帧
不把上一帧图片继续追加到历史
不保存历史截图
```

如果宿主把尾部观察写成持久消息，必须提供清理策略：

```text
只保留最新 observation
旧 observation 从模型请求中排除
UI 可记录事件，但不回放历史图片
```

否则上下文会被图片 token 快速占满。

### 8.4 注入时序

```text
采集线程更新最新帧
模型请求即将组装
ContextAssemblyHook 取最新帧
读取 max_frame_age_ms
检查 age_ms
  age_ms <= max_frame_age_ms：直接使用
  age_ms > max_frame_age_ms：重新采集一帧
裁出完整图和聚焦局部图
绘制锚点、缩放、编码
追加尾部 user 观察（两张图）
发送模型请求
```

### 8.5 会话与变化

```text
vision_request_open（发起授权）
  → 固定确认卡片
  → 用户确认
  → consent_id

vision_start(consent_id)（睁眼）
  → 校验并消费授权
  → 启动采集并同步抓取首帧
  → 建立会话
  → 持续注入
  → 首个请求携带完整图和默认局部图

视觉变化
  → SSE 推送到前端展示
  → 不自动创建模型回合

模型动作
  → 下一轮请求自动携带最新帧生成的两张图

vision_stop（闭眼）
  → 停止采集
  → 停止注入
  → 清空队列与授权
```

没有独立的“看屏”工具。

睁眼必须先获得用户确认；闭眼由模型自主决定，不需要确认。宿主不会因为模型忙碌、画面无变化或动作完成而自动闭眼。

### 8.6 聚焦控制

模型通过动作 `vision_focus` 控制眼球聚焦区域。

```json
{
  "region": {"x": 640, "y": 320, "width": 640, "height": 360},
  "center_cursor": false
}
```

约束：

```text
region 使用屏幕坐标
region 最小 64×64
region 超出屏幕时裁剪
center_cursor=true 时把鼠标移到区域中心
center_cursor=false 时不移动鼠标
```

设置聚焦区域不触发截图工具；下一轮观察自动使用新的局部区域。

`vision_focus` 只改变第二张图的范围，完整图始终保留。

### 8.7 睁眼授权与二段确认

睁眼会持续采集屏幕，必须由用户明确授权。

`vision_start` 不能凭模型自己的判断打开。模型必须先发起睁眼确认请求，用户确认后由眼睛工具签发一次性 `consent_id`，再由 `vision_start` 校验并消费。

#### 授权文案由眼睛工具提供

确认框的标题和选项全部由插件提供：

```text
标题：申请视觉操作授权,视觉操作过程中会持续录屏
选项：同意 / 拒绝
```

模型不能传入、覆盖或改写这些字段。

#### 二段流程

```text
第一段：请求
  模型调用 vision_request_open
  → 插件创建 pending consent
  → 返回固定授权卡片
  → 会话挂起，等待用户作答

第二段：确认
  用户通过插件确认端口选择“同意”或“拒绝”
  → 插件校验 pending
  → 同意：签发 consent_id
  → 拒绝：不签发
  → 插件通过内核工具恢复钩子写回结果并恢复回合

第三段：开眼
  模型调用 vision_start(consent_id)
  → 插件校验 consent_id
  → 校验通过并消费
  → eyes_open = true
  → 启动采集
```

没有 `consent_id`：

```text
vision_start 拒绝
返回：请先发起睁眼确认
```

确认被拒绝：

```text
不签发 consent_id
vision_start 不可用
```

当前已有其他 owner 会话：

```text
vision_request_open 直接拒绝
返回：眼睛正被其他会话使用
不显示授权卡片
```

视觉资源释放后，其他会话才可重新发起申请。

#### 插件确认 HTTP 端口

插件通过 `ctx.add_route` 自己提供确认端点，不修改宿主确认端点：

```text
GET  /api/plugin/visual_operator_2/eye-consent/pending
GET  /api/plugin/visual_operator_2/eye-consent/status
POST /api/plugin/visual_operator_2/eye-consent/confirm
POST /api/plugin/visual_operator_2/eye-consent/revoke
```

`pending`：

```json
{
  "conversation_id": "cid",
  "request_id": "req_...",
  "title": "申请视觉操作授权,视觉操作过程中会持续录屏",
  "options": ["同意", "拒绝"]
}
```

`GET` 只返回插件保存的固定文案和当前待确认请求。

`status` 返回当前视觉资源状态：

```json
{
  "ok": true,
  "conversation_id": "cid",
  "owner_conversation_id": "cid",
  "eyes_open": true,
  "consent_valid": true
}
```

`confirm` 请求：

```json
{
  "conversation_id": "cid",
  "request_id": "req_...",
  "choice": "agree"
}
```

`choice` 只接受：

```text
agree
reject
```

服务端校验：

```text
request_id 存在
请求属于该 conversation_id
未消费
choice 合法
当前没有其他会话持有视觉资源
```

通过后：

```text
agree  → 签发 consent_id
reject → 不签发 consent_id
```

`revoke`：

```text
用户主动撤销视觉授权
→ eyes_open = false
→ 清空全局帧队列
→ 清空待注入观察
→ 作废所有 consent_id
→ 释放 owner 会话
```

`/api/plugin/` 端点需要管理员权限。插件端点仍然校验 `conversation_id` 与 pending 的绑定关系，并校验当前 owner。

插件端点不直接写会话事实。确认完成后通过内核工具恢复钩子提交：

```text
request_id
conversation_id
decision
consent_id
```

内核把结果写回挂起的 `vision_request_open` 调用并恢复回合。插件不导入 `agent.app` 或 `agent.entry`。

#### consent_id

`consent_id` 是不透明一次性凭证，内存保存：

```json
{
  "consent_id": "consent_...",
  "conversation_id": "cid",
  "purpose": "eye_open",
  "request_id": "req_...",
  "decision": "agree",
  "consumed": false
}
```

校验：

```text
consent_id 存在
未消费
conversation_id 匹配
purpose 为 eye_open
decision 为 agree
当前没有其他会话持有视觉资源
```

只有 `vision_start` 能消费这个凭证。

#### 为什么不能复用现有确认工具

现有 `user_confirm`：

```text
title 由模型提供
选项由模型提供
回执只是文本
```

现有 `approval_confirm`：

```text
option_id 由模型提供
option_desc 由模型提供
approval_id 记录 option_id，但当前没有消费方
```

两者都不能证明：

```text
用户同意的是眼睛工具
用户同意的是持续采集屏幕
用户同意的是当前会话
用户同意只生效一次
```

眼睛授权必须使用上面的专用确认请求和专用 `consent_id`。

#### 防止“看 A 同意 B”

```text
标题、选项由眼睛工具生成
模型只拿到 request_id / consent_id
consent_id 绑定 conversation_id、purpose、request_id
consent_id 单次消费
只有 vision_start 接受 eye_open 凭证
其他工具拒绝该凭证
当前 owner 会话独占视觉资源
```

用户确认的是固定文案，不是模型临时写的理由。

#### 采集与注入开关

全局视觉资源由插件持有：

```text
owner_conversation_id
eyes_open
consent_id
consent_consumed
frame_queue
focus_region
```

宿主不保存这些插件状态的副本，也不维护插件眼睛/队列缓存。

采集前：

```text
eyes_open = false → 不截图
consent 无效 → 不截图
当前会话不是 owner → 不截图
```

闭眼：

```text
vision_stop
→ eyes_open = false
→ 停止采集
→ 清空全局帧队列
→ 清空待注入观察
→ 作废 consent_id
→ 释放 owner_conversation_id
```

关闭与在途采集的竞态由 generation 处理：

```text
关闭时 generation++
旧 generation 的迟到帧直接丢弃
不得重新写入已清空的队列
```

拼接尾部视觉帧前：

```text
eyes_open = false → 不注入
当前会话不是 owner → 不注入
队列为空 → 不注入
```

不是注入空图，而是完全不注入视觉帧。

关闭时已经发出的模型请求不追回。闭眼后从下一次请求开始不再携带视觉帧。

进程重启后：

```text
眼睛默认关闭
授权状态不恢复
待确认请求不恢复
```

### 8.8 输入区睁眼状态按钮

眼睛打开时，在输入框左侧工具区增加一个“眼睛”按钮，位置在知识库按钮旁边。

按钮状态：

```text
眼睛关闭：隐藏
眼睛打开：显示
鼠标悬浮：显示“模型已睁眼”
点击：关闭眼睛
```

按钮只提供关闭，不提供打开。

```text
隐藏状态不可点击
点击只调用 revoke
按钮不触发 vision_request_open
按钮不签发 consent_id
按钮不能绕过用户确认
```

睁眼只有一条路径：

```text
vision_request_open
→ 用户确认
→ consent_id
→ vision_start(consent_id)
```

点击关闭不需要确认，直接调用插件撤销端点：

```text
POST /api/plugin/visual_operator_2/eye-consent/revoke
```

关闭成功后：

```text
按钮隐藏
eyes_open = false
帧队列清空
待注入观察清空
consent_id 作废
下一轮请求不注入视觉帧
```

关闭失败：

```text
按钮保持显示
保留眼睛状态
显示失败原因
不静默假装已关闭
```

按钮状态来源：

```text
GET /api/plugin/visual_operator_2/eye-consent/status
```

返回：

```json
{
  "ok": true,
  "conversation_id": "cid",
  "owner_conversation_id": "cid",
  "eyes_open": true,
  "consent_valid": true
}
```

前端实现约束：

```text
按钮由插件声明，输入区通过 pluginActions 渲染
按钮标识：data-plugin="visual_operator_2"，data-plugin-action="eye_toggle"
内核提供插件动作点击回调，插件不靠捕获阶段拦截默认行为
只有一个全局委托监听器，不为每次重渲染单独绑定
页面刷新时读取一次状态回显
不做轮询
后续状态由插件 SSE 事件驱动
```

状态事件：

```text
eye_opened
eye_closed
eye_denied
```

插件确认授权成功后推送 `eye_opened`，按钮立即显示；关闭成功后推送 `eye_closed`，按钮立即隐藏。

插件按钮声明依赖内核输入区动作契约扩展：

```text
ctx.add_action(
  "eye_toggle",
  label="眼睛",
  title="模型已睁眼",
  placement="after:knowledge:kb",
  click_url="/api/plugin/visual_operator_2/eye-consent/revoke",
  click_method="POST",
)
```

内核动作契约支持 `placement`、`click_url` 与 `click_method`；点击直接调用插件端点，不打开面板。

按钮默认隐藏，只有 `eyes_open=true` 且当前会话是 owner 时显示。

知识库按钮仍在原位；眼睛按钮紧跟其后。

### 8.9 视觉帧回显

每次真正组装模型请求时，插件把同一帧同步推送到前端：

```text
ContextAssemblyHook
  → observe()
  → publish vision_frame SSE
  → 同一帧追加到模型请求
```

只在模型请求时发布，不在 5 FPS 采集循环里发布。

事件载荷：

```json
{
  "conversation_id": "cid",
  "frame_id": "f-...",
  "source": "model_input",
  "age_ms": 120,
  "cursor": {"x": 1583, "y": 900},
  "cursor_in_focus": true,
  "screen_size": [1920, 1080],
  "full_size": [1920, 1080],
  "full_scale": 1.0,
  "coordinate_space": "screen",
  "grid": {"enabled": false, "step": 100, "unit": "screen"},
  "focus": {"x": 1343, "y": 740, "width": 480, "height": 320, "zoom": 2.0, "image_size": [960, 640]},
  "full_image": "data:image/webp;base64,...",
  "focus_image": "data:image/webp;base64,..."
}
```

前端用工具壳展示，默认只显示摘要：

```text
视觉帧  frame=f-...  age=120ms  cursor=(1583,900)  scale=1.50
```

展开后可看完整图和聚焦局部图缩略图；点击缩略图打开大图详情。帧不写入会话历史，刷新后不恢复。

## 9. 动作通道

### 9.1 动作原语

```text
vision_request_open
vision_start
vision_focus
vision_move
vision_move_point
vision_click
vision_key
vision_stop
```

动作只描述行为，不携带图片。

`vision_request_open` 发起睁眼确认；`vision_start` 对应睁眼，`vision_stop` 对应闭眼：

```text
vision_request_open：创建固定文案的授权请求，等待用户确认
vision_start(consent_id)：校验并消费一次性授权，打开眼睛，持续采集并注入
vision_stop：关闭眼睛，停止采集和注入，清理队列与授权
```

`vision_start` 必须带 `consent_id`：

```json
{
  "consent_id": "consent_..."
}
```

没有授权凭证时拒绝，并提示先发起 `vision_request_open`。

`vision_request_open` 不接受标题、正文或选项参数；这些由眼睛工具提供。

`vision_stop` 不需要用户确认。

`vision_focus` 只在眼睛打开时有效；闭眼状态下调用返回明确错误，不得静默改变状态。

### 9.2 `vision_focus`

```json
{
  "region": {"x": 640, "y": 320, "width": 640, "height": 360},
  "center_cursor": false
}
```

含义：

```text
设置聚焦区域
下一帧局部图按该区域裁剪
center_cursor=true 时把鼠标移到区域中心
```

执行器返回：

```json
{
  "action_id": "act-focus-001",
  "focus": {"x": 640, "y": 320, "width": 640, "height": 360},
  "cursor_before": {"x": 400, "y": 500},
  "cursor_after": {"x": 960, "y": 500},
  "centered": true,
  "t_end": 123456.700
}
```

`center_cursor=false` 时 `cursor_after` 等于 `cursor_before`。

聚焦动作会强制抓一帧，返回 `observation_frame_id`。

### 9.3 `vision_move_point` / `vision_click`

`vision_move_point` 接收模型看到的点，以及模型看到的整图尺寸和原始图像尺寸：

```json
{
  "x": 50, "y": 40,
  "width": 100, "height": 80,
  "image_width": 200, "image_height": 100
}
```

工具换算：

```text
screen_x = image_width / width * x
screen_y = image_height / height * y
```

两个方向独立，允许非等比拉伸。

`vision_click` 不接收坐标，只点击当前鼠标位置，一次只点一下。

流程：

```text
读模型看到的目标点 + 两张图宽高 → vision_move_point
→ 等下一帧确认光标 → vision_click
```

### 9.6 相对移动（兼容）

`vision_move` 保留相对位移：

```json
{
  "dx": 120,
  "dy": -40
}
```

相对位移以当前观察帧记录的鼠标位置为起点，先恢复到该起点再执行。精确点击使用 `vision_move_to` 或 `vision_click_at`，不要依赖相对位移累加。

### 9.7 `vision_click`（兼容）

当前鼠标位置点击：

```json
{
  "button": "left",
  "count": 1
}
```

不接收坐标。需要指定目标时使用 `vision_click_at`。

### 9.8 `vision_key`

```json
{
  "keys": ["ctrl", "c"]
}
```

键盘动作同样只返回回执，不返回图片。

### 9.9 不绑定帧

当前不做：

```text
action.frame_id
点击前比较旧帧
旧帧图像保留
```

原因：

```text
帧环只有 2 帧
模型返回时旧图通常已被淘汰
视觉确认由最新画面完成
```

动作只依赖：

```text
当前观察的鼠标起点
动作前后的光标位置
动作时间
```

### 9.10 输入锁

鼠标与键盘动作串行执行。

```text
同一时刻只允许一个动作
动作完成后才接受下一个
```

动作执行期间，视觉采集继续运行。

## 10. 会话编排

### 10.1 生命周期

```text
stopped
  → vision_request_open
consent_pending
  → 用户确认
  → consent_id
  → vision_start(consent_id)（睁眼）
active
  → vision_stop（闭眼）
stopped
```

眼睛状态由“用户授权 + 模型控制”共同决定：

```text
vision_request_open：发起固定文案的授权请求
vision_start(consent_id)：用户已授权后，由模型睁眼
vision_stop：模型闭眼，不需要确认
```

约束：

```text
vision_start 必须带 consent_id
没有 consent_id：拒绝并提示先发确认请求
重复 vision_start：幂等，不重复创建采集线程
重复 vision_stop：幂等，不报错
闭眼状态调用 vision_focus：返回明确错误
宿主不自动睁眼或闭眼
```

异常路径：

```text
采集失败
权限不足
输入失败
模型请求失败
用户撤销授权
宿主关闭会话
```

任一情况都必须进入明确状态，不静默停止采集。

### 10.2 单飞

同一会话同时最多一个模型请求。

```text
模型空闲
  → 只推送 vision_frame SSE
  → 不创建模型回合

模型忙碌
  → 变化通知丢弃
  → 当前请求结束后使用最新帧
  → 不改变眼睛状态
```

### 10.3 停止条件

```text
模型调用 vision_stop
用户调用 eye-consent/revoke
宿主关闭会话
采集连续失败
动作权限被撤销
```

停止后不再采集，不再推送视觉变化。

### 10.4 用户接管

```text
用户手动移动鼠标
用户手动点击
用户手动按键
  → 立即闭眼
  → 停止采集
  → 清空队列、授权、待确认请求
  → 设置 user_takeover
  → vision_request_open 之外的视觉工具全部拒绝
```

用户重新申请并确认授权后，才能再次睁眼。

模型自身注入的鼠标和键盘事件带 injected 标记，不触发接管。用户输入使用 Windows 低层鼠标/键盘钩子识别，不依赖应用窗口标题或焦点。

用户接管状态不自动过期；闭眼事件通过 SSE 通知前端，眼睛按钮立即隐藏。

### 10.5 点击后的观察帧

```text
采集线程：持续 5 FPS
vision_click_at / vision_click：
  点击完成 → 等待 settle_ms（默认 200ms）→ 强制抓取一帧 → 工具返回
vision_click_sequence：
  所有点点击完成 → 等待一次 settle_ms → 强制抓取一帧 → 工具返回
```

不为每个点单独截图。连续点击期间只保留最后一次动作后的新帧，下一次模型请求使用该帧。

### 10.6 AI 控制标签

```text
眼睛打开 → 屏幕正上方显示 [AI控制中]
用户接管 / 闭眼 / 插件关闭 → 标签隐藏
```

标签是置顶、点击穿透、不抢焦点的独立窗口，不写入会话历史。

用户接管时额外发送 `control_returned` SSE；前端显示仅标题的工具壳：

```text
已归还用户控制
```

该工具壳无摘要、无详情、不可展开。

## 11. 配置

```ini
[vision]
enabled = 1
fps = 5
queue_size = 2
notify_max_per_sec = 1
diff_threshold = 0.02
max_frame_age_ms = 100
cursor_mask = 1
capture_scope = screen
display = 0

[image]
format = webp
quality = 80
full_max_side = 1920
focus_zoom = 2
focus_max_side = 1280
grid = 0
grid_step = 100
full_detail = low
focus_detail = original
allow_raw = 0
max_bytes = 1048576

[action]
settle_ms = 200
max_move = 4096
input_lock_timeout_ms = 10000

[security]
require_elevated = 0
```

配置约束：

```text
fps > 0
queue_size = 2
notify_max_per_sec >= 1
max_frame_age_ms > 0
full_max_side 在 320 与 4096 之间
focus_max_side 在 320 与 4096 之间
grid 为 0 或 1
grid_step 在 20 与 500 之间
focus_zoom 在 1 与 4 之间
format 为 webp、jpeg、png
```

`require_elevated=0` 只表示不强制检查，不表示能以 Medium 权限操作所有目标。实际权限不足必须在动作或采集时返回明确错误。

`grid=1` 时完整图和聚焦图都叠加屏幕坐标辅助线：细线间距 `grid_step`，每条线都标屏幕坐标，主线用红色强调。刻度单位是屏幕坐标，和 `vision_click_at` 的坐标空间一致。关闭后两张图都不带辅助线。

## 11.1 辅助线

```text
grid = 0：完整图和聚焦图都不画辅助线
grid = 0：完整图和聚焦图绘制细线、主刻度与屏幕坐标数字
grid_step = 20~500：屏幕坐标下的细线间距
```

辅助线同时画在完整图和聚焦图上。辅助线不改变图片尺寸、不改变鼠标锚点、不改变动作坐标。

## 12. 失败模型

| 失败 | 行为 |
|---|---|
| 采集无权限 | 明确返回采集权限错误，会话不启动 |
| 图片被 provider 拒绝 | 检查角色，图片必须在 `user` |
| `system` 图片返回 400 | 不重试 system 图片，改为 user 观察 |
| 鼠标坐标不稳定 | 重截或标记 `cursor_stale`，不绘制错误锚点 |
| 鼠标不在聚焦区域 | 标记 `cursor_in_focus=false`，完整图仍显示锚点 |
| 聚焦区域非法 | 拒绝该动作；不得静默改成全屏 |
| 帧龄超过 max_frame_age_ms | 重新采集后再注入 |
| 模型忙碌时变化 | 丢弃通知，保留最新帧 |
| 输入锁超时 | 返回动作失败，不排队无限等待 |
| 目标窗口未前台 | 不投递输入，返回前台要求 |
| 反作弊拒绝输入 | 返回输入被拒绝，不尝试绕过 |
| 图片过大 | 按配置缩放或拒绝，不静默降级到错误尺寸 |

## 13. 观测指标

```text
capture_ms
encode_ms
send_ms
frame_age_ms
queue_depth
diff_ratio
notify_sent
notify_dropped
action_ms
image_bytes
image_tokens
full_image_bytes
focus_image_bytes
provider_image_errors
```

验收时记录：

```text
5 FPS 是否稳定
动作帧是否插入
队列是否始终不超过 2
模型忙时通知是否丢弃
最新帧是否仍然可注入
```

## 14. 模块边界

```text
plugins/visual_operator_2/
  plugin.py                 插件入口、工具/钩子/端点/按钮注册
  config.py                 配置解析与校验
  consent.py                固定授权文案与挂起异常
  state.py                  全局视觉资源、采集、队列、owner、接管、动作
  render.py                 缩放、屏幕坐标辅助线、鼠标标记与编码
  backend.py                Windows 截屏、输入注入、人类输入接管钩子
  tools.py                  视觉工具参数面
  routes.py                 eye-consent HTTP 端点
  ui/eye-toggle.js          输入区眼睛按钮的状态回显
  ui/vision-frame.js        视觉帧工具壳
  ui/click-test.html        点击精度测试页
  plugin-config.ini         插件配置
  plugin-meta.json          插件身份
```

宿主侧通过内核上下文钩子注入：

```text
SessionRunner
  → 请求组装
  → ContextAssemblyHook（插件注册）
  → 在尾部加入 user 观察
  → provider
```

内核保证上下文角色、工具调用顺序和历史图片清理；插件只返回新上下文，不保存宿主状态。

插件不导入 `agent.app` 或 `agent.entry`。

插件只暴露：

```text
会话控制
当前观察
动作
```

不暴露图片历史、截图工具或应用专用接口。

## 15. 测试与验收

### 15.1 单元测试

```text
5 FPS 定时器
vision_start 无 consent_id 被拒绝
vision_request_open 创建固定文案请求
用户同意后签发 consent_id
用户拒绝不签发 consent_id
consent_id 重复消费、跨会话使用被拒绝
视觉资源全局独占
其他会话申请睁眼被驳回
vision_start 睁眼后持续注入
vision_stop 闭眼后停止采集与注入
vision_stop 清空全局帧队列与授权
眼睛按钮只关闭不打开
眼睛按钮隐藏状态不可点击
眼睛按钮点击调用 revoke
闭眼时截图被禁止
闭眼或空队列时不注入视觉帧
重复 vision_start / vision_stop 幂等
模型忙碌不改变眼睛状态
动作帧插入与下一帧 200ms
两帧队列淘汰
差异阈值
鼠标区域遮罩
鼠标前后坐标不一致
帧龄阈值配置生效
图片缩放和编码
完整图与局部图双图输出
观察包字段
观察只保留最新帧
聚焦区域裁剪
鼠标在聚焦区域内/外标记
聚焦区域内重置鼠标中心
非法聚焦区域拒绝
动作回执不包含图片
起点恢复后的相对位移
输入串行
```

### 15.2 集成测试

```text
Windows 截图
鼠标移动
点击
键盘输入
管理员与 Medium 权限下行为
DeepSeek user 图片被接受
两张图片在同一 user 消息中被接受
system 图片返回 400
模型忙时通知丢弃
插件 eye-consent pending 端点
插件 eye-consent status 端点
插件 eye-consent confirm 端点
插件 eye-consent revoke 端点
眼睛按钮只关闭不打开
确认端点未授权或跨会话调用被拒绝
其他会话申请睁眼被驳回
眼睛按钮由 SSE 睁眼/闭眼事件更新
```

### 15.3 验收标准

```text
平均 5 FPS 采集
vision_start 无用户确认不可用
确认卡片标题和选项由眼睛工具提供
用户同意后签发一次性 consent_id
用户拒绝后无法睁眼
consent_id 重复使用被拒绝
全局视觉资源同一时间只有一个 owner 会话
其他会话申请睁眼被驳回并提示占用
vision_start 后持续注入
vision_stop 后不再注入
vision_stop 清空全局队列与授权
眼睛按钮只提供关闭，不提供打开
眼睛按钮悬停显示模型已睁眼
眼睛按钮刷新时回显一次，不轮询
SSE 睁眼/闭眼事件可更新按钮
闭眼状态截图被禁止
闭眼或空队列不注入视觉帧
模型忙碌只丢通知，不闭眼
动作后插入一帧
下一次定时帧在动作帧后 200ms
队列保持 2 帧
原始帧差异可触发通知
通知最多每秒 1 次
模型忙时通知丢弃但最新帧保留
max_frame_age_ms 可配置并生效
每次模型请求只带最新帧生成的两张图
完整图始终是全屏
局部图按聚焦区域裁剪
鼠标不在聚焦区域时 cursor_in_focus=false
聚焦区域内 center_cursor=true 时鼠标移到区域中心
图片只出现在 user 消息
system 消息不携带图片
点击动作不返回截图
鼠标锚点来自截图时刻
移动前恢复观察起点
动作回执包含 cursor_before / cursor_after
```

游戏对局只用于验证：

```text
画面持续更新
模型能看到变化
模型能移动鼠标并确认位置
模型能完成连续动作
```

不以胜负作为验收标准。

## 16. Skills 操作指引

模型睁眼流程：

```text
0. vision_request_open（眼睛工具提供固定文案）
1. 等待用户通过插件确认端口选择同意
2. vision_start(consent_id)（睁眼）
3. 等待尾部视觉观察（完整图 + 聚焦局部图）
4. 在完整图上确定目标大致区域
5. vision_focus(region, center_cursor=true) 把光标放到目标区域中心
6. 等待新的聚焦帧，确认光标标记
7. 读模型看到的目标点 x/y 和两张图宽高
8. vision_move_point，再 vision_click 点击当前位置
9. 通过下一帧视觉观察结果
10. 完成目标后 vision_stop（闭眼）
```

约束：

```text
不要调用看屏工具
不要使用 shell、UIA 或应用接口
不要在未拿到 consent_id 时调用 vision_start
不要伪造、复用或跨会话使用 consent_id
用户拒绝后不得继续尝试睁眼
不要在未看到鼠标锚点时盲点
完整图用于全局判断，局部图用于精细确认
鼠标不在聚焦区域时先看完整图，不要假设局部图里有鼠标
不要重复点击同一个无变化目标
不要在会话停止后继续发送动作
```

## 附录 A：DeepSeek 图片输入约束

官方文档：[图像理解](https://api-docs.deepseek.com/zh-cn/guides/vision/)

```text
模型：deepseek-flash
图片格式：JPEG、PNG、GIF、WebP
传入方式：Base64 data URL、外部 URL、Files API file_id
图片位置：仅 user 消息
system / assistant 图片：400
单张图片：最大 32 MiB
请求体：最大 48 MiB
单请求图片数：最多 600
图片边长：最长 8192 像素
自动缩放：约 1300×1300
每张图片：最多约 1024 tokens
detail=low：约 512×512
```

Anthropic 兼容端点使用 `image` 内容块，图片同样放在 `user` 消息。

## 附录 B：预研验证记录

| 项目 | 结果 |
|---|---|
| 管理员权限 | 可用 |
| 屏幕采集 | 可见 |
| 鼠标移动 | 可送达 |
| 鼠标点击 | 可送达 |
| 游戏大厅 | 可进入 |
| 牌桌 | 可进入 |
| 一局完成 | 是 |
| 对局结果 | 胜利 |
| 托管参与 | 是 |
| 连续视觉 | 未形成 |
| 动作后连续反馈 | 未形成 |

预研结论：

```text
视觉采集和 HID 输入不是瓶颈
按需截图、动作后同步截图、单次工具往返是瓶颈
2.0 需要常驻采集、请求时注入、独立动作通道
```

## 附录 C：动作与视觉的因果关系

```text
动作：act-001，t=100.100 ~ 100.180
帧：f-887，t=100.250，变化比例 0.18
帧：f-888，t=100.500，变化比例 0.42
```

模型看到的是：

```text
我在 100.100 发出动作
100.250 出现变化
100.500 变化扩大
```

而不是：

```text
点击工具返回一张点击后截图
```

因果关系由共享时间轴建立，不由动作工具的返回值建立。
