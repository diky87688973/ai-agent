[English](visual-operator-interaction.md) | **中文**

# 桌面操作交互层

## 1. 结论

桌面工具面暴露的是坐标原语：窗口由模型自己挑，控件位置由模型自己估，动作有没有生效要从下一张截图反推。真实任务里这会变成反复抢前台、从缩放图上估坐标、把字打进不是目标的窗口。造成这个循环的是三个缺口：输入没有前置校验、动作没有回执、没有窗口层。

本方案把工具面从坐标原语抬到意图动词，再用带断言的批量收口。

观测与输入对前台的要求不同，这条差异决定了整体设计：

- 窗口内容与窗口结构都可以在目标不位于前台时读取：被遮挡的窗口返回自身内容，最小化窗口先恢复再取图。两种情况都不要求目标持有前台。
- 输入只会打到前台窗口。目标被别的窗口盖住时，字会落进持有焦点的那个窗口。
- `SetForegroundWindow` 不是成功信号：目标仍最小化时它也可能返回 `true`，`GetForegroundWindow()` 也会指向同一个目标。可用的信号是随后能否取到目标内容。

因此，改变桌面的动作在同一次调用内回图（`shot`），激活的成败由随后能否取到内容判定，而不是由 API 返回值判定。

三层，按顺序落地，不合并：

| 层 | 内容 | 解决的问题 |
|---|---|---|
| L1 回执 | 改变桌面的动作在平台可观测时返回 `focus` / `hit` / `changed`；输入类动作可回图（`shot`） | 点错立刻可见，不用靠下一张截图反推 |
| L2 语义动词 | `desktop_window` / `desktop_find` / `desktop_click_text` / `desktop_click_region` / `desktop_type_into` / `desktop_app` / `desktop_open` | 定位不再由模型估读 |
| L3 批量管道 | `desktop_act`：多步一次调用，每步带 `expect`，失败即停 | 稳定任务的往返从 N 降到 1 |

`docs/plan/visual-operator.md` 的决定不变：四个基线工具各自独立，不把 15 个动作塞进一个 `desktop_action`。L2 动词是 L0 调用的组合；L3 是独立的新工具，不是把参数矩阵摊平。基线参数语义不变，新增参数全部可选。

> **工具面不接 OCR。** 模型自己看截图，截图就是它的输入。读不出字时，问题在拍到的窗口、图的缩放或没展开的控件，不在缺少识别层。定位只走 UIA 与坐标。

## 2. 交互缺口

前三个是结论中的结构性缺口；后三个是另外的交互成本。

| # | 缺口 | 影响 | 改造 |
|---|---|---|---|
| 1 | 输入没有前置条件 | 目标窗口与落点都不校验；字可能落进别的窗口 | 动作回执与批量 `expect` |
| 2 | 没有窗口层 | 观测与动作都对着整屏，遮挡与层叠决定看到什么、点中什么 | `desktop_window` 与窗口级截图 |
| 3 | 动作没有回执 | 窗口被关掉只能从之后的截图反推 | `focus` / `hit` / `changed` / `window_changed` |
| 4 | 坐标从缩放图上估读 | 小控件丢失了用于辨认的像素，估出的中心落在控件之外 | 结构化定位（UIA 矩形）；视觉只做确认 |
| 5 | 一动作一往返，无等待语义 | 动作后的截图拍到的是上一帧 | `shot` 与条件等待 |
| 6 | 观测冗余 | 一回合里大多数帧没有信息增量 | diff、去重与局部裁剪 |

四条约束：

- **观测不要求前台。** 窗口内容来自窗口自身的重绘，遮挡不会改变拍到的内容。最小化窗口用 `SW_SHOWNOACTIVATE` 恢复，会触发真实重绘，但不改变前台窗口与键盘焦点。把窗口亮到前台是另一个显式选择。
- **输入要求目标在前台。** 置前失败时拒绝投递，回执写明实际持有前台的那个窗口。
- **成功要有证据，不能只靠声明。** 每次写入都以像素或结构 diff 校验；provider 的读回值永远不算证据。
- **窗口身份是结果的一部分。** 光标下的窗口、接收点击的窗口、被截图的窗口、被激活的窗口可以是四个不同的句柄。

截图的缩放并不固定：整屏图通常缩到 `max_side`，窗口图往往不到上限、按原尺寸发送。同一个屏幕坐标在两者中对应不同的图像像素，从一张图上读到的坐标不能直接搬到另一张。

## 3. 设计原则

1. **视觉负责判断，不负责定位。** "这是播放器吗""弹的是登录框吗"交给视觉；"搜索框在哪"交给 UIA。坐标只作最后兜底，用坐标的回执必须标出 `source` 与置信度。不接 OCR：读不出字时先查拍到的窗口、图的缩放与控件是否展开。
2. **动作有前置条件与后置回执。** 每次输入都必须能回答"打给了谁""打中了什么""画面变了没有"。
3. **结果句柄化。** 后一个步骤按名引用前一个步骤的产出，模型不抄数字。
4. **批量必须有断言。** 没有 `expect` 的批量会在一次调用里连错五步。
5. **上下文只放有信息增量的帧。** 成功回末帧，失败回失败帧，中间帧不进上下文。

## 4. 工具面

| 层 | 工具 | 性质 |
|---|---|---|
| L0 | `desktop_eye` / `desktop_mouse` / `desktop_keyboard` / `desktop_wait` | 基线 |
| L1 | 可选参数 `shot`；回执 `focus` / `hit` / `changed` / `window_changed` | L0 扩展 |
| L2 | `desktop_window` / `desktop_find` / `desktop_click_text` / `desktop_click_region` / `desktop_type_into` / `desktop_app` / `desktop_open` | 新增 |
| L3 | `desktop_act` | 新增 |

L2 动词是 L0 调用的组合，不引入新的系统调用面，与 L0 共用同一把输入锁与同一套 Plan 门控。

### 4.1 句柄契约

管道传递句柄，不传抄来的数字。定位结果与动作回执使用这一形态：

```json
{
  "cursor": {"x": 914, "y": 512},
  "hit": {"hwnd": 15404862, "title": "Media Player", "class": "PlayerWindow",
          "rect": {"x": 251, "y": 10, "width": 1418, "height": 1020},
          "element": {"role": "Edit", "name": "Search",
                      "rect": {"x": 498, "y": 30, "width": 502, "height": 22},
                      "source": "uia"}},
  "focus": {"hwnd": 15404862, "title": "Media Player"},
  "changed": 0.18,
  "diff_rect": {"x": 1020, "y": 60, "width": 620, "height": 380}
}
```

`source` 取 `uia` 或 `point`。`uia` 结果精确，不带置信度；`point` 结果带 0–1 的 `confidence`。没有 `source` 的坐标不是定位结果。

### 4.2 新增动词的参数面

| 工具 | 参数 | 契约 |
|---|---|---|
| `desktop_window` | `action`：`list` / `activate` / `wait` / `rect`；`window` / `hwnd` / `timeout_ms` / `interval_ms` / `limit` | `activate` 恢复并置前；成功判据是随后能取到内容，不是前台 API 返回了 `true`。`wait` 等到窗口出现且非最小化；`list` 返回候选窗口 |
| `desktop_find` | `text`、`region`、`match`（`contains` / `exact` / `regex`）、`source`（`auto` / `uia` / `point`）、`limit` | 返回 `matches[]`，每项带 `rect` / `index` / `source` / `confidence` |
| `desktop_click_text` | `text`、`index`、`region`、`button`、`count`、`shot`、`expect` | 内部：查找 → 命中校验（唯一 / 第 n 个）→ 点击 → 回执 |
| `desktop_type_into` | `target`（文本）或 `x/y/width/height`、`space` / `capture_id`、`text`、`clear`、`submit` | 内部：UIA 或矩形中心 → 聚焦 → 清空 → 输入 → 可选回车 → 像素 diff |
| `desktop_click_region` | `x/y/width/height`、`space` / `capture_id`、`window` / `hwnd`、`button`、`count` | 用矩形中心点击；`space=image` 时工具把图内矩形换算成屏幕，回执带 `changed` / `title_changed` / `verified` |
| `desktop_open` | `target`、`window`、`timeout_ms`、`activate` | 用系统默认处理器打开 URL/scheme/文件；优先绑定本次新窗口，返回 `fresh` / `reused` / `hwnd`，标题不完全匹配时也返回实际窗口 |
| `desktop_app` | `path` / `name`、`args`、`window`、`timeout_ms`、`activate` | `name` 从开始菜单快捷方式解析；启动 → 等主窗口 → 激活；返回 `pid` / `path` / `hwnd` / `rect` |

`desktop_app` 与 `desktop_open`（URL scheme 或默认浏览器）分开：前者启动程序并等待主窗口，后者只打开目标；给 `window` 时才等待窗口。
Windows 的 P2 定位适配使用系统 PowerShell 的 `UIAutomationClient`：查询参数以 base64 传入环境变量，脚本从标准输出返回 JSON；只做控件定位，不引入第三方库、不接 OCR，点击与输入仍走既有基础端口。


## 5. 两步组合

基线是四个 L0 工具下的往返数，管道后是 L1 与 L2 落地后的往返数。

| # | 组合 | 基线 | 管道后 | 传递的数据 | 备注 |
|---|---|---|---|---|---|
| 1 | 移动 → 点击 | 2 | 1 | `move.cursor` | 直接引用光标句柄 |
| 2 | 点击 → 看图 | 2 | 1 | — | `shot=true` |
| 3 | 看图 → 点击指定文字 | 2 | 1 | `find.matches[i].rect` | 定位由 UIA 给出 |
| 4 | 点击 → 打字 | 2 | 1 | 继承焦点 | `type_into` |
| 5 | 打字 → 回车 | 2 | 1 | — | `submit=true` |
| 6 | 回车 → 等变化 | 2 | 1 | `changed` | `desktop_wait(until="change")` |
| 7 | 滚动 → 看图 | 2 | 1 | — | `shot=true` |
| 8 | 激活窗口 → 看图 | 2 | 1 | `window.rect` | `desktop_window(activate)` |
| 9 | 启动应用 → 等主窗口 | 2 | 1 | `window.hwnd` | 取代固定等待后再截图 |
| 10 | 看图 → 裁剪区域 | 2 | 1 | 网格单元或 `element.rect` | 只回局部 |
| 11 | 点击 → 前后 diff | 2 | 1 | `diff_rect` | 只回变化区 |
| 12 | 拖拽 → 看图 | 2 | 1 | — | `shot=true` |
| 13 | 看图 → 局部放大 | 2 | 1 | `shot_region` | 直接取局部，不套用整屏缩放；长边上限仍然适用 |
| 14 | 查询光标 → 相对移动 | 2 | 1 | `cursor` | 精调落点 |
| 15 | 热键 → 看图 | 2 | 1 | — | `shot=true` |

## 6. 三步组合

| # | 组合 | 基线 | 管道后 | 关键点 |
|---|---|---|---|---|
| 1 | 激活窗口 → 点输入框 → 打字并回车 | 4 | 1 | 一条命令完成搜索，且绑定目标窗口 |
| 2 | 看图 → 找文字 → 点击并回图 | 3 | 1 | 点击后立即校验，误点当场暴露 |
| 3 | 移动 → 点击 → 打字 | 3 | 1 | 用 `hit` 校验落点再输入 |
| 4 | 点输入框 → 清空 → 打字 → 回车 | 4 | 1 | `clear=true` |
| 5 | 看图 → 滚动 → 看图 | 3 | 1 | 回复末帧 |
| 6 | 列窗口 → 激活 → 看图 | 3 | 1 | 解决同名窗口 |
| 7 | 启动应用 → 等主窗口 → 看图 | 3 | 1 | 取代固定等待 |
| 8 | 点击 → 等待 → 看图 | 3 | 1 | 弹层、加载 |
| 9 | 拖拽 → 看图 → diff | 3 | 1 | 验证拖拽结果 |
| 10 | 找文字 → 点第 n 个 → 再找下一个 | 3 | 1 | `index` 显式选择 |
| 11 | 点击 → 裁局部 | 3 | 1 | 只回结果区，直接取该区域 |
| 12 | 热键全选 → 打字 → 回车 | 3 | 1 | 覆盖式替换 |

## 7. 批量 `desktop_act`

### 7.1 请求

```json
{
  "steps": [
    {"app": "Media Player", "expect": {"window": "Media Player"}},
    {"type_into": {"target": "Search box", "text": "Example", "submit": true},
     "expect": {"text": "Example", "timeout_ms": 3000}},
    {"click_text": {"text": "Example", "index": 0},
     "expect": {"changed": true, "timeout_ms": 5000}},
    {"expect": {"text": "Play"}, "capture": "final"}
  ],
  "on_error": "stop",
  "capture": "failure",
  "timeout_ms": 30000
}
```

### 7.2 语义约束

| 项 | 规则 |
|---|---|
| 步骤失败 | `on_error="stop"`（默认）立即停止，返回该步截图与 step log；`on_error="continue"` 只允许用于只读步骤 |
| 断言 | `expect` 支持 `window` / `text` / `changed` / `rect_contains`，每项带独立 `timeout_ms` |
| 变量引用 | `$<step>.<field>`，例如 `$2.hit.rect`；类型固定为 `point` / `rect` / `window` / `element` / `text` |
| 破坏性动作 | 目标文字命中关闭、删除、支付、购买、退订类模式时，批量整体拒绝，要求逐条执行并确认 |
| 图片 | 只回末帧与失败帧；中间帧只向 step log 提供尺寸与 `changed` |
| 上限 | 单次批量最多 12 步、总时长 60 秒；超限在调用侧报错，不静默截断 |

### 7.3 边界

批量不是把参数矩阵摊平。

`desktop_act` 接受两个参数简写：`{"window": "标题"}` 等价于激活该窗口；`{"wait": {"ms": 500}}` 的 `ms` 映射到 `timeout_ms`，未给 `until` 时默认为 `change`。每个 step 仍是独立的 `{动词: 参数}` 对象，未知动词直接报错并列出可用动词。`desktop_act` 不接受 L0 原语之外的隐式状态：上一步的光标位置不会被后一步继承，要在那里点击必须显式写 `{"click": {"point": "$1.cursor"}}`。

## 8. 定位管线

两级降级，逐级带 `source`；UIA 之外的结果另带 `confidence`：

| 级 | 手段 | 读 | 写 | 局限 |
|---|---|---|---|---|
| 1 | UIA（`IUIAutomation`，Windows） | 可靠：目标在后台时也能返回控件矩形 | **不可靠**：`ValuePattern.SetValue` 对自绘窗口可能返回成功，界面并不变化 | provider 会返回缓存值，读回校验同样被骗过 |
| 2 | 坐标 | — | 需先做命中测试 | 精度受图像读数限制 |

写入统一走坐标加命中测试：先用 UIA 把坐标解析成具体控件，确认它是可编辑元素后再投递输入。UIA 写入只作为原生控件的快路径，且必须过像素 diff。

**不接 OCR。** 读不到文字时先查观测侧：是否拍错了窗口（`hover.hit` 与截图窗口不一致）、整屏是否被缩放、控件是否已展开。这些才是悬停失败的真实原因；OCR 只会把它们掩盖成识别错误。

验收标准：

- `desktop_find("Search")` 在暴露 UIA 树的客户端上必须返回输入框矩形；没有 UIA 时明确返回 `DesktopUnavailable`，不以伪造的 `source="point"` 结果充当定位。
- `desktop_type_into` 写入后必须以像素 diff 收尾；只读回 `ValuePattern.Value` 判定成功视为不通过。

## 9. 观测与上下文

| 手段 | 规则 |
|---|---|
| `shot` | 动作完成后取目标窗口内容；默认 `false`；语义动词默认 `true` |
| 来源 | 截图按 `hwnd` 取窗口内容，不用整屏；整屏只在无法确定窗口时使用 |
| `diff` | 与上一帧逐块比较，只回 `diff_rect` 区域；无变化时回 `changed=0`，不回图 |
| 去重 | 相同画面（哈希一致）不重复进上下文，回执返回 `same_as: <shot_id>` |
| 区域 | 区域截图优先于窗口截图，窗口截图优先于整屏；整屏只在无法确定窗口时兜底 |
| 预算 | 单次结果最多 1 张图；超出由 `build_tool_parts` 的既有预算规则处理 |

窗口截图取窗口自身的重绘（`PrintWindow` 全内容渲染），不是屏幕拷贝，因此遮挡不影响内容。窗口重绘仍然取不到内容时，回退到屏幕截图并标 `source="screen"`。整屏图会把小控件缩到无法从图上辨认落点；区域图与窗口图从目标的真实像素开始，保留的细节多于整屏帧，`max_side` 仍然限制长边。

## 10. 安全与门控

1. Plan 模式沿用 `reject_in_plan`：读与查可用，任何改变桌面状态的动作都拒绝。范围包括输入、移动光标与显式激活。`desktop_eye` 不带 `hover` 也不给 `activate=true` 时只读，照常可用；`hover` 与 `activate=true` 被拒绝。`desktop_wait` 只读，可用。除 `cursor` 外的鼠标动作与全部键盘动作被拒绝。
2. 破坏性动作：批量中的目标文字命中关闭、删除、支付、购买、退订类模式时整体拒绝。
3. 输入锁沿用 `input_guard()`；批量整体持锁，其他会话的点击不能插进步骤之间。
4. 宿主窗口规避不在本设计范围内：页面把 `screenX` / `screenY` / `outerWidth` / `outerHeight` 报给后端即可得到宿主窗口矩形，输入类工具可据此拒绝落在该矩形内的坐标。

## 11. 新增不变量

接续 `docs/plan/visual-operator.md` 的 10 条：

11. 每个改变桌面且指定窗口的动作都回执 `focus`；能确定落点时同时回 `hit`。
12. 视觉不作为最终定位手段。用坐标定位时必须在回执里标记 `source="point"`。
13. 批量失败即停并回传失败帧，不允许静默跳过失败步骤。
14. 新增参数全部可选；缺省时基线工具行为不变。
15. 观测不要求前台；**输入要求目标持有前台**。置前失败即拒绝投递并回执实际前台。
16. 写类动作的校验必须来自像素或结构 diff；provider 的读回值永远不是成功证据。
17. 坐标点击前必须做命中测试；解析不出具体控件时标记 `source="point"` 并降低置信度，不得静默执行。
18. `desktop_eye` 与手部动作都接受 `window` / `hwnd`：取图走窗口内容，输入先置前再投递。
19. 取图**默认不置前**。最小化窗口用 `SW_SHOWNOACTIVATE` 恢复（会触发真实重绘），当前前台窗口与键盘焦点都不动。要把窗口亮到前台由模型显式给 `activate=true`，不是隐式副作用。
20. 手部动作一旦指定目标窗口，置前不可关闭。输入只认当前前台，置前失败必须拒绝投递。

## 12. 分阶段落地

| 阶段 | 改动 | 文件 | 验收 |
|---|---|---|---|
| P0 | 动作回执、`shot`、恢复但不置前、前台校验 | `tools/mouse.py`、`tools/keyboard.py`、`tools/_capture.py`、`tools/_windows.py`、`diff.py`、`ports.py`、`backends/win32.py` | 误点后第一次回执就能看到 `hit` 落在窗口控制按钮上，而不是内容区；目标被遮挡时截图仍是目标内容 |
| P1 | `desktop_window`、`desktop_app`、`desktop_open` | 新增 `tools/window.py`、`tools/app.py`、`tools/open.py` | 激活在一次往返内完成，失败不靠 API 返回值判断 |
| P2 | `desktop_find`、`desktop_click_text`、`desktop_click_region`、`desktop_type_into` | 新增 `tools/find.py`、`tools/click_text.py`、`tools/click_region.py`、`tools/type_into.py`、`locate.py`、`titles.py`、`tools/_evidence.py`、`backends/win32_uia.py` | 搜索框一次命中，或明确低置信度；自绘控件用矩形中心 |
| P3 | `desktop_act` | 新增 `tools/act.py`、`pipeline.py` | 目标场景最多 3 次往返完成 |

验收预算：P0 后最多 15 次往返，P1 后 8 次，P2 后 5 次，P3 后 3 次。

## 13. 不做什么

1. 不引入三方桌面自动化或窗口库。Windows 的 UIA 定位通过系统 PowerShell 的 `UIAutomationClient` 适配：查询参数 base64、环境变量传递、stdout JSON，只读定位，不引入第三方依赖；点击与输入仍走既有端口。
2. 不做跨平台 UIA 抽象层。macOS 的 AX 接口不在范围内。
3. 不做通用录制回放；它需要独立的交互设计。
4. 不做"一个工具吃所有动作"的 `desktop_action`。
5. 不做没有 `expect` 的批量。

## 14. 风险

| 风险 | 缓解 |
|---|---|
| 自绘窗口的 UIA 树为空 | 降级到坐标，回执透出 `source`；需要时新增按 `class` 选择定位策略的适配表 |
| provider 谎报成功，界面没有变化 | 所有写操作以像素或结构 diff 校验；读回值只进日志 |
| `SetForegroundWindow` 返回 `true` 但窗口不可用 | `activate` 以能否取到内容收尾，不以返回值收尾 |
| 把"读不到字"误认为缺 OCR | 文档与回执先指向窗口身份与缩放；OCR 保持排除 |
| 断言过严导致频繁误停 | `expect` 的 `timeout_ms` 独立配置；失败回执附最后一帧 |
| 批量降低可观测性 | step log 进正文；失败帧必回 |
| 窗口标题本地化或重名 | `desktop_window` 支持 `hwnd`；`list` 返回 `rect` 与前台状态供判别 |

## 15. 回执

回执字段按需附加。字段缺席表示平台观测不到，不表示什么都没发生。

### 15.1 激活

指定了目标窗口的输入动作在投递前先激活该窗口，并回报这次尝试：

| 字段 | 契约 |
|---|---|
| `focus` | `hwnd`、`title`、`rect`、`active`、`restored`、`foreground`；标题命中多个窗口时带 `matched` 与 `alternatives` |
| `active` | 目标持有前台且未最小化。不参考 API 返回值 |
| 失败 | 不投递输入；错误写明实际持有前台的窗口 |

`desktop_eye` 在 `activate=true` 时回 `activated` 与窗口元数据。

### 15.2 动作证据

| 字段 | 契约 |
|---|---|
| `hit` | 落点所在的窗口句柄、控件类名与所属顶层窗口标题；平台不支持探测时省略 |
| `changed` / `changed_scope` | 落点周围 200×200 区域的像素差异比例 0–1；`changed_scope` 固定为 `point_200` |
| `window_changed` | 窗口层对比：`hit_before` / `hit_after`、`opened` / `closed`、`changed`、`navigated` |
| `changed_late` / `changed_late_after_ms` | 落点原地变化接近 0 时 250ms 后复采；`changed` 取较大值，`changed_note` 记录原因 |

`hit` 回答打中了什么，`changed` 回答落点原地有没有反应。跳转类点击可能让 `changed` 停在 0 而窗口层发生变化；此时以 `window_changed.navigated=true` 为准，并且不得重复同一坐标。

### 15.3 动作回图

| 参数 | 契约 |
|---|---|
| `shot` | 在同一次调用内附上截图；默认 `false` |
| `shot_region` | `[x, y, width, height]`；省略时取落点窗口或整屏 |
| `shot_max_side` | 回图长边上限；缺省取配置 |

回图跟着动作实际落在的窗口走（`shot_of="hit"`），不按标题重新解析。显式给了 `window` / `hwnd` 时以显式参数为准（`shot_of="window"` / `"hwnd"`）；两者都没有且没有落点窗口时才拍整屏。落点窗口与激活窗口不是同一个时，`note` 写明两个句柄。`desktop_mouse` 接受全部三个参数；`desktop_keyboard` 接受 `shot` 与 `shot_max_side`。`move` 回图但不做 `hit` / `changed`：移动不改变界面，但悬停可能展开控件。

### 15.4 等待

`desktop_wait` 等待 `until=change`、`window_appears` 或 `window_disappears`。`timeout_ms` 是上限；超时返回 `satisfied=false` 与最后一次观测状态，不算错误。固定 `task_sleep` 不是桌面流程里的合法等待。

## 16. 悬停与窗口身份

悬停取图与落点探测存在的原因，是窗口标题不能标识真正拥有像素的那个窗口。播放器画面可以是独立顶层窗口，而标题命中的是承载详情页的壳；光标可能在一层，截图却来自另一层。

| 问题 | 规则 | 字段 |
|---|---|---|
| 光标在哪一层未知 | 悬停后探测光标下的窗口 | `hover.hit` |
| 光标层与截图层不同 | 写明两个句柄与该用哪一个 | `note` |
| 瞬移不产生连续 mousemove | 先走 `hover_path`，再用 `hover_approach_ms` 移动，最后做小幅 `hover_wiggle` | `hover.path` / `hover.approach_ms` / `hover.wiggle` |
| `changed=0` 被读成没点中 | 增加窗口层对比并报告跳转 | `window_changed.navigated` |
| 跳转后的重绘滞后 | 落点没动时 250ms 后复采 | `changed_late` |
| `shot` 按标题重新解析 | 跟随落点窗口 | `shot_of` / `note` |

`desktop_eye(hover=[x, y])` 在一次调用内移动光标、等界面展开、截图；`hover_settle_ms` 控制这段等待。悬停控件通常 2–3 秒自动收起，而两次工具调用之间隔着一次模型往返，拆开就必然错过。对后台窗口悬停可能落到遮挡它的窗口上；要让悬停控件收到指针，必须给 `activate=true`。不给 `window` / `hwnd` 时，取图目标是光标那一层窗口（`window.auto="hover.hit"`），从该窗口取图而不是整屏；`max_side` 仍然适用。

`window` 是标题片段，可能同时命中多个窗口。候选排序为前台、Z 序、面积，因为用户眼前那个窗口通常才是目标，而面积最大的可能是盖在画面上的播放层。命中数大于 1 时，回执带 `window.matched`、`window.alternatives`（最多四个候选）与 `note`，写明选中的 `hwnd` 及其余窗口。只给一个数字等于让模型自己猜；它常用的兜底——整屏截图——会改变比例尺。

验收口径：

- 平台支持落点探测时，`hover` 回执必须带 `hover.hit`；与截图窗口不一致时必须出现 `note`。
- 支持落点探测时，带 `shot` 的鼠标动作不得返回 `shot_of="screen"`。
- `changed=0` 且 `window_changed.changed=true` 时，模型不得重复同一坐标。
- 不引入任何 OCR 依赖；`image_ocr` 不参与桌面流程。
