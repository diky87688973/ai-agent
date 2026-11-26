---
name: tts-setup
description: 安装并自检本地语音合成模型（Breeze TTS 2 · cpp/GGUF），再完成插件对接验证：目录约定、权重转换量化、启动与健康检查、合成自检、常见失败处置。
---

# 安装本地语音合成模型

## 何时使用

`plugins/tts` 需要本地模型时使用：用户要求「装本地语音」「换合成本地引擎」「语音合成报未安装」，
或 `GET status` 显示 `primary_ready=false` 且 `engine=breeze`。

## 前置检查

```text
Windows x64 + Vulkan 可用显卡（NVIDIA / AMD 均可）
磁盘 ≥ 6 GB（权重 6.5 GB 可删，稳定占用 = 模型 2.4 GB + 程序 0.22 GB）
能访问 huggingface.co（直连不通时给下载命令加 HTTP 代理）
```

先确认三件事，缺一即停，不要带着未知环境往下做：

```text
显卡：nvidia-smi 或 dxdiag，确认驱动正常
端口：netstat -ano | findstr :8137，确认没被占用
目录：安装根路径必须由用户指定，不自行决定
```

## 安装目录约定

插件按固定形状查找，放错位置会被当成未安装：

```text
<安装根>/
  breeze-tts-2-q4k-cpp.gguf          量化后的模型
  breeze-tts-2-cpp/
    breeze-server.exe                推理服务
    libbreeze.dll                    同目录兄弟文件必须一起放
```

`<安装根>` 就是插件配置项 `model_dir`。

## 安装步骤

### 1 放置推理程序

取 `breeze-tts-2-v0.1.7-windows-x64-vulkan.zip`（约 0.22 GB），整包解压到
`<安装根>/breeze-tts-2-cpp/`，确认 `breeze-server.exe` 与 `libbreeze.dll` 同目录。

### 2 下载官方权重

```text
huggingface-cli download BreezeBlue/Breeze-TTS-2 --local-dir ./Breeze-TTS-2
```

约 6.5 GB，**必须包含 `audio_tokenizer/` 子目录**，转换器缺它会直接拒绝运行。
直连不通时先设 `$env:HTTPS_PROXY`，不要用禁用代理的方式重试。

### 3 转成 GGUF

```text
pip install -r scripts/requirements.txt
python scripts/convert_hf_to_gguf.py ./Breeze-TTS-2 -o breeze-tts-2-f16.gguf --dtype f16
```

`scripts/convert_hf_to_gguf.py` 与 codec 转换脚本都要齐，缺一个都会在张量重建阶段报错。
产物约 5.9 GB，只作为量化的中间件。

### 4 量化

```text
breeze-quantize breeze-tts-2-f16.gguf breeze-tts-2-q4k-cpp.gguf q4_k
```

接受 `f16 / q8_0 / q6_k / q4_k / q3_k / q2_k`；`q4_k` 是默认档。
正常输出以 `1161/1161 ... done` 结尾，未出现即为失败。
把产物放到 `<安装根>/breeze-tts-2-q4k-cpp.gguf`，中间件可删。

### 5 填配置

`plugins/tts/plugin-config.ini`：

```ini
engine = breeze
model_dir = <安装根绝对路径>
default_model = breeze-tts-2-q4k
voice_id = <参考音色名>
```

配置改动需重载插件生效。

## 固定音色（不锁就会每句换人）

模型本身没有固定说话人：不给参考音色时，音色由指令与当前文本重新采样决定，
同一句话重播一致（seed 固定），但换一句就换一个声音。要锁住同一个声音，
必须先注册一段参考音色，之后所有合成带上 `voice_id`。

第一次给一个没听过的声音，最省事的做法是拿它自己的一段话当参考：

```text
1 启动服务，注意带上音色目录
   breeze-server <模型.gguf> --port 8137 --voices-dir <安装根>\voices

2 用想要的描述合成一句样板，存成 WAV
   curl -X POST http://127.0.0.1:8137/v1/audio/speech ^
     --form-string "text=大家好，我是您的语音助手，很高兴为您服务。" ^
     --form-string "instruction=一位温柔清晰的年轻女性，平静" ^
     --form-string "cfg_scale=2" --form-string "seed=42" ^
     -o sample.pcm
   （返回裸 PCM，24 kHz 单声道 s16le，加 44 字节 WAV 头即可）

3 注册成命名音色，ref_text 必须与样板文字完全一致
   curl -X POST http://127.0.0.1:8137/v1/voices ^
     -F "ref_audio=@sample.wav" ^
     --form-string "ref_text=大家好，我是您的语音助手，很高兴为您服务。" ^
     --form-string "name=fanyin"

4 确认注册成功
   curl http://127.0.0.1:8137/v1/voices
   期望返回 [{"id":"fanyin","frames":51,"seconds":4.08,"saved":true,...}]
   同时 <安装根>\voices\fanyin.breeze 落盘

5 配置里写 voice_id = fanyin
```

判定标准：

```text
带不存在的 id 应报 404 unknown voice_id —— 说明该字段真的被校验
带已注册 id 应返回 200 并有音频 —— 说明说话人被锁住
```

`voice_id` 生效后，`voice_desc` 不再参与指令（音色已由参考决定），
指令里只保留情感与语速。

`--voices-dir` 指向的目录必须存在；不存在时服务不报错，会静默把音色文件
写到进程当前目录，落进项目根。插件启动前会自建该目录，手工起服务时要注意。

## 验证

### 健康检查

```text
breeze-server <模型.gguf> --port 8137 --parallel 1
curl http://127.0.0.1:8137/health
```

期望 `{"status":"ok","sample_rate":24000,"ws_port":8138}`。
启动阶段会先做一次热身生成，`--parallel 1` 约 3 秒后才开始监听。

### 合成自检

```text
curl -X POST http://127.0.0.1:8137/v1/audio/speech ^
  -d "text=这是一条自检语音。" -d "instruction=一位温柔的女声，平静" ^
  -d "cfg_scale=2" -d "seed=42" --output probe.pcm
```

返回 headerless s16le / 24 kHz / 单声道 PCM。判定标准：

```text
文件大小 = 24000 × 2 × 时长秒数，一条 5 秒语音约 240 KB
读出的样本 rms 明显非零（全零 = 合成失败，不是静音文本）
```

### 插件侧确认

```text
GET /plugins/tts/status  → primary_ready=true, engine=breeze
调用 ai_speek 一次      → 听到声音且不是 Edge 音色
```

## 常见失败

| 现象 | 原因 | 处置 |
|---|---|---|
| `missing tensor: te.blk.0.attn_norm.weight` | 用了第三方转换的 GGUF，张量命名不兼容 | 只用作者脚本自行转换 |
| 启动后立即退出（退出码非 0） | 缺 `libbreeze.dll` 或 Vulkan 不可用 | 整包解压；`--cpu` 试跑确认 |
| `409 busy` | 并发请求超过 `--parallel` 且带 guidance | 串行调用，或调大 `--parallel` |
| 显存不足 | 与其他模型同时驻留 | 调小 `idle_timeout` 让它更快回收，或开 `--te-cpu` |
| 首字节 300 ms 以上 | `cfg_scale` 偏高，guidance 会翻倍计算 | 降到 1 或 2 |
| 语音音色抖、断句碎 | 单段文本过长 | 上游切段调小，本地不再二次切 |

## 换模型或换量化档

```text
breeze-quantize breeze-tts-2-f16.gguf <新名字>.gguf q6_k
```

改 `default_model` 与文件名需同步改 `plugins/tts/models.py` 的登记项；
未登记的 id 会被 `KeyError` 拒绝，不会静默回退到别的模型。
