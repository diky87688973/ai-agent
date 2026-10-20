# 桌面操作插件交互层方案

## 1. 结论

一次真实任务（会话 `8037c337-e834-4a6e-882e-27424dab7478`，「帮我打开腾讯视频，我要看斗破苍穹最新集」）
用了 64 次模型往返仍未完成。复盘后判定：**失败点不在"能不能点"，而在工具面缺了三样东西**——
输入前不校验落点、动作后不回执结果、没有窗口层。

优化主线一句话：**把工具面从"坐标原语"抬到"意图动词"，再用"带断言的批量"收口。**

重测（见 §2.5）修正了一处归因：**"抢前台"不是瓶颈**。`SetForegroundWindow` 在多数环境下能成功，
但它的返回值会骗人——目标仍是最小化窗口时也返回 `true`，`GetForegroundWindow()` 同样指向它。
真正稳定的是"抓目标窗口的内容"与"读窗口结构"，两者都不要求目标在前台。
因此本方案把 `capture` 从"锦上添花"提升为**必选回执**，并把 `activate` 的成功判据
从 API 返回值改成"随后能否取到目标内容"。

三层，按顺序落地，不合并：

| 层 | 内容 | 解决的问题 |
|---|---|---|
| L1 回执与断言 | 每个动作返回 `focus` / `hit` / `changed`；动作可带 `capture` | 点错立刻知道，不用靠下一张截图猜 |
| L2 语义动词 | `desktop_window` / `desktop_find` / `desktop_click_text` / `desktop_type_into` / `desktop_wait` / `desktop_app` | 定位与等待不再由模型估读 |
| L3 批量管道 | `desktop_act`：多步一次调用，每步带 `expect`，失败即停 | 稳定任务的往返从 N 降到 1 |

与既有方案（`docs/plan/visual-operator.md`）的关系：第 1 节"不把 15 个动作塞进一个 `desktop_action`"的决定不变。
批量是**新增的独立工具**，不是把参数矩阵摊平。三个 L0 工具的参数语义保持不变，只加可选参数。

> **红线：不接 OCR 工具。** 模型本身有视觉能力，截图就是它的输入；读不出字要修的是
> 「拍错了窗口 / 图被缩小 / 控件没展开」，而不是再加一层文字识别。这里关于 OCR 的
> 对比与选型只作为**排除记录**保留，不作为落地项。定位只走 UIA 与视觉坐标。

## 2. 复盘

### 2.1 回合指标

| 指标 | 数值 |
|---|---|
| 模型往返 | 64（撞上 `[agent] max_passes` 默认上限） |
| 工具调用 | 65 |
| 截屏 | 22 张整屏（另 3 张区域） |
| 真实意图 | 4 个：打开客户端、切前台、搜索、点开最新集 |
| 实际完成 | 0 |

### 2.2 关键链路

| 往返 | 事件 |
|---|---|
| P1–P4 | 定位并启动 `QQLive.exe`。P2 的 `run_command` 被 `safe_mode` 以"包含禁止字符 `$`"拒绝，白跑一次 |
| P5–P16 | 主窗口 `iconic=True`，`SetForegroundWindow` 不生效。依次尝试 `ShowWindow` / `AttachThreadInput` / `SetWindowPlacement` / `SwitchToThisWindow` / ALT 键技巧，12 次往返才抢到前台（重测见 §2.5：该能力不稳定，不作为设计前提） |
| P17 | 从 1600×900 缩放图估读搜索框在 (1632, 42)，点击 |
| P18–P19 | 输入「斗破苍穹」、回车 |
| P20–P23 | 发现浏览器原生 alert「当前会话仍在执行中」，且宿主聊天框里出现了「斗破苍穹」 |
| P24–P31 | 最小化 Chrome、`AppActivate`、`tasklist`；P30 已查不到 QQLive 进程 |
| P32–P45 | 两个同名窗口（hwnd 2561250 / 15404862）来回漂；P38–P39 模型自己拆成 `move` + `click` |
| P46–P53 | Esc、后退、连点，无信息增量 |
| P54–P55 | 翻注册表找 URL scheme；`taskkill` 掉客户端重启 |
| P56–P64 | 重复点击与滚动，撞上限结束 |

### 2.3 误点判定

客户端主窗口实测矩形为 `(251, 10, 1418, 1020)`（100% 缩放）。UIA 树给出两个关键矩形：

| 元素 | 矩形 | 说明 |
|---|---|---|
| 搜索输入框 `EditControl` | `(498, 30, 502, 22)` | 真实落点 |
| 窗口控制按钮 `ButtonControl` | `(1625, 34, 20, 20)` | 关闭键 |

`(1632, 42)` 精确落在关闭按钮内，与搜索框横向相距 **1134 像素**。
这不是"缩放后估读偏差"，而是把窗口控制区当成了内容区。
UIA 只需一次读取（92ms）就能给出两个矩形，模型当时却只有一张缩放截图。

三条独立证据：

1. P6 的 `tasklist` 有 3 个 `QQLive.exe` 进程；
2. P21 模型自述「腾讯视频窗口不见了」；
3. P30 的 `tasklist` 输出「没有运行的任务匹配指定标准」。

因此这次点击关闭了客户端。由此产生的所有混乱都是它的级联：输入落进宿主聊天框 → 回车触发
`alert`（`agent/shell/web_assets/classic/js/chat/send.js` 第 11 行）→ 原生模态抢前台 →
之后的点击与焦点切换全部受它干扰。

### 2.4 归因

| # | 根因 | 证据 | 改造 |
|---|---|---|---|
| 1 | 输入无前置校验：不校验前台窗口、不校验落点 | P17 点空、P18 字进宿主 UI | 动作回执 + `expect` |
| 2 | 没有窗口层 | P5–P16 共 12 次往返在抢前台；重测表明抢前台并非瓶颈，真正缺的是**不依赖前台的观测与定位** | `desktop_window` + 窗口级截图 |
| 3 | 动作无回执 | 客户端被关掉，靠 4 次截图才反推出来 | `focus` / `hit` / `changed` |
| 4 | 坐标靠估读 | 缩放 1.2 倍后控件高约 25 像素，模型自述"很难精确" | 结构化定位（UIA），视觉只做确认 |
| 5 | 一动作一往返，无等待语义 | 点完立即截图，看到旧画面再点 | `capture` + `desktop_wait` |
| 6 | 观测冗余 | 22 帧里真正有信息增量的不超过 4 帧 | `diff` / 去重 / 局部裁剪 |
| 7 | 护栏咬错位置 | `safe_mode` 拦 `$`；`max_passes=64` 成了终点 | `$` 改为按危险模式判定 |

补一条：模型在 P38–P39 自己发明了 `move` → `click` 两步，说明它已经在手工拼管道。
这是交互缺口的直接信号，不是模型笨。

### 2.5 重测基线

环境：Windows 10 19045，腾讯视频 `EVO_WidgetWin_0`，主窗口 `(251, 10, 1418, 1020)`。
测量时把 Cursor 置于前台并覆盖目标窗口，模拟"用户盯着 agent 进度"的真实状态。

| # | 用例 | 判定 | 数据 |
|---|---|---|---|
| 1 | 遮挡截图：`PrintWindow(PW_RENDERFULLCONTENT)` vs GDI `BitBlt` | PrintWindow 有效 | 同区域 135,589 色 vs 52,775 色；叠合率 **0.6%**，mean_diff **210.3** |
| 2 | 目标在后台时读 UIA 树 | 有效 | 69–71 节点 / 72–92ms，能拿到 `Edit` 与全部 `Button` 矩形 |
| 3 | 最小化窗口取图 | 恢复即可，置前可选 | `SW_SHOWNOACTIVATE` 恢复后 `PrintWindow` 得 5.78MB 非空帧，`GetForegroundWindow()` 仍是调用前的窗口；`SW_RESTORE` 也能取到同样内容，但会改变前台，因此只用于显式要求置前时 |
| 4 | UIA `ValuePattern.SetValue` 写搜索框 | **假成功** | 返回 `true`、读回值正确，但像素差 **0.00**，界面零变化 |
| 5 | 误点坐标复现 | 命中关闭键 | `(1632,42) ∈ (1625,34,20,20)` |

补充观测：

- `SetForegroundWindow` 返回 `true` 时，`GetForegroundWindow()` 也会指向目标，
  但目标可能仍是 `iconic`。**两者都不能作为"窗口可用"的判据**，唯一判据是能否取到内容。
- 测试进程若由前台进程启动（`Cursor → PowerShell → python`），抢前台会被放行；
  换成无关进程则不一定。该变量不可控，因此不作为设计前提。
- 一次作废的对照实验：尝试用记事本建立"非 Cursor 前台"参照组，但无法把前台从目标窗口切走，
  数据无效，未计入上表。

结论：**观测走 PrintWindow，定位走 UIA，写入后的校验走像素 diff。** 三者的输入侧不要求目标在前台。

但"窗口能用"和"输入能打进去"是两件事：
- 观测与定位可以不动前台：最小化窗口用 `SW_SHOWNOACTIVATE` 恢复即可取到真实重绘，
  当前前台与键盘焦点都不变；`desktop_eye` 的 `activate` 默认 false，要亮出来才给 true；
- 输入只会打到当前前台。最小化或前台不是目标时，必须先像人点任务栏一样
  恢复 + 置前，**否则字会打进别的窗口**（本回合 P18 就是这么把"斗破苍穹"写进宿主聊天框的）。
  手部动作的置前不可关闭，置前失败时拒绝投递，不用盲打去赌。

### 2.6 三方库横向对比（实测）

上一版只测了 `mss`（裁剪）与 `uiautomation`（单点），每个能力域只有一个候选，等于没有对比。
本节按能力域各拉一组市面主流库，与自研 ctypes 实现同机、同目标、同用例跑一遍。

被测库共 15 个：`mss` / `Pillow` / `dxcam` / `pyautogui` / `pywin32` / `pywinauto` /
`pygetwindow` / `uiautomation` / `pydirectinput` / `RapidOCR` / `PaddleOCR` / `EasyOCR` /
`winsdk`(Windows OCR) / `OpenCV` / `comtypes`。

#### A. 截屏（目标被 Cursor 完全遮挡）

| 候选 | 遮挡可取内容 | 中位耗时 | 色彩数 | 备注 |
|---|---|---|---|---|
| 自研 `PrintWindow(PW_RENDERFULLCONTENT)` | **是** | 18.7ms | 218,693 | 唯一自研路径 |
| `pywin32` `PrintWindow` | **是** | 19.6ms | 190,382 | 与自研同底层，多 15.8MB 依赖 |
| 自研 GDI `BitBlt`（**仓库现用实现**） | 否 | 19.2ms | 43,657 | 抓到的是 Cursor |
| `mss` | 否 | 18.6ms | 57,090 | 屏幕级 |
| `Pillow` `ImageGrab` | 否 | 19.2ms | 53,977 | 屏幕级 |
| `dxcam`(DXGI) | 否 | 2–3ms（有帧） | 52,495 | 屏幕级；无新帧时返回 `None`，需自建重试 |
| `pyautogui` `screenshot` | 否 | 19.1ms | 52,585 | 屏幕级 |
| `pywinauto` `capture_as_image` | 否 | 19.3ms | 53,469 | 名为窗口截图，实际走屏幕 |
| `uiautomation` `CaptureToImage` | 否 | 53.8ms | 64,333 | 实际走屏幕 |

9 个候选里只有 2 个能做到遮挡取图，且都是同一个 Win32 API。
**没有任何三方库提供"遮挡窗口截图"的额外能力。**
最小化态 9/9 全部失败（恢复后约 440ms 才能重绘出内容）——最小化窗口不可截，必须先恢复再等重绘。

**仓库现状与文档不一致**：`backends/win32.py` 的 `capture()` 走 `BitBlt`，
`PrintWindow` 只出现在方案描述里。这意味着当前实现拿不到被遮挡窗口的内容，
正是本次任务里"看到的是 Cursor 而不是腾讯视频"的直接来源。

#### B. 窗口激活（独立进程，先摆状态再测）

| 候选 | 遮挡态 | 最小化态 | 相对开销（含固定等待） | 备注 |
|---|---|---|---|---|
| 自研 `SwitchToThisWindow` | 3/3 | 3/3 | 最低 | 推荐 |
| 自研 `ShowWindow+SetForegroundWindow` | 3/3 | 3/3 | 低 | |
| 自研 `AttachThreadInput` | 3/3 | 3/3 | 中 | 代码量最大，无收益 |
| 自研 `ALT+SetForegroundWindow` | 3/3 | 3/3 | 中 | 注入按键，有副作用 |
| `pywin32` `SetForegroundWindow` | 3/3 | 3/3 | 低 | 与自研等价 |
| `pywinauto` `set_focus` | 3/3 | 3/3 | 偏高 | |
| `pygetwindow` `activate` | 3/3 | **0/3** | 低 | 最小化窗口只移前台指针、不恢复，且 `IsIconic` 仍为真 |
| `uiautomation` `SetActive` | 3/3 | 3/3 | 高 | |
| `uiautomation` `ShowWindow` | 3/3 | 3/3 | 最高 | |

遮挡态全员通过，这一域没有技术门槛，自研不必换。
`pygetwindow.activate()` 在最小化态会**返回成功但窗口仍是图标态**——又一个"API 说谎"样本，
与 2.5 的 `SetValue` 同类，必须用回执校验而不能信返回值。

#### C. 元素定位（目标在后台且被遮挡）

| 候选 | 节点数 | 耗时 | 输入框误差 | "片库"误差 |
|---|---|---|---|---|
| 自研 COM UIA（comtypes 仅做类型库绑定） | 68 | **53.2ms** | 0px | 0px |
| `uiautomation` | 69 | 72.7ms | 0px | 0px |
| `pywinauto`(uia) | 68 | 73.5ms | 0px | 0px |
| `pywinauto`(win32) | **1** | 0.3ms | 未命中 | 未命中 |
| `OpenCV` 模板匹配 | — | 61.5ms | 不适用 | 4px |
| `RapidOCR` | 77 行 | 1677ms | 不适用 | 9px |

`pywinauto` 的 win32 后端在 CEF 上只能枚举到 1 个节点（没有子 HWND），**完全不可用**。
UIA 三家精度一致（底层同 COM），自研少一层封装反而最快。
模板匹配需要预置素材，跨主题/分辨率即失效；OCR 慢 30 倍且只能定位有文字的目标。
三者不是替代关系：UIA 为主，视觉确认，模板/坐标兜底；OCR 不接入（见红线）。

#### D. OCR（排除记录，不接入）

> 红线：不接 OCR。理由：模型自己看截图，OCR 是重复建设，
> 还会把"拍错窗口"这类真问题掩盖成"识别不准"。下表不再作为选型依据。

| 引擎 | 召回 | 识别耗时 | 首次可用 | 体积 | 备注 |
|---|---|---|---|---|---|
| `RapidOCR` | 0.80 | 778ms | 2.0s | 50.7MB | ONNX，无 torch |
| `PaddleOCR` 3.7 | 0.90 | **25.7s** | 28.6s | 394MB | 本机 oneDNN 崩溃，须关 mkldnn，关后极慢 |
| `EasyOCR` 1.7 | 0.60 | 3.1s | 1.0s | ~1GB（含 torch） | 需 torch 2.2 才起得来，torch 2.14 `c10.dll` 初始化失败 |
| `winsdk` Windows OCR | 0.60 | **78.9ms** | 0.34s | 41.6MB | 系统内置，零模型下载 |
| `pytesseract` | — | — | — | — | 二进制装不上（GitHub 下载被阻断），未计入 |

`RapidOCR` 是上表里"准确率/延迟/体积"三项最均衡的；Windows OCR 快一个数量级但漏小字；
PaddleOCR 准确率最高但在本机不可交互使用。**这些都不接入工具面**：
已有的教训是，模型读不到字几乎总是因为拍错了窗口或图被缩小，而不是缺一个 OCR。

#### E. 输入注入（靶子 = 记事本 Edit，`VisualOperator-test-42`）

| 候选 | 中文 | ASCII | 耗时 | 需要前台 | 抢焦点 |
|---|---|---|---|---|---|
| 自研 `SendInput`(KEYEVENTF_UNICODE) | **✓** | ✓ | **5.8ms** | 是 | — |
| `uiautomation` `SendKeys` | ✓ | ✓ | 688ms | 是 | — |
| `pyautogui.write` | **✗**（`IO-test-42`） | ✓ | 210ms | 是 | — |
| `pydirectinput.write` | **✗**（`-test-42`） | ✓ | 2225ms | 是 | — |
| `pywin32` `PostMessage(WM_CHAR)` | ✓ | ✓ | 76ms | **否** | **否** |
| `uiautomation` `ValuePattern.SetValue` | ✓ | ✓ | 554ms | 否 | **是** |

`pyautogui` / `pydirectinput` 的键位表只有 ASCII，**中文直接丢弃且不报错**——
对一个中文桌面场景的产品是硬伤，一票否决。
后台投递只有 `PostMessage(WM_CHAR)` 一条路，且它只对原生控件有效，
对 CEF 这类自绘窗口会被忽略，所以不能替代前台 `SendInput`。

另有一个环境级陷阱：目标刚获得焦点时**第一个按键会被吞**。
自研 `SendInput` 丢 1 字、`pyautogui` 丢 3 字、`pydirectinput` 丢 5 字、`uiautomation` 丢 1 字。
先发一个哨兵字符再清空，四家全部 100% 复原。这说明"打字成功"必须靠回读校验，
不能靠 API 返回值。

#### 选型结论

| 能力 | 采用 | 理由 |
|---|---|---|
| 截屏 | 自研 ctypes `PrintWindow`（**替换现有 `BitBlt`**） | 9 个候选里唯一能遮挡取图的一档；无依赖 |
| 窗口激活 | 自研 `SwitchToThisWindow` + 回执校验 | 与三方等价，代码最少 |
| 元素定位 | 自研 COM UIA | 精度同三方，快 20ms，零依赖 |
| OCR | **不采用** | 模型自带视觉；OCR 是重复建设，且会掩盖"拍错窗口" |
| 输入 | 自研 `SendInput` + 哨兵字符 + 回读校验 | 唯一同时满足中文与低延迟 |
| 后台输入 | `PostMessage(WM_CHAR)`（原生控件限定） | 唯一不抢焦点且不丢焦点的路径 |

结论：**除 UIA（系统自带 COM）外，其余四域不需要引入任何三方依赖。** 三方库在这四个域里
没有提供自研拿不到的能力，只提供了更短的调用代码和更大的依赖面。
真正需要补的是"用对了 API"，不是"换一个库"。

## 3. 设计原则

1. **视觉负责判断，不负责定位。** "这是播放器吗""弹的是登录框吗"交给视觉；
   "搜索框在哪"交给 UIA，坐标只作最后兜底，且必须在回执里标明用的哪一级与置信度。
   **不接 OCR**：读不出字时先查是否拍错了窗口、图是否被缩小、控件是否展开。
2. **动作有前置条件与后置回执。** 每次输入都必须能回答"打给了谁""打中了什么""画面变了没有"。
3. **结果句柄化。** 上一步的产出能被下一步按名引用，而不是让模型抄数字。抄就是误差。
4. **批量必须有断言。** 没有 `expect` 的批量等于一口气错五步，比多几次往返更糟。
5. **上下文只放有信息增量的帧。** 成功回末帧，失败回失败帧，中间帧不进上下文。

## 4. 工具面

| 层 | 工具 | 性质 |
|---|---|---|
| L0 | `desktop_eye` / `desktop_mouse` / `desktop_keyboard` | 已有，保留 |
| L1 | 三者新增可选参数 `capture`、`expect`；返回值补 `focus` / `hit` / `changed` | 改造 |
| L2 | `desktop_window` / `desktop_find` / `desktop_click_text` / `desktop_type_into` / `desktop_wait` / `desktop_app` | 新增 |
| L3 | `desktop_act` | 新增 |

L2 的六个动词都是 L0 的组合，不引入新的系统调用面；它们与 L0 共用同一把输入锁与同一套 Plan 门控。

### 4.1 句柄契约

所有返回值里的坐标对象都带类型标签，供管道引用：

```json
{
  "cursor": {"x": 914, "y": 512},
  "hit": {"hwnd": 15404862, "title": "腾讯视频", "class": "EVO_WidgetWin_0",
          "rect": {"x": 251, "y": 10, "width": 1418, "height": 1020},
          "element": {"role": "Edit", "name": "搜索", "rect": {"...": "..."}, "source": "uia", "confidence": 0.94}},
  "focus": {"hwnd": 15404862, "title": "腾讯视频"},
  "changed": true,
  "diff_rect": {"x": 1020, "y": 60, "width": 620, "height": 380}
}
```

`source` 取值 `uia` / `point`；`confidence` 只在 `uia` 之外的级别出现。
模型据此知道这次定位该不该信。

### 4.2 新增动词的参数面

| 工具 | 参数 | 说明 |
|---|---|---|
| `desktop_window` | `action`: `list` / `activate` / `wait` / `rect`；`title` / `hwnd` / `class` / `timeout_ms` | `activate` 做恢复 + 前台，但**成功判据是随后能取到窗口内容**，不是 `SetForegroundWindow` 的返回值；`wait` 等到窗口出现且非最小化 |
| `desktop_find` | `text`、`region`、`match`(`contains`/`exact`/`regex`)、`source`(`auto`/`uia`/`point`)、`limit` | 返回 `matches[]`，每项带 `rect` / `index` / `source` / `confidence` |
| `desktop_click_text` | `text`、`index`、`region`、`button`、`count`、`capture`、`expect` | 内部：find → 命中校验（唯一 / 第 n 个）→ 点击 → 回执 |
| `desktop_type_into` | `target`（文本或矩形）、`text`、`clear`、`submit`、`interval_ms`、`capture`、`expect` | 内部：定位 → 聚焦 → 清空 → 输入 → 可选回车 → 等变化 |
| `desktop_wait` | `until`(`change`/`text`/`window`/`idle`)、`text`、`timeout_ms`、`interval_ms` | 轮询截图或窗口状态，命中即返回 |
| `desktop_app` | `name` / `path`、`args`、`timeout_ms`、`capture` | 启动 + 等主窗口 + 激活；返回 `pid` / `hwnd` / `rect` |

`desktop_app` 与 `desktop_open`（URL scheme / 默认浏览器）分开：前者要窗口，后者不要。

## 5. 两步组合

"现在"是当前工具面下需要的往返数，"管道后"是新增 L1/L2 后的往返数。

| # | 组合 | 现在 | 管道后 | 传递的数据 | 备注 |
|---|---|---|---|---|---|
| 1 | 移动 → 点击 | 2 | 1 | `move.cursor` | 本回合 P38–P39 的手工拼接 |
| 2 | 点击 → 看图 | 2 | 1 | — | `capture=true` |
| 3 | 看图 → 点击指定文字 | 2 | 1 | `find.matches[i].rect` | 定位改由 UIA 给 |
| 4 | 点击 → 打字 | 2 | 1 | 焦点继承 | `type_into` |
| 5 | 打字 → 回车 | 2 | 1 | — | `submit=true` |
| 6 | 回车 → 等变化 | 2 | 1 | `changed` | `desktop_wait(until="change")` |
| 7 | 滚动 → 看图 | 2 | 1 | — | `capture=true` |
| 8 | 激活窗口 → 看图 | 2 | 1 | `window.rect` | `desktop_window(activate)` |
| 9 | 启动应用 → 等主窗口 | 2 | 1 | `window.hwnd` | 取代 `sleep(12)` + 截图 |
| 10 | 看图 → 裁剪区域 | 2 | 1 | `grid cell` / `element.rect` | 只回局部 |
| 11 | 点击 → 前后 diff | 2 | 1 | `diff_rect` | 只回变化区 |
| 12 | 拖拽 → 看图 | 2 | 1 | — | `capture=true` |
| 13 | 看图 → 局部放大 | 2 | 1 | `shot_region` | 局部按原尺寸发送，不缩图 |
| 14 | 查询光标 → 相对移动 | 2 | 1 | `cursor` | 精调落点 |
| 15 | 热键 → 看图 | 2 | 1 | — | `capture=true` |

## 6. 三步组合

| # | 组合 | 现在 | 管道后 | 关键点 |
|---|---|---|---|---|
| 1 | 激活窗口 → 点输入框 → 打字+回车 | 4 | 1 | 一条命令完成搜索，且绑定目标窗口 |
| 2 | 看图 → 找文字 → 点击并回图 | 3 | 1 | 点击后立即校验，错点当场暴露 |
| 3 | 移动 → 点击 → 打字 | 3 | 1 | 用 `hit` 校验落点再输入 |
| 4 | 点输入框 → 清空 → 打字 → 回车 | 4 | 1 | `clear=true` |
| 5 | 看图 → 滚动 → 看图 | 3 | 1 | 回复末帧 |
| 6 | 列窗口 → 激活 → 看图 | 3 | 1 | 解决同名窗口（本回合真实踩坑） |
| 7 | 启动应用 → 等主窗口 → 看图 | 3 | 1 | 取代固定等待 |
| 8 | 点击 → 等待 → 看图 | 3 | 1 | 弹层、加载 |
| 9 | 拖拽 → 看图 → diff | 3 | 1 | 验证拖拽结果 |
| 10 | 找文字 → 点第 n 个 → 再找下一个 | 3 | 1 | `index` 显式选择 |
| 11 | 点击 → 裁局部 | 3 | 1 | 只回结果区，按原尺寸发送 |
| 12 | 热键全选 → 打字 → 回车 | 3 | 1 | 覆盖式搜索 |

## 7. 批量 `desktop_act`

### 7.1 请求

```json
{
  "steps": [
    {"app": "腾讯视频", "expect": {"window": "腾讯视频"}},
    {"type_into": {"target": "搜索框", "text": "斗破苍穹", "submit": true},
     "expect": {"text": "斗破苍穹", "timeout_ms": 3000}},
    {"click_text": {"text": "斗破苍穹", "index": 0},
     "expect": {"changed": true, "timeout_ms": 5000}},
    {"expect": {"text": "播放"}, "capture": "final"}
  ],
  "on_error": "stop",
  "capture": "failure",
  "timeout_ms": 30000
}
```

### 7.2 语义约束

| 项 | 规则 |
|---|---|
| 步骤失败 | `on_error="stop"`（默认）立即停，返回该步截图与 step log；`on_error="continue"` 仅用于只读步骤 |
| 断言 | `expect` 支持 `window` / `text` / `changed` / `rect_contains`，每项带独立 `timeout_ms` |
| 变量引用 | `$<step>.<field>`，如 `$2.hit.rect`；类型固定为 `point` / `rect` / `window` / `element` / `text` |
| 破坏性动作 | `close` / `delete` / `purchase` 类目标文字命中时，批量整体拒绝，要求逐条执行并确认 |
| 图片 | 只回末帧与失败帧；中间帧只进 step log 的尺寸与 `changed` 字段 |
| 上限 | 单次批量最多 12 步、总时长 60 秒；超限在调用侧报错，不静默截断 |

### 7.3 与既有决策的边界

批量不是"把参数矩阵摊平"。每个 step 仍是 `{动词: 参数}` 的独立对象，
未知动词直接报错并列出可用动词。`desktop_act` 不接受坐标原语之外的隐式状态：
上一步的光标位置不会被下一步自动继承，必须显式写 `{"click": {"point": "$1.cursor"}}`。

## 8. 定位管线

两级降级，逐级透出 `source` 与 `confidence`：

| 级 | 手段 | 读 | 写 | 局限 |
|---|---|---|---|---|
| 1 | UIA（`IUIAutomation`，Windows） | 可靠：腾讯视频 69 节点 / 92ms，能拿到输入框与按钮矩形 | **不可靠**：`ValuePattern.SetValue` 对 CEF 返回成功但不进 DOM | CEF 的 provider 会返回缓存值，读回校验同样被骗过 |
| 2 | 坐标 | — | 需先做命中测试 | 精度受估读限制 |

写入统一走"坐标 + 命中测试"：先用 UIA 把坐标解析成具体控件，确认它是可编辑元素后再投递输入。
UIA 写入只作为原生控件的快路径，且**必须过像素 diff 校验**。

**不接 OCR**：读不到文字时先回到观测侧——是否拍错了窗口（`hover.hit` 与截图窗口不一致）、
是否整屏被缩放、控件是否已展开。这些是本轮 4 次 hover 失败的真实原因，OCR 只会把问题掩盖成"识别不准"。

**验收标准**：

- `desktop_find("搜索")` 在腾讯视频客户端上必须命中输入框 `(498, 30, 502, 22)`，
  或明确返回 `source="point"` 与低置信度，不允许"静默给一个看起来像的坐标"。
- `desktop_type_into` 写入后必须以像素 diff 收尾；只读回 `ValuePattern.Value` 判定成功视为不通过。

## 9. 观测与上下文

| 手段 | 规则 |
|---|---|
| `capture` | 动作完成后取目标窗口内容（`PrintWindow`），默认 `false`；合成动词默认 `true` |
| 来源 | 截图按 `hwnd` 取窗口内容，不用整屏；整屏只在列出全部窗口时使用 |
| `diff` | 与上一帧逐块比较，只回 `diff_rect` 区域；无变化时回文本 `changed=false`，不回图 |
| 去重 | 相同画面（哈希一致）不重复进上下文，只回 `same_as: <shot_id>` |
| 局部 | 区域截图优先于窗口截图；窗口截图优先于整屏；整屏只在无法确定窗口时兜底 |
| 预算 | 单次结果最多 1 张图；超出由 `build_tool_parts` 的既有预算规则处理 |

量化参照：本回合 22 张整屏中，真正改变判断的不超过 4 张。按 `diff` + 去重，图片数量可降到 5–6 张。

## 10. 安全与门控

1. Plan 模式沿用现有 `reject_in_plan`：读与查可用，输入类拒绝。
2. 破坏性动作：`desktop_act` 中出现关闭、删除、支付、退订类文字目标时整体拒绝。
3. 输入锁沿用 `input_guard()`，批量整体持锁，不让其他会话的点击插进步骤之间。
4. 宿主窗口规避（可选，暂不实现）：页面把 `screenX/screenY/outerWidth/outerHeight`
   报给后端即可得到宿主窗口矩形，输入类工具可拒绝命中该矩形。
   本期只在文档登记，不落代码。

## 11. 新增不变量

接续 `docs/plan/visual-operator.md` 的 10 条：

11. 每个改变桌面的动作都回执 `focus`；能确定落点时同时回 `hit`。
12. 视觉不作为最终定位手段；用坐标定位时必须在回执里标记 `source="point"`。
13. 批量失败即停并回传失败帧，不允许隐式跳过失败步骤。
14. 新增参数全部可选，三个 L0 工具在缺省参数下的行为不变。
15. 观测不要求前台；**输入必须以目标拿到前台为前置条件**，置前失败即拒绝投递并回执实际前台。
16. 写类动作的校验必须来自像素或结构 diff，禁止用 provider 的读回值作为成功证据。
17. 坐标点击前必须做命中测试；解析不出具体控件时标记 `source="point"` 并降低置信度，不得静默执行。
18. `desktop_eye` 与手部动作都接受 `window` / `hwnd`：取图走窗口内容，输入先置前再投递。
19. 取图**默认不置前**：最小化窗口用 `SW_SHOWNOACTIVATE` 恢复（会触发真实重绘），
    当前前台窗口与键盘焦点都不动。要把窗口亮到前台，由模型显式给 `activate=true`；
    这是模型可控参数，不是隐式副作用。
20. 手部动作的置前**不可关闭**：输入只认当前前台，置前失败必须拒绝投递。

## 12. 分阶段落地

| 阶段 | 改动 | 文件 | 验收 |
|---|---|---|---|
| P0 | 动作回执、`capture`、`expect`（仅 `window`/`changed`）；`capture` 改用 `PrintWindow` | `tools/mouse.py`、`tools/keyboard.py`、`ports.py`、`backends/win32.py` | 复现本回合：误点后第一次回执就能看到 `hit` 落在窗口控制按钮上；目标被遮挡时截图仍是目标内容 |
| P1 | `desktop_window`、`desktop_wait`、`desktop_app` | 新增 `tools/window.py`、`tools/wait.py`、`tools/app.py` | 抢前台从 12 次往返降到 1 次，且失败不再靠 API 返回值判断 |
| P2 | `desktop_find`、`desktop_click_text`、`desktop_type_into` | 新增 `tools/find.py`、`tools/click_text.py`、`tools/type_into.py`、`locate.py` | 腾讯视频搜索框一次命中，或明确低置信度 |
| P3 | `desktop_act` | 新增 `tools/act.py`、`pipeline.py` | 目标场景 ≤3 次往返完成 |

以本回合为基准的往返预算：P0 后 ≤15，P1 后 ≤8，P2 后 ≤5，P3 后 ≤3。

## 13. 不做什么

1. 不引入 `pyautogui` / `pywin32`，现有后端是纯 `ctypes`。UIA 通过 COM 访问（`ctypes` 直调或纯 Python 实现），不引入编译依赖。
2. 不做跨平台 UIA 抽象层：macOS 的 `AX` 接口单独排期，不与 Windows 同期。
3. 不做通用录制回放；那是 P3 之后的事，且需要用户交互设计。
4. 不做"一个工具吃所有动作"的 `desktop_action`。
5. 不为了省往返牺牲断言：没有 `expect` 的批量不允许合入。

## 14. 风险

| 风险 | 缓解 |
|---|---|
| Electron/CEF 应用 UIA 树为空 | 三级降级，回执透出 `source`；必要时新增应用适配表（按 `class` 选择定位策略） |
| provider 谎报成功（`SetValue` 返回值真、界面不变） | 所有写操作以像素/结构 diff 为准，读回值只进日志 |
| `SetForegroundWindow` 返回 `true` 但窗口不可用 | `activate` 以"能否取到窗口内容"收尾，不以返回值收尾 |
| 用户误以为"读不到字=缺 OCR" | 文档与回执明确：先查窗口身份与缩放；红线不接 OCR |
| 断言过严导致频繁误停 | `expect` 的 `timeout_ms` 独立配置；失败回执附最后一帧供模型判断 |
| 批量降低可观测性 | 强制 step log 进正文；失败帧必回 |
| 窗口标题本地化或重名 | `desktop_window` 支持 `hwnd` / `class`；`list` 返回 `pid` 与 `rect` 供判别 |

## 15. 第一轮落地与第二次复盘

第二次真实任务（会话 `d7bd6a65-c93c-46ec-9c85-f07955fd17c4`，「打开腾讯视频看斗破苍穹最新集」）
完成了任务，但用了 46 次往返、232 秒模型时间。失败面与第一次不同：定位基本正确，
卡在「观测与动作之间的时间差」和「回执信息不足」。据此先落地 L1 的一部分，
名字与前面的规划有一处不同：

| 规划 | 实际 | 说明 |
|---|---|---|
| `capture` 参数 | `shot` | 与 `desktop_eye` 的取图参数区分，避免"截图"和"抓取"同词 |
| `capture` 位置 | `shot` / `shot_region` / `shot_max_side` | 鼠标与键盘同一套；`shot_region` 只给鼠标 |
| 回执 `hit` / `changed` | 已实现 | `changed` 是落点周围 200×200 的像素差比例，0–1 |
| `focus` | 已实现（`focus_target`） | 给 `window` / `hwnd` 时回执带激活结果与同名候选 |
| `desktop_wait` | 已实现 | `until=change / window_appears / window_disappears`，超时不是错误 |
| 悬停取图 | 已实现 | `desktop_eye(hover=[x, y])`：移光标、等展开、截图在一次调用内完成 |
| 同名窗口消歧 | 已实现 | `window.matched` + `alternatives`，排序改为前台 → Z 序 → 面积 |
| `desktop_window` / `desktop_find` / `desktop_app` / `desktop_act` | 未落地 | 仍按分阶段计划推进 |

第二次复盘的五个直接原因：

1. **悬停控件活不过一次往返。** 播放器控制条约 3 秒自动收起，而两次工具调用之间
   隔着 2–8 秒模型时间，`move` → `eye` 分两步必然拍不到，同一位置试了 5 次。
2. **同名窗口被静默选中。** `window` 命中 2 个时只回 `matched=2`，没说是哪一个；
   模型无法判断该用哪个 `hwnd`，只好放弃窗口取图改用整屏，比例尺从 1.0 变成 1.2。
3. **点击没有命中证据。** 回执只有坐标，点空与点中都长得一样，只能靠下一张截图反推。
4. **盲睡。** 用固定 `task_sleep` 赌"预告播完自动进正片"，白等 42 秒且条件并未发生。
5. **启动路径靠多轮试探。** 开始菜单的展开与命中没有可等待的窗口信号。

对应的验收口径：

- 同一悬停位置只允许失败一次：第二次必须改用 `hover`。
- `window` 命中多个时，回执必须同时给出选中项与其余 `hwnd`；不改用整屏。
- 改变界面的动作必须带 `hit` 与 `changed`；`changed=0` 时不得直接重复同一坐标。
- 等待必须带条件；`task_sleep` 不再是桌面流程的合法等待手段。

## 16. 第三次复盘：hover 失败不是"鼠标没动"

同一会话的第三次重跑（11 次调用，4 次真正干活）暴露出上一轮的归因错误：
4 次 `desktop_eye(hover=...)` 全部没拍到控制条，看起来像"光标瞬移、播放器认为鼠标没动"。
逐条核对回执后，真正的因果链是**窗口身份错配**：

| 调用 | 落点 `hit` | 截图 `window` |
|---|---|---|
| 点首页卡片 | hwnd=4264122 `腾讯视频` | hwnd=10030986 `腾讯视频` |
| 点视频区 | hwnd=6229548 `ViewsPlayerPluginWnd` | hwnd=10030986 `腾讯视频` |

视频画面是独立顶层窗口，`window="腾讯视频"` 命中的却是承载详情页的壳。
控制条即使出现也不在那张图里，换多少次 y 坐标都一样。已落地的修正：

| 问题 | 修正 | 回执字段 |
|---|---|---|
| 不知道光标在哪一层 | 悬停后探测落点窗口 | `hover.hit` |
| 光标层 ≠ 截图层 | `note` 直接点明并给出该用的 `hwnd` | `note` |
| 瞬移不产生连续 mousemove | `hover_path` + `hover_approach_ms` + `hover_wiggle` | `hover.path` / `approach_ms` / `wiggle` |
| `changed=0` 被读成"没点中" | 增加窗口层对比与跳转判据 | `window_changed.navigated` |
| 跳转后的重绘晚于 60ms | 落点没动时 250ms 后复采 | `changed_late` |
| `shot` 按标题重新解析到别的窗口 | 回图改跟落点窗口 | `shot_of` / `note` |

**不做 OCR**：模型自己看截图。读不出字先查"拍的是不是那个窗口、图有没有被缩小、
控件有没有展开"，而不是再加一层识别。

验收口径：

- `hover` 回执必须带 `hover.hit`；与截图窗口不一致时 `note` 必须出现。
- 带 `shot` 的鼠标动作，`shot_of` 不得为 `screen`（除非平台没有落点探测）。
- `changed=0` 且 `window_changed.changed=true` 时，模型不得重复同一坐标。
- 不引入任何 OCR 依赖；`image_ocr` 不参与桌面流程。
