# 本地出图（image_gen）

用本地扩散模型出图。权重与运行环境都在 `model_dir` 指向的安装目录里，插件只负责确认、调度与结果回传，
不在主进程加载任何扩散依赖。

## 资产归属

| 归属 | 位置 |
| --- | --- |
| 工具声明与动作编排 | `plugins/image_gen/plugin.py`（`ToolPlugin`，对外只有 `image_gen` 一个工具） |
| 环境探测、配置合并、命令装配、任务索引 | `plugins/image_gen/engine.py` |
| 模型清单（体积 / 建议显存 / 镜像源 / 是否需授权） | `plugins/image_gen/models.py` |
| 出图子进程（加载 → 采样 → 存图 → 退出） | `plugins/image_gen/runner.py` |
| 下载子进程 | `plugins/image_gen/fetcher.py` |
| 配置模板（入库、默认空值） | `plugins/image_gen/plugin-config.ini` |
| 运行态（`task-index.json`） | `data/plugin/image_gen/`（宿主经 `ctx.data_dir` 注入） |
| 出图结果 | `<model_dir>/output/` |

配置只有一处来源 `plugin-config.ini`；运行态只存任务索引，不另存配置副本。

`plugin-config.ini` 入库为空模板，由安装引导或用户填写；运行态任务索引落在已忽略的 `data/`。
插件不自行拼数据路径，注入缺失时直接报错。

## 配置

配置写在 `plugin-config.ini`（入库，三项默认空值），由安装引导或用户主动填写：

| 键 | 含义 |
| --- | --- |
| `model_dir` | 安装目录。目录下存在 `models/` 时以它为权重根，否则目录本身即权重根；出图与下载都在这里 |
| `runtime_python` | 装有 torch / diffusers / transformers 的解释器，出图与下载都由它起子进程 |
| `default_model` | 默认模型 id。留空表示未配置，出图时必须显式传 `model`；由安装引导或用户主动填写 |

三项都只在安装引导时按本机情况填入，或由用户主动配置，插件不预置任何默认值。
用户确认的安装目录与该次选择的模型由 `download` 写回同一份 `plugin-config.ini`。

## 工具动作

| 动作 | 行为 |
| --- | --- |
| `generate`（默认） | 省略 `model` 时用配置里的 `default_model`，两者都没有则报错；先做模型闸门：`model_dir` 为空或没有就位模型时返回 `needs_setup` 并附清单与本机显卡建议；就位则起后台任务，立即返回 `task_id` |
| `check` | 只探测显卡与本地模型，不出图 |
| `download` | 必须 `confirmed=true` 才执行；需授权的仓库返回 `needs_auth` 并列出可匿名替代；缺目录返回 `need_model_dir` |
| `status` | 凭 `task_id` 读结果文件返回 `image_path`；不读取后台任务输出 |

后台任务一律复用宿主既有的任务服务（`SERVICE_BACKGROUND_TASKS`），插件不自建任务队列。

## 依赖

主进程：`requests`（见 `plugins/image_gen/requirements.txt`）。
`runtime_python` 侧：`torch`、`diffusers`、`transformers`、`safetensors`、`accelerate`、`gguf`、`Pillow`。

## 权重许可

插件不附带权重，由使用者按清单自行下载：

| 模型 | 许可 |
| --- | --- |
| FLUX.1-dev（含社区量化版） | BFL Non-Commercial License，不可商用 |
| FLUX.1-schnell | Apache-2.0 |
| SDXL base 1.0 | OpenRAIL++ |

## 失败行为

| 场景 | 表现 |
| --- | --- |
| `model_dir` 未配置 / 无就位模型 | `needs_setup`，附清单与推荐 |
| 显存低于清单建议值 | 子进程报错并落结果文件，`status` 返回 `failed` 与原因 |
| 下载源返回 401（需授权） | `needs_auth`，不静默换模型 |
| 配置或索引读失败 | 上报后按缺省继续，不把解析失败当成正常空值 |
| 结果文件写失败 | 子进程向 stderr 留痕，`status` 依据任务状态给出 `pending` 或失败 |
