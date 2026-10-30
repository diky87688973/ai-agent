[English](visual-operator-2.0.md) | **中文**

# 视觉操作 2.0（`visual_operator_2` 插件）

视觉操作 2.0 为模型提供持续视觉上下文，并在授权后执行桌面输入。它与旧版 `visual_operator` 插件相互独立，旧插件保持禁用。内核负责把当前视觉帧注入模型上下文；工具负责显式聚焦、移动、点击和键盘动作。

## 职责边界

```text
内核：截图节奏、视觉帧注入、工具注册、上下文装配
插件：授权状态、帧、聚焦、鼠标键盘动作、SSE 事件
```

插件不通过 UIA、OCR、窗口控件树或 shell 命令驱动目标应用；这些能力属于下面的可选桌面工具。

## 授权生命周期

```text
vision_request_open -> 用户确认 -> vision_start -> 视觉工具
                                             |
                                             +-> vision_stop（闭眼）
```

- `vision_request_open` 发起授权请求，界面提示用户确认。
- `vision_start` 消费授权并睁眼；授权缺失、过期或重复使用时失败。
- `vision_stop` 闭眼，并清空帧、聚焦区域、授权和挂起请求。
- 用户接管（鼠标移动超过配置距离）会立即闭眼，并发出 `eye_closed` / `control_returned`。
- 眼睛关闭、会话不是当前持有者或用户已接管时，所有视觉动作都会被拒绝。

## 持续视觉帧

眼睛打开时，运行时按 `fps` 截图并保留最近 `queue_size` 帧。模型回合装配时注入当前帧；正常流程不需要额外调用“看屏”。

```ini
[vision]
fps = 3
queue_size = 2
focus_width = 512
focus_height = 512
focus_zoom = 1
settle_ms = 100
takeover_distance = 100
```

完整图按 `image_max_side` 缩放；模型读取的是实际注入图中的坐标。`vision_eye` 是独立工具：只截取一次窗口或区域，返回该图，不替代持续视觉帧。

## 坐标与校准

绝对定位工具接收模型图内坐标、模型图中心和原始尺寸：

```text
vision_move_point(x, y, center_x, center_y, image_width, image_height)
vision_click_sequence(points, center_x, center_y, image_width, image_height)
```

启用校准时，当前帧包含一个随机 `C1` 标记。绝对移动和连续点击必须传 `check_points`，其值是完整图中 `C1` 标记中心；运行时把标记映射到真实屏幕坐标，偏差超过 `calibration_tolerance_px` 直接失败。

`vision_focus` 和 `vision_move_focus` 是恢复路径，不要求 `check_points`。聚焦区域会裁到屏幕内，裁剪后至少 10×10；部分超出屏幕时裁剪，不补黑区。

## 工具

### 视觉核心

| 工具 | 作用 |
|---|---|
| `vision_request_open` | 申请用户授权 |
| `vision_start` | 用有效授权睁眼 |
| `vision_stop` | 闭眼并清空视觉状态 |
| `vision_focus` | 设置固定聚焦区域；下一帧附带 1:1 聚焦图 |
| `vision_move` | 相对移动鼠标 |
| `vision_move_point` | 带校准的绝对移动 |
| `vision_move_focus` | 在聚焦图内移动 |
| `vision_click` | 在当前光标位置点击 |
| `vision_click_sequence` | 带校准的多点移动与点击 |
| `vision_key` | 通过 Windows 输入后端发送按键或组合键 |

`vision_move_point` 和 `vision_click_sequence` 要求 `check_points`；`vision_focus` 和 `vision_move_focus` 不要求。

### 迁移的桌面工具

这些工具要求眼睛已打开，用于视觉本身无法完成的系统级动作。

| 工具 | 作用 |
|---|---|
| `vision_app` | 启动本地应用并等待窗口 |
| `vision_window` | 列出、激活、等待或读取窗口 |
| `vision_eye` | 单次窗口或区域截图 |
| `vision_type_into` | 向 UIA 控件或截图矩形输入文本 |
| `vision_keyboard` | 输入 Unicode 文本或单键；组合键用 `vision_key` |
| `vision_wait` | 等待画面变化或窗口事件 |
| `vision_find` | 按文字查找 UIA 控件 |
| `vision_click_text` | 点击 UIA 文字控件 |
| `vision_mouse` | 滚动或拖拽；移动和点击用视觉核心 |
| `vision_open` | 打开 URL、文件或协议 |

`vision_eye` 是独立看屏，不是持续视觉帧的替代。`vision_mouse` 只接受 `drag` / `scroll`；`vision_keyboard` 只接受 `type` / `key`，组合键用 `vision_key`；`vision_click_text` 只用于标准 UIA 控件，自绘界面走视觉链。

## 输入后端

2.0 核心后端目前只支持 Windows：

```text
截图：GDI / ImageGrab
鼠标：SetCursorPos / SendInput
键盘：SendInput，keybd_event 回退
```

按键注入返回结构化回执。`SendInput` 插入数量不足时回退 `keybd_event`；Alt+Tab 在回退后报告成功并带警告，Win 和 Ctrl+Esc 在当前环境中报告失败，因为系统 shell 不接受注入的系统热键。失败不会报告成成功。

迁移的桌面工具使用现有 `visual_operator` 桌面后端；2.0 核心不新增 macOS 输入或窗口/UIA 支持。

## 配置

`plugin-config.ini`：

```ini
[vision]
fps = 3
queue_size = 2
focus_width = 512
focus_height = 512
focus_zoom = 1
settle_ms = 100
takeover_distance = 100
move_settle_ms = 50
move_duration_ms = 200
calibration_enabled = 1
calibration_tolerance_px = 32

[image]
format = webp
quality = 80
square_size = 0
image_max_side = 1600
focus_max_side = 512
```

`calibration_enabled=0` 关闭 `C1` 生成和 `check_points` 校验。`calibration_tolerance_px` 是标记报告位置与真实映射点之间允许的最大偏差。

## 日志与事件

步骤日志为 JSONL，2 MB 轮转：

```text
data/logs/visual_operator_2.steps.log
```

每次调用记录 `tool_start`、`tool_done` 或 `tool_failed`，并记录 `key_inject` 与 `click_inject` 回执。前端监听 `eye_opened`、`eye_closed`、`control_returned` 和 `vision_frame`；眼睛按钮在闭眼时隐藏。

## 测试

`tests/test_visual_operator_2.py` 覆盖聚焦边界、10×10 最小值、无 `check_points` 的聚焦移动、授权、接管、鼠标/点击契约、按键回执、迁移工具授权和步骤日志路径解析。桌面工具使用旧后端；测试不移动真实光标，也不注入真实按键。

## 相关文档

- [plugins.zh.md](plugins.zh.md)：插件生命周期与扩展点
- [tools.zh.md](tools.zh.md)：工具注册与执行
- [visual-operator-2.0.md](visual-operator-2.0.md)：英文版
