# AI说话（`ai_speak` 插件）

AI说话把模型正在做的步骤交给后端合成语音，再通过插件事件送到浏览器播放条。
工具负责接收、校验、入队，并在同步模式下等待播放完成；合成、播放与开关各自在独立模块里。

## 包结构

```
plugins/ai_speak/
  plugin.py                    入口：配置、运行时、工具/端点/启动脚本/订阅
  config.py                    [ext] 读取与校验
  text.py                      字符规范、切段、合成前净化
  provider.py                  edge-tts 端口与适配
  runtime.py                   每会话串行合成、SSE 发布、停止与计数
  tool.py                      ai_speak 工具
  plugin-config.ini.example    [base] + [ext]
  ui/player.js                 悬浮播放条与队列
  ui/player.css                播放条样式
  ui/tool-view.js              对话区工具卡
```

## 工具

```python
name = "ai_speak"
label = "AI说话"
icon = "🔊"
parameters = {"msg": {"type": "string"}}
```

工具描述要求模型代入当前角色、使用人类口语，并把每一步直接说出来。异步模式返回
`{"accepted": true, "segments": N, "characters": N}`；同步模式在播放结束后返回
`{"accepted": true, "played": true, "segments": N, "characters": N, "waited_ms": N}`。
两种结果都由内核包成统一工具信封。
校验失败、引擎未安装、没有 Web 连接或队列满时抛错，内核收成 `ok=false`。

工具调用自动产生 `tool_started` / `tool_done` / `tool_ended` 事实。对话区工具卡
由 `ui/tool-view.js` 注册：标题「AI说话」，摘要显示 `msg`，展开为默认的请求/响应
报文。

## 文本规范

允许字符：

| 类别 | 允许 |
|---|---|
| 中文 | `U+3400–U+4DBF`、`U+4E00–U+9FFF` |
| 英文/数字 | `A–Z` `a–z` `0–9` |
| 空格 | 半角 `U+0020`、全角 `U+3000` |
| 中文标点 | `，` `。` `？` `！` `；` `、` `：` `“` `”` `‘` `’` `（` `）` |
| 英文标点 | `.` `,` `?` `!` `;` `:` `'` `"` `(` `)` |
| 四则符号 | `+` `-` `*` `/` `×` `÷` `＋` `－` `＊` `／` |
| 百分号 | `%` `％`，只在数字后 |

引号与括号必须成对，允许嵌套，禁止交叉；空对拒绝。`-` 可以是英文连接符、
二元减号或负数前缀；`+` `*` `/` `×` `÷` 必须是二元符号。文本以边界标点结尾；
`...`、`?!` 作为连续边界整体。

边界标点：中文 `，。？！；、：`，英文 `. , ? ! ; :`。数字内部的 `.`、`,`、`:`
分别是小数点、千分位与时间分隔，不参与切分。引号/括号内部的标点不切分。

单次 `msg` 最多 512 字。`max_segment_chars` 控制单段上限，默认 128，取值是
≥1 的整数，没有上限；设为 300 就按 300 字贪心装段，设为 1000 就按 1000 字
装段。单个分句超过配置值时失败，不在词中间硬切。

## 合成前净化

- 去掉中文/英文引号、括号，保留其中文本；
- `数字%` / `数字％` 转成「百分之 + 中文数字」，例如 `10%` → `百分之十`；
- 数字之间的四则运算转成中文读法，例如 `5+3` → `五加三`、`10/2` →
  `十除以二`、`-5` → `负五`；日期与英文连接符里的 `-` 原样保留；
- 数字中的千分位逗号删除，小数点保留；
- 连续空格压成一个。

## 配置

```ini
[base]
id = ai_speak
name = AI说话
desc = 把 AI 正在做的事用人类语气说出来。
enable = 1
icon = 🔊
version = 1.0

[ext]
engine = edge
voice = zh-CN-XiaoxiaoNeural
max_segment_chars = 128
play_interval_ms = 0
sync_playback = 0
```

| 键 | 默认 | 范围 | 说明 |
|---|---|---|---|
| `engine` | `edge` | 仅 `edge` | 合成引擎；其它值装载期报错 |
| `voice` | `zh-CN-XiaoxiaoNeural` | 非空 | edge-tts 音色名 |
| `max_segment_chars` | 128 | ≥1 的整数，无上限 | 单段字符上限 |
| `play_interval_ms` | 0 | ≥0 | 段间播放间隔（毫秒） |
| `sync_playback` | 0 | `0` / `1` | 1 = 工具等前端播完再返回 |

配置文件是插件目录下的 `plugin-config.ini`；模板与解析器键集合一致。
`edge-tts` 属于可选依赖，安装命令是 `pip install -e ".[tts]"`。它延迟导入，
缺库时插件可装载，工具执行时返回安装提示。

## 事件与播放

后端合成一段就经 `SERVICE_PLUGIN_EVENTS` 的发布器广播一条 `plugin_event`；
发布器由 `ClassicAdapter.announce_plugin_event()` 实现。前端 `stream.js` 把它转成
`ai-agent:plugin-event` DOM 事件：

| 事件 | 字段 |
|---|---|
| `segment` | `conversation_id`、`call_id`、`index`、`total`、`text`、`voice`、`mime`、`audio`、`bytes`、`gap_ms` |
| `error` | `conversation_id`、`call_id`、`index`、`code`、`message` |
| `stop` | `conversation_id`、`reason` |

`audio` 是标准 base64，音频不落盘。插件事件帧没有顶层 `seq`；`seq` 是 SSE 断线
续传游标，不能占用。播放器把段生成 Blob URL 入队，按到达顺序串行播放，段间等待
`gap_ms`。每个标签页各自持有一个播放器与队列，多标签页可以同时播放。

播放器提供暂停/继续、停止与「点击播放」；自动播放被浏览器拦截时保留队列。
`stop` 按会话或调用过滤队列；插件卸载时后端发布 stop，壳层派发
`ai-agent:plugins-changed` 作为第二道停止信号。

## 同步播放

`sync_playback = 1` 时，`ai_speak` 不是入队即返回：工具先登记本次 `call_id`，
再等前端确认最后一段音频播完才返回。模型因此不会在读屏或改文件之前抢跑。

播放器按 `call_id` 记录段数，最后一段 `ended` 后 `POST /api/plugin/ai_speak/played`：

| 字段 | 说明 |
|---|---|
| `conversation_id` | 会话 id；缺省时后端按 `call_id` 唯一匹配 |
| `call_id` | `ai_speak` 工具调用 id，必须与入队时一致 |
| `status` | `played` / `stopped` / `error` / `incomplete` |

`incomplete` 表示队列丢弃或段不齐；后端按 `dropped` 处理。
播放被用户停止、播放器报错、无 SSE 连接或等待超时，工具返回失败，不把未播完
当成已播完。停止按钮在同步模式下同时请求 `/api/chat/stop`，让工具等待和回合取消
一起收口；等待期间会检查回合的取消标记，避免工具线程卡死。

安全超时按文本长度计算：`max(30s, min(600s, 15s + 字符数 × 0.35))`。
自动播放被拦截时播放器不 ack，等用户点击播放；用户一直不点则超时失败。
多标签页各播一份，当前按**首个 ack** 放行；同步模式默认假设只有一个活动播放页。

## 边界

- 合成只走 edge-tts，不访问插件自定义网络端点。
- 音频只在内存中，不写文件；刷新或重连后不补发。
- 单段音频上限 4 MB；每会话待合成段上限 1024；前端待播项上限 512。
- 插件开关关闭即卸载工具、端点与启动脚本，并停止当前合成。
- 失败路径：引擎缺失、单段合成失败、无 SSE 连接、队列满、文本非法各自给出
  可执行信息；合成失败按段隔离，不拖垮整次调用。
