---
name: visual-operator-2
description: 需要看屏幕、按模型可见图上的点移动鼠标、点击当前位置、聚焦观察或处理用户接管时使用。
---

# 视觉操作

涉及看屏、定位、移动鼠标、点击或用户接管时，先按本 Skill 执行。

## 1. 启动

1. 调用 `vision_request_open`。
2. 等用户在确认卡选择。
3. 用户同意后，用返回的 `consent_id` 调用 `vision_start`。
4. 没有 `consent_id` 不得调用 `vision_start`。

用户拒绝后不重复申请同一个请求。

视觉资源全局唯一，同一时间只属于一个会话。被其他会话占用时，等待 owner 闭眼，不要绕过。

## 2. 视觉帧

视觉启动后，每个模型请求的尾部自动带两张图：

```text
完整图：全屏画面，坐标基准
聚焦图：鼠标附近的放大观察
```

工具返回值不含图片。看到的是下一轮请求尾部的完整图和聚焦图，不是移动或点击工具的返回内容。

观察文字提供：

```text
frame_id
age_ms
cursor
cursor_in_focus
focus
screen_size
full_size
coordinate_space=model_image
image_size
scale_x
scale_y
focus_size
```

## 3. 坐标

完整图在服务端非等比拉伸成正方形，不填黑边。

模型只上报三组数：

```text
x、y：目标点在模型看到的图上的像素
width、height：模型看到的整张图宽高
image_width、image_height：原始截图宽高，取 original_image_size
```

工具换算：

```text
screen_x = screen_width / width * x
screen_y = screen_height / height * y
```

两个方向独立，不假设等比。

示例：

```text
屏幕：200×100
模型看到正方形：100×100
目标点：x=50, y=50

screen_x = 200 / 100 * 50 = 100
screen_y = 100 / 100 * 50 = 50
```

所以 `width`、`height` 永远是整张模型可见图，不是目标框的宽高。

## 4. 移动与点击

移动：

```text
vision_move_point(
  x=..., y=..., width=..., height=...,
  image_width=..., image_height=...
)
```

相对移动：

```text
vision_move(dx=..., dy=...)
```

点击当前位置：

```text
vision_click
```

`vision_click` 不接收坐标，支持点击次数和间隔：

```text
vision_click(count=2, interval_ms=72)
```

`interval_ms` 缺省 72，最小 72。

流程：

```text
看完整图 → 读目标点 x/y 和两张图的宽高
→ vision_move_point
→ 看新帧确认光标在目标上 → vision_click
```

移动后不立即盲点；确认新帧里的光标位置。

## 5. 聚焦

放大目标附近：

```text
vision_focus(region={"x":...,"y":...,"width":...,"height":...})
```

把光标放到聚焦区域中心：

```text
vision_focus(region={...}, center_cursor=true)
```

`region` 使用屏幕坐标区域，超出屏幕的部分会先裁剪。聚焦只影响第二张观察图，不改变完整图坐标。

## 6. 连续点击

多个已确认点一次完成：

```text
vision_click_sequence(
  points=[{"x":...,"y":...}, {"x":...,"y":...}],
  width=..., height=...,
  image_width=..., image_height=...,
  interval_ms=60,
  count=1
)
```

`interval_ms` 缺省 72，最小 72。

每个点的 x/y 都按与 `vision_move_point` 完全相同的双轴比例换算。每个新点用 200ms 轨迹滑过去，点完停 72ms；下一个点相同时不再移动，原地点击。

`width/height` 是模型看到的整张图尺寸；`image_width/image_height` 是原始截图尺寸。

连续点击结束后等待 `settle_ms=100` 再抓帧。移动鼠标后等待 `move_settle_ms=50` 立即抓帧。

目标布局会在点击后变化时，不拿旧帧的多个点继续点。

## 6. 点击后的观察

`vision_click` 会在 `settle_ms` 后抓一帧，并返回：

```text
observation_frame_id
observation_note
```

下一步请求尾部会出现点击后的完整图和聚焦图。点击后先看新帧，再决定下一次移动。

## 7. 用户接管

用户手动移动鼠标、点击或按键后，控制权立即归还用户：

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
不从聚焦图读坐标
不调用连续点击工具
不在没有当前视觉帧时移动或点击
```
