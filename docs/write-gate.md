# 写盘门控：设计意图与当前链路

本文记录写盘门控的真实行为与设计意图。权威实现在 `agent/mechanisms/quality/`（入口 `QualityGate` / `build_pipeline_gate`），提交结论工具见 `agent/capabilities/builtin/review_conclusion.py`。

相关代码：

| 位置 | 作用 |
|---|---|
| `QualityGate.check_write` | 提交前按固定顺序决定放行或拒绝 |
| `QualityGate.confirm` | 给一份预览盖章，章上是当时的真写次数 |
| `QualityGate.review_done` | 清空写后提醒账，并关闭补丁通道 |
| `QualityGate.note_committed` | 一次提交成功后的记账 |
| `review_conclusion` | 先 `confirm` 这份预览，再无条件 `review_done` |
| `build_pipeline_gate` | `commit_write` 成功后只把结果里的主路径交给 `note_committed` |

## 设计意图

写盘做成预览 → `review_conclusion` → `commit_write`，**不是**合规或审计要求。模型写一次就对、或写一百次才对，都没有外部规章约束。门控要达成的是：让模型**尽可能少用工具、一次写对**——先看见将要写入的内容，再过一道审阅仪式，再落盘。

其中 `pending_review` / `reviewed_ok` 是**会话级软提醒**，不是「必须按路径正确复读刚落盘的那个文件」：

- 真写成功后亮灯：提醒模型「文件变了，留意行号、上下文，别凭旧印象继续改」。
- 任意一次 `review_conclusion`（无论审的是哪份预览、conclusion 里写了什么）都会 `review_done` 熄灯。
- 提醒给到即可。多数模型会因此更谨慎；个别模型审了别的文件来过关，也无需按「复核对象必须正确」去纠结——那不是这盏灯的目标。
- 因此**全局共用一个状态来记「写后要留意」是有意为之**，不要按「复核必须绑 `confirm_id` / 绑路径」去改掉它。

强约束与软提醒要分开看：

| 层级 | 例子 | 性质 |
|---|---|---|
| 强约束 | 未 `confirm` 不能交；`confirm_id` 一次有效；同路径写后未 `read` 不能再交；诊断红灯限制可修路径 | 挡错写、挡瞎改 |
| 软提醒 | `pending_review` / `reviewed_ok` / 任意审阅即全局熄灯 | 降低摩擦、促模型留意变化 |

## 当前状态

这些字段是会话级的，不是按文件各记一份：

| 字段 | 含义 |
|---|---|
| `_pending[confirm_id]` | 一份预览快照。`confirmed` 表示已审，`confirmed_generation` 是审阅当时的真写次数。登记时同路径只留最新；条数上限 `MAX_PENDING_PREVIEWS`（100），满则按登记顺序挤掉最旧的 |
| `_write_generation` | 成功提交的次数，从 0 起 |
| `pending_review` | 写后软提醒用的路径列表（记的是最近真写涉及的主路径；熄灯时整表清空） |
| `reviewed_ok` | 为假时，跨文件提交会要求先走过一次 `review_conclusion`（除非预览是「写之前已解锁」） |
| `needs_reread` | 刚写过、再次改之前必须 `read` 的路径（强约束） |
| `apply_patch_pending` | 是否有一次 `apply_patch` 已经落盘且尚未被 `review_done` 清掉 |
| `pending_diagnose_red` / `fixable_paths` | 写后诊断失败时，只允许改列出的路径 |

`review_conclusion` 的顺序固定：

1. `cancel_preview` 为真时只丢弃这份预览，不解锁。
2. 带 `confirm_id` 时 `confirm`：快照标为已审，`confirmed_generation = 当前真写次数`。
3. 无论这次审的是哪一个文件，都调用 `review_done`：`pending_review` 清空，`reviewed_ok = True`，`apply_patch_pending = False`。大删除红灯一并解除。诊断红灯（语法、JSON 失败）不因这次调用解除。这是软提醒的熄灯动作，不是「只授权刚审的那一份」。

`commit_write` 成功后的 `note_committed`：

1. `_write_generation` 先加一。
2. 内容类工具（`write_file`、`replace_in_file`、`apply_patch`、`read_write`、`file_undo`）把主路径放进 `needs_reread`。删除、移动、复制不要求重读。
3. 主路径追加进 `pending_review`，`reviewed_ok` 设为假（亮起写后提醒）。
4. 工具名是 `apply_patch` 时，`apply_patch_pending` 设为真。

记账用的主路径来自提交结果的 `path`。`apply_patch` 的 `path` 是补丁里第一个目标文件，同一次补丁的其余文件不进入 `pending_review`，也不进入 `needs_reread`。

## 提交前的判定顺序

`check_write` 命中即返回，后面的规则不再看：

1. `confirm_id` 不存在或已消费：拒绝。
2. 该预览未 `confirm`：拒绝，文案要求先 `review_conclusion`。
3. 快照里解析不出路径：拒绝。
4. 意图是排查或调试且还没有只读证据：拒绝。
5. 诊断红灯亮着，且目标路径不在 `fixable_paths`（空则退回 `pending_review`）：拒绝。
6. `pending_review` 非空且 `reviewed_ok` 为假，目标路径不在这份列表里，并且预览不是「写之前已解锁」：拒绝，文案为「上一次真写的 review 尚未完成」。
7. 工具是 `apply_patch` 且 `apply_patch_pending` 为真，并且预览不是「写之前已解锁」：拒绝，文案为「apply_patch 上一次真写尚未 review」。
8. 目标路径在 `needs_reread`：拒绝，要求先 `read`。
9. `replace_in_file` 单次替换过大：拒绝。
10. 其余放行。

「写之前已解锁」的判定：`confirmed_generation` 是整数，且严格小于当前 `_write_generation`。审阅发生在最近一次成功提交之前，这个条件为真。审阅发生在那次提交之后，章上的次数等于当前次数，条件为假。

路径是否算「同一个文件」用 `_in_paths`：规范化后全等，或者一方是另一方加上 `/` 前缀的后缀。`bar.txt` 与 `foo/bar.txt` 会被当成同一个路径。

## 四条单文件链路

下面的 A、B 是两个互不相干的路径，工具是 `write_file` 这一类一次只写一个文件的入口。2026-10-17 用工具入口实测，四条都落盘成功。

| 顺序 | 当前结果 | 放行原因 |
|---|---|---|
| 预览 A → 审 A → 预览 B → 审 B → 交 A → 交 B | 通过 | 两份章都盖在任何真写之前。交 A 把 `reviewed_ok` 打回假，交 B 时章仍早于这次真写 |
| 预览 A → 审 A → 预览 B → 交 A → 审 B → 交 B | 通过 | 交 A 之后审 B。B 自己的章并不早于这次真写；审 B 时 `review_done` 熄掉写后提醒，交 B 放行 |
| 预览 A → 预览 B → 审 A → 审 B → 交 A → 交 B | 通过 | 与第一条相同，两份都在真写前盖章 |
| 预览 A → 预览 B → 审 A → 交 A → 审 B → 交 B | 通过 | 与第二条相同，靠审阅仪式熄灯 |

未审阅就提交仍然拒绝。同一路径刚写过、尚未 `read` 就再交一次，被第 8 步拦住，与上面四条不是同一条规则。

交 A 之后再审 C（任意一份），同样会熄灯：这是软提醒的预期行为，不是「C 错误地替 A 做了路径级复核」。

## 批量修改的当前行为

一次 `apply_patch` 是一个 `confirm_id`、一次审阅、一次提交。门控在提交前只检查这一次，补丁内部的多个文件不再逐个过 `check_write`。

提交成功后：

- `pending_review` 与 `needs_reread` 只增加第一个目标文件。
- `apply_patch_pending` 变成真。这个开关不记录补丁改了哪些文件，之后每一次新的 `apply_patch` 都看它，直到某次 `review_done`（与写后软提醒同一套熄灯）。
- 写后质量报告也只针对主路径。

因此同一次补丁里的第二个文件，马上用另一次预览去改，不会被「先 read」拦住。另一份在这次真写之前已经审过的补丁，代际条件为真，第 6 步和第 7 步都跳过。另一份在这次真写之后才审的补丁，通常先死在第 6 步的提醒文案上；只有路径被 `_in_paths` 算成同一个文件时，才会落到第 7 步的补丁专用文案。

`file_ops` 的记账路径按 `dest`、`source` 的顺序取第一个非空值。移动同时涉及的另一端不记账。这类操作不进入 `needs_reread`，但仍会把 `reviewed_ok` 打回假。

## 行为后果（按设计，不是缺陷）

### 审任意一份都会熄掉写后提醒

`review_conclusion` 在给某份预览盖章之后，固定调用全局 `review_done`。链路 2、4 里交 B 能过，靠的就是这次熄灯。交 A 之后审 C，C 也可以提交——因为提醒已被勾掉，不是因为系统认定「C 复核了 A」。

不要把「审的不是刚写的那个文件」写成漏洞；软提醒只要求走过审阅仪式。

### 章可以跨过后来的提醒灯

`confirmed_generation < _write_generation` 只比较次数。预览在真写之前已盖章的，提交时可以跳过第 6 / 7 步的提醒检查。这与「同一批已审预览连续交」一致，也会让「很早盖章、中间写过别的、一直没交」的预览在提醒灯亮着时仍能交——仍属当前代际规则的行为，不是路径级审计缺口。

## 仍可斟酌的点

下面几条与「全局软提醒」无关，若改，也不要动提醒的会话级设计。

### 一次补丁只记第一个文件

同一次 `apply_patch` 落盘的其余文件：

- 不在 `needs_reread` 里，随后修改不会要求先读当前内容（`needs_reread` 是强约束，这里记账偏窄可能影响「改已落盘文件前先 read」）。
- 不在 `pending_review` 里（对软提醒影响很小：提醒本就不绑「必须审对路径」）。
- 写后语法、JSON、大删除检查也不跑这些路径。

若优化：结果 `files` 里每个路径都进入 `needs_reread` 与写后检查；补丁通道是否仍用全局布尔，可单独定，但不要借机取消「任意 `review_conclusion` 熄灯」。

### 两条规则叠在一起，后一条很少开口

第 6 步的写后提醒和第 7 步的补丁通道用的是同一套「是不是写之前已解锁」。另一份文件在写之后才解锁时，第 6 步先拒绝，第 7 步的文案到不了。读拒绝原因时，会以为只有跨文件提醒，看不到补丁通道也亮着。若改，优先改文案或合并提示，不必改状态模型。

### 路径按后缀算同一个文件

`_in_paths` 把 `bar.txt` 和 `foo/bar.txt` 视为命中。跨文件规则、重读、红灯范围可能把不同文件混在一起。斜杠不同的同一路径，用规范化后的全路径相等即可；是否去掉后缀匹配可单独评估。

## 优化时不要做什么

- **不要**把 `pending_review` / `reviewed_ok` 改成「必须按路径 / 按 `confirm_id` 精确复核才熄灯」。
- **不要**让 `review_conclusion` 在解锁一份预览后不再调用 `review_done`，除非同时另有机制完成「写后提醒熄灯」且仍保持低摩擦。
- **不要**把三步曲理解成合规审计；改动应服务「少用工具、写对」与「提醒模型留意文件变化」。

若动强约束（`needs_reread`、诊断红灯、未审不能交、补丁多文件记账），与软提醒分层评估，互不绑定。
