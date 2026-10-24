# Visual Operator 插件方案

## 1. 结论

把 Windows / macOS 的桌面看与动做成一个内置插件 `plugins/visual_operator`，由它注册四个工具：

| 工具 | 心智 | 能力 |
|---|---|---|
| `desktop_eye` | 看 | 截屏（整屏、区域或窗口），叠坐标网格，图片直接交给模型；`hover` 可拍悬停后才出现的控件 |
| `desktop_mouse` | 手 | 移动 / 点击 / 拖拽 / 滚轮 / 只读查询光标；回执带 `hit` / `changed`，可带 `shot` |
| `desktop_keyboard` | 手 | 输入文本 / 单键 / 组合键；可带 `shot` |
| `desktop_wait` | 等 | 等画面变化、窗口出现或窗口消失，命中即返回 |

`desktop_wait` 与三个 L0 工具共用后端与输入锁（它本身只读）。参数级契约以
[visual-operator.md](../subsystems/visual-operator.md) 为准，设计取舍见下。

形态选择：插件贡献工具，而不是把 15 个动作塞进一个 `desktop_action`。
三类能力各自有独立的参数面（坐标、按键、文本），合成一个工具后参数描述必须写成
「当 action=click 时看 x/y，当 action=type 时看 text」，模型错配参数的概率显著上升。

插件写进工程根的 `plugins.ini`，默认启用：新克隆的仓库起来就有这四个工具。
关掉开关时 `set_plugin_enabled` 保留清单节、把 `enabled` 写成 0，
对应工具随之注销并从列表消失；再打开即热装载，不需要重启。

默认开启带来两条硬约束：`catalog/tools.json` 必须把四个工具登记进去；
插件在 Linux 上必须能正常 import 与注册（平台能力在执行期判定，见不变量 1）。
CI 跑在 Ubuntu 上，装配集与 Windows 本机必须是同一份。

插件不贡献面板、端点、上下文注入与开屏脚本。对外可见面只有工具声明与工具卡。

## 2. 不变量

1. 工具注册与平台无关：四个工具在任何平台都注册。平台能力在执行期判定，
   不支持时回结构化错误。装配集在 Windows 与 Linux 上必须是同一份。
2. 坐标只有一个空间：屏幕坐标（Windows 物理像素，macOS 显示点）。截图返回的尺寸、网格刻度、
   鼠标参数、返回值里的光标位置全在这个空间里。平台内部的倍率换算只发生在截图加工，
   不出现在工具契约里。
3. 截图不作为文件产物保存：以 `ToolResult.attach` 回带，读完即用。
   macOS 的 `screencapture` 只写临时文件，后端在 `finally` 里删除；
   不存在需要模型再 `read_image` 的落盘路径，也没有清理动作。
4. 图片缩放不改变坐标语义：网格刻度写的是屏幕坐标，缩放只改变图片尺寸，
   模型按刻度读数，不需要做换算。
5. 四类能力各自可关：`eye` / `mouse` / `keyboard` / `wait` 为 0 时该工具不注册，
   而不是注册后拒绝调用。
6. Plan 模式禁止桌面输入与移光标，允许截屏与条件等待。读取桌面不改变任何状态。
7. 输入动作串行：同一进程内鼠标与键盘动作共用一把锁，跨会话也不会交错。
   拖拽中途被另一会话的点击插入会留下按下的键。
8. 失败必须带可执行动作：缺权限说清去哪一栏勾选，平台不支持说清支持哪两个平台，
   参数不对说清该用哪个 action。
9. 插件不 import `agent.app` / `agent.entry`，只依赖 `capabilities`、`mechanisms`、`core`。
10. 平台模块只在对应平台导入：`backends/__init__.py` 在 `load_backend()` 里按
    `sys.platform` 惰性导入，非本平台不会执行 `WinDLL` / `CDLL`。

## 3. 包结构

```
plugins/visual_operator/
  plugin.py                    入口：读配置 → 取后端 → 按开关注册四个工具
  config.py                    DesktopConfig + load_config()（纯函数，含夹取规则）
  coords.py                    ScreenRect / ScreenPoint / 裁剪与交集（纯函数）
  keys.py                      规范键名、别名归一、组合键校验（纯函数）
  errors.py                    四类异常
  canvas.py                    网格 / 光标 / 缩放 / PNG 编码（Pillow）
  ports.py                     端口协议 + Screenshot / WindowInfo / Backend 数据结构
  guard.py                     Plan 模式拒绝
  input_lock.py                输入动作串行锁
  backends/__init__.py         load_backend()：按平台惰性导入；不可用后端
  backends/win32.py            GDI 截图、DPI、虚拟屏、SendInput 鼠标键盘
  backends/macos.py            screencapture、CGEvent、TCC 权限、Retina 倍率
  tools/__init__.py            四个工具类的统一出口
  tools/_params.py             参数取值与动作矩阵校验（四个工具共用）
  tools/eye.py                 DesktopEyeTool
  tools/mouse.py               DesktopMouseTool
  tools/keyboard.py            DesktopKeyboardTool
  tools/wait.py                DesktopWaitTool
  plugin-config.ini    [config]
```

估算：平台后端各 350–450 行，其余文件 60–180 行，合计约 1500 行（不含测试）。

职责边界：

| 文件 | 只做 | 不做 |
|---|---|---|
| `plugin.py` | 读配置、取后端、装配工具 | 平台分支、参数校验 |
| `backends/*` | 调系统 API、点与像素换算、权限探测 | 图片加工、文案组织 |
| `canvas.py` | 图片加工与编码 | 系统调用、坐标换算语义 |
| `tools/*` | 参数校验、调端口、组返回值 | 系统 API、图片编码 |
| `ports.py` | 协议与数据类 | 任何实现 |

## 4. 工具契约

### 4.1 `desktop_eye`

```python
name = "desktop_eye"
label = "看屏"
icon = "👁"
parallel_safe = False
description = (
    "截取桌面并作为图片直接查看（不是 OCR）。支持整屏、区域与指定窗口。"
    "给 window / hwnd 时取该窗口自身内容：被遮挡也能看到；若已最小化，"
    "先恢复再取图（默认不置前，不动当前前台窗口），回执带 restored。"
    "要把它亮到前台时给 activate=true。"
    "图上叠坐标网格，刻度数字与 desktop_mouse 使用同一套屏幕坐标。"
    "返回屏幕矩形、光标位置与实发尺寸。"
)
parameters = {
    "x": {"type": "integer", "description": "区域左上角 x（屏幕坐标）；与 y/width/height 同时给出"},
    "y": {"type": "integer", "description": "区域左上角 y"},
    "width": {"type": "integer", "description": "区域宽度（屏幕坐标）"},
    "height": {"type": "integer", "description": "区域高度（屏幕坐标）"},
    "window": {"type": "string", "description": "窗口标题片段；取该窗口自身内容，遮挡不影响"},
    "hwnd": {"type": "integer", "description": "窗口句柄；与 window 二选一，hwnd 更精确"},
    "activate": {"type": "boolean", "description": "取图前是否置前（默认 false：只恢复，不改变当前前台）"},
    "grid": {"type": "boolean", "description": "叠加坐标网格与刻度（默认 true）"},
    "max_side": {"type": "integer", "description": "长边缩到不超过该像素；0 = 不缩放；缺省取插件配置"},
}
```

返回数据（图片另走附件）：

```json
{
  "platform": "win32",
  "screen": {"x": -1920, "y": 0, "width": 3840, "height": 1080},
  "capture": {"x": -1920, "y": 0, "width": 3840, "height": 1080},
  "image": {"width": 3840, "height": 1080, "sent_width": 1920, "sent_height": 540,
            "scale": 2.4, "bytes": 812345},
  "cursor": {"x": 412, "y": 300},
  "grid": {"step": 100, "unit": "屏幕坐标"},
  "dpi": "per-monitor-v2",
  "window": {"hwnd": 2363600, "title": "腾讯视频", "rect": {"...": "..."},
             "minimized": false, "visible": true},
  "restored": true
}
```

`window` / `restored` / `activated` 只在给了 `window` 或 `hwnd` 时出现：
`restored` 表示取图前窗口最小化、已恢复；`activated` 只在显式给了 `activate`
时出现，写置前是否成功。

`note` 只在这些情况下出现：缩放过（给出换算关系）、恢复过窗口（说明有没有置前）、
窗口内容取不到而回退屏幕（可能含遮挡物）、画面全黑（锁屏 / 安全桌面 / 受保护内容）、
多屏缩放不一致（坐标可能偏移）。常态不写提示语，省请求体积。

校验：

- `x/y/width/height` 必须成组出现；只给一部分 → `ValueError` 指出缺哪个。
- `width`、`height` 必须为正；区域与屏幕无交集 → `ValueError` 附屏幕矩形。
- 区域超出屏幕按屏幕裁剪，裁剪后的矩形放在 `capture` 里。
- 像素数超过 `MAX_CAPTURE_PIXELS`（40M）→ `ValueError`，请模型给更小的区域。
- `activate` 只对 `window` / `hwnd` 有意义；整屏取图给了它就 → `ValueError`。

#### 取图与置前的关系

| 窗口状态 | `activate` 缺省（false） | `activate=true` |
|---|---|---|
| 正常显示、被遮挡 | 不碰窗口状态，直接取窗口自身重绘 | 先置前，再取图 |
| 最小化 | **恢复**（`SW_SHOWNOACTIVATE`）后取图，当前前台不变 | 恢复 + 置前，等价于点任务栏 |

恢复是必须的：最小化窗口的 `GetWindowRect` 是 `(-32000,-32000,160,28)`，
`PrintWindow` 只会得到空帧。实测 `SW_SHOWNOACTIVATE` 能触发 Chromium/Chromium 真实重绘
（5.78MB 非空帧，与 `SW_RESTORE` 一致），所以「不打扰用户」和「取到内容」可以同时成立。

### 4.2 `desktop_mouse`

```python
name = "desktop_mouse"
label = "鼠标"
icon = "🖱"
description = (
    "操作鼠标：move 移动 / click 点击 / drag 拖拽 / scroll 滚轮 / cursor 只读查询位置。"
    "坐标是屏幕坐标，与 desktop_eye 的网格刻度一致；click 不给 x/y 时在原地点击。"
    "给 window / hwnd 时先把该窗口恢复并置前再动作，回执带 focus；"
    "置前失败则拒绝落点，避免点到遮挡物。"
    "返回动作后的光标位置。"
)
parameters = {
    "action": {"type": "string", "description": "move / click / drag / scroll / cursor",
               "enum": ["move", "click", "drag", "scroll", "cursor"]},
    "x": {"type": "integer", "description": "目标 x（move / click）或起点 x（drag）或滚动锚点 x（scroll）"},
    "y": {"type": "integer", "description": "同上，y"},
    "to_x": {"type": "integer", "description": "drag 终点 x"},
    "to_y": {"type": "integer", "description": "drag 终点 y"},
    "button": {"type": "string", "description": "left / right / middle（默认 left）",
               "enum": ["left", "right", "middle"]},
    "count": {"type": "integer", "description": "连击次数 1–3（默认 1）"},
    "amount": {"type": "integer", "description": "滚轮格数，正数向下或向右；绝对值 ≤ 50"},
    "horizontal": {"type": "boolean", "description": "横向滚动（默认 false）"},
    "duration_ms": {"type": "integer", "description": "移动或拖拽的过渡时长 0–5000（默认 0 = 直接落点）"},
    "window": {"type": "string", "description": "目标窗口标题片段；先置前再动作"},
    "hwnd": {"type": "integer", "description": "目标窗口句柄；与 window 二选一，hwnd 更精确"},
}
```

动作矩阵（`tools/_params.py` 唯一实现，逐条校验）：

| action | 必填 | 允许 | 拒绝 |
|---|---|---|---|
| `move` | `x,y` | `duration_ms` | `to_*` / `amount` / `button` / `count` / `horizontal` |
| `click` | 无 | `x,y,button,count` | `to_*` / `amount` / `horizontal` / `duration_ms` |
| `drag` | `x,y,to_x,to_y` | `button,duration_ms` | `amount` / `count` / `horizontal` |
| `scroll` | `amount` | `x,y,horizontal` | `to_*` / `button` / `count` / `duration_ms` |
| `cursor` | 无 | 无 | 其余全部 |

拒绝时回 `ValueError`，文案点名该用哪个 action，例如
`action=click 不接受 to_x；拖拽改用 action=drag`。

返回：

```json
{"action": "click", "button": "left", "count": 1, "cursor": {"x": 300, "y": 400}}
{"action": "drag", "from": {"x": 10, "y": 20}, "to": {"x": 300, "y": 400}, "cursor": {"x": 300, "y": 400}}
{"action": "scroll", "amount": -3, "horizontal": false, "cursor": {"x": 800, "y": 500}}
{"action": "cursor", "cursor": {"x": 412, "y": 300}, "screen": {"x": 0, "y": 0, "width": 2560, "height": 1440}}
```

`drag` 的按下与松开必须成对：后端用 `try/finally` 保证异常路径也发出松开事件。

### 4.3 `desktop_keyboard`

```python
name = "desktop_keyboard"
label = "键盘"
icon = "⌨"
description = (
    "操作键盘：type 输入文本 / key 按一次键 / hotkey 按组合键。"
    "文本按 Unicode 逐字投递，不受当前键盘布局影响；\\n 走回车，\\t 走制表。"
    "键名小写，组合键如 [\"ctrl\", \"c\"]、[\"cmd\", \"space\"]。"
    "给 window / hwnd 时先恢复并置前再输入，回执带 focus；置前失败则拒绝投递。"
)
parameters = {
    "action": {"type": "string", "description": "type / key / hotkey",
               "enum": ["type", "key", "hotkey"]},
    "text": {"type": "string", "description": "action=type 时要输入的文本"},
    "key": {"type": "string", "description": "action=key 时的键名，如 enter / esc / f5 / a"},
    "keys": {"type": "array", "description": "action=hotkey 时的键名数组，2–4 个"},
    "repeat": {"type": "integer", "description": "key / hotkey 重复次数 1–20（默认 1）"},
    "window": {"type": "string", "description": "目标窗口标题片段；先置前再输入"},
    "hwnd": {"type": "integer", "description": "目标窗口句柄；与 window 二选一，hwnd 更精确"},
}
```

返回：

```json
{"action": "type", "chars": 12}
{"action": "key", "key": "enter", "repeat": 1}
{"action": "hotkey", "keys": "ctrl+c", "repeat": 1}
```

键名规范（`keys.py`）：

- 规范名：`enter tab esc space backspace delete insert home end pageup pagedown
  left up right down capslock f1…f20 ctrl shift alt win cmd`，以及单个可见字符。
- 别名归一：`return→enter`、`escape→esc`、`control→ctrl`、`option|alt→alt`、
  `command|meta|super→cmd`（Windows 侧映射到 Win 键）、`page_up|pgup→pageup`。
- 未知键名 → `ValueError` 附规范名清单的短摘要，不回退成「按第一个字符」。
- `keys` 按字符串给（schema 只声明字符串），按 `+` 或 `,` 拆开；数组形式在解析层也容忍。
- `hotkey` 只接受 2–4 个键，且至少一个非修饰键；全是修饰键 → `ValueError`。

整数参数接受数字字符串（`"300"`），拒绝布尔与浮点；小数按 `ValueError`，
不静默取整。

## 5. 配置

`plugins/visual_operator/plugin-config.ini`：

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

| 键 | 默认 | 范围 | 作用 |
|---|---|---|---|
| `eye` | 1 | 0/1 | 是否注册 `desktop_eye` |
| `mouse` | 1 | 0/1 | 是否注册 `desktop_mouse` |
| `keyboard` | 1 | 0/1 | 是否注册 `desktop_keyboard` |
| `wait` | 1 | 0/1 | 是否注册 `desktop_wait` |
| `max_side` | 1920 | 0–8192 | 截图长边上限，0 = 不缩放 |
| `grid_step` | 100 | 20–500 | 网格间距（屏幕坐标） |
| `cursor_mark` | 1 | 0/1 | 网格图上画光标十字并标坐标 |
| `settle_ms` | 60 | 0–2000 | 鼠标键盘动作后的停顿，给界面刷新留时间 |
| `type_interval_ms` | 12 | 0–200 | 逐字输入的字符间隔 |
| `hover_settle_ms` | 250 | 0–2000 | `hover` 移完光标后等界面展开 |
| `hover_approach_ms` | 120 | 0–2000 | `hover` 移到落点用多少毫秒，0 = 一次跳变 |
| `hover_wiggle` | 1 | 0/1 | 到达后是否做 1–2px 微移动，唤醒只认连续 mousemove 的控件 |
| `wait_interval_ms` | 200 | 50–2000 | `desktop_wait` 的默认轮询间隔 |

解析规则（`config.py`，纯函数，无 IO 副作用）：

- 真实配置缺失 → 全部取默认值。
- 整数键：非数字取默认；越界夹到边界（`grid_step=1000 → 500`）。
- 开关键：接受 `1/0`、`true/false`、`yes/no`、`on/off`（大小写不敏感），其余取默认。
- 未知键忽略：真实配置允许带注释与其它节，不因多一个键装载失败。
- 夹取与回退不写日志：配置错误在装载期不阻断，也不该刷错误日志；
  生效值可由 `desktop_eye` 的 `grid.step` 与 `image` 字段反查。

插件装载失败（`plugin.py` 抛错）仍由宿主记录并回滚，配置解析不在失败面内。

## 6. 坐标、图像与缩放

### 6.1 空间定义

- 屏幕坐标空间的原点是虚拟桌面左上角；多屏时 `x` 或 `y` 可以为负。
  Windows 用物理像素，macOS 用全局显示点。
- `screen` 返回虚拟桌面矩形；`capture` 返回本次实际截取的矩形。
- 网格刻度写屏幕坐标值（`screen.x + 偏移`），不是图片像素。
- 鼠标参数按同一空间解释，后端直接按该坐标系投递。

### 6.2 加工顺序

```
系统截取（原始截图）
  → 按区域裁剪（后端完成）
  → 全黑检测（仅记录 note）
  → 缩放到 max_side（LANCZOS）
  → 叠网格与光标（在缩放后的画布上画，标签按屏幕坐标换算）
  → PNG 编码 → ToolResult.attach
```

网格画在缩放后的画布上：标签在最终尺寸下渲染才不会被缩成模糊小字。
落点由 `图内偏移 = (屏幕坐标 - rect 原点) × 实发尺寸 / rect 尺寸` 计算，
所以缩放与 Retina 倍率都不影响读数。

网格细节：

- 每 `grid_step` 个屏幕坐标一条细线，每 5 条一条粗线并标注数值（上下边缘各标一次）。
- 刻度文字用 Pillow 内嵌字体（`ImageFont.load_default(size=…)`，随 Pillow 一起分发，
  不依赖系统字体）；该参数自 Pillow 10.1 起可用，取字体时对 `TypeError` 回退到
  `load_default()`，不因依赖小版本差异让截图整条失败。
- 文字加深色描边，保证在浅色与深色背景上都可读。
- 光标十字与坐标标签只在 `cursor_mark=1` 且光标落在本次截图区域内时绘制，
  与 `grid` 开关无关。
- 线宽与字号随最终图宽自适应：宽图细线 1px、字号 11–16px；标签不与边缘重叠。

### 6.3 缩放与坐标

`image.scale = 原图宽 / 实发宽`。模型不需要用它换算（网格刻度已是屏幕坐标），
它只用于核对与排障。缩放发生时 `note` 给出这一句，避免模型按图片像素直接点击。

### 6.4 体积

- 单张截图（整屏或区域）超过 40M 像素时在调用侧报错，提示改用区域参数；
  错误停在参数检查，不先分配几百 MB 位图再失败。
- 截图会进入会话历史。插件文档写明：常开时把 `config.ini` 的
  `[image] image_max` 调到 40 以内，避免每轮请求都带十几张全屏图。

## 7. 平台后端

### 7.1 公共契约（`ports.py`）

```python
class ScreenPort(Protocol):
    def geometry(self) -> ScreenGeometry: ...
    def capture(self, region: ScreenRect | None) -> Screenshot: ...

class MousePort(Protocol):
    def cursor(self) -> ScreenPoint: ...
    def move(self, point: ScreenPoint, duration_ms: int) -> None: ...
    def click(self, point: ScreenPoint | None, button: str, count: int) -> None: ...
    def drag(self, start: ScreenPoint, end: ScreenPoint, button: str, duration_ms: int) -> None: ...
    def scroll(self, point: ScreenPoint | None, amount: int, horizontal: bool) -> None: ...

class KeyboardPort(Protocol):
    def type_text(self, text: str, interval_ms: int) -> None: ...
    def press(self, key: str, repeat: int) -> None: ...
    def hotkey(self, keys: Sequence[str], repeat: int) -> None: ...
```

`Screenshot` 带 `png: bytes`、`rect: ScreenRect`。
`Backend` 是 `platform / screen / mouse / keyboard` 四个字段的冻结数据类。

`backends/__init__.py` 的 `load_backend()`：

```python
if sys.platform == "win32":   return Win32Backend()
if sys.platform == "darwin":  return MacOSBackend()
return unavailable_backend()
```

装配抛错时打印一行诊断并退到不可用后端。不可用后端的三个端口在每个方法上抛
`DesktopUnavailable`，枚举原因不变，保证工具仍然注册、错误可解释。

### 7.2 Windows

| 能力 | 实现 |
|---|---|
| DPI 感知 | `SetProcessDpiAwarenessContext(-4)` → `shcore.SetProcessDpiAwareness(2)` → `SetProcessDPIAware()`，一次性，记录生效档位 |
| 虚拟屏 | `SM_XVIRTUALSCREEN` / `SM_YVIRTUALSCREEN` / `SM_CXVIRTUALSCREEN` / `SM_CYVIRTUALSCREEN` |
| 截图 | `GetDC(NULL)` → 兼容 DC / 位图 → `BitBlt(SRCCOPY)` → `GetDIBits`（32 位、`BI_RGB`、`biHeight = -h` 取顶朝下）→ Pillow `frombuffer("BGRX")` |
| 光标 | `Get外部编辑器Pos` |
| 移动 | `Set外部编辑器Pos`；`duration_ms > 0` 时按线性插值分步投递，每步 10ms |
| 点击 | `SendInput` 按下 / 抬起，连击间隔 20ms；连击逐次重复 |
| 拖拽 | 起点落位 → 按下 → 插值移动 → `finally` 抬起 |
| 滚轮 | `MOUSEEVENTF_WHEEL` / `MOUSEEVENTF_HWHEEL`，纵向取反后乘 120 |
| 键盘 | `SendInput` + `KEYEVENTF_UNICODE`；特殊键用虚拟键码；组合键顺序按下、逆序抬起 |

坐标选择 `Set外部编辑器Pos` 而不用 `MOUSEEVENTF_ABSOLUTE`：后者不带 `VIRTUALDESK`
时只覆盖主屏，归一化还会在混合 DPI 下引入误差。`Set外部编辑器Pos` 直接吃虚拟桌面像素坐标。

已知边界（写进文档）：UIPI 提权窗口（以管理员运行的程序）会丢弃普通权限进程的
`SendInput`，且不报错；锁屏与 UAC 安全桌面下 `BitBlt` 得到全黑图。

### 7.3 macOS

| 能力 | 实现 |
|---|---|
| 屏幕录制权限 | `CGPreflightScreenCaptureAccess()`（10.15+；符号缺失视为不适用） |
| 辅助功能权限 | `AXIsProcessTrusted()` |
| 截图 | `/usr/sbin/screencapture -x [-R x,y,w,h] <临时文件>` → Pillow 读入 → 删临时文件 |
| 几何 | `CGGetActiveDisplayList` + `CGDisplayBounds`（点）+ `CGDisplayPixelsWide/High`（像素） |
| 光标 | `CGEventCreate(nil)` + `CGEventGetLocation` + `CFRelease` |
| 移动 / 点击 / 拖拽 | `CGEventCreateMouseEvent` + `CGEventPost(kCGHIDEventTap)`；双击用 `kCGMouseEventClickState` 逐次递增 |
| 滚轮 | `CGEventCreateScrollWheelEvent`（单位：行） |
| 键盘 | `CGEventCreateKeyboardEvent`；文本用 `CGEventKeyboardSetUnicodeString`；组合键用 `CGEventSetFlags`（cmd/shift/alt/ctrl 掩码） |

Retina：`screencapture` 出的是物理像素，事件坐标是点。工具坐标直接用全局显示点，
不做额外换算；`pixel_ratio = 像素宽 / 点宽` 由 `geometry()` 报出，供模型理解图片倍率。
多屏比例不一致时置 `mixed_scale=True`，返回值里给 `note`。

`screencapture -R` 的区域单位是点，输出像素 = 点 × 比例。网格与光标按
「截图区域 → 实发图片尺寸」的比例落位，与显示器倍率无关。

## 8. 安全与门控

| 机制 | 位置 | 行为 |
|---|---|---|
| Plan 模式 | `guard.py`，`desktop_mouse` / `desktop_keyboard` 的 `execute` 首行 | 抛 `ModeConflict("Plan 模式下禁止桌面输入（可先 run_type 切回 auto / execute）")`；`desktop_mouse action=cursor` 只读，放行 |
| 能力开关 | `plugin.py` | 四个工具各自按配置注册；关闭即不出现 |
| 输入串行 | `input_lock.py` | 鼠标与键盘动作共用 `threading.Lock`，10 秒拿不到抛 `DesktopBusy` |
| 默认启用 | `plugins.ini` 有节 | 开箱即用；关掉开关即注销工具，清单节保留 |
| 截屏 | 无额外门控 | 只读，Plan 模式同样可用 |

不做快捷键黑名单。键盘本身就能敲出任意命令（先按 Win 再输入），
黑名单挡不住，只会给出一层看起来安全的假象。真正的边界是「插件是否启用」、
「是否在 Plan 模式」与「用户是否在场」。

风险声明写进插件文档：启用后，任何能影响模型输入的内容（网页、文件、工具结果）
都可能变成真实的点击与键入。插件与 `run_command` 同一风险量级，只是入口不同。

## 9. 错误与文案

| 异常 | 触发 | 文案要点 |
|---|---|---|
| `DesktopUnavailable` | 平台不支持、无图形会话、缺 Pillow | 说明支持的两个平台与当前平台 |
| `DesktopPermissionDenied` | macOS 屏幕录制 / 辅助功能未授权 | 点明系统设置里的具体栏目与目标程序 |
| `ScreenCaptureFailed` | `BitBlt` / `screencapture` 失败 | 带系统错误码或进程退出码，不回退成空图 |
| `DesktopBusy` | 输入锁超时 | 说明另一个输入动作未结束 |
| `ModeConflict` | Plan 模式下的鼠标键盘 | 与内置命令工具同一句式 |
| `ValueError` | 参数缺失 / 越界 / 动作矩阵不符 | 点名参数与可用 action |

异常由管道捕获成 `ok=false` 结构化回灌，单步失败不终止回合。
错误信息里不出现堆栈与内部路径。

## 10. 测试

新增两个测试文件，全部在 Linux CI 上可跑（不触碰真实桌面）：

`tests/test_visual_operator.py`

| 类 | 覆盖 |
|---|---|
| `ConfigTest` | 缺文件取默认、越界夹取、开关解析、未知键忽略 |
| `KeysTest` | 别名归一、未知键报错、组合键数量与修饰键校验、两张平台键码表覆盖全部规范名 |
| `CoordsTest` | 区域成组校验、越界裁剪、无交集报错、负原点、Retina 比例换算 |
| `CanvasTest` | 缩放后尺寸与 `scale`、网格像素落点、标签存在（像素差断言）、光标在区域外不画、全黑检测 |
| `EyeToolTest` | 附件恰好一张 PNG、返回字段、`max_side=0` 不缩放、区域参数错误 |
| `MouseToolTest` | 五个动作的矩阵校验、拒绝越权参数、拖拽顺序（按下→移动→抬起）、滚动先移动 |
| `KeyboardTest` | 文本必填、`\n`/`\t` 走特殊键、repeat 范围、hotkey 传参、间隔取配置 |

`tests/test_visual_operator.py`（注册与契约测试同文件）

| 类 | 覆盖 |
|---|---|
| `RegistrationTest` | 全开注册四个工具；单开只注册一个；全关注册零个；后端不可用仍注册 |
| `SchemaTest` | 四个工具的 `name/label/icon/parameters` 与 `catalog` 风格一致（无 `required` 键，参数是属性映射） |
| `PlanGuardTest` | 假 `live_state` 返回 plan：鼠标键盘抛 `ModeConflict`，截图放行 |
| `LockTest` | 两个线程同时点击时串行；持锁超时抛 `DesktopBusy` |
| `UnavailableTest` | 假平台下四个工具都抛 `DesktopUnavailable`，文案含当前平台 |
| `ManifestTest` | 临时清单 + `PluginHost.load_enabled` 后四个工具在注册表里；卸下后消失 |

测试加载方式：`spec_from_file_location(名称, plugin.py, submodule_search_locations=[插件目录])`，
与 `PluginHost._load_one` 同形，使插件内部的相对导入可用。该加载器放
`tests/testkit.py`，两个测试文件共用。

覆盖率：纯逻辑文件（`config` / `coords` / `keys` / `canvas` / `diff` / 四个工具 / `guard`）
目标 85% 以上；平台后端在 Linux 不被 import，不计入 CI 覆盖率。
本机提交前跑一次 `python scripts/run_coverage.py --print` 核对
`plugins` 组不低于 60%。

平台后端的验证分两层：

- 逻辑层：假 FFI 层（monkeypatch `_api()` 返回假函数表）验证调用序列与参数，
  包括 Retina 换算、双击 clickState、组合键 flags、权限拒绝路径。
- 真机层：Windows 本机按 §12 的手动步骤跑一遍；macOS 需要真机，
  清单见 §12，本轮在 Windows 上无法代跑。

## 11. 门禁与文档

代码：

- `plugins/visual_operator/` 全部文件、两个测试文件、`tests/testkit.py` 的加载器。
- 需要改 `catalog/tools.json`：插件进了 `plugins.ini`，装配集包含这四个工具，
  提交前运行 `python scripts/gen_catalog.py` 重新生成，再跑 `python scripts/check_catalog.py`。

文档：

| 文件 | 改动 |
|---|---|
| `docs/subsystems/visual-operator.md` | 新增：四个工具、坐标约定、配置全表、权限、已知限制 |
| `docs/subsystems/plugins.md` | 内置插件表加一行；启用方式一句话 |
| `docs/subsystems/tools.md` | 插件工具小节补一句这四个工具的存在 |
| `README.md` | 子系统表加链接；用例数按实际同步 |
| `docs/plan/visual-operator.md` | 本方案 |

命令（提交前逐条跑过）：

```
python -m ruff check plugins/visual_operator tests/test_visual_operator.py
python scripts/check_comment_style.py
python scripts/check_architecture_hygiene.py
python scripts/check_catalog.py
python scripts/gen_unit_tests_md.py
python scripts/gen_complexity_md.py
python scripts/ci.py
```

`ci.py` 会重算 README 的用例数，对不上就把数字改成 `check_readme.py` 报的实际值。
`acceptance_web.py` 的插件清单是脚本自建的临时清单，新增的插件目录只会多出一张
未启用的卡片，不影响既有断言。

## 12. 实施顺序

| 步 | 内容 | 完成判据 |
|---|---|---|
| 1 | `config` / `coords` / `keys` / `errors` + 单测 | 三个文件的用例全绿，键码表覆盖校验通过 |
| 2 | `canvas` + 单测 | 缩放、网格、标签、全黑检测的像素级断言通过 |
| 3 | `ports` / `guard` / `input_lock` / 四个工具 + 单测 | 动作矩阵与返回值稳定，不 import 任何平台 API |
| 4 | `backends/win32.py` + 假 FFI 单测 | Linux 上单测全绿；本机手动截图与点击可用 |
| 5 | `plugin.py` + `plugin-config.ini` + 注册/Plan/并发单测 + `plugins.ini` 节 + catalog 重生成 | 临时清单与工程清单都注册出四个工具，`check_catalog` 零漂移 |
| 6 | `backends/macos.py` + 假 FFI 单测 | 换算、双击、flags、权限路径有断言 |
| 7 | 文档、README 数字、全量门禁、本机手动回归 | `ci.py` 全绿，Windows 闭环通过 |

手动回归（Windows，本机）：

1. 启动服务，设置页打开「桌面操作」开关，确认工具列表出现四个工具。
2. `desktop_eye` 整屏截图，核对网格刻度与光标十字位置。
3. `desktop_mouse` 用网格坐标点击记事本窗口标题栏。
4. `desktop_keyboard` 输入中英混排文本，`desktop_eye` 复核屏幕内容。
5. 拖拽一次窗口边缘，滚轮滚动一次，确认无残留按下状态。
6. 切到 Plan 模式，确认鼠标键盘被拒、截图仍可用。

手动回归（macOS，需真机）：

1. 首次截图触发屏幕录制授权，拒绝时错误文案指向正确栏目。
2. 授权后重试截图；Retina 屏上按网格坐标点击，落点与刻度一致。
3. 辅助功能未授权时鼠标键盘报错；授权后双击、拖拽、组合键生效。
4. 副屏（不同缩放）上重复第 2 步，记录偏差并在文档标注。

## 13. 已知限制

| 限制 | 影响 | 处置 |
|---|---|---|
| macOS 无真机验证 | 坐标与权限路径只经假 FFI 验证 | 交付说明标注；真机清单交给用户或在 Mac 上补 |
| 混合 DPI 多屏 | Windows 副屏不同缩放时可能偏移数像素 | 返回值给 `dpi` 与 `note`；文档标注 |
| UIPI 提权窗口 | 管理员程序丢弃输入且不报错 | 文档标注；必要时提示以管理员启动服务 |
| 安全桌面 / 锁屏 | 截图全黑 | 全黑检测给出 `note` |
| 键盘布局 | Unicode 投递对少数游戏 / 自绘控件无效 | 文档标注；这类程序需要真实扫描码 |
| 截图累积 | 会话请求体膨胀 | 文档建议 `image_max` 收紧 |
| 提示词注入 | 模型可能被诱导点击与键入 | Plan 模式拦截、文档风险声明、关掉开关即整体失效 |

## 14. 未纳入

| 能力 | 原因 |
|---|---|
| 窗口枚举 / 按标题聚焦 | Windows 便宜，macOS 需要遍历 `CGWindowListCopyWindowInfo` 的 CF 字典，成本高收益低；模型可以先截图再点一下 |
| 剪贴板读写 | 读剪贴板会把用户无意复制的凭据带进上下文 |
| 指针加速开关 | 改的是注册表里的用户设置，属于系统配置而非一次动作 |
| 画圆轨迹 | 调试与演示用途，模型不需要 |
| 截图在界面里回显 | 工具附件不进事件流；`read_image` 目前也是「模型看得到、界面看不到」，保持一致 |
| 端口级限流 | 会话回合本身有界；先靠 Plan 模式与默认关闭控风险 |
