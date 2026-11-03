[English](session-storage-refactor.md) | **中文**

**状态：** 设计，未实现。

# 会话存储重构

## 1. 目标

会话事实落盘改为增量分段存储，读取改为有界窗口：

1. 只追加，不重写历史。
2. 字符窗口默认 10,000；窗口边界触碰的整轮必须完整返回。
3. 支持按轮区间读取，例如 `[1, 10]`。
4. 拒绝任何全量读取。
5. 支持大量会话并发，常驻内存不随会话历史总量增长。
6. 全部以本地文件承载。
7. 不兼容旧数据，不为旧格式保留旁路。

## 2. 红线

| 规则 | 级别 |
|---|---|
| 在线读取不得加载完整会话 | MUST |
| `chars=0`、`before=0` 不得解释成全量 | MUST |
| 不提供 `read_all` / `load_all` / `read_from_start` | MUST |
| 窗口不得切断 `assistant(tool_calls)` 与对应 `tool` 结果 | MUST |
| 单次读取内存只与窗口、当前轮相关 | MUST |
| 旧 `.raw` 不读取、不迁移、不删除 | MUST |
| 读取路径不使用全局锁 | MUST |
| 写入按会话单写者 | MUST |
| 崩溃恢复不重写已提交记录 | MUST |
| 核心模块不得导入存储实现 | MUST |
| 插件不得直接打开会话文件 | MUST |

参数语义：

```text
chars = 10000       # 默认；<= 0 非法
from_round = 1      # 1-based
to_round = 10       # 1-based，必须 >= from_round
before_round = None # 最新页；不得使用 0 表示最新
```

错误码：

```text
WINDOW_INVALID
WINDOW_TOO_LARGE
ROUND_WINDOW_TOO_LARGE
ROUND_NOT_FOUND
INDEX_MISSING
INDEX_CORRUPT
CORRUPT_RECORD
SESSION_NOT_FOUND
```

## 3. DSH 对标

DSH 的持久化基线：

```text
JSONL
不可变 generation
append + fsync
header / 格式版本
projection cache
turn outline
```

DSH 的完整读取限制：

```text
readSession 完整回放日志
readSurface / filterEvents 读取完整逻辑日志
冷读 observation 首次读取物化完整 events
```

本设计保留其追加与格式隔离思想，拒绝其全量读取路径：

| 能力 | DSH | 本设计 |
|---|---|---|
| 完整历史 | `readSession` 全量回放 | 禁止 |
| 事件窗口 | 前后最多 50 条原始事件 | 10K 字符 + 整轮边界 |
| 轮次读取 | `turnOutline` 全量折叠投影 | `rounds.idx` 直接定位 |
| 冷读 | 物化完整 events | 只物化窗口 |
| 会话内存 | 可保留完整日志 | 只保留窗口与当前轮 |
| 大输出 | 随事件写入 JSONL | blob + 有界预览 |
| 并发读取 | 完整 observation | 分段索引 + 无锁读取 |

## 4. 分层与资产归属

### 4.1 分层

```text
agent/core/history_port.py
  HistoryPort 协议：只定义有界读取，不碰文件

agent/mechanisms/session_history/
  format.py    文件格式、编码、校验
  index.py     段索引、轮索引
  writer.py    append、序列、恢复
  reader.py    快照、窗口、轮读取
  cache.py     窗口缓存、轮缓存、字节预算
  service.py   宿主服务实现

agent/shell/classic_adapter/
  history_page.py  UI 分页模型，不直接打开文件
```

依赖方向保持：

```text
entry -> shell -> capabilities -> mechanisms -> core
```

`core` 不导入 `mechanisms.session_history`。核心模块只依赖 `HistoryPort`。

### 4.2 插件 2.0 边界

```text
存储属于 mechanisms，不属于插件。
SessionHistoryService 作为宿主服务注册。
插件不直接读 data/session。
classic UI 通过 HTTP / SSE 消费窗口。
插件需要历史时通过宿主服务协议，不持有文件句柄。
```

启动装配：

```text
app/host/services/session_history
  factory: boot/host_factories.py
  dependencies: data_root, config
  lifecycle: startup open allocator; shutdown close handles
```

不在 `app.py` 增加具体模块分支。

### 4.3 数据归属

```text
新数据根：<data_root>/session/v2/
旧数据根：<data_root>/session/raw/
```

旧文件保留，不删除、不移动、不覆盖；新服务不扫描、不列出、不识别旧文件。

## 5. 文件布局

```text
<data_root>/session/v2/
  _stream/
    head.json                 # 全局 stream seq 高水位
  <session_id>/
    header.json               # 身份、格式、加密、创建时间
    manifest.json             # generation、segment 列表、提交水位
    seg-000001.log            # append-only JSONL
    seg-000001.idx            # 固定宽度索引
    seg-000001.rounds.idx     # 本段轮索引
    blobs/
      <sha256>.bin            # 大结果，内容寻址
    projections/
      rounds.json             # 最终轮摘要，可重建
```

### 5.1 事件行

```json
{"seq":123456,"round":7,"type":"tool_done","ts":1760000000123,"chars":842,"data":{}}
```

| 字段 | 含义 |
|---|---|
| `seq` | 全局单调序号；允许空洞 |
| `round` | 1-based 轮次 |
| `type` | 事件类型 |
| `ts` | 写入时间 |
| `chars` | 规范文本字符数 |
| `data` | 事件载荷 |

只写落盘需要的内容；不重复写 `conversation_id`，目录即会话身份。

### 5.2 段索引

固定宽度二进制：

```text
seq         uint64
round       uint32
offset      uint64
length      uint32
chars       uint32
event_type  uint16
flags       uint16
crc32       uint32
```

索引不保存正文，只保存读取定位和窗口统计。

### 5.3 轮索引

```text
round_no
first_seq
last_seq
first_offset
last_offset
chars
message_count
status
```

轮索引只保存摘要，正文仍在 segment。

## 6. 写入协议

### 6.1 单写者

```text
同会话同一时刻一个写者
进程内锁 + 跨进程 .lock
读取端不加锁
```

### 6.2 批次提交

```text
1. 从全局 allocator 预留 seq block
2. 整批写入 active segment
3. fsync（配置开启时）
4. 追加 .idx
5. fsync 索引
6. 原子更新 manifest 提交水位
```

提交顺序固定：

```text
log -> idx -> manifest
```

失败处理：

```text
本批不可见
已提交前缀不回滚
批次进入有界重试队列
```

### 6.3 崩溃恢复

```text
manifest 后残缺尾行：截断，不进入索引
log 已写、idx 未写：从 index_end 到 committed_end 有界重扫
idx 已写、manifest 未提交：忽略超出提交水位的索引
manifest 已提交：正常读取
```

恢复只允许扫描当前 active segment，最大一个 segment，不扫描全部历史。

### 6.4 全局序号

禁止启动时扫描全部日志求最大序号。

```text
_stream/head.json
  next_block
  block_size = 1024
```

- 写者一次预留 1024 个序号。
- 用文件锁 + 原子 replace 更新高水位。
- 崩溃只浪费预留块，不回退序号。
- 读取端只读 `head.json`，不扫描日志。

## 7. 读取协议

```text
HistoryPort:
  head(session_id)
  stats(session_id)
  read_latest(session_id, chars=10000)
  read_before(session_id, before_round, chars=10000)
  read_rounds(session_id, from_round, to_round)
  read_round(session_id, round_no)
  read_record(session_id, seq)
  read_blob(session_id, blob_id, offset, length)
```

没有：

```text
read_all
load_all
load
load_with_seq
read_from_start
```

### 7.1 快照

每次读取绑定：

```text
snapshot = (generation, committed_seq, committed_end)
```

- 只读 `committed_seq` 之前的数据。
- 读取过程中发生 append，不影响本次结果。
- 返回 `snapshot_seq`。
- 不返回半条记录。

### 7.2 页面结构

```json
{
  "items": [],
  "rounds": [8, 9, 10],
  "chars": 11240,
  "has_more": true,
  "next_before_round": 8,
  "snapshot_seq": 123456,
  "oversized_round": false
}
```

页面只包含完整轮；`next_before_round` 用于向上翻页，边界轮不重复返回。

## 8. 字符窗口

### 8.1 字符口径

使用 Unicode 码点计数：

```text
用户正文                 计入
assistant 正文           计入
工具结果文本             计入
工具参数 JSON            计入
工具名 / 状态 / UI 字段   不计入
图片 base64              不计入
图片占位文本             计入
```

写入时计算一次 `chars` 并存入索引，读取时不再重新计算。

### 8.2 轮是窗口原子单位

一个用户轮：

```text
input_claimed 到下一个 input_claimed 之前
```

窗口按整轮累加：

```text
从最新轮向前
累加每轮 chars
达到或超过 10000
把触碰边界的整轮包含进来
```

单轮超过 10K：

```text
整轮返回
oversized_round=true
不截断
不继续向历史扩展
```

整轮原子保证：

```text
assistant(tool_calls) 不被切走
tool result 不被切走
轮内多个工具调用完整
```

### 8.3 向上翻页

```text
read_before(before_round=10, chars=10000)
```

- 返回第 8-10 轮时，`next_before_round=8`。
- 下一页从第 7 轮向前，不重复第 8 轮。
- `has_more=false` 仅表示已到第 1 轮。

### 8.4 非法参数

```text
chars <= 0
before_round = 0
from_round < 1
to_round < from_round
```

全部返回 `WINDOW_INVALID`。

`0` 永远不是全量，也不是“最新”的快捷方式。

## 9. 轮区间读取

```text
read_rounds(from_round=1, to_round=10)
```

使用轮索引直接定位：

```text
rounds.idx -> first_offset / last_offset
pread 目标事件
只折叠目标轮
```

硬上限：

```text
max_rounds = 64
max_bytes = 2 MiB
max_records = 4096
```

超限返回 `ROUND_WINDOW_TOO_LARGE`，不降级为全量。

### 9.1 轮内缓存

```text
RoundWindowCache
  key = session_id + snapshot_revision + round_no
  value = 已折叠消息 + last_seq + chars
```

规则：

- 轮开始加载一次。
- 轮内多次工具调用直接命中。
- 工具结果追加时增量更新当前轮。
- 轮结束冻结，后续淘汰。
- 单会话上限 2 MiB，全局上限 64 MiB。

## 10. 并发与服务化

### 10.1 无全局读锁

```text
封存 segment 不可变
读取使用独立句柄
读取不加会话写锁
manifest 快照更新不影响已开始的读
```

### 10.2 句柄预算

```text
全局句柄上限 64
LRU 淘汰空闲句柄
单请求句柄不超过当前 segment 数
请求结束立即释放
```

### 10.3 内存预算

```text
单次读取 <= 2 MiB
单会话轮缓存 <= 2 MiB
全局窗口 / 轮缓存 <= 64 MiB
索引 mmap 或按需读取
```

### 10.4 服务模型

```text
SessionHistoryService
  每个请求独立快照
  每会话独立写锁
  无全局 events 表
  无全库扫描
  读并发由 shell 线程池控制
  写批次有界队列
```

1000 个空闲会话只保留 header/manifest，不保留完整事件数组。

### 10.5 平台读取

```text
POSIX: os.pread
Windows: 每请求独立文件句柄 + seek/read
封存 segment: mmap 只读，按提交长度映射
active segment: 只读 committed_end
```

不共享 seek 位置，不跨线程共享文件对象。

## 11. 大记录与 blob

```text
规范文本 <= max_inline_record_chars（建议 64 KiB）
  直接写入事件行

超过：
  正文写入 blobs/<sha256>.bin
  事件行保存 preview + blob_id + blob_length
  窗口 chars 只计 preview
```

读取：

```text
历史窗口只读 preview
read_blob 必须带 offset / length
禁止一次读取完整 blob
```

## 12. 失败处理

| 故障 | 行为 |
|---|---|
| 缺 manifest | `SESSION_NOT_FOUND` |
| 缺 rounds 索引 | `INDEX_MISSING`，不扫描全量 |
| 索引损坏 | `INDEX_CORRUPT`，只允许修复当前 segment |
| 尾部半行 | 截断未提交尾部 |
| log 已写、索引未写 | 当前 segment 有界重扫 |
| 磁盘满 | 批次不可见，进入重试 |
| 读时 manifest 陈旧 | 返回旧快照，不阻塞写 |
| 单条损坏 | `CORRUPT_RECORD` |
| 窗口超限 | 明确错误，不降级全量 |

## 13. 安全

```text
session_id 只允许 ^[A-Za-z0-9_-]{8,128}$
所有路径基于 data_root 解析，拒绝 ..
拒绝 symlink 逃逸
索引 / 事件 / blob 带 CRC 或 hash
沿用现有 local 行级加密
索引不保存明文密钥
日志错误不输出正文
插件不得直接打开 data/session/v2
```

## 14. 可观测性

```text
history_read_bytes
history_read_records
history_window_chars
history_round_cache_hit
history_window_cache_hit
history_snapshot_lag
history_active_handles
history_cache_bytes
full_read_rejected_total
```

`full_read_rejected_total` 每次非法全量请求必须增加。在线路径出现全量读取视为事故。

## 15. 测试与门禁

### 15.1 单元

```text
窗口边界整轮包含
单轮超过 10K
轮区间 [1,10]
before_round 语义
0 / 负数拒绝
索引缺失不兜底
坏尾行恢复
加密行读取
blob 范围读取
```

### 15.2 并发

```text
同会话单写多读
多会话并发 append
1000 会话打开 / 关闭
句柄 LRU 不泄漏
缓存超限淘汰
读快照不看到半条记录
```

### 15.3 红线

```text
代码中不存在 read_all / load_all
任何读调用不超过窗口预算
旧 .raw 存在时启动不读取
旧 session_id 返回 not found
```

### 15.4 性能预算

```text
10K 窗口：不随总事件数线性增长
轮读取：只读目标轮
append：不重写旧文件
单会话 100 万事件：常驻内存不随事件数增长
1000 空闲会话：内存仅 header / manifest
```

### 15.5 门禁

```text
ruff
check_imports
check_architecture_hygiene
check_complexity + gen_complexity_md
gen_unit_tests_md --check
check_readme
check_comment_style
受影响单测
```

## 16. 实施顺序

```text
1. HistoryPort / 错误码 / 窗口语义
2. v2 格式、索引、manifest
3. append + 全局 seq + 崩溃恢复
4. 字符窗口 + 轮区间 + 轮缓存
5. UI 历史分页接入
6. 模型当前轮与历史窗口接入
7. 删除旧全量读取路径
8. 并发、内存、崩溃注入压测
```

每一步先过对应门禁，不先接 UI 再接存储。

## 17. 明确不做

```text
不做 .raw 兼容
不做旧数据迁移
不做旧会话列表
不做索引缺失全量回退
不做启动全库扫描
不做全局事件列表缓存
不做 read_all 特殊分支
```

## 18. 未验证项

```text
Windows mmap 与句柄上限实测
加密模式随机读吞吐
1000 并发读的 p95
blob 与工具结果截断阈值的最终取值
超大单轮的产品降级方式
```

以上为设计边界，不代表已实现或已通过压测。
