# AI说话（`ai_speak` 插件）

AI说话把模型正在做的步骤交给后端合成语音，再通过插件事件送到浏览器播放条。
工具负责接收、校验、入队，并在同步模式下等待播放完成；合成、播放与开关各自在独立模块里。

## 包结构

```
plugins/ai_speak/
  plugin.py                    入口：配置、运行时、工具/端点/启动脚本/订阅
  config.py                    [config] 读取与校验
  text.py                      字符规范、切段、合成前净化
  provider.py                  edge-tts 端口与适配
  runtime.py                   每会话串行合成、SSE 发布、停止与计数
  tool.py                      ai_speak 工具
  plugin-meta.json            身份元数据
  plugin-config.ini           真实配置（入库）
  ui/player.js                 输入框上方的播放条与队列
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

字符合法性只拦破坏结构的控制字符（Unicode `C` 类：换行、制表符、回车等），
其余一律放行。不在校验层拦“念不出来”的符号——模型天生会用各种引号、箭头、
emoji，逐个列举只会不断漏（书名号曾这样漏过去）；它们交给
[合成前净化](#合成前净化) 统一清除。

引号与括号必须成对，允许嵌套，禁止交叉；空对拒绝。可用的成对符号：
`“”` `‘’` `（）` `《》` `「」` `""` `()` `''`。
`-` 可以是英文连接符、二元减号或负数前缀；`+` `*` `/` `×` `÷` 必须是二元符号。
文本以边界标点结尾；`...`、`?!` 作为连续边界整体。

文件名的点不算分句：`.` 前是字母/数字/下划线、后接 1–5 个字母且其后不再接
名字字符时（`USER_RULES.md`、`a/b.py`），整段念出来而不切开。

边界标点：中文 `，。？！；、：`，英文 `. , ? ! ; :`。数字内部的 `.`、`,`、`:`
分别是小数点、千分位与时间分隔，不参与切分。引号/括号内部的标点不切分。

单次 `msg` 最多 512 字。`max_segment_chars` 控制单段上限，默认 128，取值是
≥1 的整数，没有上限；设为 300 就按 300 字贪心装段，设为 1000 就按 1000 字
装段。单个分句超过配置值时失败，不在词中间硬切。

## 合成前净化

净化用“保留可发音字符”而不是“逐个删掉已知符号”：后者每遇到一种新引号
就漏一次（书名号就是这样一路留到引擎的）。只保证一件事——留下的每一个
字符都有声音。

保留：字母与数字（含全角）、空格、分句边界、文件名符号 `_ . / \ -`、词内撇号。
其余符号（各类引号与括号，含 `「」` `《》`、箭头、emoji 等）全部移除。

另有三项发音改写：

- `数字%` / `数字％` 转成「百分之 + 中文数字」，例如 `10%` → `百分之十`；
- 数字之间的四则运算转成中文读法，例如 `5+3` → `五加三`、`10/2` →
  `十除以二`、`-5` → `负五`；日期与英文连接符里的 `-` 原样保留；
- 数字中的千分位逗号删除，小数点保留；

最后把连续空格压成一个。

## 配置

```ini
[config]
engine = edge
voice = zh-CN-XiaoxiaoNeural
user_salutation = 陛下
assistant_salutation = 臣妾
tone = 温婉
max_segment_chars = 128
play_interval_ms = 0
sync_playback = 0
speed = 1.0
```

身份在 `plugin-meta.json`，开关在 `plugins.ini`。

| 键 | 默认 | 范围 | 说明 |
|---|---|---|---|
| `engine` | `edge` | 仅 `edge` | 合成引擎；其它值装载期报错 |
| `voice` | `zh-CN-XiaoxiaoNeural` | 非空 | edge-tts 音色名 |
| `user_salutation` | `陛下` | 非空 | 模型对用户的称呼 |
| `assistant_salutation` | `臣妾` | 非空 | 模型对自己的称呼 |
| `tone` | `温婉` | 非空 | 模型说话的语气约束 |
| `max_segment_chars` | 128 | ≥1 的整数，无上限 | 单段字符上限 |
| `play_interval_ms` | 0 | ≥0 | 段间播放间隔（毫秒） |
| `sync_playback` | 0 | `0` / `1` | 1 = 工具等前端播完再返回 |
| `speed` | `1.0` | `0.5`–`2.0` | 合成语速倍率；`1.0` 为原速 |

配置文件是插件目录下的 `plugin-config.ini`；解析器读取同一组键。
`edge-tts>=7.3.1` 属于可选依赖，安装命令是 `pip install -e ".[tts]"`。它延迟导入，
缺库时插件可装载，工具执行时返回安装提示。

## 系统指令注入

插件启用后通过 `add_mode_tail` 把指令追加在执行模式与 Todo-List 之后，不进入系统提示词前缀。指令要求模型主动调用 `ai_speak` 与用户沟通；语音引擎不可用时不追加。

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
`gap_ms`。

播放器按 `conversation_id` 维护独立状态；同一会话只有一个播放器实例与 audio，
A/B 会话互不干扰。支持 Web Locks 的浏览器中，同一 cid 跨标签页只允许一个播放者，
其余标签页保持暂停；不同 cid 可以各自播放。系统媒体暂停/恢复触发的 `pause` / `play` 事件会同步
按钮状态与字幕动画。

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
合成失败单独标记为 `synthesis_failed`，工具返回 `SpeechSynthesisFailed` 并带引擎原因；
播放报错、被用户停止、无 SSE 连接或等待超时，工具返回 `SpeechPlaybackFailed`，
不把未播完当成已播完。停止按钮在同步模式下同时请求 `/api/chat/stop`，让工具等待和回合取消
一起收口；等待期间会检查回合的取消标记，避免工具线程卡死。

安全超时按文本长度计算：`max(30s, min(600s, 15s + 字符数 × 0.35))`。
自动播放被拦截时播放器不 ack，等用户点击播放；用户一直不点则超时失败。
支持 Web Locks 时，同一 cid 的多个标签页只选择一个播放者，其余页面不参与 ack；
不同 cid 各自独立上报。

## 边界

- 合成只走 edge-tts，不访问插件自定义网络端点。
- 音频只在内存中，不写文件；刷新或重连后不补发。
- 单段音频上限 4 MB；每会话待合成段上限 1024；前端待播项上限 512。
- 插件开关关闭即卸载工具、端点与启动脚本，并停止当前合成。
- 失败路径：引擎缺失、单段合成失败、无 SSE 连接、队列满、文本非法各自给出
  可执行信息；合成失败按段隔离，不拖垮整次调用。
