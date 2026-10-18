# 桌面 IO（`desktop_io` 插件）

桌面 IO 把「看屏幕」与「操作鼠标键盘」做成三个工具，交给模型在真实桌面上
读图、定位、点击与输入。截屏结果以图片附件直接进入模型上下文，不落盘；
鼠标与键盘动作走输入锁串行投递。插件机制本身见 [plugins.md](plugins.md)。

## 包结构

```
plugins/desktop_io/
  plugin.py                  入口：读配置、选后端、注册三个工具
  plugin-config.ini          真实配置（不入库）
  plugin-config.ini.example  模板
  config.py                  [ext] 读取、回退与夹取
  keys.py                    键名规范、别名与组合键校验
  coords.py                  屏幕矩形 / 点 / 几何比例
  ports.py                   后端端口与数据结构
  canvas.py                  缩放、坐标网格、光标十字、PNG 编码
  guard.py                   Plan 模式门控
  input_lock.py              鼠标与键盘共用的输入锁
  errors.py                  异常层级
  tools/
    _params.py               参数读取与动作矩阵
    eye.py                   desktop_eye
    mouse.py                 desktop_mouse
    keyboard.py              desktop_keyboard
  backends/
    __init__.py              按平台选择后端
    win32.py                 Windows：GDI + SendInput
    macos.py                 macOS：screencapture + CoreGraphics
    _unavailable.py          其它平台：调用时报明确原因
```

## 三个工具

| 工具 | 方向 | 能力 |
|---|---|---|
| `desktop_eye` | 接收 | 截取整屏或区域，叠坐标网格后作为图片附件交给模型 |
| `desktop_mouse` | 输出 | `move` / `click` / `drag` / `scroll` / `cursor` |
| `desktop_keyboard` | 输出 | `type` 任意 Unicode 文本 / `key` 单键 / `hotkey` 组合键 |

三个工具各自持有完整的 JSON Schema，不共用一个多动作大工具：动作与参数的
对应关系由 `tools/_params.py` 的动作矩阵校验，属于别的动作的参数直接报错，
不会被静默忽略。

### `desktop_eye`

| 参数 | 说明 |
|---|---|
| `x` / `y` / `width` / `height` | 区域，四个一起给；省略则截整屏。区域会裁到屏幕内，完全落在屏外报错 |
| `grid` | 是否叠网格与刻度，默认 `true` |
| `max_side` | 长边上限，`0` 不缩放；缺省取配置 |

返回值（`data`）：

```json
{
  "platform": "win32",
  "screen": {"x": 0, "y": 0, "width": 1920, "height": 1080},
  "capture": {"x": 0, "y": 0, "width": 1920, "height": 1080},
  "image": {"width": 1920, "height": 1080, "sent_width": 1200, "sent_height": 675,
            "scale": 1.6, "bytes": 428177},
  "dpi": "96 dpi",
  "cursor": {"x": 734, "y": 709},
  "grid": {"step": 100, "unit": "屏幕坐标"},
  "note": "图片已从 1920x1080 缩到 1200x675；…"
}
```

图片经 `ToolResult.attach` 作为 `image/png` 附件返回。附件走结果信封的独立字段，
不并入 `data`，也不写临时文件。

单张截图上限定为 4000 万像素；超过时在调用侧报错并提示改用区域参数。

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

### `desktop_keyboard`

| `action` | 参数 |
|---|---|
| `type` | `text`（任意 Unicode，含换行与制表符） |
| `key` | `key`、`repeat`（1–20） |
| `hotkey` | `keys`（`"ctrl+c"` / `"alt+tab"`）、`repeat` |

键名先归一成规范名：`return` → `enter`、`esc` / `escape`、`control` → `ctrl`、
`option` → `alt`、`command` / `meta` → `cmd`、`windows` → `win`、`pgup` / `pgdn`、
方向键、`f1`–`f20`、字母、数字与 `- = [ ] ; ' , . / \` `` ` `` 等单字符键。

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
max_side = 1600
grid_step = 100
cursor_mark = 1
settle_ms = 60
type_interval_ms = 12
```

| 键 | 缺省 | 说明 |
|---|---|---|
| `eye` / `mouse` / `keyboard` | `1` | 能力开关；关掉后对应工具不注册 |
| `max_side` | `1600` | 发送前长边上限，`0` 不缩放；夹到 `0–8192` |
| `grid_step` | `100` | 网格间距（屏幕坐标）；夹到 `20–500` |
| `cursor_mark` | `1` | 截图是否画光标十字 |
| `settle_ms` | `60` | 输入动作后等待界面响应的毫秒数；夹到 `0–2000` |
| `type_interval_ms` | `12` | `type` 每字符间隔；夹到 `0–200` |

配置文件缺失、节缺失或值写坏时回退缺省；越界值夹到边界。配置错误不阻断工具注册，
生效值可从 `desktop_eye` 的返回值反查。

## 平台后端

### Windows

- 截屏：`GetDC(NULL)` + `BitBlt(SRCCOPY | CAPTUREBLT)` + `GetDIBits`，按虚拟桌面坐标
  截取，负坐标的副屏也在内；像素按 `BGRX` 直接编码 PNG，不额外翻转。
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

- Plan 模式：`desktop_eye` 与 `desktop_mouse` 的 `cursor` 只读动作可用；
  `desktop_mouse` 其余动作与 `desktop_keyboard` 全部动作抛 `ModeConflict`。
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
坏数据）、三个工具的参数矩阵与返回值、Plan 门控、输入锁、平台后端选择；
Windows 上额外校验虚拟键码表覆盖全部规范键名与 UTF-16 代理对拆分。
后端用记录型替身，测试不移动真实光标、不注入真实按键。

## 延伸阅读

- [plugins.md](plugins.md)：插件包形态、扩展点与生命周期
- [tools.md](tools.md)：工具注册、执行管道与图片附件
- [llm.md](llm.md)：多模态请求里的图片块
