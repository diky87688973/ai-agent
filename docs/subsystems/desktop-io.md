# 桌面 IO（`desktop_io` 插件）

桌面 IO 把「看屏幕」与「操作鼠标键盘」做成四个工具，交给模型在真实桌面上
读图、定位、点击、输入与等待。截屏结果以图片附件直接进入模型上下文，不落盘；
鼠标与键盘动作走输入锁串行投递。插件机制本身见 [plugins.md](plugins.md)。

## 包结构

```
plugins/desktop_io/
  plugin.py                  入口：读配置、选后端、注册四个工具
  plugin-config.ini          真实配置（不入库）
  plugin-config.ini.example  模板
  config.py                  [ext] 读取、回退与夹取
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
| `desktop_eye` | 接收 | 截取整屏或区域，叠坐标网格后作为图片附件交给模型；可带 `hover` 展开悬停控件 |
| `desktop_mouse` | 输出 | `move` / `click` / `drag` / `scroll` / `cursor` |
| `desktop_keyboard` | 输出 | `type` 任意 Unicode 文本 / `key` 单键 / `hotkey` 组合键 |
| `desktop_wait` | 等待条件 | 等画面变化、窗口出现或窗口消失，命中即返回 |

四个工具各自持有完整的 JSON Schema，不共用一个多动作大工具：动作与参数的
对应关系由 `tools/_params.py` 的动作矩阵校验，属于别的动作的参数直接报错，
不会被静默忽略。

### `desktop_eye`

| 参数 | 说明 |
|---|---|
| `x` / `y` / `width` / `height` | 区域，四个一起给；省略则截整屏。区域会裁到屏幕内，完全落在屏外报错 |
| `window` / `hwnd` | 取该窗口自身内容；二选一，`hwnd` 更精确 |
| `activate` | 取图前是否置前，默认 `false`（只恢复最小化窗口，不动前台） |
| `hover` | `[x, y]`：取图前把光标移到这里，用来展开控制条、下拉菜单、提示气泡 |
| `hover_settle_ms` | 移完光标等界面展开的毫秒数，`0–5000`；缺省取配置 |
| `grid` | 是否叠网格与刻度，默认 `true` |
| `max_side` | 长边上限，`0` 不缩放；缺省取配置 |

`hover` 是「移光标 + 截图」能成立的前提。悬停控件普遍 2–3 秒自动收起，
而两次工具调用之间隔着一次模型往返（实测 2–8 秒），拆成 `desktop_mouse(move)`
加 `desktop_eye` 两步必然错过。窗口取图时，移光标发生在窗口恢复/置前之后、
真正取图之前：顺序反了，拍到的要么是没展开的画面，要么是别的窗口上的展开。
移光标会改变桌面状态，所以 Plan 模式下带 `hover` 的调用被拒绝，
不带 `hover` 的取图照常可用。

返回值（`data`）：

```json
{
  "platform": "win32",
  "screen": {"x": 0, "y": 0, "width": 1920, "height": 1080},
  "capture": {"x": 0, "y": 0, "width": 1920, "height": 1080},
  "image": {"width": 1920, "height": 1080, "sent_width": 1600, "sent_height": 900,
            "scale": 1.2, "bytes": 548735},
  "dpi": "96 dpi",
  "cursor": {"x": 734, "y": 709},
  "grid": {"step": 100, "unit": "屏幕坐标", "scale": 1.2},
  "note": "图片已从 1920x1080 缩到 1600x900；…；换算：图上像素 × 1.2 = 屏幕坐标，…"
}
```

图片经 `ToolResult.attach` 作为 `image/png` 附件返回。附件走结果信封的独立字段，
不并入 `data`，也不写临时文件。

单张截图上限定为 4000 万像素；超过时在调用侧报错并提示改用区域参数。

### 同名窗口

`window` 给的是标题片段，同名窗口可能同时存在（CEF/Electron 常见：主窗 +
播放层 + 隐藏辅助窗）。候选排序是 **前台 → Z 序 → 面积**，不是单纯的面积：
用户眼前那个窗口几乎总是他要操作的那个，面积最大的反而可能是盖在画面上的播放层。

命中数大于 1 时，回执里的 `window` 会带 `matched` 与 `alternatives`，
`note` 也会写清「有 N 个、选了哪个、其余 hwnd 是哪些」。只给一个数字
等于让模型自己猜，它猜不到另一个窗口是什么，于是要么反复重试，
要么改用整屏——比例尺也跟着变。

### 缩放与换算

整屏图通常会被缩到 `max_side`，窗口图往往不到上限、按原尺寸发送。
同一任务里出现两种比例尺时，模型每次点击都要心算倍数，是实测误点的来源之一。
所以只要发生缩放，`note` 必须给出换算例句（`图上像素 × 1.2 = 屏幕坐标`），
`grid.scale` 同时给出倍数。细节看不清时用区域参数取局部：局部通常按原尺寸发送。

### `desktop_mouse`

| `action` | 必填 | 可选 |
|---|---|---|
| `move` | `x`、`y` | `duration_ms`（0–5000） |
| `click` | — | `x`、`y`、`button`（left / right / middle）、`count`（1–3） |
| `drag` | `x`、`y`、`to_x`、`to_y` | `button`、`duration_ms`（默认 300） |
| `scroll` | `amount`（-50–50，正数向下 / 向右） | `x`、`y`、`horizontal` |
| `cursor` | — | — |

`click` / `scroll` 省略坐标时作用在当前光标位置。动作完成后返回光标位置与屏幕矩形；
`cursor` 只读，不触发模式门控。

改变界面的动作（`click` / `drag` / `scroll`）额外回执两份证据：

| 字段 | 含义 |
|---|---|
| `hit` | 落点所在的窗口句柄、控件类名与所属顶层窗口标题；平台不支持探测时省略 |
| `changed` | 落点周围 200×200 区域在动作前后的差异比例（0–1）；`0` 表示画面完全没动 |

`hit` 回答「打中了什么」，`changed` 回答「有没有生效」。两者都不是语义判断，
但足以让一次点空当场暴露，而不是留到下一轮靠截图重新推理。

`shot=true` 在动作完成后于同一次调用内截图并返回图片附件，省掉
「再调一次 `desktop_eye`」的往返：

| 参数 | 说明 |
|---|---|
| `shot` | 是否随动作回图，默认 `false` |
| `shot_region` | `[x, y, width, height]`；省略则取目标窗口或整屏 |
| `shot_max_side` | 回图的长边上限；缺省取配置 |

带 `shot` 时返回体是取图回执，动作本身的结果收在 `performed` 字段。
`shot` 对 `move` / `click` / `drag` / `scroll` 开放；`cursor` 是只读查询，不接受它。
`move` 只回图，不做 `hit` / `changed` 比较——移动本身不改变界面，
但悬停可能展开控件，所以回图仍有意义。

### `desktop_keyboard`

| `action` | 参数 |
|---|---|
| `type` | `text`（任意 Unicode，含换行与制表符） |
| `key` | `key`、`repeat`（1–20） |
| `hotkey` | `keys`（`"ctrl+c"` / `"alt+tab"`）、`repeat` |

同样支持 `shot` / `shot_max_side`：打完立刻回图，省一次往返。

键名先归一成规范名：`return` → `enter`、`esc` / `escape`、`control` → `ctrl`、
`option` → `alt`、`command` / `meta` → `cmd`、`windows` → `win`、`pgup` / `pgdn`、
方向键、`f1`–`f20`、字母、数字与 `- = [ ] ; ' , . / \` `` ` `` 等单字符键。

### `desktop_wait`

| 参数 | 说明 |
|---|---|
| `until` | `change` 画面变化 / `window_appears` 窗口出现 / `window_disappears` 窗口消失 |
| `window` / `hwnd` | `change` 用来限定区域，`window_*` 时是必填 |
| `x` / `y` / `width` / `height` | `change` 的比较区域；省略则用窗口矩形或整屏 |
| `timeout_ms` | 最长等待，`50–60000`，默认 10000 |
| `interval_ms` | 轮询间隔，`50–2000`；缺省取配置 |
| `threshold` | `change` 的判定阈值 `0–1`，默认 `0.02` |

超时不是错误：返回 `satisfied: false` 与该轮的实测值，由模型决定换动作还是延长等待。
用固定秒数的 `task_sleep` 赌「预告播完会自动进正片」，实测白等 42 秒且没有发生；
条件等待把这段变成「变了就走」。

`until=change` 用屏幕合成结果比较（不触发窗口置前）；窗口被遮挡时比较的仍是屏幕内容。
窗口最小化时直接报错，不会对着 `(-32000,...)` 那块空画面白等到超时。

## 界面展示

四个工具的标题后跟一句执行摘要，参数里有目标就写目标，执行完用回执补全：

| 工具 | 摘要 | 例 |
|---|---|---|
| `desktop_eye` | `类型 -> 简要描述` | `看屏 · 窗口 -> 腾讯视频`、`看屏 · 局部 -> (x, y, 宽×高)` |
| `desktop_mouse` | `动作 -> 目标 (位置)` | `鼠标 · 点击 -> 腾讯视频 (x, y)`、`鼠标 · 移动 -> (x, y)` |
| `desktop_keyboard` | `动作 -> 内容` | `键盘 · 输入 -> 斗破苍穹` |
| `desktop_wait` | 等待条件 | `等待条件 · 窗口出现 -> 腾讯视频` |

摘要只做展示，不参与门控，也不编造参数里没有的目标。看屏与带 `shot=true`
的手部动作，详情区直接铺回执截图（与 `read_image` 同一套渲染），不必再发一次
`desktop_eye` 去看结果。`task_sleep` 的标题是「等待」，摘要为 `N 秒`，
等待期间逐秒递减；`desktop_wait` 按 `timeout_ms` 同样倒计时。

`desktop_wait` 收尾时停表，用回执里的 `waited_ms` 写成 `已达成 1.2 秒`（超时写
`超时 N 秒`）。`task_sleep` 只是登记休眠请求、工具立即返回，倒计时不会在
`tool_end` 时停下，而是按请求时长走到 0 并写成 `N 秒 · 已到点` —— 否则用户在
界面上只看得到一个静止的秒数。历史回放（刷新页面、切回会话）不重启倒计时：
那一次等待已经结束，重新从总数往下数会读成「还在等」。

## 坐标契约

- 工具参数里的 x / y 与网格刻度都是同一套屏幕坐标：Windows 为物理像素，
  macOS 为全局显示坐标（点）。
- macOS Retina 上截图是点的两倍像素：`pixel_ratio` 记录这个比例，鼠标坐标仍按点投递。
- 网格刻度画在缩放后的图上，但数字是原屏幕坐标，可以直接填回 `desktop_mouse`。
  网格线与光标十字按「屏幕矩形 → 实发图片尺寸」的比例落位，Retina 上不会偏移半屏。
- 多显示器时屏幕矩形是虚拟桌面的并集，左上角可能为负（主屏左侧的副屏）。
  缩放比例不一致时返回 `note` 提示跨屏坐标可能有偏差。

## 截图加工

`canvas.render()` 是所有平台共用的后处理：

1. 解码 PNG；解不开报 `ScreenCaptureFailed`；
2. 检测全黑画面（锁屏、UAC 安全桌面、受保护内容），在返回值里给 `note`；
3. 长边超过 `max_side` 时用 Lanczos 缩到上限，记录 `scale`；
4. `grid` 打开时叠网格：每 `grid_step` 个屏幕坐标一条细线，每 5 条一条带刻度的主线；
   线距过密时只画主线。刻度在最终尺寸下渲染，缩图不会把字糊掉；
5. `cursor_mark` 打开时画光标十字与坐标标签，与 `grid` 开关无关；
6. 以 PNG 编码，交给 `desktop_eye` 放进附件。

## 配置

```ini
[base]
id = desktop_io
name = 桌面 IO
enable = 1
version = 1.0

[ext]
eye = 1
mouse = 1
keyboard = 1
wait = 1
max_side = 1600
grid_step = 100
cursor_mark = 1
settle_ms = 60
type_interval_ms = 12
hover_settle_ms = 250
wait_interval_ms = 200
```

| 键 | 缺省 | 说明 |
|---|---|---|
| `eye` / `mouse` / `keyboard` / `wait` | `1` | 能力开关；关掉后对应工具不注册 |
| `max_side` | `1600` | 发送前长边上限，`0` 不缩放；夹到 `0–8192` |
| `grid_step` | `100` | 网格间距（屏幕坐标）；夹到 `20–500` |
| `cursor_mark` | `1` | 截图是否画光标十字 |
| `settle_ms` | `60` | 输入动作后等待界面响应的毫秒数；夹到 `0–2000` |
| `type_interval_ms` | `12` | `type` 每字符间隔；夹到 `0–200` |
| `hover_settle_ms` | `250` | `hover` 移完光标等界面展开的毫秒数；夹到 `0–2000` |
| `wait_interval_ms` | `200` | `desktop_wait` 默认轮询间隔；夹到 `50–2000` |

配置文件缺失、节缺失或值写坏时回退缺省；越界值夹到边界。配置错误不阻断工具注册，
生效值可从 `desktop_eye` 的返回值反查。

## 平台后端

### Windows

- 截屏：整屏走 `GetDC(NULL)` + `BitBlt(SRCCOPY | CAPTUREBLT)` + `GetDIBits`，按虚拟桌面坐标
  截取，负坐标的副屏也在内；窗口走 `PrintWindow(PW_RENDERFULLCONTENT)`，取窗口自身重绘，
  被别的窗口遮挡也能拿到内容。像素按 `BGRX` 直接编码 PNG，不额外翻转。
- 落点探测：`WindowFromPoint` 拿坐标下的子窗口，`GetAncestor(GA_ROOT)` 拿所属顶层窗口，
  `GetClassNameW` 拿控件类名。拿不到就省略 `hit`，不猜。
- DPI：装载时声明 per-monitor v2；宿主已经声明过则沿用宿主的选择。声明失败时
  依次退回 `SetProcessDpiAwareness` 与 `SetProcessDPIAware`。
- 输入：定位用 `SetCursorPos`，按键用 `SendInput`；文本走 `KEYEVENTF_UNICODE`
  （代理对拆成两个 UTF-16 单元），功能键与组合键走虚拟键码。
- 已知边界：锁屏与 UAC 安全桌面截不到内容；向更高完整性级别的窗口投递输入会被
  系统丢弃；混合缩放的多屏在系统层面仍可能有少量偏差。

### macOS

- 截屏：`/usr/sbin/screencapture -x -R x,y,w,h`，区域按全局显示坐标（点）给；
  图片像素按显示器比例放大，`geometry` 用 `CGDisplayPixelsWide` 报出 `pixel_ratio`。
- 输入：CoreGraphics 的 `CGEventCreateMouseEvent` / `CGEventCreateKeyboardEvent`；
  文本用 `CGEventKeyboardSetUnicodeString` 注入，组合键同时设置修饰键 flags。
- 权限：截屏需要屏幕录制权限，输入需要辅助功能权限。缺少时分别报
  `DesktopPermissionDenied`，文案指向「系统设置 → 隐私与安全性」下对应的开关。

### 其它平台

Linux 与未识别平台装配不可用后端：工具照常注册，调用截屏或输入时抛出
`DesktopUnavailable`。这样 CI 与不同机器上的工具表保持一致，模型看到的是明确原因，
而不是工具凭空消失。

## 门控与并发

- Plan 模式：`desktop_eye` 不带 `hover` 时可用（只读取屏幕）；带 `hover` 时拒绝，
  因为它会移动真实光标。`desktop_mouse` 的 `cursor` 只读动作可用，其余动作与
  `desktop_keyboard` 全部动作抛 `ModeConflict`。`desktop_wait` 只读，可用。
  门控按会话取 `live_state`，装载阶段拿不到时在执行时再取。
- 输入锁：鼠标与键盘共用一把进程内锁，同一时刻只有一个动作在投递；
  等锁超过 10 秒抛 `DesktopBusy`。拖拽的按下与松开始终成对。
- 坐标校验：动作前检查目标点是否落在屏幕矩形内，屏外坐标直接报错。

## 失败文案

| 异常 | 含义 |
|---|---|
| `DesktopUnavailable` | 平台不支持、缺 Pillow 或后端装配失败 |
| `DesktopPermissionDenied` | macOS 缺屏幕录制 / 辅助功能权限 |
| `ScreenCaptureFailed` | GDI / screencapture 失败，或截图数据解不开 |
| `DesktopBusy` | 另一个桌面动作占着输入锁 |
| `DesktopError` | 其余系统调用失败（带 WinError 或系统调用名） |

## 测试

`tests/test_desktop_io.py` 覆盖坐标、键名、配置、截图加工（缩放 / 网格 / 空白 /
坏数据）、四个工具的参数矩阵与返回值、`hover` / `shot` / `hit` / `changed`、
条件等待、同名窗口消歧、Plan 门控、输入锁、平台后端选择；
Windows 上额外校验虚拟键码表覆盖全部规范键名与 UTF-16 代理对拆分。
后端用记录型替身，测试不移动真实光标、不注入真实按键。

## 延伸阅读

- [plugins.md](plugins.md)：插件包形态、扩展点与生命周期
- [tools.md](tools.md)：工具注册、执行管道与图片附件
- [llm.md](llm.md)：多模态请求里的图片块
