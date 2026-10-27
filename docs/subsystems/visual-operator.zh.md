[English](visual-operator.md) | **中文**

# Visual Operator（`visual_operator` 插件）

Visual Operator 把看屏幕与操作鼠标键盘做成四个工具，交给模型在真实桌面上读图、定位、点击、输入与等待。截图作为图片附件交给模型；插件只保存坐标映射元数据，不保留截图文件。鼠标与键盘输入动作经输入锁串行投递。插件机制本身见 [plugins.md](plugins.md)。

## 包结构

```
plugins/visual_operator/
  plugin.py                  入口：读配置、选后端、注册四个工具
  plugin-config.ini          装载时读取的配置
  plugin-meta.json           身份元数据
  config.py                  [config] 读取、回退与夹取
  capture_store.py           截图映射登记（只存元数据，不存图片）
  keys.py                    键名规范、别名与组合键校验
  coords.py                  屏幕矩形 / 点 / 几何比例
  ports.py                   后端端口与数据结构
  canvas.py                  缩放、坐标网格、光标十字、PNG 编码
  diff.py                    动作前后的区域差异比较
  guard.py                   Plan 模式门控
  input_lock.py              鼠标与键盘共用的输入锁
  errors.py                  异常层级
  tools/
    _params.py               参数读取与动作矩阵
    _windows.py              window / hwnd 解析、候选清单与前置激活
    _capture.py              取图、加工、回执与提示文案的唯一实现
    eye.py                   desktop_eye
    mouse.py                 desktop_mouse
    keyboard.py              desktop_keyboard
    wait.py                  desktop_wait
  backends/
    __init__.py              按平台选择后端
    win32.py                 Windows：GDI + SendInput + 落点探测
    macos.py                 macOS：screencapture + CoreGraphics
    _unavailable.py          其它平台：调用时报明确原因
```

## 四个工具

| 工具 | 方向 | 能力 |
|---|---|---|
| `desktop_eye` | 交给模型 | 截取整屏、区域或窗口，叠坐标网格后作为图片附件返回；可带 `hover` 在取图前展开悬停控件 |
| `desktop_mouse` | 作用于桌面 | `move` / `click` / `drag` / `scroll` / `cursor` |
| `desktop_keyboard` | 作用于桌面 | `type` 任意 Unicode 文本 / `key` 单键 / `hotkey` 组合键 |
| `desktop_wait` | 等待条件 | 等画面变化、窗口出现或窗口消失，命中即返回 |

四个工具各自声明完整的 JSON Schema，不共用一个多动作大工具。动作与参数的对应关系由 `tools/_params.py` 的动作矩阵校验：属于别的动作的参数直接报错，不会被静默忽略。

### `desktop_eye`

| 参数 | 说明 |
|---|---|
| `x` / `y` / `width` / `height` | 区域，四个一起给，宽高必须为正；四个都省略则截整屏。区域裁到屏幕内（给了窗口时再裁到窗口内），完全落在屏外报错 |
| `window` / `hwnd` | 取该窗口自身内容；二选一，`hwnd` 是正整数且更精确。由 Windows 后端实现 |
| `activate` | 取图前是否置前，默认 `false`：只恢复最小化窗口，不改变前台。仅对 `window` / `hwnd` 有效 |
| `hover` | `[x, y]` 屏幕坐标：取图前把光标移到这里，用来展开控制条、下拉菜单、提示气泡 |
| `hover_path` | `[[x, y], ...]`：到 `hover` 之前先经过的中间点，1–4 个；必须与 `hover` 一起给 |
| `hover_settle_ms` | 移完光标等界面展开的毫秒数，`0–5000`；缺省取配置 |
| `hover_approach_ms` | 移到落点用多少毫秒，`0–2000`，默认 120；`0` = 一次跳变 |
| `hover_wiggle` | 到达后是否在落点附近做几次 1–2px 微移动，默认 `true` |
| `grid` | 是否叠网格与刻度，默认 `true` |
| `grid_step` | 网格间距（屏幕坐标），`20–500`；缺省取配置。点小目标时可调到 20–40 |
| `grid_unit` | 刻度单位：`screen` 屏幕坐标（默认）/ `image` 图内像素 |
| `max_side` | 长边上限，`0–8192`；`0` 不缩放；缺省取配置 |
| `annotate` | `annotated` 只回标注图（默认）/ `raw` 只回原图 / `both` 先回标注图再回原图；回执 `attachment_order` 标明顺序 |

窗口原本最小化时，取图前会先恢复，并在回执里标 `restored`。

`hover` 是「移光标 + 截图」能成立的前提：悬停控件通常在 2–3 秒内自动收起，而两次工具调用之间隔着一次模型往返，耗时更长。窗口取图时，移光标发生在窗口恢复或置前之后、真正取图之前；顺序反了，拍到的要么是没展开的画面，要么是别的窗口上的展开。移光标会改变桌面状态，因此 Plan 模式拒绝带 `hover` 的 `desktop_eye` 调用；不带 `hover` 的取图仍可用。

移动不是一次瞬移：先走完 `hover_path` 的中间点，再用 `hover_approach_ms` 连续移到落点，最后在 1–2px 内来回几次。播放器与网页的自动隐藏控件靠连续的 `WM_MOUSEMOVE` 判断鼠标在动；一次 `SetCursorPos` 后静止会被当成没动。轨迹与微移动都是真实的光标移动，不是只改回执里的数字。微动结束后会读回真实光标并收回落点；如果目标窗口把光标抢偏且回不去，调用报 `DesktopError`，不会把偏移后的位置当成落点。

回执的 `hover.hit` 给出光标下的窗口。它与这次取图的窗口不是同一个时，`note` 会直接点明：播放器画面常是独立顶层窗口，而按标题命中的往往是承载详情页的另一个窗口。此时改 `y` 坐标不能改变目标，需用 `hwnd` 指定光标那一层。

不带 `window` / `hwnd` 且不带区域而带 `hover` 时，取图目标就是光标那一层窗口（回执 `window.auto="hover.hit"`）：取窗口自身像素、无遮挡；`max_side` 仍会生效。这种 hover 取图不给这些参数时只取光标那一层窗口；要截整屏或指定窗口，需显式给区域或窗口。

返回值（`data`）：

```json
{
  "platform": "win32",
  "screen": {"x": 0, "y": 0, "width": 2560, "height": 1440},
  "capture": {"x": 0, "y": 0, "width": 2560, "height": 1440},
  "source": "screen",
  "annotate": "annotated",
  "image": {"width": 2560, "height": 1440, "sent_width": 1920, "sent_height": 1080,
            "scale": 1.3333, "bytes": 548735},
  "image_to_screen": {"scale_x": 1.3333, "scale_y": 1.3333, "ox": 0, "oy": 0},
  "capture_id": "a1b2c3d4e5f6",
  "dpi": "96 dpi",
  "cursor": {"x": 734, "y": 709},
  "grid": {"step": 100, "unit": "screen", "scale": 1.3333},
  "note": "图片已从 2560x1440 缩到 1920x1080；…"
}
```

图片经 `ToolResult.attach` 作为 `image/png` 附件返回。附件走结果信封的独立字段，不并入 `data`，也不保留临时文件。`annotate=both` 时返回两个附件，顺序由 `attachment_order` 标明：`["annotated", "raw"]`；`raw_image` 给出原图的尺寸信息。

`capture_id` 是**内存映射的键**，不是文件路径：登记表只保存 `capture` 矩形、图片宽高、hwnd 与创建时间，不保存 PNG。默认 TTL 300 秒、每个插件实例最多 64 条；服务重启或条目淘汰后旧 ID 失效，需要重新截图。`image_to_screen` 是同一份映射的可读形式，给排障和前端展示用；换算由服务端完成，模型不需要拿它做乘法。

`grid_unit=image` 时刻度与光标标签是图内像素；默认 `screen` 保持屏幕坐标，`hover`、区域参数和 `desktop_wait` 的区域仍使用屏幕坐标。要用图内坐标点击，先用图内像素网格取图，再把 `capture_id` 与图内 x/y 交给 `desktop_mouse`。

单张截图上限定为 4000 万像素；超过时在调用侧报错，并提示改用区域参数。

### 同名窗口

Windows 上 `window` 给的是不区分大小写的标题片段，同名窗口可能同时存在（自绘窗口常见：主窗 + 播放层 + 隐藏辅助窗）。候选排序是前台 → Z 序 → 面积（大到小），不是单纯的面积：用户眼前那个窗口几乎总是要操作的那个，面积最大的反而可能是盖在画面上的播放层。

命中数大于 1 时，回执里的 `window` 会带 `matched` 与 `alternatives`（最多 4 个），`note` 也会写清有 N 个、选了哪个、其余 hwnd 是哪些。只给命中数不足以区分其余窗口，因此回执列出它们的 hwnd。

### 缩放与换算

整屏图通常会被缩到 `max_side`，窗口图往往不到上限、按原尺寸发送。截图的图内坐标与屏幕坐标可能缩放，也可能带负原点（窗口阴影）。

`desktop_mouse` 接受 `capture_id` + 图内 x/y 时，用登记表里的 `capture` 与图片宽高换算，模型不做乘法：

```
screen_x = capture.x + image_x * capture.width / image.width
screen_y = capture.y + image_y * capture.height / image.height
```

`space=image` 显式声明图内坐标；只给 `capture_id` 时也按图内解释。`space=screen`（默认）仍接受屏幕坐标；两种空间不混用。ID 不存在、过期或不属于当前会话时直接报错，不退回屏幕坐标。

细节看不清时用区域参数取局部：局部通常按原尺寸发送。点小目标时给 `grid_step=20–40`：网格更细，坐标可以直接读，不必在 100px 的格子里估。

### `desktop_mouse`

| `action` | 必填 | 可选 |
|---|---|---|
| `move` | `x`、`y` | `duration_ms`（0–5000，默认 0） |
| `click` | — | `x`、`y`、`button`（left / right / middle）、`count`（1–3） |
| `drag` | `x`、`y`、`to_x`、`to_y` | `button`、`duration_ms`（默认 300，0–5000） |
| `scroll` | `amount`（-50–50，不能为 0，正数向下 / 向右） | `x`、`y`、`horizontal` |
| `cursor` | — | — |

所有动作都接受 `window` / `hwnd`；`cursor` 以外的动作会先恢复目标窗口并置前，再执行动作，置前失败时不落点、直接报错，避免点到遮挡物。`cursor` 不发送输入，因此不激活窗口。

`x` / `y` / `to_x` / `to_y` 默认是屏幕坐标。给 `capture_id` 时按该截图内的像素坐标解释；再加 `space=image` 更明确。`space=screen` 不接受 `capture_id`，避免同一组数字被两套坐标系重复解释。图内坐标必须给点且落在图片内，不回退到当前光标位置。

`click` / `scroll` 省略坐标时作用在当前光标位置。动作完成后返回光标位置与屏幕矩形；`cursor` 只读，不触发模式门控。

改变界面的动作（`click` / `drag` / `scroll`）额外回执三份证据：

| 字段 | 含义 |
|---|---|
| `hit` | 落点所在的窗口句柄、控件类名与所属顶层窗口标题；后端不支持探测时省略 |
| `changed` / `changed_scope` | 落点周围最多 200×200 的区域差异比例（0–1，三位小数），裁到屏幕内；`scope` 固定为 `point_200`；只说明落点附近有没有变化 |
| `window_changed` | 窗口层对比：`hit_before` / `hit_after`、`opened` / `closed`、`changed`、`navigated` |

`hit` 回答「打中了什么」，`changed` 回答「落点附近有没有响应」。跳转类点击（卡片 → 详情页、打开新窗口）的变化发生在窗口层：`changed` 可能仍是 `0.0`，此时 `window_changed.navigated=true` 表示发生了跳转。`changed` 首次采样低于 0.005 时会再等 250ms 复采一次，结果放在 `changed_late`；如果后采值更大，`changed` 取后采值并附 `changed_note`。

`window_changed` 只在动作前后窗口集合确实变化时带 `opened` / `closed`（各最多 3 条，更多用 `opened_more` / `closed_more` 计数）；窗口清单读取失败只跳过这项观测，不会把已经投递的动作改判为失败。

`shot=true` 在动作完成后于同一次调用内截图并返回图片附件，省掉「再调一次 `desktop_eye`」的往返：

| 参数 | 说明 |
|---|---|
| `shot` | 是否随动作回图，默认 `false` |
| `shot_region` | `[x, y, width, height]`；省略则取落点所在窗口或整屏；裁到取图目标内 |
| `shot_max_side` | 回图的长边上限；缺省取配置 |

带 `shot` 时返回体是取图回执，动作本身的结果收在 `performed` 字段。回图默认跟着落点实际所在的窗口走（`shot_of: "hit"`），而不是按 `window` 标题重新解析：点击可能落在独立顶层窗口上，按标题取到的却是承载详情页的另一个窗口。显式给了 `window` / `hwnd` 时以显式参数为准（`shot_of: "window"` / `"hwnd"`）；两者都没有且拿不到落点窗口时，回退为屏幕截图（可带 `shot_region`）。落点窗口与置前窗口不是同一个时，`note` 会写明两者 hwnd。`shot` 对 `move` / `click` / `drag` / `scroll` 开放；`cursor` 是只读查询，不接受它。`move` 只回图，不做 `hit` / `changed` 比较——移动本身不改变界面，但悬停可能展开控件，所以回图仍有意义。

### `desktop_keyboard`

| `action` | 参数 |
|---|---|
| `type` | `text`（任意 Unicode，含换行与制表符；换行发送为 Enter，制表符发送为 Tab） |
| `key` | `key`、`repeat`（1–20） |
| `hotkey` | `keys`（`"ctrl+c"` / `"alt+tab"`）、`repeat`（1–20） |

所有动作还接受 `window` / `hwnd`：先恢复并置前目标窗口，再输入，回执带 `focus`；置前失败时不会输入，直接报错，避免字落进别的窗口。`shot` / `shot_max_side` 在动作后回图。

键名先归一成规范名：`return` → `enter`，`escape` → `esc`，`control` → `ctrl`，`option` → `alt`，`command` / `meta` / `super` → `cmd`，`windows` → `win`，`pgup` / `page_up` → `pageup`，`pgdn` / `page_down` → `pagedown`；方向键、`f1`–`f20`、字母、数字，以及 `-`、`=`、`[`、`]`、`;`、`'`、`,`、`.`、`/`、`\` 与反引号等单字符键。`hotkey` 接受 2–4 个键，至少包含一个非修饰键，分隔符为 `+` 或 `,`。

### `desktop_wait`

| 参数 | 说明 |
|---|---|
| `until` | `change` 画面变化 / `window_appears` 窗口出现 / `window_disappears` 窗口消失 |
| `window` / `hwnd` | `change` 时用来限定比较区域；`window_appears` / `window_disappears` 只接受 `window`（必填），`hwnd` 不适用 |
| `x` / `y` / `width` / `height` | `change` 的比较区域；四个一起给，宽高为正。省略则用窗口矩形或整屏。显式区域优先于窗口矩形 |
| `timeout_ms` | 最长等待，`50–60000`，默认 10000 |
| `interval_ms` | 轮询间隔，`50–2000`；缺省取配置 |
| `threshold` | `change` 的判定阈值 `0–1`，默认 `0.02` |

超时不是错误：返回 `satisfied: false` 与该回合的读数，由模型决定换动作还是延长等待。固定秒数的休眠把等待押在猜测上；条件等待在条件满足时立即返回。

`until=change` 用屏幕合成结果比较，不触发窗口置前；窗口被遮挡时比较的仍是屏幕内容。比较区域来自最小化窗口时直接报错，不会对着 `(-32000,...)` 那块空画面等到超时。

`window_appears` / `window_disappears` 在首次探测时就已满足时，结果带 `already: true` 与说明，表示本次没有实际等待；否则轮询到条件成立或超时。

`desktop_wait` 只读，Plan 模式可用，且不占用输入锁。

## 界面展示

每个工具的标题后跟一句执行摘要。摘要优先用参数里的目标，执行完再用回执补全：

| 工具 | 摘要 | 例 |
|---|---|---|
| `desktop_eye` | `看屏 · 目标` | `看屏 · 窗口 -> 编辑器`、`看屏 · 局部 -> (x, y, width×height)` |
| `desktop_mouse` | `鼠标 · 动作 -> 目标 (位置)` | `鼠标 · 点击 -> 编辑器 (x, y)`、`鼠标 · 移动 -> (x, y)` |
| `desktop_keyboard` | `键盘 · 动作 -> 内容` | `键盘 · 输入 -> 示例文本` |
| `desktop_wait` | `等待条件 · 条件` | `等待条件 · 窗口出现 -> 编辑器` |

摘要只做展示，不参与门控，也不编造参数里没有的目标。`desktop_eye` 与带 `shot=true` 的鼠标或键盘动作，详情区直接显示回执截图（与 `read_image` 同一套渲染），不必再发一次 `desktop_eye` 去看结果。

详情区的形态与 `read_image` 一致：自定义视图里是图片与元信息（尺寸；缩放时另有发送尺寸；再是窗口或屏幕），请求与响应收进「查看报文」按钮后面。自定义视图不能自己挂 `请求` / `响应` 面板：一旦出现 `.chat-tool-layer--req/res`，壳就会判定这行用的还是默认视图并跳过装箱，JSON 便会挤在图片上面。

倒计时完全由前端按参数自己数，服务端不推送计时帧。`desktop_wait` 的超时只是上限：数到 0 还没收到工具结果，就把摘要改成 `已超时 3 秒` 继续往上数，直到 `tool_end`。结束时停表，在标题末尾直接接上回执里的实际等待时长（`窗口出现 -> 编辑器 · 0 秒`），不写「已达成」/「未达成」这类状态文字——结束与否由 `done` 与标题颜色表达。时长文本按秒 / 分 / 时 / 天展开，例如 `5 秒`、`1 分 30 秒`、`1 天`；`86400 秒` 写成 `1 天`，跨天等待不必自己换算。历史回放（刷新页面、切回会话）不重启倒计时：那一次等待已经结束，重新从总数往下数会读成「还在等」。

## 坐标契约

- 默认坐标空间是屏幕坐标：Windows 为物理像素，macOS 为全局显示坐标（点）。`grid_unit=image` 时网格与光标标签是图内像素；图内坐标只通过 `capture_id` 交给 `desktop_mouse`，不直接当屏幕坐标使用。
- macOS 高 DPI 屏上截图是点的两倍像素：`pixel_ratio` 记录这个比例，鼠标坐标仍按点投递。
- 网格线按「屏幕矩形 → 实发图片尺寸」的比例落位；`grid_unit=image` 时刻度数字由同一比例反推为图内像素。高 DPI 屏上不会偏移半屏。
- `capture` 是截图的屏幕矩形，原点是窗口/裁剪区域左上角，可能为负；`image_to_screen` 给出 `scale_x/scale_y/ox/oy`，换算由服务端完成。
- 多显示器时屏幕矩形是虚拟桌面的并集，左上角可能为负（主屏左侧的副屏）。缩放比例不一致时返回 `note` 提示跨屏坐标可能有偏差。

## 截图加工

`canvas.render()` 是所有平台共用的后处理：

1. 解码 PNG；解不开报 `ScreenCaptureFailed`。
2. 检测全黑画面（锁屏、UAC 安全桌面、受保护内容），在返回值里给 `note`。
3. 长边超过 `max_side` 时用 Lanczos 缩到上限，记录 `scale`。
4. `grid` 打开时叠网格：每 `grid_step` 个屏幕坐标一条蓝色细线，每 5 条一条红色粗线并带刻度；线距小于 8px 时只画主线。线有黑色衬边，线宽随图片宽度增加，压缩后不会细到消失。刻度在最终尺寸下渲染；`grid_unit=image` 时刻度文字用图内像素，但线距仍按 `grid_step` 的屏幕坐标布点。
5. `cursor_mark` 打开时只在光标附近画短十字：黑色衬边、白色分隔层、亮绿芯，小圆环，以及带坐标的 `CURSOR` 标签；十字中心留空，不盖住落点像素，也不铺满全图。短边小于 140 的区域只写坐标、省略 `CURSOR` 前缀，且只描字不铺黑底；短边小于 90 的区域不画标签，坐标只从回执 `cursor` 读取。字号按截图缩放与短边反推，保证不同缩放下屏幕观感一致；标签单位跟随 `grid_unit`。
6. 以 PNG 编码，交给 `desktop_eye` 放进附件。

## 配置

身份在 `plugin-meta.json`。插件开关在 `plugins.ini`；能力开关与时间参数在 `plugin-config.ini`。

```ini
[config]
eye = 1
mouse = 1
keyboard = 1
wait = 1
max_side = 1920
grid_step = 100
cursor_mark = 1
settle_ms = 60
type_interval_ms = 12
hover_settle_ms = 250
hover_approach_ms = 120
hover_wiggle = 1
wait_interval_ms = 200
```

| 键 | 缺省 | 说明 |
|---|---|---|
| `eye` / `mouse` / `keyboard` / `wait` | `1` | 能力开关；关掉后对应工具不注册 |
| `max_side` | `1920` | 发送前长边上限，`0` 不缩放；夹到 `0–8192` |
| `grid_step` | `100` | 网格间距（屏幕坐标）；夹到 `20–500` |
| `cursor_mark` | `1` | 截图是否画光标十字 |
| `settle_ms` | `60` | 输入动作后等待界面响应的毫秒数；夹到 `0–2000` |
| `type_interval_ms` | `12` | `type` 每字符间隔；夹到 `0–200` |
| `hover_settle_ms` | `250` | `hover` 移完光标等界面展开的毫秒数；夹到 `0–2000` |
| `hover_approach_ms` | `120` | `hover` 移到落点用多少毫秒；夹到 `0–2000`，`0` = 一次跳变 |
| `hover_wiggle` | `1` | 到达后是否做 1–2px 微移动，唤醒只认连续 mousemove 的播放器控件 |
| `wait_interval_ms` | `200` | `desktop_wait` 默认轮询间隔；夹到 `50–2000` |

配置文件缺失、节缺失或值写坏时回退缺省；越界值夹到边界。配置错误不阻断工具注册。网格开启时，`grid_step` 会出现在回执里；`max_side` 造成的缩放可从 `image` 与 `note` 反查。其余键不回显。

## 平台后端

### Windows

- 截屏：整屏走 `GetDC(NULL)` + `BitBlt(SRCCOPY | CAPTUREBLT)` + `GetDIBits`，按虚拟桌面坐标截取，负坐标的副屏也在内；窗口走 `PrintWindow(PW_RENDERFULLCONTENT)`，取窗口自身重绘，被别的窗口遮挡也能拿到内容。像素按 `BGRX` 直接编码 PNG，不额外翻转。
- 回退：`PrintWindow` 得到单一颜色（包括全黑）时，会在重绘时限内重试；仍取不到内容且窗口可见时回退屏幕截图，并把 `source` 标成 `screen`；窗口不可见且取不到内容时报 `ScreenCaptureFailed`。
- 落点探测：`WindowFromPoint` 拿坐标下的子窗口，`GetAncestor(GA_ROOT)` 拿所属顶层窗口，`GetClassNameW` 拿控件类名。拿不到就省略 `hit`，不猜。
- 窗口清单：`EnumWindows` 枚举可见顶层窗口（跳过工具窗与屏幕外辅助窗），只用于动作前后的 `window_changed` 对比；清单本身不进上下文。
- DPI：装载时声明 per-monitor v2；宿主已经声明过则沿用宿主的选择。声明失败时依次退回 `SetProcessDpiAwareness` 与 `SetProcessDPIAware`。
- 输入：定位用 `SetCursorPos`，按键用 `SendInput`；文本走 `KEYEVENTF_UNICODE`（代理对拆成两个 UTF-16 单元），功能键与组合键走虚拟键码。
- 已知边界：锁屏与 UAC 安全桌面截不到内容；向更高完整性级别的窗口投递输入会被系统丢弃；混合缩放的多屏在系统层面仍可能有少量偏差。
- 窗口取图、落点探测与窗口清单只在 Windows 后端实现。

### macOS

- 截屏：`/usr/sbin/screencapture -x -t png -R x,y,w,h <临时文件>`，区域按全局显示坐标（点）给；图片像素按显示器比例放大，`geometry` 用 `CGDisplayPixelsWide` 报出 `pixel_ratio`。读取后删除临时文件。
- 输入：CoreGraphics 的 `CGEventCreateMouseEvent` / `CGEventCreateKeyboardEvent`；文本用 `CGEventKeyboardSetUnicodeString` 注入，组合键同时设置修饰键 flags。
- 权限：截屏需要屏幕录制权限，输入需要辅助功能权限。缺少时分别报 `DesktopPermissionDenied`，文案指向「系统设置 → 隐私与安全性」下对应的开关。
- 能力边界：macOS 后端没有窗口端口与落点探测端口。`desktop_eye`、`desktop_mouse`（`cursor` 以外的动作）、`desktop_keyboard` 的 `window` / `hwnd` 参数，以及 `desktop_wait` 的窗口条件或窗口区域比较，都会抛 `DesktopUnavailable`。`desktop_eye(hover=...)` 只移动光标并截屏幕合成结果，不会自动选取光标下的窗口；`hit` 缺失，`window_changed` 只给出 `changed: false`。输入发给当前前台应用；调用方需用其它方式把目标应用置前。

### 其它平台

Linux 与未识别平台装配不可用后端：工具照常注册，调用截屏或输入时抛 `DesktopUnavailable`。这样 CI 与不同机器上的工具表保持一致，模型看到的是明确原因，而不是工具凭空消失。后端装配失败时写入一条 stderr 诊断，并回退到同一不可用后端。

## 门控与并发

- Plan 模式：`desktop_eye` 不带 `hover` 时可用；带 `hover` 时拒绝，因为它会移动真实光标。门控不检查 `activate`：`activate=true` 在 Plan 模式下仍可把窗口置前。`desktop_mouse` 的 `cursor` 可用，其余动作与 `desktop_keyboard` 全部动作抛 `ModeConflict`。`desktop_wait` 只读，可用。门控按会话取 `live_state`；装载阶段拿不到时在执行时再取，取不到则不拦。
- 输入锁：`desktop_mouse` 与 `desktop_keyboard` 共用一把进程内锁，同一时刻只有一个动作在投递；等锁超过 10 秒抛 `DesktopBusy`。拖拽的按下与松开始终成对。`desktop_eye` 的 `hover` 移动光标不经过这把锁。
- 坐标校验：动作前检查目标点是否落在屏幕矩形内，屏外坐标直接报错；没有坐标的动作使用当前光标位置，没有可校验的点。

## 失败文案

| 异常 | 含义 |
|---|---|
| `DesktopUnavailable` | 平台不支持、缺 Pillow 或后端装配失败 |
| `DesktopPermissionDenied` | macOS 缺屏幕录制 / 辅助功能权限 |
| `ScreenCaptureFailed` | GDI / screencapture 失败、截图数据解不开，或不可见窗口取不到内容 |
| `DesktopBusy` | 另一个桌面动作占着输入锁 |
| `DesktopError` | 其余系统调用失败（带 WinError 或系统调用名） |

## 测试

`tests/test_visual_operator.py` 覆盖坐标、键名、配置、截图加工（缩放 / 网格 / 空白 / 坏数据）、四个工具的参数矩阵与返回值、`hover` / `hover_path` / `hover_wiggle` / `shot` / `hit` / `changed` / `window_changed` / `navigated`、条件等待、同名窗口消歧、Plan 门控、输入锁、平台表与后端可用性；Windows 上额外校验虚拟键码表覆盖全部规范键名与 UTF-16 代理对拆分。后端用记录型替身，测试不移动真实光标、不注入真实按键。

## 延伸阅读

- [plugins.md](plugins.md)：插件包形态、扩展点与生命周期
- [tools.md](tools.md)：工具注册、执行管道与图片附件
- [llm.md](llm.md)：多模态请求里的图片块
