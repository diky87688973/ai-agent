# 语音合成（`tts` 插件）

## 1. 概览

`tts` 是多引擎的语音合成入口：把上游的诉求（音色、情感、语速）翻译成具体引擎
能接受的参数，并在本地模型不可用时回落到 Edge。上游插件只说「想要什么样的声音」，
不关心谁来合成。

## 2. 插口协议

### 暴露

| 插口路径 | 能力 | 关键属性 | 可替换/覆盖方式 |
|---|---|---|---|
| `app/plugins/tts/service` | 进程内服务 | owner=插件；装配期构造，退出时释放 | 同路径 `replace=true` 覆盖；卸载时恢复原插口 |
| `backend/http/routes/tts-config` | HTTP 端点 | owner=插件；路径由声明给出；卸载时撤销 | 同路径 `replace=true` 覆盖 |
| `backend/http/routes/tts-status` | HTTP 端点 | owner=插件；路径由声明给出；卸载时撤销 | 同路径 `replace=true` 覆盖 |

### 依赖

| 依赖路径 | 能力 | 提供者 | 为什么依赖 |
|---|---|---|---|
| 无 | — | — | 本插件是最底层合成能力，只依赖 `agent.common.tts_contract` 与标准库 |

## 3. 插口能力

### 包结构

```
plugins/tts/
  plugin.py                    入口：装配服务、两个只读端点
  config.py                    [config] 读取与校验
  provider.py                  引擎注册点：按 engine 装配
  service.py                   对外门面：主引擎 + 兜底 + 状态快照
  edge_provider.py             Edge 引擎（网络合成）
  breeze_provider.py           本地 Breeze TTS 2 引擎（HTTP）
  supervisor.py                本地服务的进程生命周期
  pinyin.py                    Edge 专属的多音字辅助
  models.py                    可安装模型清单与目录约定
  plugin-meta.json             身份元数据
  plugin-config.ini            真实配置（入库）
  settings-schema.json         设置页字段
```

### 契约

契约放在 `agent/common/tts_contract.py`，上下游共用：

| 名称 | 说明 |
|---|---|
| `TTSRequest` | `text`、`voice`（音色诉求）、`instruction`、`speed`、`cfg_scale`、`timeout_s` |
| `TTSResult` | `audio`（内存字节）、`sample_rate`、`mime`、`engine` |
| `TTSCapabilities` | `supports_instruction`、`supports_speed`、`supports_cfg`、`needs_pinyin_hints` |
| `TTSUnavailable` | 引擎不可用；子类 `TTSEngineUnavailable`、`TTSNotInstalled` |
| `TTSSynthesisError` | 单段合成失败，调用方按段隔离 |

`voice` 是音色诉求而非引擎参数：上游写「温柔清晰的年轻女性」，由 provider 决定
是拼进指令还是忽略。

### 两个引擎

| 能力 | Edge | Breeze（本地） |
|---|---|---|
| `supports_instruction` | 否 | 是 |
| `supports_speed` | 是（转 rate 百分比） | 是（转自然语言描述） |
| `supports_cfg` | 否 | 是 |
| `needs_pinyin_hints` | 是 | 否 |
| 音色来源 | 配置项 `edge_voice` | 上游诉求拼进指令 |

语速统一用数值表达，映射各自实现：

```text
speed < 1   → 「语速慢，约正常速度的 0.8 倍」
speed = 1   → 「语速正常」
speed > 1   → 「语速快，约正常速度的 1.2 倍」
```

Edge 走 `rate` 百分比；本地引擎没有数值语速参数，只能靠描述，方向正确但不精确。

### 引擎选择与回落

```text
engine = breeze
  ├─ 装配成功 → primary=breeze，fallback=edge（fallback_to_edge=1 时）
  └─ 装配失败 → primary=edge，跳过兜底，原因写入状态
合成失败只分两类：
  TTSUnavailable    → 换兜底引擎
  TTSSynthesisError → 不换，按段失败上报
```

单段合成失败不换引擎，否则会把真实故障伪装成一次成功。

### 音色与说话人

模型本身没有固定说话人。不给 `voice_id` 时，音色由指令与当前文本重新采样决定：
同一句重播一致（seed 固定），但换一句就是另一个声音。

锁定声音的办法是先注册一段参考音色（见 Skills `tts-setup`），再在配置里写 `voice_id`。
生效后 `voice_desc` 不再参与指令，指令只保留情感与语速。

### 音色工作台

音色不靠手写描述凑：五个正交维度（年龄声线 / 音质质感 / 性格气质 / 语速节奏 /
情绪底色）拼成一句描述，试听满意后再存成命名音色。

维度与措辞的唯一来源是 `schema.py`，界面通过 `GET voice-options` 获取，
不在前端写死；改文案只改一处，同一组合必然拼出同一句描述。

| 接口 | 作用 |
|---|---|
| `GET voice-options` | 维度、预设、样板句 |
| `GET voice-list` | 已注册音色及其维度组合 |
| `POST voice-preview` | 按组合合成样板，不入库 |
| `POST voice-save` | 固化为命名音色，维度写进 metadata |
| `POST voice-delete` | 删内存与 `.breeze` 两处 |
| `POST voice-current` | 写进配置 `voice_id`，重载后生效 |

入口：输入区左下的「音色」按钮打开右侧面板。删除必须自己删 `.breeze`，
因为服务端 `DELETE` 只清内存，文件会在下次启动时把音色读回来。

### 本地服务的生命周期

```text
缺文件          → TTSNotInstalled，错误信息带安装引导
stopped         → 起子进程，轮询 /health 直到 startup_timeout
ready           → 直接 HTTP；期间并发请求不重复拉起
空闲超时         → 停服释放约 3.8 GiB 显存
进程异常退出     → 下次请求重新拉起
```

服务进程会被纳入作业对象（`KILL_ON_JOB_CLOSE`）：agent 正常退出或直接被强杀，
系统都会连带终止它，不会留下占着显存的孤儿进程。

服务只绑 `127.0.0.1`，回环请求显式绕过系统代理。

### 状态端点

`GET /api/plugin/tts/status`：

| 字段 | 说明 |
|---|---|
| `engine` | 实际主引擎（退化时是 `edge`） |
| `primary_ready` | 主引擎依赖是否齐备 |
| `fallback_engine` / `fallback_ready` | 兜底引擎与其可用性 |
| `last_fallback_reason` | 最近一次回落原因 |
| `capabilities` | 主引擎能力矩阵 |
| `warnings` | 配置回退记录 |

## 4. 其他细节

### 配置

```ini
[config]
engine = breeze
model_dir =
default_model = breeze-tts-2-q4k
server_port = 8137
startup_timeout = 20
idle_timeout = 600
cfg_scale = 2
voice_desc = 一位温柔清晰的年轻女性，声音柔和亲切
emotion = 平静
speed = 1.0
edge_voice = zh-CN-XiaoxiaoNeural
fallback_to_edge = 1
```

| 键 | 默认 | 范围 | 说明 |
|---|---|---|---|
| `engine` | `breeze` | `breeze` / `edge` | 非法值装载期报错 |
| `model_dir` | 空 | 目录 | 模型与推理程序的安装根 |
| `default_model` | `breeze-tts-2-q4k` | 已登记 id | 未登记的 id 直接拒绝 |
| `server_port` | 8137 | 1–65535 | 本地服务端口 |
| `startup_timeout` | 20 | ≥1 | 拉起服务的等待上限 |
| `idle_timeout` | 600 | ≥0；0 不回收 | 空闲停服秒数 |
| `cfg_scale` | 2 | 1–5 | 指令引导强度 |
| `voice_desc` | 一位温柔清晰的年轻女性，声音柔和亲切 | 非空 | 上游未给音色诉求时的默认描述 |
| `voice_id` | 空 | 已注册音色名 | 填了就锁定说话人；留空每句重新采样，音色会漂 |
| `emotion` | 平静 | 自由文本 | 情感档位 |
| `speed` | 1.0 | 0.5–2.0 | 语速倍率 |
| `edge_voice` | `zh-CN-XiaoxiaoNeural` | 非空 | 仅 Edge 使用 |
| `fallback_to_edge` | 1 | `0` / `1` | 本地不可用时是否回落 |

### 安装引导

本地引擎的安装、量化、自检与常见失败处置见 Skills：`tts-setup`。
清单只登记实测可用的一项模型；新增模型要同时改 `models.py` 的登记，否则会被拒绝。

### 边界

- 音频只在内存中流转，不落盘。
- 单段文本上限 800 字，超出即失败，由调用方切段。
- 首版不做流式：等服务返回完整音频后再抛给上游。
- 本地引擎理解为「可选增强」：装配失败不阻断插件装载，退化到 Edge 并留痕。

## 5. 延伸阅读

| 主题 | 文档 |
|---|---|
| AI角色扮演 | [ai-cosplay.zh.md](ai-cosplay.zh.md) |
| 插件 | [plugins.zh.md](plugins.zh.md) |
