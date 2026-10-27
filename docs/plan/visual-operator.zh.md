[English](visual-operator.md) | **中文**

# Visual Operator 插件

Visual Operator 在桌面上为 Agent 提供观察与输入能力。基线是四个坐标工具；窗口、应用启动与打开工具作为 P1 交互层一并注册：

| 工具 | 方向 | 能力 |
|---|---|---|
| `desktop_eye` | 观察 | 截取整屏、区域或窗口，叠坐标网格，把图片交给模型；`hover` 可在取图前展开悬停控件。 |
| `desktop_mouse` | 输入 | 移动、点击、拖拽、滚动或查询光标；回执可带 `hit`、`changed` 与可选的 `shot`。 |
| `desktop_keyboard` | 输入 | 输入文本、单键或组合键；可选 `shot` 返回动作后的画面。 |
| `desktop_wait` | 等待 | 等画面区域变化，或窗口出现、消失；条件成立立即返回。 |
| `desktop_window` | 窗口 | 列出、激活、等待、读取顶层窗口；返回稳定 hwnd。 |
| `desktop_app` | 启动 | 启动本地程序并等待主窗口，返回 pid 与 hwnd。 |
| `desktop_open` | 打开 | 用系统默认处理器打开 URL、scheme 或文件。 |
| `desktop_find` | 定位 | 用 UIA 按文字查找控件，返回矩形与可点击点。 |
| `desktop_click_text` | 输入 | 定位文字控件并点击。 |
| `desktop_type_into` | 输入 | 定位文字控件、聚焦并输入。 |
| `desktop_click_region` | 输入 | 用视觉矩形中心点击，减少模型估中心。 |
| `desktop_type_into` | 输入 | 定位文字控件、聚焦并输入。 |
| `desktop_act` | 批量 | 多步执行、断言、失败即停与末帧/失败帧。 |

`desktop_wait` 只读，不占输入锁；窗口与打开工具同样共用已选后端。参数级契约以 [visual-operator.md](../subsystems/visual-operator.zh.md) 为准。

插件提供多个工具，而不是一个多动作工具。鼠标、键盘与看屏各有独立的参数面：坐标、键名、文本与取图选项。合成一个工具就必须描述每个参数在哪个动作下生效，模型错配参数的概率更高。`tools/_params.py` 的动作矩阵直接拒绝属于别的动作的参数，不会静默忽略。

插件在 `plugins.ini` 里有 `[plugin:visual_operator]` 节，默认启用。写入 `enabled = 0` 会保留节并注销工具；重新启用即热装载，不需要重启进程。注册面与平台无关：工具在每台主机上都声明，平台能力在执行期判定。生成的 `catalog/tools.json` 包含全部工具。

插件不贡献面板、端点、上下文注入与开屏脚本。对外可见面只有工具声明与工具卡。

## 1. 不变量

1. 工具注册与平台无关。基线四工具和 L2/L3 工具在所有平台都注册；没有可用后端时在执行期回结构化错误，因此各主机的工具集一致。
2. 只有一个坐标空间：屏幕坐标，Windows 用物理像素，macOS 用显示点。截图矩形、网格刻度、鼠标参数与光标位置都在这个空间里。平台内部的换算只发生在图片加工与几何描述里，不出现在工具契约中。
3. 截图以 `ToolResult.attach` 附件返回，不落盘。macOS 后端为 `screencapture` 写临时文件，并在 `finally` 中删除；不存在需要模型再读图的落盘路径。
4. 图片缩放不改变坐标语义。网格标签默认写屏幕坐标，网格间距也按屏幕坐标计；`grid_unit=image` 显式选择图内像素，鼠标输入必须同时给 `capture_id`。两种坐标空间不会被静默混用。
5. 四类能力各自可关。`eye` / `mouse` / `keyboard` / `wait` 为 `0` 时该工具不注册，而不是注册后拒绝调用。
6. Plan 模式禁止鼠标与键盘输入，以及任何移动光标的动作。不带 `hover` 的截图仍可用，但恢复最小化窗口或给 `activate=true` 仍可能改变窗口状态。只读光标查询与条件等待也可用。
7. 鼠标与键盘动作由同一把进程内锁串行，跨会话也不会交错。一个拖拽不会被另一会话的点击插进来。等锁超过 10 秒抛 `DesktopBusy`。
8. 带目标窗口的输入要求该窗口在前台。鼠标或键盘动作带 `window` / `hwnd` 时，先恢复并置前，再确认它真的到达前台；置前失败则不投递任何输入。
9. 失败必须带可执行动作：缺哪个权限、支持哪些平台、哪个 action 接受当前参数。
10. 插件不 import `agent.app` / `agent.entry`，只依赖 `agent.capabilities`、`agent.mechanisms` 与 `agent.core`。
11. 平台模块只在对应平台导入。`backends/__init__.py` 在 `load_backend()` 里检查 `sys.platform` 后惰性导入；非 Windows 主机不执行 `WinDLL`，非 macOS 主机不加载 CoreGraphics。

## 2. 包结构

```text
plugins/visual_operator/
  plugin.py                    入口：读配置、选后端、按开关注册工具
  plugin-config.ini            插件配置
  plugin-meta.json             插件身份元数据
  config.py                    [config] 解析、默认值与夹取
  capture_store.py             短期截图元数据登记
  coords.py                    屏幕点、矩形、交集与几何比例
  keys.py                      规范键名、别名与组合键校验
  errors.py                    桌面异常层级
  canvas.py                    缩放、坐标网格、光标叠层与 PNG 编码
  diff.py                      两次截图之间的区域差异比较
  ports.py                     后端协议与数据结构
  guard.py                     Plan 模式拒绝
  input_lock.py                进程内输入锁
  backends/__init__.py         按平台惰性选择后端，失败落不可用后端
  backends/win32.py            Windows 截图、激活、输入与落点探测
  backends/win32_common.py     Win32 类型、常量、DPI 与显示器指标
  backends/macos.py            macOS 截图、权限与 CoreGraphics 输入
  backends/_unavailable.py     不支持的平台的明确后端
  tools/__init__.py            工具出口
  tools/_params.py             参数读取与动作矩阵校验
  tools/_windows.py            窗口查找、候选排序与激活
  tools/_capture.py            取图、加工、回执与提示
  tools/eye.py                 DesktopEyeTool
  tools/mouse.py               DesktopMouseTool
  tools/keyboard.py            DesktopKeyboardTool
  tools/wait.py                DesktopWaitTool
```

职责边界：

| 文件 | 只做 | 不做 |
|---|---|---|
| `plugin.py` | 读配置、选一个后端、装配工具 | 平台分支、参数校验 |
| `backends/*` | 调系统 API、点与像素换算、权限探测 | 图片加工、面向用户的文案 |
| `canvas.py` | 缩放、画网格与光标叠层、PNG 编码 | 系统调用、定义坐标语义 |
| `tools/*` | 参数校验、调端口、组回执 | 调系统 API、图片编码 |
| `capture_store.py` | 把 `capture_id` 映射到矩形与图片尺寸 | 保存 PNG 或会话历史 |
| `ports.py` | 协议与数据类 | 任何实现 |

## 3. 工具契约

### 3.1 `desktop_eye`

```python
name = "desktop_eye"
label = "看屏"
icon = "👁"
parallel_safe = False
description = (
    "截取桌面并作为图片直接查看（不是 OCR）。支持整屏、区域与指定窗口，"
    "坐标网格的刻度与 desktop_mouse 使用同一套屏幕坐标。"
    "hover 在取图前移动光标，用来展开悬停后才出现的控件；"
    "annotate 选择标注图、原图或两者。"
)
parameters = {
    "x": {"type": "integer", "description": "区域左上角 x（屏幕坐标）；与 y/width/height 同时给出"},
    "y": {"type": "integer", "description": "区域左上角 y（屏幕坐标）"},
    "width": {"type": "integer", "description": "区域宽度（屏幕坐标）"},
    "height": {"type": "integer", "description": "区域高度（屏幕坐标）"},
    "window": {"type": "string", "description": "窗口标题片段；取该窗口自身内容，遮挡不影响"},
    "hwnd": {"type": "integer", "description": "窗口句柄；与 window 二选一，hwnd 更精确"},
    "activate": {"type": "boolean", "description": "取图前是否把窗口带到前台（默认 false：只恢复）"},
    "hover": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2,
              "description": "取图前把光标移到这里 [x, y]（屏幕坐标），用来展开悬停控件"},
    "hover_path": {"type": "array", "items": {"type": "array", "items": {"type": "integer"},
                                              "minItems": 2, "maxItems": 2},
                   "description": "到 hover 之前先经过的中间点，最多 4 个"},
    "hover_settle_ms": {"type": "integer", "description": "移完光标等界面展开的毫秒数 0–5000；缺省取插件配置"},
    "hover_approach_ms": {"type": "integer", "description": "移到落点用多少毫秒 0–2000（默认 120）；0 = 一次跳变"},
    "hover_wiggle": {"type": "boolean", "description": "到达后是否在落点附近做几次 1–2px 微移动（默认 true）"},
    "grid": {"type": "boolean", "description": "叠加坐标网格与刻度（默认 true）"},
    "grid_step": {"type": "integer", "description": "网格间距（屏幕坐标）20–500；缺省取插件配置"},
    "grid_unit": {"type": "string", "enum": ["screen", "image"],
                  "description": "刻度单位：screen 屏幕坐标（默认）/ image 图内像素"},
    "max_side": {"type": "integer", "description": "长边缩到不超过该像素 0–8192；0 = 不缩放；缺省取插件配置"},
    "annotate": {"type": "string", "enum": ["annotated", "raw", "both"],
                 "description": "annotated 只回标注图（默认）/ raw 只回原图 / both 先标注图后原图"},
}
```

`desktop_eye` 返回 PNG 附件与 JSON 回执。不带 `window` / `hwnd` 时取屏幕合成结果，可能包含遮挡物；带任一参数时取窗口自身内容，遮挡通常不影响结果；窗口不重绘时仍可能回退屏幕截图。`window` 匹配标题片段，`hwnd` 精确指定窗口，两者互斥。

最小化窗口会先恢复。默认 `activate=false` 只恢复，不改变当前前台；`activate=true` 恢复并置前。`restored` 记录是否恢复过；`activated` 只在 `activate=true` 时出现，记录是否真的到了前台。置前失败会写进回执，但已经取到的窗口内容仍然返回。

窗口自身内容在重绘等待后仍是单色时，后端回退到屏幕截图，把 `source` 写成 `screen`，并在 `note` 里说明可能包含遮挡物。回执不会把屏幕回退冒充成窗口内容。

`hover` 在同一个调用内移动真实光标、等界面展开、再截图。拆成“先移动、再截图”通常失败：悬停控件常在 2–3 秒内自动收起，短于一次模型往返。给 `window` / `hwnd` 时，移光标发生在窗口恢复或置前之后、真正取图之前，展开的控件才属于目标窗口。两者都不给且后端有窗口与落点端口时，自动目标是光标下的顶层窗口；窗口取图不受屏幕遮挡影响，但 `max_side` 仍然生效。没有窗口端口时仍按屏幕截图处理。自动目标会以 `window.auto = "hover.hit"` 标明。

光标轨迹不是一次跳变：先经过 `hover_path` 的中间点，再按 `hover_approach_ms` 移到 `hover`，最后在 `hover_wiggle` 开启时做几次 1–2px 微移动。这些都是真实的光标移动，因为自动隐藏控件认连续的 mousemove；一次跳变后静止会被很多界面当成鼠标没动。微动结束后会读回真实光标并收回落点；若目标窗口把光标抢偏且回不去，调用报错，不会把偏移后的位置当成落点。

网格在缩放后绘制，标签在最终尺寸下渲染。默认刻度写屏幕坐标，即使图片被缩小或 `capture` 带负原点也不变。`grid_unit=image` 把刻度切成图内像素，需配合 `capture_id` 使用。光标叠层由插件配置里的 `cursor_mark` 控制，与 `grid` 开关无关。

返回字段：

```json
{
  "platform": "win32",
  "screen": {"x": -1920, "y": 0, "width": 3840, "height": 1080},
  "capture": {"x": -1920, "y": 0, "width": 3840, "height": 1080},
  "source": "window",
  "annotate": "annotated",
  "image": {"width": 3840, "height": 1080, "sent_width": 1920, "sent_height": 540,
            "scale": 2.0, "bytes": 548735},
  "image_to_screen": {"scale_x": 2.0, "scale_y": 2.0, "ox": -1920, "oy": 0},
  "capture_id": "a1b2c3d4e5f6",
  "dpi": "96 dpi",
  "cursor": {"x": 412, "y": 300},
  "grid": {"step": 50, "unit": "screen", "scale": 2.0},
  "window": {"hwnd": 123456, "title": "示例窗口",
             "rect": {"x": -1920, "y": 0, "width": 3840, "height": 1080},
             "minimized": false, "visible": true, "foreground": true},
  "restored": true,
  "note": "窗口原为最小化，已在不置前的情况下恢复后取图。"
}
```

`window`、`restored`、`activated` 只在指定窗口时出现。标题命中多个可见窗口时，`window.matched` 与 `window.alternatives` 一并给出。`hover.hit` 标识光标下的窗口。`capture_id` 是内存引用，不是文件路径；默认 300 秒过期，每个插件实例最多保留 64 条，且只对当前会话有效。`note` 只在需要行动时出现：缩放过、恢复或置前过、回退屏幕、画面全黑、多屏缩放不一致、标题命中多个窗口、悬停层与取图窗口不同，或自动选择了悬停目标。

校验：

- `x`、`y`、`width`、`height` 四个一起给或一起省略。宽高必须为正。区域超出屏幕会裁剪；与屏幕无交集则报错并附屏幕矩形。
- `window` 与 `hwnd` 互斥。`hwnd` 必须是正整数；`window` 必须是非空片段。
- `activate` 只对 `window` / `hwnd` 有意义；整屏取图给它会报错。
- 单张截图超过 4000 万像素时拒绝，并提示改用更小的区域；检查在渲染前完成。
- `hover_path` 必须与 `hover` 一起给，可含 1–4 个点，所有点都必须在虚拟屏内；`hover` 也必须在屏幕内。
- `grid_step` 为 20–500，`max_side` 为 0–8192，`hover_settle_ms` 为 0–5000，`hover_approach_ms` 为 0–2000。未知参数直接拒绝。

#### 窗口取图与置前

| 窗口状态 | `activate=false`（默认） | `activate=true` |
|---|---|---|
| 正常显示，包括被遮挡 | 不改变窗口状态，取窗口自身内容 | 先置前，再取图 |
| 最小化 | 用 `SW_SHOWNOACTIVATE` 恢复后取图，当前前台不变 | 恢复并置前，等价于点任务栏 |

恢复是必须的：最小化窗口的矩形在屏幕外，取不到有效内容。后端恢复后等待真实重绘，并在 1.2 秒内重试；画面仍为单色时回退屏幕截图。显式置前失败会写 `activated=false`；窗口内容可用时仍返回图片，并用 `note` 说明窗口不在前台。

### 3.2 `desktop_mouse`

```python
name = "desktop_mouse"
label = "鼠标"
icon = "🖱"
description = (
    "操作鼠标：move 移动 / click 点击 / drag 拖拽 / scroll 滚动 / cursor 查询光标。"
    "默认坐标是屏幕坐标；给 capture_id 时按截图内的像素坐标解释，由工具完成换算。"
    "给 window / hwnd 时先恢复并置前；置前失败则不投递输入。"
)
parameters = {
    "action": {"type": "string", "enum": ["move", "click", "drag", "scroll", "cursor"]},
    "x": {"type": "integer", "description": "x；默认屏幕坐标，给 capture_id 时为图内像素"},
    "y": {"type": "integer", "description": "y；默认屏幕坐标，给 capture_id 时为图内像素"},
    "to_x": {"type": "integer", "description": "拖拽终点 x；坐标空间同 x"},
    "to_y": {"type": "integer", "description": "拖拽终点 y；坐标空间同 y"},
    "space": {"type": "string", "enum": ["screen", "image"],
              "description": "坐标空间：screen 屏幕（默认）/ image 图内像素（需 capture_id）"},
    "capture_id": {"type": "string", "description": "desktop_eye 回执里的 capture_id"},
    "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "按键（默认 left）"},
    "count": {"type": "integer", "description": "点击次数 1–3（默认 1）"},
    "amount": {"type": "integer", "description": "滚动量 -50 ~ 50，正数向下或向右"},
    "horizontal": {"type": "boolean", "description": "横向滚动（默认 false）"},
    "duration_ms": {"type": "integer", "description": "移动或拖拽时长 0–5000；0 = 一次跳变"},
    "window": {"type": "string", "description": "目标窗口标题片段；先置前再动作"},
    "hwnd": {"type": "integer", "description": "目标窗口句柄；与 window 二选一"},
    "shot": {"type": "boolean", "description": "动作完成后在同一次调用内截图（默认 false）"},
    "shot_region": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4,
                    "description": "截图区域 [x, y, width, height]（屏幕坐标）"},
    "shot_max_side": {"type": "integer", "description": "shot 的长边上限；缺省取插件配置"},
}
```

动作矩阵：

| `action` | 必填 | 该动作允许的可选参数 | 拒绝 |
|---|---|---|---|
| `move` | `x`、`y` | `duration_ms` | `to_x`、`to_y`、`amount`、`button`、`count`、`horizontal` |
| `click` | 无；省略 `x`、`y` 时用当前光标 | `x`、`y`、`button`、`count` | `to_x`、`to_y`、`amount`、`horizontal`、`duration_ms` |
| `drag` | `x`、`y`、`to_x`、`to_y` | `button`、`duration_ms` | `amount`、`count`、`horizontal` |
| `scroll` | `amount` | `x`、`y`、`horizontal` | `to_x`、`to_y`、`button`、`count`、`duration_ms` |
| `cursor` | 无 | 无 | 其余动作参数，以及 `space`、`capture_id` 和整组 `shot` |

`window` / `hwnd` 对所有动作都接受；`cursor` 不产生输入，因此不激活窗口。非 `cursor` 动作还接受 `space`、`capture_id`、`shot`、`shot_region`、`shot_max_side`。参数不匹配时抛 `ValueError`，点名参数与接受它的 action。

坐标：

- 默认使用屏幕坐标。给 `capture_id` 即切到那张截图的图内坐标；`space=image` 是同一意思的显式写法。`capture_id` 配 `space=screen` 会报错。`capture_id` 不存在、过期或不属于当前会话时直接报错，不回退到屏幕坐标。
- 图内坐标必须给点，且必须落在图片边界内。换算为 `screen_x = capture.x + image_x * capture.width / image.width`，y 同理。
- `click` / `scroll` 可以省略 `x`、`y`，此时作用在当前光标位置；`move` / `drag` 必须给点。图内坐标不会从当前光标推断。
- `amount` 非零，范围 -50 到 50；正数向下或向右；`horizontal` 选择横轴。
- `duration_ms` 为 0–5000。`move` 默认 0（一次跳变），`drag` 默认 300。

返回：

```json
{"action": "click", "space": "screen", "cursor": {"x": 300, "y": 400},
 "screen": {"x": 0, "y": 0, "width": 2560, "height": 1440},
 "hit": {"hwnd": 123456, "class": "ExampleClass", "title": "示例窗口"},
 "changed": 0.34, "changed_scope": "point_200",
 "window_changed": {"changed": true, "navigated": true}}
```

```json
{"action": "drag", "space": "screen", "cursor": {"x": 300, "y": 400},
 "screen": {"x": 0, "y": 0, "width": 2560, "height": 1440}}
```

```json
{"action": "scroll", "space": "screen", "cursor": {"x": 800, "y": 500},
 "screen": {"x": 0, "y": 0, "width": 2560, "height": 1440}}
```

```json
{"action": "cursor", "cursor": {"x": 412, "y": 300},
 "screen": {"x": 0, "y": 0, "width": 2560, "height": 1440}}
```

`click`、`drag`、`scroll` 在后端支持时额外回执三份证据：

- `hit` 给出落点下的窗口句柄、类名与所属顶层窗口标题；不支持落点探测时省略。
- `changed` 是落点周围 200×200 区域的像素变化比例，范围 0–1；`changed_scope` 固定为 `point_200`。0 只说明落点局部没变，不代表没点中。首次采样低于 0.005 时，等 250ms 再采一次；`changed` 取较大值，`changed_late` 与 `changed_note` 描述后采结果。
- `window_changed` 对比动作前后的顶层窗口。`opened` / `closed` 各最多列 3 条，超出部分计入 `opened_more` / `closed_more`；有新窗口出现或消失、或落点窗口改变时，`changed=true`。若落点局部没变而窗口层变了，`navigated=true`，这是点进详情页或新窗口的正解。

`shot=true` 在同一次调用内截图。默认拍落点所在的顶层窗口（`shot_of: "hit"`），不按标题重新解析；显式给 `window` / `hwnd` 时以显式参数为准（`shot_of: "window"` / `"hwnd"`），两者都没有且无落点与焦点时才拍整屏。回图回执复用 `desktop_eye` 的辅助线，动作结果收在 `performed` 字段。默认回图跟随落点窗口、且它与置前窗口不是同一个时，`note` 写明两个 hwnd。`move`、`click`、`drag`、`scroll` 可用 `shot`；`cursor` 只读，拒绝它。

拖拽的按下与松开必须成对：后端在 `finally` 中发送松开事件，移动抛错也不会留下按下的键。

### 3.3 `desktop_keyboard`

```python
name = "desktop_keyboard"
label = "键盘"
icon = "⌨"
description = (
    "操作键盘：type 输入 Unicode 文本 / key 按单键 / hotkey 按组合键。"
    "给 window / hwnd 时先恢复并置前，再输入；置前失败则不投递输入。"
)
parameters = {
    "action": {"type": "string", "enum": ["type", "key", "hotkey"]},
    "text": {"type": "string", "description": "action=type 时要输入的文本"},
    "key": {"type": "string", "description": "action=key 时的键名，如 enter / esc / f5 / a"},
    "keys": {"type": "string", "description": "action=hotkey 时的组合键，如 \"ctrl+c\" / \"alt+tab\""},
    "repeat": {"type": "integer", "description": "key / hotkey 的重复次数 1–20（默认 1）"},
    "window": {"type": "string", "description": "目标窗口标题片段；先置前再输入"},
    "hwnd": {"type": "integer", "description": "目标窗口句柄；与 window 二选一"},
    "shot": {"type": "boolean", "description": "完成输入后在本次调用内截图（默认 false）"},
    "shot_max_side": {"type": "integer", "description": "shot 的长边上限；缺省取插件配置"},
}
```

`type` 按 Unicode 单位逐个投递，不受当前键盘布局影响。换行与回车走 Enter，制表符走 Tab。`key` 按一次规范键。`hotkey` 按 2–4 个键，修饰键按给定顺序按下，再按逆序抬起。

返回：

```json
{"action": "type", "chars": 12}
{"action": "key", "key": "enter", "repeat": 1}
{"action": "hotkey", "keys": ["ctrl", "c"], "repeat": 1}
```

`window` / `hwnd` 会追加 `focus` 回执；置前失败会在任何按键投递前中止。带 `shot=true` 时，返回体是取图回执，键盘结果收在 `performed`；取图目标优先使用显式 `window` / `hwnd`，否则取整屏。

键名：

- 规范名：`enter`、`tab`、`esc`、`space`、`backspace`、`delete`、`insert`、`home`、`end`、`pageup`、`pagedown`、`left`、`up`、`right`、`down`、`capslock`、`f1`–`f20`、`ctrl`、`shift`、`alt`、`win`、`cmd`，以及单个 ASCII 字母、数字与 `-`、`=`、`[`、`]`、`;`、`'`、`,`、`.`、`/`、`\`、`` ` `` 等标点键。
- 别名：`return` → `enter`、`escape` → `esc`、`control` → `ctrl`、`option` → `alt`、`command` / `meta` / `super` → `cmd`、`windows` → `win`、`page_up` / `pgup` → `pageup`、`page_down` / `pgdn` → `pagedown`，以及常见的标点别名。
- 未知键名抛 `ValueError`，附可用名称的短摘要；不会回退成按第一个字符。
- `keys` 的 schema 声明为字符串，按 `+` 或 `,` 拆开，因此 `"ctrl+c"` 与 `"ctrl,c"` 等价。解析层也接受数组，但对外契约以字符串为准。
- 组合键必须含 2–4 个键，且至少一个非修饰键；全是修饰键则报错。

整数参数接受数字字符串（如 `"300"`），拒绝布尔与浮点。小数抛 `ValueError`，不会静默截断。

### 3.4 `desktop_wait`

| 参数 | 含义 |
|---|---|
| `until` | `change` 等区域变化；`window_appears` 等窗口出现；`window_disappears` 等窗口消失。 |
| `window` | 窗口标题片段。`change` 时用来限定比较区域；`window_appears` / `window_disappears` 时必填。 |
| `hwnd` | 窗口句柄。`change` 时可替代 `window`；窗口出现或消失的等待按标题判断。 |
| `x`、`y`、`width`、`height` | `change` 的比较区域；四个一起给或一起省略。省略时用窗口矩形或整屏。 |
| `timeout_ms` | 最长等待 50–60000，默认 3000。 |
| `interval_ms` | 轮询间隔 50–2000；缺省取插件配置。 |
| `threshold` | `change` 的判定阈值 0–1，默认 0.02；越小越敏感。 |

`until=change` 先取一张基线图，再比较同一区域的后续截图。它使用屏幕合成结果，不激活窗口；窗口最小化时直接报错，不面对屏幕外矩形白等到超时。`until=window_appears` / `window_disappears` 按标题查可见顶层窗口。平台没有窗口端口时抛 `DesktopUnavailable`。

超时不是错误：返回 `satisfied: false` 与最后一次实测值，由调用方决定换动作还是延长等待。等待开始时条件已经成立时，回执带 `already`，并由 `note` 说明没有实际等待。

`desktop_wait` 只读：不占输入锁、不移动光标，Plan 模式下可用。

回执示例：

```json
{"until": "change", "satisfied": true, "waited_ms": 420,
 "changed": 0.18, "threshold": 0.02,
 "capture": {"x": 100, "y": 100, "width": 800, "height": 600}}
```

```json
{"until": "window_appears", "satisfied": false, "waited_ms": 3000,
 "note": "等待超时，指定标题的窗口仍未出现。"}
```

## 4. 配置

`plugins/visual_operator/plugin-config.ini`：

```ini
[config]
eye = 1
mouse = 1
keyboard = 1
wait = 1
max_side = 1920
grid_step = 50
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
| `max_side` | 1920 | 0–8192 | 发出图片的长边上限；0 = 不缩放 |
| `grid_step` | 50 | 20–500 | 网格间距（屏幕坐标） |
| `cursor_mark` | 1 | 0/1 | 是否画光标十字与坐标标签 |
| `settle_ms` | 60 | 0–2000 | 鼠标或键盘动作后的停顿 |
| `type_interval_ms` | 12 | 0–200 | 逐字输入的字符间隔 |
| `hover_settle_ms` | 250 | 0–2000 | 悬停移动后等界面展开 |
| `hover_approach_ms` | 120 | 0–2000 | 悬停移动时长；0 = 一次跳变 |
| `hover_wiggle` | 1 | 0/1 | 是否在落点附近做 1–2px 微移动 |
| `wait_interval_ms` | 200 | 50–2000 | `desktop_wait` 的默认轮询间隔 |

单次调用参数覆盖对应配置。取图主要覆盖 `grid_step`、`max_side`、`hover_settle_ms`、`hover_approach_ms`、`hover_wiggle`；输入工具使用各自的时间配置，`desktop_wait` 使用 `interval_ms` 参数，缺省取配置值。

`config.py` 的解析规则：

- 文件缺失或没有 `[config]` 节时全部取默认值。
- 整数键不是整数时取默认值；越界时夹到最近边界。
- 开关键接受 `1` / `0`、`true` / `false`、`yes` / `no`、`on` / `off`，大小写不敏感；其余取默认值。
- 未知键忽略。文件里的注释与其它节不影响装载。
- 解析与回退不写日志，配置错误不阻断插件装载。生效值可从 `desktop_eye` 回执的 `grid` 与 `image` 字段反查。

## 5. 坐标、图像与缩放

### 5.1 坐标空间

- 屏幕坐标原点在虚拟桌面左上角；多屏时任一坐标都可能为负。Windows 用物理像素，macOS 用全局显示点。
- `screen` 是虚拟桌面矩形，`capture` 是本次实际截取的矩形。屏幕区域在截取前裁到虚拟桌面内，窗口区域再裁一次到窗口内。
- 网格标签默认写屏幕坐标，按 `screen.x + 偏移` 计算，不是图片像素。
- 鼠标参数使用同一屏幕空间，各后端按该空间投递。切到图内坐标时，由 `capture_id` 提供到屏幕坐标的映射。

### 5.2 加工顺序

```text
屏幕或窗口截取
  -> 窗口恢复/置前，然后可选的悬停移动
  -> 裁到请求区域
  -> 全黑检测
  -> 按 max_side 缩放长边（LANCZOS）
  -> 在最终画布上叠网格与光标
  -> PNG 编码
  -> ToolResult.attach
```

全黑检测只生成提示，不拒绝截图；回执没有单独的 blank 字段。窗口取图可能在加工前回退到屏幕截图，此时 `source` 反映回退来源。

叠层在缩放后应用，标签在最终尺寸下渲染，不会因二次缩放变模糊。屏幕坐标到叠层像素的映射是：

```text
image_x = (screen_x - capture.x) * sent_width / capture.width
image_y = (screen_y - capture.y) * sent_height / capture.height
```

反向映射由回执里的 `image_to_screen.scale_x`、`scale_y`、`ox`、`oy` 给出，供排障与界面展示；使用屏幕坐标或网格标签的调用方不需要再做乘法。

### 5.3 网格与光标叠层

- 每 `grid_step` 个屏幕坐标画一条细线；每第 5 条为主线并带刻度。竖线在上下边缘各标一次，横线在左右边缘各标一次；标签被夹在图片内。
- 细线间距小于 8 个图片像素时只画主线。否则密集网格会糊成一层色块。
- 细线为蓝色，宽 1–2 像素；主线为红色，宽 2–3 像素。刻度使用内嵌字体并加深色描边，字号随图宽在 8–18 像素之间变化。
- 仅当 `cursor_mark` 开启且光标落在本次截图内时绘制光标叠层；它与 `grid` 开关无关。
- 叠层由短亮绿十字、黑色光晕、白色分隔、细圆环与写有坐标的 `CURSOR` 标签组成。十字中心留空，落点像素仍然可见。
- 短边小于 90 像素时不画光标标签，坐标可从回执 `cursor` 读取；短边小于 140 像素时使用紧凑标签，省略 `CURSOR` 标题与深色底。
- `grid_unit=image` 时，网格与光标标签都写图内像素。`desktop_mouse`、`desktop_click_region` 或 `desktop_type_into` 需要同时给 `capture_id` 与 `space=image`；同一次动作不得混用两种坐标。

### 5.4 体积与历史

- 单张截图超过 4000 万像素时拒绝，并提示改用更小区域。检查在渲染前完成；屏幕截图在分配位图前拒绝，窗口截图可能已经取到图后才检查。
- 返回的截图是工具结果里的图片附件，会进入会话历史并可能被后续请求重放。重放由 `[context]` 配置限制：`image_turns` 控制最近多少个带图用户轮进入请求，`image_max` 限制单次请求的图片总数（工具附件也计入）。两者与截图尺寸上限相互独立。
- `max_side` 只改变发出的图片，不改变坐标契约：除非显式 `grid_unit=image`，网格标签仍是屏幕坐标。`image.scale` 是原图宽除以实发宽；发生缩放时回执给出换算示例。

## 6. 平台后端

### 6.1 公共契约

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

`Screenshot` 带 `png`、`rect`、`source`、`restored`、`foreground` 与 `activation`。`Backend` 是冻结数据类，含 `platform`、`screen`、`mouse`、`keyboard`，以及可选的 `windows` 与 `hit`。`windows` 提供窗口查找、激活与窗口取图；`hit` 提供落点探测。缺少对应端口时，相关回执字段省略，或操作抛 `DesktopUnavailable`。

`load_backend()` 按平台惰性选择：

```python
if sys.platform == "win32":
    from .win32 import Win32Backend
    return Win32Backend()
if sys.platform == "darwin":
    from .macos import MacOSBackend
    return MacOSBackend()
return unavailable_backend()
```

后端装配失败会被捕获，向 stderr 写一条诊断，然后退到不可用后端。它的端口在每个方法上抛 `DesktopUnavailable`，消息里带当前平台与支持的平台。工具仍然注册，因此缺系统库只改变执行结果，不改变工具表。

### 6.2 Windows

| 能力 | 实现 |
|---|---|
| DPI 感知 | `SetProcessDpiAwarenessContext(-4)`，再 `shcore.SetProcessDpiAwareness(2)`，再 `SetProcessDPIAware()`；宿主已声明时沿用宿主选择 |
| 虚拟屏 | `SM_XVIRTUALSCREEN`、`SM_YVIRTUALSCREEN`、`SM_CXVIRTUALSCREEN`、`SM_CYVIRTUALSCREEN` |
| 屏幕截图 | `GetDC(NULL)` → 兼容 DC 与位图 → `BitBlt` 带 `SRCCOPY` 与 `CAPTUREBLT` → 32 位 `BI_RGB`、负高度取顶朝下的 `GetDIBits` → Pillow `BGRX` |
| 窗口截图 | `GetWindowDC` → `PrintWindow(PW_RENDERFULLCONTENT)` → `GetDIBits`；等待非单色帧最多 1.2 秒；仍为单色则回退屏幕截图 |
| 恢复 | 仅取图时 `ShowWindow(SW_SHOWNOACTIVATE)`；需要激活时用 `SW_RESTORE` |
| 激活 | 先 `SwitchToThisWindow`，再以 `SetForegroundWindow` 兜底；成败由 `GetForegroundWindow` 与 `IsIconic` 判断，不看 API 返回值 |
| 光标 | `GetCursorPos` |
| 移动 | `SetCursorPos`；`duration_ms > 0` 时在 `duration_ms` 内分最多 120 步插值 |
| 点击 | `SendInput` 按下与抬起；连击间隔 20ms |
| 拖拽 | 起点落位、按下、插值移动到终点、`finally` 抬起 |
| 滚轮 | `MOUSEEVENTF_WHEEL` 或 `MOUSEEVENTF_HWHEEL`；纵向先取反再乘 120 |
| 键盘 | `SendInput` + `KEYEVENTF_UNICODE`；功能键与命名键用虚拟键码；组合键按顺序按下、逆序抬起 |
| 落点探测 | `WindowFromPoint`、`GetAncestor(GA_ROOT)`、`GetClassNameW`；取不到时省略 `hit`，不编造结果 |
| 窗口清单 | `EnumWindows` 枚举可见顶层窗口；按前台 → Z 序 → 面积排序，跳过工具窗与屏幕外辅助窗 |

用 `SetCursorPos` 而不是归一化的 `MOUSEEVENTF_ABSOLUTE`：后者不带 `VIRTUALDESK` 时只覆盖主屏，归一化在混合 DPI 下还会引入误差。`SetCursorPos` 直接吃虚拟桌面像素坐标。

已知边界：更高完整性级别的窗口（例如以管理员运行的程序）会静默丢弃普通进程的 `SendInput`；锁屏与安全桌面得到全黑截图；混合 DPI 多屏仍可能有少量坐标偏移。

### 6.3 macOS

| 能力 | 实现 |
|---|---|
| 屏幕录制权限 | `CGPreflightScreenCaptureAccess()`；符号缺失视为不适用 |
| 辅助功能权限 | `AXIsProcessTrusted()` |
| 截图 | `/usr/sbin/screencapture -x -t png -R x,y,w,h <临时文件>`；读入后 `finally` 删除临时文件 |
| 几何 | `CGGetActiveDisplayList` + `CGDisplayBounds`（点）+ `CGDisplayPixelsWide` / `CGDisplayPixelsHigh`（像素） |
| 光标 | `CGEventCreate(nil)` + `CGEventGetLocation` + `CFRelease` |
| 移动、点击、拖拽 | `CGEventCreateMouseEvent` + `CGEventPost(kCGHIDEventTap)`；连击递增 `kCGMouseEventClickState` |
| 滚轮 | `CGEventCreateScrollWheelEvent`，单位为行；正数向下或向右 |
| 键盘 | `CGEventCreateKeyboardEvent`；文本用 `CGEventKeyboardSetUnicodeString`；组合键用 `CGEventSetFlags` 设 command、shift、option、control 掩码 |

截图是物理像素，事件坐标是显示点，工具契约统一用点。`geometry()` 报 `pixel_ratio = 像素宽 / 点宽`；多屏比例不一致时置 `mixed_scale=true` 并加提示。`screencapture -R` 按点给区域，输出尺寸是点乘以显示器比例。叠层按“截图矩形 → 实发图片尺寸”的比例映射，标签与光标位置不依赖显示器倍率。

macOS 后端只提供屏幕、鼠标与键盘端口，没有窗口端口与落点端口。`window` / `hwnd`、窗口级 `desktop_wait` 条件与窗口激活都会抛 `DesktopUnavailable`。输入只会进入当前前台应用，调用方需要通过其它方式把目标应用带到前台。

屏幕录制与辅助功能检查失败时抛 `DesktopPermissionDenied`，文案指向对应的系统设置栏目。缺屏幕录制权限时截图不可用；缺辅助功能权限时输入事件不可用。

## 7. 安全与门控

| 机制 | 位置 | 行为 |
|---|---|---|
| Plan 模式 | `guard.py`，由各工具的执行路径调用 | 拒绝输入与移动光标的动作，抛 `ModeConflict`；`desktop_mouse action=cursor` 只读，在检查前返回；`desktop_eye activate=true` 不在该门控内。 |
| 能力开关 | `plugin.py` | 每个工具只在对应 `[config]` 开关开启时注册；关闭即注销。 |
| 输入串行 | `input_lock.py` | 鼠标与键盘共用一把 `threading.Lock`；10 秒拿不到抛 `DesktopBusy`。 |
| 目标断言 | `tools/_windows.py` | 带窗口的鼠标或键盘动作先激活并验证前台；失败即中止，不投递输入。 |
| 默认启用 | `plugins.ini` | 插件有清单节；写 `enabled=0` 保留清单节并移除工具。 |
| 截屏 | 无额外门控 | Plan 模式下不带 `hover` 的截图可用；最小化目标会被恢复，`activate=true` 仍可能把窗口带到前台。 |

Plan 模式逐操作判定：

| 操作 | Plan 模式 |
|---|---|
| 不带 `hover` 且不带 `activate=true` 的 `desktop_eye` | 允许；最小化目标仍可能被恢复 |
| 带 `activate=true`、不带 `hover` 的 `desktop_eye` | 允许，但目标激活不受门控 |
| 带 `hover` 的 `desktop_eye` | 拒绝：调用会移动真实光标 |
| `desktop_mouse action=cursor` | 允许 |
| 其它 `desktop_mouse` 动作 | 拒绝 |
| 所有 `desktop_keyboard` 动作 | 拒绝 |
| `desktop_wait` | 允许：只读，不移动光标，不占输入锁 |

Plan 检查发生在任何输入事件之前。对鼠标动作，它还发生在窗口激活之前；不会为了让调用发现“输入被禁止”而先把目标窗口拉到前台。不带 `window` / `hwnd` 时，鼠标与键盘作用于当前前台，无法做目标断言。宿主拿不到会话 live state 时，插件没有模式可查，因此不拦截；正常装配会在执行期提供状态。

不设快捷键黑名单。键盘本身就能敲出任意命令，包括先打开系统界面再输入；黑名单挡不住这条路，只会制造一层看起来安全的假象。真正的边界是插件是否启用、会话是否在 Plan 模式，以及是否有操作者在场。

启用后，任何能影响模型输入的内容——网页、文件、工具结果——都可能变成真实的点击与键入。这与命令执行属于同一风险量级，只是入口不同。启用插件是授予桌面控制权，不是对内容做信任判断。

截图可能包含凭据、个人数据或其它敏感内容，并会作为附件发给模型；插件不做脱敏。可用的控制是各能力开关、`[context]` 的图片重放上限，以及 Plan 模式对光标移动的拦截；Plan 模式本身不拦截截图。

## 8. 错误

| 异常 | 触发 | 文案要求 |
|---|---|---|
| `DesktopUnavailable` | 平台不支持、缺图片依赖，或后端装配失败 | 按情况说明缺失的依赖、当前平台或支持的平台 |
| `DesktopPermissionDenied` | macOS 缺屏幕录制或辅助功能权限 | 点名系统设置栏目与需要授权的程序 |
| `ScreenCaptureFailed` | `BitBlt`、`PrintWindow`、`screencapture` 或图片解码失败 | 带系统错误或进程退出状态；不返回空图 |
| `DesktopBusy` | 输入锁被占用 10 秒 | 说明另一个桌面输入动作未结束 |
| `ModeConflict` | Plan 模式下的鼠标或键盘输入 | 与内置命令门控同一句式 |
| `ValueError` | 参数缺失、越界或动作矩阵不符；坐标在屏幕或图片外；`capture_id` 无效或过期 | 点名参数与可用值或 action |
| `DesktopError` | 其它系统调用失败、没有活动显示器，或目标窗口无法激活 | 带失败操作与可重试的上下文 |

工具管道把这些异常转成结构化的 `ok=false` 结果；单步失败不终止回合。错误文本不出现 Python 堆栈或仓库内部路径。

## 9. 验证

| 范围 | 必须覆盖的行为 |
|---|---|
| 注册 | 全开时所有工具都注册；只开一个开关时只注册一个；全关时零个；后端不可用时仍注册全部工具。 |
| 取图 | 附件中的 PNG 数量正确；区域裁剪、窗口选择、屏幕回退与超大区域拒绝都有覆盖；`annotate` 顺序正确。 |
| 坐标与网格 | 负原点与缩放下的图内坐标换算正确；网格与光标像素落在预期位置；标签遵守尺寸阈值；全黑检测有效。 |
| 鼠标与键盘 | 动作矩阵拒绝越权参数；拖拽顺序为按下 → 移动 → 抬起；滚动方向与契约一致；键名、别名、组合键形态与文本编码都有覆盖。 |
| 等待与安全 | 画面变化与窗口条件命中即返回；超时返回 `satisfied=false`；Plan 模式拦截输入与悬停，光标查询、截图与等待可用，但取图激活不受门控；输入锁串行并在超时后报错。 |
| 后端 | 非本机平台通过假 FFI 验证调用序列与权限失败；真实桌面行为需在每个支持的平台验证。 |

测试面不得在非桌面主机上移动真实光标或注入真实按键。后端通过端口替换；测试使用合成图片与假窗口记录。

## 10. 已知限制

| 限制 | 影响 | 处置 |
|---|---|---|
| macOS 没有窗口与落点端口 | 窗口取图、窗口级等待与窗口激活不可用；输入只进当前前台应用 | 报 `DesktopUnavailable`；改用整屏或区域截图，并用其它方式切换应用 |
| 混合 DPI 多屏 | 副屏缩放不同时可能有少量坐标偏移 | 回执给 `dpi` 与 `mixed_scale`，并加提示 |
| 更高完整性级别的窗口 | 系统静默丢弃输入 | 文档标注；必要时以管理员启动服务 |
| 安全桌面或锁屏 | 截图全黑 | 全黑检测加提示；仍返回该帧 |
| 键盘布局与扫描码 | 少数游戏或自绘控件只认扫描码，Unicode 注入无效 | 文档标注；这类程序需要其它输入路径 |
| 截图累积 | 重放全屏图片会增大请求体 | `[context]` 的 `image_turns` 与 `image_max` 限制重放 |
| Plan 模式下的窗口激活 | `desktop_eye activate=true` 会在 Plan 模式下把窗口带到前台，因为门控只覆盖光标移动与输入，不覆盖取图激活 | 前景不应变化时避免这个组合；改用不带激活的取图，或离开 Plan 模式后显式激活 |
| 提示词注入 | 观察到的内容可能诱导点击与键入 | Plan 模式、各能力开关、关闭插件与操作者复核 |
| 进程内输入锁 | 不协调其它进程或真人同时操作键鼠 | 会话操作桌面期间按独占处理 |
| 悬停不受输入锁保护 | `desktop_eye hover` 移动光标时不占输入锁，可能与另一会话的拖拽或鼠标动作交错 | 不要把悬停取图与并发输入混用；在会话层串行 |
| 窗口内容回退 | 目标不重绘时，屏幕截图可能包含遮挡物 | `source=screen` 与提示会把它和窗口内容区分开 |

## 11. 未纳入

| 能力 | 原因 |
|---|---|
| OCR 或文字识别 | 模型可以直接读截图。OCR 增加延迟，还会把取错窗口或缩放不当的问题掩盖成识别错误。 |
| 剪贴板读写 | 读剪贴板会把用户为别的目的复制的凭据带进模型上下文。 |
| 指针加速设置 | 改的是操作系统里的用户偏好，不是一次桌面动作。 |
| 圆形指针轨迹 | 用于演示，不是模型任务需要的能力。 |
| 端口级限流 | 会话回合本身有界。Plan 模式与能力开关提供主要控制。 |
