---
name: visual-operator-2
description: 需要看屏幕、按模型可见图上的点移动鼠标、点击当前位置或处理用户接管时使用。
---

# 视觉操作

涉及看屏、定位、移动鼠标、点击或用户接管时，先按本 Skill 执行。

本 Skill 只负责视觉观察、取点和落点。窗口激活、打开应用、键盘切换、菜单、对话框和任务栏/托盘操作，先按 `windows-desktop-operations` 执行。

## 0. 操作流程

```text
1. 判断目标是否已经在前台
2. 不在前台：先激活窗口，不点窗口内容
3. 应用没打开：先通过开始菜单、搜索、运行框或任务栏打开
4. 需要菜单：先展开菜单，再读菜单项
5. 需要精确位置：看当前视觉帧，取目标中心
6. 移动 → 看新帧 → 点击 → 看新帧
7. 没有变化就停，不连续重复
```

视觉不是第一步。能用系统操作完成的前置动作，先用系统操作。移动或点击后必须看下一轮实时注入帧，用黄色光标标记确认是否覆盖目标；工具回执不代表成功。

### 0.1 视觉落点示例

```text
激活窗口
→ 看当前帧
→ 读目标左右上下边
→ 取中心 x/y
→ vision_move_point
→ 看新帧确认光标在目标内
→ vision_click
→ 看新帧确认结果
```

倒计时或布局会变化的场景，不沿用旧帧坐标。

## 1. 启动

1. 调用 `vision_request_open`。
2. 等用户在确认卡选择。
3. 用户同意后，用返回的 `consent_id` 调用 `vision_start`。
4. 拿到 `consent_id` 的当前回合必须立即调用 `vision_start`，不得再次让用户确认，不得先说话或重新申请。
5. 没有 `consent_id` 不得调用 `vision_start`。

用户拒绝后不重复申请同一个请求。

视觉资源全局唯一，同一时间只属于一个会话。被其他会话占用时，等待 owner 闭眼，不要绕过。

## 2. 视觉帧

视觉启动后，每个模型请求的尾部自动带图。

```text
注入内容：完整图；设置聚焦后追加聚焦图
完整图：全屏画面，最长边超过 1600 时按同一比例缩到最长边 1600，短边等比缩小，不填充黑区
聚焦图：固定屏幕区域，1:1 原生像素，不跟随光标，不填充黑区
默认不注入聚焦图，需要时用 vision_focus 设置
光标标记：画面上唯一一处黄色圆圈套十字，圆心即当前鼠标位置，不属于页面元素
```

黄色圆圈套十字是画面里唯一的光标标记，与 `cursor` 字段指向同一点。看到它就当鼠标位置读，不要当成待点击的目标。

聚焦图不是光标局部图，不会被鼠标移动改变；默认不注入，需要时用 `vision_focus` 设置任意固定区域，直到再次修改或闭眼。

取点时先把光标位置与目标分开：方块、按钮一律按自身边界取中点，不参照光标位置。

工具返回值不含图片。看到的是下一轮请求尾部的完整图，不是移动或点击工具的返回内容。

观察文字提供：

```text
frame_id
age_ms
cursor_model
image_center
original_image_size
compressed_image_size
coordinate_space=model_image
owner
focus_size
```

`original_image_size` 是屏幕尺寸，也是各点击工具 `image_width/image_height` 该取的值；`compressed_image_size` 是压缩后完整图的尺寸，也就是模型看到的那张图的真实宽高。两者不一致时，图上的 x/y 按模型看到的图读。

## 2.1 校准开关

```ini
[vision]
calibration_enabled = 1
calibration_tolerance_px = 32
```

关闭 `calibration_enabled` 后不再生成 C1，也不再检查 `check_points`。

## 2.2 聚焦区域

模型指定一个固定屏幕区域放大查看：

```text
vision_focus(
  x=..., y=...,
  width=..., height=...,
  center_x=..., center_y=...,
  image_width=..., image_height=...
)
```

区域坐标取模型图上的像素，工具用 `center_x/center_y` 对准屏幕中心后换算成屏幕区域。区域超出屏幕会裁剪，最小 10×10，不补黑区。以及聚焦不需要 check_points。

默认不注入聚焦图；调用 `vision_focus` 才设置区域。

```text
每帧带完整图 + 聚焦图
聚焦图保持同一屏幕区域
不跟随光标移动
再次 vision_focus 才更换
```

聚焦图是屏幕 1:1 截图，模型只读聚焦图上的 x/y，不自己换算屏幕坐标。

工具返回的 `scale` 是屏幕坐标与原图尺寸的比值对象，不是模型图的缩放系数；模型图宽高只看 `compressed_image_size`。

## 3. 坐标

完整图最长边超过 1600 时等比压缩到 1600，不填充黑区。

模型只上报图上的读数，不自己换算屏幕坐标：


```text
x、y：目标点在模型看到的图上的像素
center_x、center_y：模型看到的图像中心坐标
image_width、image_height：原始截图宽高，取 original_image_size
check_points：传 C1 随机标记中心的图内坐标
```

工具按模型图宽高和原始尺寸分别换算 screen_x/screen_y；模型只给图上的 x/y，不自己换算。
绝对定位移动和点击工具必须带 `check_points` 单个随机标记中心，工具按真实屏幕点做 32px 校验；缺失或偏差超限直接失败，要求重新读当前帧 C1。

`check_points` 始终从完整图的 C1 读取；聚焦内的移动不需要 check_points。

```text
scale_x = image_width / (2 * center_x)
scale_y = image_height / (2 * center_y)
screen_x = image_width / 2 + (x - center_x) * scale_x
screen_y = image_height / 2 + (y - center_y) * scale_y
```

两个方向独立，不假设等比。模型端把图片拉伸成任意尺寸也不影响落点。

换算只认你给的四个数字：`image_width/image_height` 与 `center_x/center_y`。`image_width/image_height` 给错，落点就按错的比例偏，它必须等于当前帧的 `original_image_size`。

示例：

```text
屏幕：200×100
模型看到的图中心：center_x=50, center_y=50
目标点：x=50, y=50

screen_x = 200 / 2 + (50 - 50) * 200 / (2 * 50) = 100
screen_y = 100 / 2 + (50 - 50) * 100 / (2 * 50) = 50
```

所以 `center_x`、`center_y` 是模型看到的图像中心，不是目标点。

### 3.1 取点

公式只负责换算，不负责找点。x、y 靠目测当前帧取，取偏了公式再对也点不中。

```text
以当前帧为准：center_x/center_y 与 x、y 取自同一帧
原图尺寸不变：image_width/image_height 取 original_image_size，不随帧改
落在几何中心：矩形取两对边中点连线的交点，圆取圆心
先定边再取中：读出目标的左、右、上、下边像素位，取其平均，不凭感觉瞄
小目标放大看：用 vision_focus 设固定区域，再在聚焦图里读边；读不准就不点
不用旧帧的数：画面刷新、滚动、布局变化后，旧坐标全部作废
取完自检：x 落在左右边之间且接近中点，y 落在上下边之间且接近中点
```

取点误差与目标尺寸的关系：

```text
目标边长 100px，偏 10px → 仍在目标内
目标边长 30px，偏 10px → 落到目标外，算误点
```

连续点击前逐个点按上述自检过一遍再提交；任一不确定，先单点该目标确认，再继续其余点。

## 4. 移动与点击

移动：

```text
vision_move_point(
  x=..., y=...,
  center_x=..., center_y=...,
  image_width=..., image_height=...
)
```

`center_x/center_y` 必填，缺任一个工具直接报错；没有 `width/height` 入参。

按聚焦图移动：

```text
vision_move_focus(
  x=..., y=...,
  width=..., height=...
)
```

`x/y` 是聚焦图上的像素，`width/height` 是模型看到的聚焦图宽高。工具按当前固定聚焦区域换算屏幕坐标，不需要 center_x/center_y。

相对移动：

```text
vision_move(dx=..., dy=...)
```

点击当前位置：

```text
vision_click
```

`vision_click` 不接受坐标，支持点击次数和间隔：

```text
vision_click(count=2, interval_ms=72)
```

`interval_ms` 缺省 72，最小 72。它没有坐标入参，因此不传 center_x/center_y。

流程：

```text
看完整图 → 读目标点 x/y 和原图宽高 → vision_move_point
→ 看新帧确认光标在目标上 → vision_click
```

移动后不立即盲点；确认新帧里的光标位置。

移动类工具返回的 `observation_note` 写的是“完整图和聚焦图”；设置聚焦区域后，下一帧确实会带这两张图。

## 5. 多次点击

多个已确认点一次完成：

```text
vision_click_sequence(
  points=[{"x":...,"y":...}, {"x":...,"y":...}],
  center_x=..., center_y=...,
  image_width=..., image_height=...,
  interval_ms=72,
  count=1
)
```

`interval_ms` 缺省 72，最小 72。`center_x/center_y` 必填，缺任一个工具报 KeyError。

`count` 是每个点的点击次数，取值 1~3；`vision_click` 的 `count` 是 1~10，两者不通用。

每个点的 x/y 都按与 `vision_move_point` 完全相同的双轴比例换算。光标移动耗时由 `move_duration_ms` 决定（配置值 200ms）；点完停 `interval_ms`；下一个点与上一个相同时不再移动，原地点点击。

`center_x/center_y` 是模型看到的图像中心；`image_width/image_height` 是原始截图尺寸。

移动类动作结束后等 `move_settle_ms`（配置值 50ms）再抓帧；点击类动作结束后等 `settle_ms`（配置值 100ms）再抓帧。两者都以配置为准。

目标布局会在点击后变化时，不拿旧帧的多个点继续点。

## 6. 点击后的观察

`vision_click` 与 `vision_click_sequence` 都会在动作后抓一帧，并返回：

```text
observation_frame_id
observation_note
```

下一次请求尾部会出现点击后的完整图。点击后先看新帧，再决定下一次移动。

本插件注册 `vision_request_open`、`vision_start`、`vision_focus`、`vision_move`、`vision_move_point`、`vision_move_focus`、`vision_click`、`vision_click_sequence`、`vision_key`、`vision_stop`。

## 7. 用户接管

以下任一种人类输入都会让控制权归还用户：

```text
鼠标累计移动达到 100px（阈值取配置 takeover_distance）
按下鼠标（非注入事件）
按下任意按键（非注入事件）
```

本进程注入的鼠标键盘事件会被识别并排除，不算人类输入。接管后：

```text
视觉关闭
帧队列清空
观察帧不再注入
[AI控制中] 标签隐藏
前端出现“已归还用户控制”
```

接管后除 `vision_request_open` 外，所有视觉工具都会被拒绝。必须重新申请授权，不复用旧的 `consent_id`。

主动闭眼：

```text
vision_stop
```

## 8. 失败处理

```text
没有 consent_id
  → 先 vision_request_open

用户拒绝
  → 停止申请，等待用户下一步

眼睛被其他会话占用
  → 等待 owner 闭眼

没有当前帧
  → 不移动、不点击，先重新观察

光标不在目标上
  → 重新读完整图，再移动

用户接管
  → 停止视觉动作，重新申请
```

## 9. 禁止

```text
不使用 shell、python、UIA 或应用接口代替视觉操作
不伪造、复用或跨会话使用 consent_id
不在眼睛关闭或用户接管后操作
不按页面布局猜坐标
不凭印象报点：未在当前帧读出目标边界就报 x、y
不把上一帧的坐标用到刷新后的画面
不调用连续点击工具做未确认的目标
不在没有当前视觉帧时移动或点击
```
