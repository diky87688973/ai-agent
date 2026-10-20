# AI说话插件方案

## 结论

用插件 `plugins/ai_speak` 替换 `plugins/tts`。插件只提供一个工具 `ai_speak`，
模型在任务过程中把当前这一步要说的话交给它；后端完成校验、切段与语音合成，
通过 SSE 把音频逐段送到前端，前端播放器按顺序排队播放。

旧 `tts` 插件、前端遗留的 `audio` 事件分支与相关测试一并删除，不做兼容。

## 目标

1. 模型在每一步主动调用 `ai_speak`，用当前角色的第一人称、人类口语汇报进度。
2. 工具只暴露 `msg` 一个参数，校验不通过时返回失败并给出可执行的规范。
3. 语音在后端合成，不落盘；合成一段就推送一段，前端边收边播。
4. 工具调用进入现有工具事实流；对话区工具壳显示「AI说话 | 消息」，
   展开详情沿用默认的请求/响应报文。
5. 设置页开关控制插件装载与卸载；关闭时停止播放并清空队列。
6. 配置沿用 `engine` / `voice` / `max_segment_chars`，增加串行播放间隔与同步播放开关。
7. 旧 `tts` 的所有代码、测试与文档引用清理干净。

## 范围外

- 情绪、语气、角色声线等参数；工具契约只有 `msg`。
- 浏览器端语音合成。
- 音频文件落盘、历史回放与断线续播。
- 多音色、多角色同时说话、字幕、语音识别。
- 旧 `tts` 插件及其前端的兼容层。

## 术语

| 词 | 含义 |
|---|---|
| `msg` | 工具的唯一入参，模型要说的一段话 |
| 分句 | 两个边界标点之间的一段文本，边界标点见「切分算法」 |
| 段 | 一次合成、一次 SSE 推送、一个播放队列项；一段由若干分句贪心拼装而成，长度受 `max_segment_chars` 限制 |
| 段序 | 一段在本次工具调用内的序号，从 0 开始，用于队列排序与丢帧检测 |
| 工具事实 | `tool_started` / `tool_done` / `tool_failed` / `tool_ended`，由内核落盘 |
| 插件事件 | 类型为 `plugin_event` 的 SSE 帧，不落盘、不参与断线续传 |
| 播放页 | 每个浏览器标签页各自持有一个播放器与队列，互不同步 |

「一句」在口语里指一段可朗读的话；实现与文档统一用「段」表示合成单位，
避免与「分句」混淆。

## 不变量

1. 内核与机制层不出现 `ai_speak`；插件只依赖 `core` / `mechanisms` / `capabilities`
   的公开接口与 `SERVICE_PLUGIN_EVENTS` 服务，不 import `agent.app` / `agent.entry` /
   `agent.shell`。
2. 语音只在后端合成。前端不调用浏览器 TTS，不保存音频文件。
3. 工具事实由内核产生；音频帧是实时旁路，不写事实日志，不参与 SSE 续传。
4. 校验在工具入口一次完成。校验失败时整次调用失败，不产生部分入队。
5. 单段上限取 `max_segment_chars`（默认 128，可配置为 300、1000 等正整数）；
   单次 `msg` 最多 512 字。
6. 同一会话的合成串行：后一段的合成与推送不越过前一段。
7. 每个浏览器标签页各有一个播放队列，队列项按到达顺序播放；不同标签页互不同步。
8. 插件关闭、回合被用户停止、播放器停止按钮三者都清空本页队列并停止当前音频。
9. 插件事件帧不带顶层 `seq`。`seq` 是 SSE 断线续传的存储坐标，音频段序号用
   `index` / `total` 表达。
10. 配置模板与解析器读取的键集合双向一致，由测试锁定。
11. 旧 `tts` 与前端 `audio` 分支不保留转发层、别名或空壳。

## 现状

| 项 | 事实 |
|---|---|
| 合成位置 | `plugins/tts/plugin.py` 用 `edge_tts` 在后端合成，`_emit_audio` 只写 stderr |
| 前端播放 | `stream.js` 有 `audio` 分支调用 `playAudio`，但素材里没有 `playAudio` 定义 |
| 契约 | `EV_AUDIO` 被放进 `NEVER_EMIT`，`test_audio_never_emitted` 锁定「不发它」 |
| 插件事件 | 没有通用出口；`ClassicAdapter` 只有 `announce_plugins` / `announce_model` |
| 插件端点 | `/api/plugin/<名>/...` 只返回 JSON 或文本，不能直接送二进制音频 |
| 设置广播 | `plugins_changed` 只被壳层 `applyPluginsChanged` 消费，插件脚本没有公开钩子 |
| 工具入参 | 工具执行时 `msg` 已是完整字符串，不存在字符级增量 |

由此得到两条设计约束：

- 「连续文字拼句」由后端完成。后端切段后逐段合成、逐段推送，前端只排队播放。
- 音频不能走插件 HTTP 端点，改用 SSE 下发 base64，前端生成 Blob URL 播放。

## 总体结构

```
模型
  └─ ai_speak(msg)
       ├─ text.validate()        字符、配对、长度、结尾
       ├─ text.split()           分句 → 按 max_segment_chars 贪心装段
       ├─ runtime.enqueue()      按会话串行排队
       │    └─ worker            edge-tts 合成 → base64
       │         └─ ClassicAdapter.announce_plugin_event()
       │              └─ SSE plugin_event
       │                   └─ 前端播放器队列 → <audio> 顺序播放
       ├─ tool_started / tool_done / tool_ended（内核事实）
       └─ 对话区工具壳（插件 tool-view）

设置页开关
  └─ sync_plugins → plugin_host.load / unload
       ├─ 装载：注册工具、启动脚本、只读端点
       └─ 卸载：撤工具/端点/启动脚本、停止合成、广播 stop
            └─ SSE plugins_changed / 播放器停播
```

| 组件 | 位置 | 职责 |
|---|---|---|
| 工具 | `plugins/ai_speak/tool.py` | 校验 `msg`、取会话与插件事件发布器、调用运行时入队 |
| 文本 | `plugins/ai_speak/text.py` | 字符白名单、配对校验、切分与装段（纯函数） |
| 配置 | `plugins/ai_speak/config.py` | 读 `[config]`、取默认值、校验范围（无副作用） |
| 合成 | `plugins/ai_speak/provider.py` | edge-tts 适配、超时、异常归类 |
| 运行时 | `plugins/ai_speak/runtime.py` | 每会话串行队列、worker、停止、计数 |
| 入口 | `plugins/ai_speak/plugin.py` | 装配、注册工具/端点/启动脚本/事件订阅 |
| 播放器 | `plugins/ai_speak/ui/player.js` | 本页队列、音频元素、间隔、暂停/停止 |
| 样式 | `plugins/ai_speak/ui/player.css` | 悬浮播放条，类名前缀 `ai-speak-` |
| 工具卡 | `plugins/ai_speak/ui/tool-view.js` | 对话区标题与摘要，挂默认请求/响应面板 |
| 通用事件出口 | `agent/core/context.py`、`agent/app.py`、`agent/shell/classic_adapter/` | `SERVICE_PLUGIN_EVENTS` + `PluginEventPublisher` + `plugin_event_frame` + `announce_plugin_event` |
| 播放器开关通知 | `agent/shell/web_assets/classic/js/plugins/host.js` | 把 `plugins_changed` 转成 DOM 事件 |

## 包结构

```
plugins/ai_speak/
  plugin.py                 入口：读配置 → 建运行时 → 注册工具/端点/启动脚本/订阅
                            `_config_path()` 委托 `config.config_path()`，供配置归属测试
  config.py                 AISpeakConfig + load_config()（纯函数）
  text.py                   validate / split / to_speech_text（纯函数）
  provider.py               SpeechAudio / TTSProvider / EdgeTTSProvider
  runtime.py                AISpeakRuntime + 每会话 worker
  tool.py                   AISpeakTool
  plugin-config.ini [config]
  ui/player.js              浮动播放条与队列
  ui/player.css             播放条样式
  ui/tool-view.js           对话区工具卡视图
```

职责边界：

| 文件 | 只做 | 不做 |
|---|---|---|
| `plugin.py` | 装配与注册、事件订阅、端点处理器 | 字符校验、合成调用 |
| `config.py` | 读取与校验配置、导出常量 | 创建线程、访问网络 |
| `text.py` | 校验、切分、TTS 文本净化 | 读写配置、合成 |
| `provider.py` | 调 edge-tts、超时、错误归类 | 队列、SSE、会话状态 |
| `runtime.py` | 队列、worker、停止、计数、发布事件 | 解析配置、校验文本 |
| `tool.py` | 取会话/发布器、调用运行时、返回结果 | 直接合成、直接广播 |

单文件目标行数均在 800 行以下，单函数在 80 行以下。预计 Python 约 850 行，
前端约 500 行，测试约 900 行。

## 工具契约

```python
class AISpeakTool(ToolPlugin):
    name = "ai_speak"
    label = "AI说话"
    icon = "🔊"
    parallel_safe = False
    needs_preview = False
    write_path_keys = ()

    parameters = {
        "msg": {
            "type": "string",
            "description": "要说的话；当前角色口吻、人类口语；单次最多 512 字。",
        }
    }
```

工具描述（模型可见）：

```
把你要对用户说的话直接说出来。用当前角色的第一人称、人类口语，像当面汇报，
不使用播音腔、书面语，不解释自己在调用工具。每完成一步就调用一次，不等到全部做完。

允许：中文、英文、数字、空格；中文标点 ，。？！；、：“”‘’（）；
英文标点 . , ? ! ; : ' " ( )；四则符号 + - * / × ÷（含全角 ＋－＊／）；
百分号 % 或 ％。英文单词内可用 - 和 '。
禁止其他符号、emoji、换行、Markdown、代码、链接。

每个分句以边界标点结尾；后端按标点贪心拼装，单段上限取插件配置
max_segment_chars（默认 128 字），超过上限会失败并返回规范。
一次最多 512 字。例如「进度 10%。」会读成「进度 百分之十。」；
「5+3。」会读成「五加三。」。

示例：主子，文件已经写好了，您要不要看一眼？
```

成功返回：

```json
{
  "accepted": true,
  "segments": 3,
  "characters": 210
}
```

同步模式在播放完成后额外返回 `"played": true` 与 `"waited_ms": N`。
内核把它包成 `{"ok": true, "data": {...}}` 回灌模型；工具卡响应面板显示同一信封。

失败返回：

| 异常 | 触发 | 顶层结果 |
|---|---|---|
| `MessageValidationError` | 空、超过 512 字、非法字符、配对错误、结尾错误、分句超限 | `{"ok": false, "error": "..."}` |
| `SpeechEngineUnavailable` | `edge-tts` 未安装、无 Web 壳连接 | 同上，错误文案给可执行动作 |
| `SpeechBusy` | 该会话待合成段达到上限 | 同上，附当前队列长度 |

工具成功只表示「已接受并入队」，不表示音频已经合成或播放。逐段合成失败通过
`error` 插件事件送到播放器，并在 `/status` 计数；不改变已经返回的工具结果。

## 文本规范

### 允许字符

| 类别 | 允许 |
|---|---|
| 中文 | `U+3400–U+4DBF`、`U+4E00–U+9FFF` |
| 英文 | `A–Z`、`a–z` |
| 数字 | `0–9` |
| 空格 | 半角空格 `U+0020`、全角空格 `U+3000` |
| 中文标点 | `，` `。` `？` `！` `；` `、` `：` `“` `”` `‘` `’` `（` `）` |
| 英文标点 | `.` `,` `?` `!` `;` `:` `'` `"` `(` `)` |
| 四则符号 | `+` `-` `*` `/` `×` `÷` `＋` `－` `＊` `／` |
| 百分号 | `%`、`％`，只在数字之后，见「百分号」 |

其余字符一律拒绝，包括但不限于：

- ASCII 的 `[ ] { } \ | < > = # @ & _ ~ ^ $` 与反引号
- 全角字母数字、不间断空格、制表符、换行、控制字符、零宽字符
- `《》` `【】` `…` `—` `·` `～` `￥`
- emoji

`-` 有三种合法位置：夹在两个 ASCII 字母或数字之间（`well-known`、`GPT-4`、
`2026-10-19`）；作为二元减号（`5-3`、`5 - 3`）；作为负数前缀（`-5`）。
`-abc`、`abc-`、`a--b` 不合法。`'` 夹在两个 ASCII 字母之间时是英文撇号，
不参与引号配对；其余位置的 `'` 是英文单引号，必须成对。

### 配对与结构

1. 引号与括号必须成对：`“”`、`‘’`、`（）`、`""`、`''`、`()`；允许嵌套，
   禁止交叉；中文开符号只能由对应中文闭符号收尾，英文同理。
2. 空对 `“”`、`‘’`、`（）`、`""`、`''`、`()` 拒绝。
3. 文本不能以边界标点或闭引号/闭括号开头。
4. 文本不能以开引号/开括号结尾。
5. 连续边界标点作为一个边界整体，允许 `...`、`?!` 这类英文写法。
6. 文本必须以边界标点结尾，或以其后紧跟闭引号/闭括号结尾。

### 百分号

`%` / `％` 前面必须是一个 ASCII 数字，中间允许空格；数字可带小数点和千分位
逗号。合成前把「数字 + 百分号」整体转成中文「百分之 + 数字」：

| 原文 | 合成文本 |
|---|---|
| `10%` | `百分之十` |
| `3.5%` | `百分之三点五` |
| `100%` | `百分之百` |
| `1,000%` | `百分之一千` |
| `0%` | `百分之零` |

整数按中文数位转写：`10` 读十，`11` 读十一，`20` 读二十，`101` 读一百零一，
`100` 读百，`1000` 读一千。小数逐位读，小数点读「点」。数字中的千分位逗号
在合成文本中删除；小数点保留。`%` 前面不是 ASCII 数字时校验失败，并指出位置。
上表是合成文本片段；完整 `msg` 仍须以边界标点结尾，例如 `进度 10%。`。

### 四则符号

`+` `-` `*` `/` `×` `÷` 及全角 `＋` `－` `＊` `／` 都允许。位置规则：

- `+`/`＋`、`*`/`＊`、`/`/`／`、`×`、`÷` 必须是二元符号，左右各有一个
  非空白操作数；文本开头、结尾或左右为空时拒绝；
- 操作数指字母、数字、闭括号或闭引号；边界标点不算操作数；
- `-`/`－` 可以是二元减号、负数前缀，或英文连接符；
- 四则符号不能连续出现（`5--3`、`3**4` 拒绝）。

合成前把数字之间的简单四则运算转成中文读法：

| 原文 | 合成文本 |
|---|---|
| `5+3` | `五加三` |
| `10-2` | `十减二` |
| `3*4`、`3×4` | `三乘四` |
| `10/2`、`10÷2` | `十除以二` |
| `-5` | `负五` |
| `well-known` | `well-known` |
| `2026-10-19` | `2026-10-19` |

只转换「数字 + 符号 + 数字」或「负数前缀」这两种形态；全角符号按同一规则
转换。英文连接符与日期里的 `-` 原样保留。字母之间的 `/`、`+` 等不转换，
交给 edge-tts 按原文处理。

### 长度

| 项 | 上限 | 含义 |
|---|---|---|
| 单段 | `max_segment_chars`（默认 128，正整数，无配置上限） | 一次合成、一次 SSE、一个队列项的文本长度 |
| 单分句 | `max_segment_chars`（同上） | 两个边界标点之间的文本；超过即失败 |
| 单次 `msg` | 512 字 | 一次工具调用的原始文本长度；超过拒绝 |

`max_segment_chars = 300` 时按 300 字贪心装段；`max_segment_chars = 1000`
时按 1000 字贪心装段。该值没有 128 的硬上限，128 只是默认值。单个分句超过
配置值时工具失败并指出分句序号、长度与配置上限，不在词中间硬切。

## 切分算法

### 边界

边界标点：

- 中文：`，` `。` `？` `！` `；` `、` `：`
- 英文：`.` `,` `?` `!` `;` `:`

四则符号与百分号不是边界标点，`5+3`、`10%` 不会在符号处切分。扫描时维护一个
期望闭符号栈：

- `“` 压入 `”`，`‘` 压入 `’`，`（` 压入 `）`；
- `"` 压入 `"`，`(` 压入 `)`；
- `'` 夹在两个 ASCII 字母之间时是撇号，不入栈；其余位置压入 `'`；
- 遇到闭符号时与栈顶比较，不匹配即失败；
- 栈为空时遇到的边界标点是一个分句边界；
- 连续边界标点（`...`、`?!`）合并为一个边界整体；
- 文本末尾若由闭符号收尾，且最后一个非闭符号是边界标点，该末尾也是一个边界。

三个英文标点在数字之间有特殊含义，不参与切分：

| 形态 | 处理 |
|---|---|
| `3.14` | `.` 是小数点，保留在数字里 |
| `1,000` | `,` 是千分位，保留在数字里；合成文本中删除 |
| `10:30` | `:` 是时间分隔，保留在数字里 |

引号或括号内部的标点不切分，避免把一段引语切成两段。跨引号的分句在一次扫描中
作为一个整体处理。

### 装段

1. 按边界切出分句，每个分句必须非空。
2. 每个分句长度不得超过 `max_segment_chars`；超过即返回失败，指出分句序号、
   长度与配置上限。
3. 按顺序贪心装段：当前段加入下一个分句后不超过配置值就加入，否则先结束当前段。
4. 每个段都以边界标点结尾；闭引号/闭括号可以跟在后面。
5. 段数不另设上限；它受 512 字的 `msg` 上限约束。

示例（`max_segment_chars = 128`）：

| 输入 | 结果 |
|---|---|
| `主子，文件写好了，您看一眼？` | 1 段：`主子，文件写好了，您看一眼？` |
| `第一句。第二句！` | 1 段（总长不超过 128，多个分句合并） |
| 70 字分句 + 70 字分句 | 2 段 |
| `他说“好。”` | 1 段；末尾由闭引号收尾，最后一个非闭符号是 `。` |
| `Wait... what?` | 1 段；`...` 与 `?` 是边界整体 |
| `进度 10%。` | 1 段；合成文本为 `进度 百分之十。` |
| `a` × 129 且无标点 | 失败：缺少边界，单分句超过 128 |
| `hello-world don't` | 字符合法；没有边界，失败：必须以边界标点结尾 |

`max_segment_chars = 300` 时同样的输入按 300 字装段；`max_segment_chars = 1000`
时按 1000 字装段。

### TTS 文本

送合成前执行：

1. 移除中文/英文引号与括号符号本身，保留其中文本；
2. 把「数字 + `%` / `％`」转成「百分之 + 中文数字」，见「百分号」；
3. 把数字之间的简单四则运算与负数前缀转成中文读法，见「四则符号」；
4. 删除数字里的千分位逗号，保留小数点；
5. 保留 `，。？！；、：`、英文 `. , ? ! ; :`、英文 `-`、撇号 `'`，
   以及没有被第 3 步转换的四则符号；
6. 连续空格压成一个，首尾去空白。

SSE 下发的 `text` 是原始段文本，播放器显示原始文本；合成使用净化后的文本。

## 后端合成

### 端口

```python
@dataclass(frozen=True, slots=True)
class SpeechAudio:
    data: bytes
    mime: str = "audio/mpeg"
    voice: str = ""


class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, *, voice: str, timeout_s: float) -> SpeechAudio: ...
```

### edge-tts 适配

- 延迟导入 `edge_tts`；插件装载不因缺库失败。
- 合成使用异步流：`asyncio.run` 内用 `asyncio.wait_for` 包住 `Communicate.stream()`，
  收集 `type == "audio"` 的字节块。
- 超时、无音频、网络异常、音色不存在都转成 `SpeechSynthesisError`，附音色名与
  文本前 20 字；不把底层堆栈交给模型。
- 单段音频超过 4 MB 视为异常，丢弃该段并发布错误；512 字的段通常远低于该值。
- 合成结果只留在内存，不写磁盘。

`engine` 只接受 `edge`；其它值在装载期报错，插件卡片显示失败原因。

### 超时

单段合成超时 15 秒。超时后该段失败、发布 `error` 事件、继续处理下一段；
不重试同一段，避免把队列拖死。

## SSE 契约

### 通用出口

在 `agent/core/context.py` 增加服务名：

```python
SERVICE_PLUGIN_EVENTS = "plugin_events"
```

在 `agent/shell/classic_adapter/contract.py` 增加：

```python
EV_PLUGIN_EVENT = "plugin_event"

def plugin_event_frame(
    plugin: str,
    event: str,
    payload: dict | None = None,
) -> dict: ...
```

规则：

1. `plugin` / `event` 非空，去掉首尾空白；`plugin` 只允许 `[A-Za-z0-9_-]`。
2. `payload` 必须是 dict 或 None；返回新 dict，不修改调用方对象。
3. 保留键 `type`、`plugin`、`event`、`seq` 不允许出现在 payload；
   出现即 `ValueError`。`seq` 被 SSE 传输层当作断线续传游标，插件事件不能占用。
4. 帧形状固定为 `{"type": "plugin_event", "plugin": ..., "event": ...}` 加 payload。

`ClassicAdapter` 增加公开方法：

```python
def announce_plugin_event(self, plugin: str, event: str,
                          payload: dict | None = None) -> int:
    return self._broadcast(C.plugin_event_frame(plugin, event, payload))
```

该方法不经过 `translate()`，不落盘，不参与 `replay_after()`；返回值是本帧实际
广播到的 SSE 连接数。`_broadcast` 同步改为返回投递数，现有调用方忽略返回值。
`agent/shell/classic_adapter/plugin_events.py` 的 `PluginEventPublisher` 包住这个方法，
暴露 `__call__` 与 `connected()`；`build_app()` 把它登记为
`SERVICE_PLUGIN_EVENTS`。插件经 `current_context().app.get(SERVICE_PLUGIN_EVENTS)`
取用，不 import `agent.shell`。连接数为 0 时工具返回「没有已连接的 Web 界面」，
不入队、不合成。

### 帧类型

| 事件 | 字段 | 语义 |
|---|---|---|
| `segment` | `conversation_id`、`call_id`、`index`、`total`、`text`、`voice`、`mime`、`audio`、`bytes`、`gap_ms` | 一段音频就绪 |
| `error` | `conversation_id`、`call_id`、`index`、`code`、`message` | 某段合成失败；播放器提示后继续 |
| `stop` | `conversation_id`、`reason` | 停止该会话的播放；无 `conversation_id` 时停全部 |

`segment.audio` 是标准 base64，不带 `data:` 前缀；`mime` 目前固定
`audio/mpeg`。`gap_ms` 是服务端配置的串行播放间隔，播放器以最近一帧为准，
配置保存后不需要重新加载启动脚本。

示例：

```json
{
  "type": "plugin_event",
  "plugin": "ai_speak",
  "event": "segment",
  "conversation_id": "0f3c...",
  "call_id": "call-7",
  "index": 0,
  "total": 3,
  "text": "主子，文件已经写好了。",
  "voice": "zh-CN-XiaoxiaoNeural",
  "mime": "audio/mpeg",
  "audio": "SUQz...",
  "bytes": 18234,
  "gap_ms": 0
}
```

### 顺序与丢失

- 同一会话的 worker 串行合成、串行发布；`index` 严格递增。
- 不同会话的段在全局通道按到达顺序交错；播放器按到达顺序播放。
- SSE 连接慢时 `_Channel` 会丢最旧帧；音频帧不重放。播放器按
  `(call_id, index)` 检测缺口，缺口只提示一次，不尝试补发。
- 断线重连只恢复工具事实与界面状态；已经错过的音频不补。

### 帧体积

单段音频上限 4 MB，base64 约 5.3 MB；SSE 帧仍在单连接队列可承受范围内。
播放器对单帧做大小检查，超过上限直接丢弃并提示。

## 前端播放器

### 形态

右下角悬浮迷你条，固定定位，不占布局：

```
┌──────────────────────────────────────┐
│ 🔊 AI说话  当前句…        队列 3  ⏸  ■ │
└──────────────────────────────────────┘
```

- 当前句最多显示 60 字，超出省略；完整文本放在 `title`。
- 队列数显示待播项数量；0 时隐藏队列数字。
- 暂停/继续按钮；停止按钮清空队列并隐藏播放条。
- 自动播放被浏览器拦截时，显示「点击播放」按钮，队列保留。
- 播放条不抢焦点；按钮带 `aria-label` 与 `title`。

### 队列

```js
items = [
  { cid, callId, index, total, text, mime, url }
]
```

- `enqueue(frame)`：去重 `(callId, index)`；入队；超过 512 项时丢弃最旧的待播项
  并计数；空闲时启动 `playNext()`。
- `playNext()`：取出队首，生成 Blob URL，设置 `<audio>`，调用 `play()`。
- `ended`：释放 URL，等待 `gap_ms`，播下一项。
- `error`：释放 URL，显示错误 3 秒，播下一项。
- `stop(cid?, callId?)`：暂停并释放当前；按范围过滤队列；范围为空时清空。
- `pause()` / `resume()`：暂停/继续当前音频；等待间隔期间暂停则清掉定时器。

### 自动播放

`audio.play()` 返回的 Promise 被 `NotAllowedError` 拒绝时：

1. 保留当前项与队列；
2. 设置 `blocked = true`，显示「点击播放」；
3. 用户点击后再次 `play()`，成功后清掉 `blocked`；
4. 其他错误按播放失败处理，提示并继续下一项。

### 多标签页

每个浏览器标签页各自创建播放器、`<audio>` 与队列。SSE 广播到每一页，各页独立
播放；一个页面暂停或停止不影响其它页面，也不做跨标签页的同步。
同步播放按首个 ack 放行，默认假设只有一个活动播放页。

### 同步播放

`sync_playback = 1` 时，工具在入队前登记 `(conversation_id, call_id)`，等前端把
最后一段播完后返回。播放器按 `call_id` 统计段数，最后一段 `ended` 后调用
`POST /api/plugin/ai_speak/played`；`status` 为 `played` / `stopped` /
`error` / `incomplete`。

- `incomplete` 按 `dropped` 处理；队列丢弃、无 SSE、合成失败都不能报已播完。
- 用户停止时播放器同时请求 `/api/chat/stop`；工具等待期间检查回合取消标记。
- 等待超时按文本长度计算，`max(30s, min(600s, 15s + 字符数 × 0.35))`。
- 自动播放被拦截时播放器不 ack；用户点击播放并播完后才 ack。
- 等待者只存 `(conversation_id, call_id)` 与状态，不改变音频帧契约。

### 配置

启动脚本调用 `GET /api/plugin/ai_speak/config`：

```json
{"ok": true, "play_interval_ms": 0, "max_segment_chars": 128,
 "voice": "zh-CN-XiaoxiaoNeural", "engine": "edge",
 "sync_playback": false}
```

`segment` 帧的 `gap_ms` 覆盖本地值。配置读取失败时 `gap_ms` 取 0，
播放条仍可工作。

### 设置开关

- 播放器监听 `ai-agent:plugins-changed`；`loaded` 不含 `ai_speak` 时立即
  `stop()`、移除播放条。
- 插件后端在卸载时发布 `stop`（尽力而为）；两个通道任一到达都能停播。

### 资源释放

- 每个 Blob URL 在 `ended` / `error` / `stop` 时 `URL.revokeObjectURL`。
- 定时器在停止、暂停、页面卸载时清理。
- 播放条移除时解绑所有监听器；重复初始化先调用上一次的 `destroy()`。

## 工具卡

插件通过开屏脚本注册 `window.aiAgentChatTools.register`：

| 属性 | 值 |
|---|---|
| `match` | `chatToolName(script) === "ai_speak"` |
| `title` | `AI说话` |
| `summary` | `args.msg` 原文 |
| `mount` | 建「请求」与「响应」两个默认面板 |
| `fill` | 用 `chatToolResponseText` 填响应面板 |

壳层在标题与摘要之间画一条竖分隔线，视觉为「AI说话 │ 消息」；摘要文本完整值放在
`title` 属性，长消息由 CSS 省略。展开详情仍是默认的请求/响应报文，不注册自定义
详情视图。

左侧步骤卡只显示工具名「AI说话」；对话区工具壳显示消息摘要。两者共用同一次
工具调用的 `tool_call_id`。

## 生命周期与开关

### 装载

1. 读 `plugin-config.ini` 的 `[config]`，校验 `engine`、解析数值。
2. 建 `AISpeakRuntime`，此时不创建线程。
3. 注册 `AISpeakTool`。
4. 注册两个开屏脚本：`ui/player.js`、`ui/tool-view.js`。
5. 注册只读端点 `GET config`、`GET status`，以及播放完成的 `POST played`。
6. 订阅 `turn_ended` 与 `error`：回合被停止/中断时停该会话的队列。
7. `ctx.set_runtime(runtime)`，供壳层与测试按名字取同一实例。
8. 工具执行时从 `current_context().app` 取 `SERVICE_PLUGIN_EVENTS`；
   取不到或返回 0 个连接时返回不可用错误。
9. 返回 disposer 列表；任一注册失败时先 `runtime.dispose()` 再抛出。

### 卸载

1. 宿主逆序执行 disposer。
2. `runtime.dispose()`：停止接受新段、唤醒 worker、清空队列、发布 `stop`。
3. 工具、端点、开屏脚本由宿主撤销。
4. 设置页广播 `plugins_changed`；前端 `applyPluginsChanged` 派发
   `ai-agent:plugins-changed`，播放器停播并移除播放条。

### 重新启用

开屏脚本按 URL 去重，卸载时壳层的 `prunePluginScripts` 会删除脚本标签并清掉
加载表；再次启用时脚本重新执行。播放器初始化前先销毁旧实例，避免双份 `<audio>`
与双份监听器。

### 回合停止

`turn_ended` 的 `stopped` 或 `halted` 为真时，停该会话的队列；正常 `done` 不打断
已经排队的音频，让最后几句播完。`error` 事件同样停该会话队列。

## 配置

`plugins/ai_speak/plugin-config.ini`：

```ini
[config]
engine = edge
voice = zh-CN-XiaoxiaoNeural
max_segment_chars = 128
play_interval_ms = 0
sync_playback = 0
```

| 键 | 默认 | 范围 | 说明 |
|---|---|---|---|
| `engine` | `edge` | 仅 `edge` | 合成引擎；其它值在装载期报错 |
| `voice` | `zh-CN-XiaoxiaoNeural` | 非空 | edge-tts 音色名；未知音色在合成期报错 |
| `max_segment_chars` | 128 | ≥ 1 的整数，无上限 | 单段字符上限；300 按 300 贪心，1000 按 1000 贪心 |
| `play_interval_ms` | 0 | ≥ 0 | 段间播放间隔（毫秒） |
| `sync_playback` | 0 | `0` / `1` | 1 = 工具等前端播完再返回 |

解析规则：

- 文件缺失 → 全部取默认值；真实配置由设置页生成。
- 整数键：非数字取默认；`max_segment_chars` 小于 1 取默认 128；
  `play_interval_ms` 小于 0 取 0。两者回退时记一条 `report_error`。
  `max_segment_chars` 不设上限。
- 开关在 `plugins.ini` 的 `enabled`，`0` 不装载。
- 未知 `[config]` 键忽略，不阻断装载。
- `engine` 非 `edge`、`voice` 为空、配置解析抛错：记 `report_error` 并让插件
  装载失败，错误出现在插件列表与 stderr。

配置模板与解析器键集合由 `tests` 双向比对：模板缺键、模板多键、解析器读了
模板没有的键，三种情况都失败。

## 并发与资源

### 运行时结构

```python
class AISpeakRuntime:
    _workers: dict[str, _SessionWorker]
    _lock: threading.Lock
    _disposed: bool
    _totals: Counter
```

`_SessionWorker`：

```python
class _SessionWorker:
    _queue: queue.Queue[_SegmentJob | None]
    _thread: threading.Thread
    _stop: threading.Event
    _generation: int
```

### 串行保证

- 每个会话一个 worker；`enqueue` 在运行时锁内检查队列容量并一次放入全部段，
  避免部分入队。
- worker 逐段取、逐段合成、逐段发布；同一会话的 `index` 严格递增。
- 不同会话的 worker 并行；每个浏览器标签页只有一个队列，按到达顺序播放。

### 停止与取消

- `stop_cid(cid, reason)`：提升该会话的 generation、清空待播段、发布 `stop`；
  worker 在每次合成前与发布前检查 generation 与 `_stop`。
- `dispose()`：置 `_disposed`，对所有 worker 置 `_stop`、投 `None`、等待最多 3 秒；
  仍未退出则记一条 `report_error` 并放弃等待（daemon 线程）。
- 停止顺序：停止接受新段 → 停 worker → 清队列 → 发布 stop → 清计数。

### 队列上限

| 队列 | 上限 | 超限行为 |
|---|---|---|
| 每会话待合成段 | 1024 | 工具返回 `SpeechBusy`，不入队 |
| 前端待播项 | 512 | 丢最旧待播项，计数并在播放条提示 |
| 单帧音频 | 4 MB | 该段失败，发布 `error` |

### 并发检测

`tests/test_concurrency.py` 增加一组用例：多线程向同一会话入队、停止与入队并发、
两个会话并行、队列满时拒绝。CI 已用 `-X dev` 跑该文件。

## 错误与可观测性

### 错误类别

| 类别 | 产生方 | 处理 |
|---|---|---|
| 校验失败 | `text.validate` | 工具抛 `MessageValidationError`；顶层 `ok=false`；不落音频 |
| 依赖不可用 | `EdgeTTSProvider` / 无 SSE 连接 | 工具抛 `SpeechEngineUnavailable`；文案给安装或启用路径 |
| 队列忙 | `runtime.enqueue` | 工具抛 `SpeechBusy`；文案给队列长度与重试建议 |
| 合成失败 | worker | 发布 `error` 事件；`report_error` 留痕；继续下一段 |
| 播放失败 | 前端 | 播放条提示；跳过当前项；控制台留错误 |
| 事件非法 | `plugin_event_frame` | 抛 `ValueError`；插件侧记录；不广播 |

### 状态端点

`GET /api/plugin/ai_speak/status`：

```json
{
  "ok": true,
  "engine": "edge",
  "engine_ready": true,
  "voice": "zh-CN-XiaoxiaoNeural",
  "max_segment_chars": 128,
  "play_interval_ms": 0,
  "sessions": [
    {"conversation_id": "0f3c...", "queued": 2, "spoken": 5, "failed": 0, "dropped": 0}
  ],
  "totals": {"queued": 12, "spoken": 10, "failed": 1, "dropped": 0},
  "last_error": {"code": "synthesis_failed", "message": "..."}
}
```

不返回密钥（插件没有密钥）；`last_error` 只保留最近一条，避免状态无界增长。

### 日志

- 配置错误、合成错误、停止超时走 `report_error("plugin.ai_speak", ...)`。
- 逐段成功不写 stderr，避免每句刷屏；计数由 `/status` 提供。
- 播放器错误写 `console.error`，不把服务器文本当 HTML 插入。

## 安全与信任

| 项 | 约束 |
|---|---|
| 信任边界 | 插件与本机代码同等信任；装载后同进程运行，没有沙箱 |
| 输入校验 | 在工具入口一次完成；下游不再猜字符是否合法 |
| DOM 注入 | 播放器与工具卡只用 `textContent`；不把服务器文本放进 `innerHTML` |
| 样式隔离 | 类名前缀 `ai-speak-`；样式文件由插件资产路由送达 |
| 音频体积 | 单段 4 MB 上限；base64 只在内存中生成 Blob |
| 文件 | 不写磁盘、不读用户文件、不拼路径 |
| 网络 | 只由 edge-tts 访问其服务；插件不另发请求 |
| 秘密 | 插件没有密钥；配置模板不含凭据 |
| 事件出口 | `plugin_event_frame` 校验插件名/事件名/保留键；不接受任意路由 |

每个浏览器标签页各自创建播放器与队列，SSE 广播到每一页；多标签页可以同时播放，
互不暂停、停止或同步。播放器只保留本页内存状态。

## 旧 tts 清理

| 文件 | 动作 |
|---|---|
| `plugins/tts/` | 整目录删除（含真实 `plugin-config.ini`，删除前备份） |
| `plugins.ini` | 去掉 tts 注释节，加入 `[plugin:ai_speak]` |
| `plugins.ini` | 注释示例改为 `ai_speak` |
| `agent/core/context.py` | 增加 `SERVICE_PLUGIN_EVENTS` 服务名 |
| `agent/app.py` | 把 `PluginEventPublisher(classic)` 登记为 `SERVICE_PLUGIN_EVENTS`（装配末尾、插件装载之前） |
| `agent/shell/classic_adapter/plugin_events.py` | 新增窄发布器：`__call__` 返回送达连接数，`connected()` 查询是否有连接 |
| `agent/shell/classic_adapter/contract.py` | 删除 `EV_AUDIO` / `NEVER_EMIT`；增加 `EV_PLUGIN_EVENT` 与 `plugin_event_frame` |
| `agent/shell/classic_adapter/adapter.py` | 增加 `announce_plugin_event`，返回连接数；保持文件不超过 800 行 |
| `agent/shell/web_assets/classic/js/chat/stream.js` | 删除两处 `audio` 分支；增加 `plugin_event` 转发到 DOM |
| `agent/shell/web_assets/classic/js/plugins/host.js` | `applyPluginsChanged` 派发 `ai-agent:plugins-changed` |
| `agent/shell/web_assets/classic/css/theme-light.css` | 删除未使用的 `.tts-toggle-btn` |
| `agent/shell/web_assets/classic/agent-ui.html` | 删除顶部 TTS 入口注释 |
| `tests/test_classic_adapter.py` | 删除 `test_audio_never_emitted`；更新订阅数注释；补 `plugin_event_frame` 用例 |
| `tests/test_kb_plugin.py` | 插件目录清单用 `ai_speak` 替换 `tts` |
| `tests/test_settings_panel.py` | 夹具中的 `plugin:tts` 文本改为 `plugin:ai_speak` |
| `tests/test_plugin_http.py` | 注释里的 `tts` 改为 `ai_speak` |
| `scripts/acceptance_phase3.py` | 用 `ai_speak` 替换 `tts`；断言工具/端点/启动脚本/卸载 |
| `docs/subsystems/plugins.md` | 内置插件表与最小形态示例更新 |
| `docs/subsystems/tools.md` | 插件工具清单加入 `ai_speak` |
| `docs/architecture.md` | 删除 TTS 专属表述，改为通用插件边界 |
| `catalog/tools.json` | 重新生成，包含 `ai_speak` |
| `docs/unit-tests.md` | 重新生成 |
| `README.md` | 更新用例数与文档索引 |

旧 `tts` 不保留别名、转发模块或兼容导入。旧会话事实里没有音频，删除不改变历史可读性。

## 测试计划

### 单元测试

`tests/test_ai_speak_text.py`

| 类 | 覆盖 |
|---|---|
| `CharacterTest` | 中英文允许字符；四则符号；每一类拒绝字符；emoji、换行、全角字母数字 |
| `PairTest` | 中文/英文引号与括号配对、嵌套、交叉、空对、撇号与单引号区分 |
| `ConnectorTest` | `-` 的连接符、二元减号、负数前缀、连续与首尾位置 |
| `BoundaryTest` | 中英文分句边界、引号内标点、闭符号收尾、缺失结尾、`...`/`?!` |
| `NumberTest` | `3.14` 小数点、`1,000` 千分位、`10:30` 时间不作为边界 |
| `PercentTest` | `10%`、`3.5%`、`100%`、`1,000%`、`0%` 的中文读法；非数字后的 `%` 拒绝 |
| `MathTest` | `5+3`、`10-2`、`3*4`、`10/2`、`×`、`÷`、全角符号、`-5`、日期与英文连接符 |
| `SplitTest` | 单段、多分句合并、`max_segment_chars` 128/300/1000、分句超限、512 字上限 |
| `SpeechTextTest` | 引号/括号移除、百分号转换、四则转中文、千分位删除、空格压缩 |
| `ConfigTest` | 缺文件、非法整数、非正数取默认、300/1000 生效、未知引擎、模板键双向一致 |

`tests/test_ai_speak_runtime.py`

| 类 | 覆盖 |
|---|---|
| `ProviderTest` | 假 edge-tts 流、空音频、异常、超时、缺库 |
| `RuntimeTest` | 入队顺序、发布顺序、base64、失败继续、停止、dispose、队列满、512 字 |
| `ToolTest` | 入参只有 `msg`、成功返回、校验失败、引擎缺失、无 Web 壳、队列忙 |
| `RegistrationTest` | 工具/端点/启动脚本/订阅/运行时注册；卸载后全部回收 |
| `ContractTest` | `plugin_event_frame` 保留键、空名、payload 拷贝、无 `seq` |

`tests/test_ai_speak_plugin.py`

| 类 | 覆盖 |
|---|---|
| `AISpeakAppTest` | `build_app` 装载工具/端点/启动脚本/运行时；事件发布器连接计数；卸载后全部回收 |

`tests/test_classic_adapter.py`

| 用例 | 覆盖 |
|---|---|
| `announce_plugin_event` | 广播到所有通道、返回连接数、无 `seq`、帧形状 |
| `plugin_event_frame` | 保留键拒绝、非法插件名/事件名、payload 不共享 |
| 删除 `test_audio_never_emitted` | 旧 `audio` 分支已移除 |

`tests/test_concurrency.py`

| 用例 | 覆盖 |
|---|---|
| 同会话多线程入队 | 不丢段、顺序稳定、无重复 |
| 入队与停止并发 | 停止后不再发布；已入队段被清空 |
| 两会话并行 | 各自串行，互不阻塞 |
| 队列满 | 拒绝整批，不出现部分入队 |

### 验收

- `scripts/acceptance_phase3.py`：临时清单装载 `ai_speak` + 知识库；
  断言工具存在、两个启动脚本、两个只读端点加 `POST played`、两个事件订阅、运行时已登记；
  卸载后全部消失、worker 停止、无残留线程。
- `scripts/acceptance_web.py`（播放器场景在 `acceptance_web_player.py`）：
  打开页面、确认播放条注入、派发 `plugin_event` 与 `plugins-changed`，断言无未捕获
  异常且关闭插件后播放条撤销。真实声音不在自动化里验证，用手动回归。
- 手动回归：
  1. 启动服务，设置页启用 AI说话，确认插件卡片与工具清单。
  2. 让模型执行一个多步任务，确认每一步调用工具、播放条逐段播放、句间间隔生效；
     把 `max_segment_chars` 设为 300 与 1000 各跑一次，确认装段长度随配置变化。
  3. 暂停/继续/停止；停止后当前音频立即停。
  4. 设置页关闭插件，确认播放停止、队列清空、工具消失；再启用后工具恢复。
  5. 打开两个标签页，确认两页各自播放；一页暂停/停止不影响另一页。
  6. 浏览器自动播放被拦截时，确认「点击播放」按钮可用。
  7. 卸载 `edge-tts`，确认工具返回可执行的安装提示。
  8. 输入带 `@`、emoji、换行、超过 512 字、单分句超过配置上限的消息，确认
     失败文案指出位置与规范；输入 `进度 10%。` 确认读成「进度 百分之十。」；
     输入 `5+3。`、`10-2。`、`3*4。`、`10/2。`、`-5。` 确认读成对应中文。
  9. 检查 `data/` 下没有新增音频文件。

### 覆盖率

`run_coverage.py` 口径已含 `plugins`，下限 60%。纯逻辑文件目标 85% 以上；
`provider` 的 edge-tts 适配通过假模块覆盖成功、异常、超时三条路径。

## 门禁与文档

实现后需要跑的目标检查：

```
python -m unittest tests.test_ai_speak_text tests.test_ai_speak_runtime \
    tests.test_ai_speak_plugin tests.test_classic_adapter tests.test_concurrency
python -m ruff check plugins/ai_speak tests/test_ai_speak_*.py \
    agent/shell/classic_adapter/contract.py agent/shell/classic_adapter/adapter.py
python scripts/check_comment_style.py
python scripts/check_architecture_hygiene.py
python scripts/check_ui_js.py
python scripts/gen_catalog.py
python scripts/check_catalog.py
python scripts/gen_unit_tests_md.py
python scripts/check_readme.py
python scripts/check_complexity.py
```

`catalog/tools.json` 与 `docs/unit-tests.md` 是生成物，先重新生成再比对。
`acceptance_phase3.py` 更新后纳入验收。

文档落点：

| 文件 | 内容 |
|---|---|
| `docs/plan/ai-speak.md` | 本方案 |
| `docs/subsystems/ai-speak.md` | 实现后的工具、文本规范、配置、SSE、播放器与限制 |
| `docs/subsystems/plugins.md` | 内置插件表与启动脚本/端点示例更新 |
| `docs/subsystems/tools.md` | 插件工具清单加入 `ai_speak` |
| `docs/architecture.md` | 删除旧 TTS 专属表述 |
| `README.md` | 文档索引与用例数 |
| `docs/unit-tests.md` | 生成物 |

## 交付顺序

| 顺序 | 内容 | 完成判据 |
|---|---|---|
| 1 | `text.py` + `config.py` + 单测 | 字符、配对、切分、配置用例全绿 |
| 2 | `provider.py` + 假 edge-tts 单测 | 成功、异常、超时、缺库路径全绿 |
| 3 | `runtime.py` + `tool.py` + 单测 | 串行、停止、队列满、计数稳定 |
| 4 | `plugin.py` + 配置模板 + 注册测试 | 临时清单可装载，卸载零残留 |
| 5 | 壳层 `plugin_event` 出口 + `stream.js` / `host.js` + 单测 | 帧可送达浏览器，保留键被拒 |
| 6 | `ui/player.js` / `ui/player.css` / `ui/tool-view.js` | 播放、暂停、停止、多标签页独立、工具卡可用 |
| 7 | 删除旧 tts、更新清单/catalog/测试/文档 | `check_catalog` 零漂移，旧引用清零 |
| 8 | 本机手动回归 + 目标门禁 | 播放、开关、错误路径、双标签页各自播放均通过 |

## 风险与限制

| 项 | 影响 | 处置 |
|---|---|---|
| 浏览器自动播放策略 | 首次播放可能被拒 | 「点击播放」按钮保留队列 |
| edge-tts 依赖网络 | 离线或服务不可用时无音频 | 工具失败给安装/网络提示；`/status` 记最后错误 |
| base64 体积 | 大段音频占用内存与带宽 | 配置的单段上限、4 MB 音频上限、队列上限 |
| SSE 帧丢失 | 慢消费者丢最旧帧 | 播放器按 `(call_id,index)` 检测缺口并提示；不补发 |
| 多标签页 | 同一段会被多个页面收到并各自播放 | 这是允许行为；各页独立控制，不跨页同步 |
| 多会话 | 单页队列会交错 | 按到达顺序播放；每项带会话 id，可按范围停止 |
| 配置值较小 | 分句可能超过配置上限 | 校验失败并指出有效上限；不硬切词 |
| 符号白名单 | 代码、URL、公式、`@`/`#`/`&` 等符号不能直接说 | 模型改用文字表达；`%` 由插件转成中文百分比 |
| 音色名错误 | edge-tts 合成失败 | 单段错误事件；`/status` 记录 |
| 音频不落盘 | 刷新或重连后不能回放 | 工具事实仍在；音频属于实时旁路 |

## 实现口径

1. `max_segment_chars` 默认 128，取值是 ≥1 的整数，没有上限；设为 300 就按
   300 字贪心装段，设为 1000 就按 1000 字贪心装段。单个分句超过该值时失败，
   不在词中间硬切。
2. 中文标点：`，` `。` `？` `！` `；` `、` `：` `“` `”` `‘` `’` `（` `）`。
   英文标点：`.` `,` `?` `!` `;` `:` `'` `"` `(` `)`。四则符号：
   `+` `-` `*` `/` `×` `÷`（含全角 `＋` `－` `＊` `／`）。空格支持半角与全角。
   `-` 可作英文连接符、二元减号或负数前缀；`+` `*` `/` `×` `÷` 必须是二元
   符号。`%`/`％` 只在数字后并转成中文百分比。其它符号、emoji、换行、
   Markdown 一律拒绝。
3. 中英文边界标点都是分句边界；数字内部的 `.`、`,`、`:` 分别是小数点、
   千分位与时间分隔，四则符号与百分号也不是边界。段内可含多个分句，
   段末一定是边界标点。
4. 单次 `msg` 上限 512 字，超出拒绝；段数不另设上限。
5. 每个浏览器标签页独立播放；多标签页可以同时播放，不做跨页同步。
