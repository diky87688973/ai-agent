[English](write-gate.md) | **中文**

# 写盘门控：设计意图与当前链路

写盘门控的真实行为与设计意图如下。权威实现在 `agent/mechanisms/quality/`（入口 `QualityGate` / `build_pipeline_gate`），提交结论工具见 `agent/capabilities/builtin/review_conclusion.py`。

相关代码：

| 位置 | 作用 |
|---|---|
| `QualityGate.check_write` | 提交前按固定顺序决定放行或拒绝 |
| `QualityGate.confirm` | 给一份预览盖章，章上是当时的真写次数 |
| `QualityGate.review_done` | 清空写后提醒账，并关闭补丁通道 |
| `QualityGate.note_committed` | 一次提交成功后的记账 |
| `review_conclusion` | 非取消时先 `confirm` 这份预览（带 `confirm_id`），再调用 `review_done` |
| `build_pipeline_gate` | `commit_write` 成功后只把结果里的主路径（而非其余文件）交给 `note_committed` |

## 设计意图

写盘做成预览 → `review_conclusion` → `commit_write`，**不是**合规或审计要求。模型写一次就对、或写一百次才对，都没有外部规章约束。门控要达成的是：让模型**尽可能少用工具、一次写对**——先看见将要写入的内容，再过一道审阅步骤，再落盘。

其中 `pending_review` / `reviewed_ok` 是**会话级软提醒**，不是「必须按路径正确复读刚落盘的那个文件」：

- 真写成功后亮灯：提醒模型「文件变了，留意行号与上下文」。
- 任意一次成功的非取消 `review_conclusion`（无论审的是哪份预览、conclusion 里写了什么）都会 `review_done` 熄灯。
- 提醒给到即可。多数模型会因此更谨慎；个别模型审了别的文件来过关，也不影响这盏灯的作用——它不是按「复核对象必须正确」设计的。
- 因此**全局共用一个状态来记「写后要留意」是有意为之**，改为按 `confirm_id` 或路径绑定会改变软提醒的摩擦成本。

强约束与软提醒要分开看：

| 层级 | 例子 | 性质 |
|---|---|---|
| 强约束 | 未 `confirm` 不能交；`confirm_id` 一次有效；预览路径就是目标文件时，同路径写后未 `read` 不能再交；写后红灯限制可修路径 | 挡错写、挡瞎改 |
| 软提醒 | `pending_review` / `reviewed_ok` / 任意审阅即全局熄灯 | 降低摩擦、促模型留意变化 |

## 当前状态

这些字段是会话级的，不是按文件各记一份：

| 字段 | 含义 |
|---|---|
| `_pending[confirm_id]` | 一份预览快照。`confirmed` 表示已审，`confirmed_generation` 是审阅当时的真写次数。登记时同一快照路径只留最新；条数上限 `MAX_PENDING_PREVIEWS`（100），满则按登记顺序挤掉最旧的 |
| `_write_generation` | 成功提交的次数，从 0 起 |
| `pending_review` | 写后软提醒用的路径列表（记的是上次熄灯以来各次真写的主路径；熄灯时整表清空） |
| `reviewed_ok` | 为假时，跨文件提交会要求先走过一次 `review_conclusion`（预览在最近一次真写之前已解锁时除外） |
| `needs_reread` | 刚写过、再次改之前必须 `read` 的路径（强约束） |
| `apply_patch_pending` | 是否有一次 `apply_patch` 已经落盘且尚未被 `review_done` 清掉 |
| `pending_diagnose_red` / `fixable_paths` | 写后红灯亮着时，只允许改列出的路径（列表为空则退回 `pending_review`）。每次成功提交会把主路径加入 `fixable_paths`；红灯全部解除后由 `review_done` 清空该列表 |

`review_conclusion` 的顺序固定：

1. `cancel_preview` 为真且带 `confirm_id` 时，只丢弃这份预览并返回：不 `confirm`，也不调用 `review_done`。不带 `confirm_id` 时取消不生效，调用继续按审阅处理。
2. 带 `confirm_id` 时 `confirm`：快照标为已审，`confirmed_generation = 当前真写次数`。
3. 非取消的调用无论审的是哪一个文件，都调用 `review_done`：`pending_review` 清空，`reviewed_ok = True`，`apply_patch_pending = False`。大删除红灯一并解除。诊断红灯（语法、JSON 失败）不因这次调用解除。若已无红灯，`fixable_paths` 一并清空。这是软提醒的熄灯动作，不是「只授权刚审的那一份」。

`commit_write` 成功后的 `note_committed`：

1. `_write_generation` 先加一。
2. 内容类工具（`write_file`、`replace_in_file`、`apply_patch`、`read_write`、`file_undo`）把主路径放进 `needs_reread`。删除、移动、复制不要求重读。
3. 主路径追加进 `pending_review`，`reviewed_ok` 设为假（亮起写后提醒）。
4. 工具名是 `apply_patch` 时，`apply_patch_pending` 设为真。

主路径同时加入 `fixable_paths`。记账用的主路径来自提交结果的 `path`。`apply_patch` 的 `path` 是补丁里第一个目标文件，同一次补丁的其余文件不进入 `pending_review`、`needs_reread` 或 `fixable_paths`。

预览快照的 `path` 由工具声明的 `write_path_keys` 解析；`apply_patch` 声明的是 `path`，即补丁根目录。因此提交前检查按根目录比较，不按目标文件；提交结果的顶层 `path` 才是第一个目标文件。

## 提交前的判定顺序

`check_write` 命中即返回，后面的规则不再看。管道在 `check_write` 之前还有 Plan / Execute 模式门控；下面只是 `check_write` 的判定顺序。

1. `confirm_id` 不存在或已消费：拒绝。
2. 该预览未 `confirm`：拒绝，文案要求先 `review_conclusion`。
3. 快照里解析不出路径：拒绝。
4. 意图是排查或调试且还没有只读证据：拒绝。
5. 写后红灯亮着，且快照路径不在 `fixable_paths`（列表为空则退回 `pending_review`）：拒绝。
6. `pending_review` 非空且 `reviewed_ok` 为假，快照路径不在这份列表里，并且预览不是「写之前已解锁」：拒绝，文案为「上一次真写的 review 尚未完成」。
7. 工具是 `apply_patch` 且 `apply_patch_pending` 为真，并且预览不是「写之前已解锁」：拒绝，文案为「apply_patch 上一次真写尚未 review」。
8. 快照路径在 `needs_reread`：拒绝，要求先 `read`。
9. `replace_in_file` 单次替换超出体积规则（`MAX_DIFF_LINES`，80）：拒绝。
10. 其余放行。

「写之前已解锁」的判定：`confirmed_generation` 是整数，且严格小于当前 `_write_generation`。审阅发生在最近一次成功提交之前，这个条件为真。审阅发生在那次提交之后，章上的次数等于当前次数，条件为假。

路径是否算「同一个文件」用 `_in_paths`：规范化后全等，或者一方是另一方加上 `/` 前缀的后缀。`bar.txt` 与 `foo/bar.txt` 会被当成同一个路径。`_in_paths` 用于跨文件提醒（第 6 步）与红灯限面（第 5 步）；第 8 步的重读检查按快照路径全等比较。

## 四条单文件链路

下面的 A、B 是两个互不相干的路径，工具是 `write_file` 这一类一次只写一个文件的入口。

| 顺序 | 当前结果 | 放行原因 |
|---|---|---|
| 预览 A → 审 A → 预览 B → 审 B → 交 A → 交 B | 通过 | 两份章都盖在任何真写之前。交 A 把 `reviewed_ok` 打回假，交 B 时章仍早于这次真写 |
| 预览 A → 审 A → 预览 B → 交 A → 审 B → 交 B | 通过 | 交 A 之后审 B。B 自己的章并不早于这次真写；审 B 时 `review_done` 熄掉写后提醒，交 B 放行 |
| 预览 A → 预览 B → 审 A → 审 B → 交 A → 交 B | 通过 | 与第一条相同，两份都在真写前盖章 |
| 预览 A → 预览 B → 审 A → 交 A → 审 B → 交 B | 通过 | 与第二条相同，靠审阅熄灯 |

预览未 `confirm` 就提交仍然拒绝。对预览路径就是目标文件的工具（如 `write_file`），同一路径刚写过、尚未 `read` 就再交一次，会被第 8 步拦住；这与上面四条不是同一条规则。`apply_patch` 的预览路径是补丁根目录，第 8 步不会命中它的目标文件。

交 A 之后再审 C（任意一份），同样会熄灯：这是软提醒的预期行为，不是「C 错误地替 A 做了路径级复核」。

## 批量修改的当前行为

一次 `apply_patch` 是一个 `confirm_id`、一次审阅、一次提交。门控在提交前只检查这一次，补丁内部的多个文件不再逐个过 `check_write`。

提交成功后：

- `pending_review`、`needs_reread` 与 `fixable_paths` 只增加第一个目标文件。
- `apply_patch_pending` 变成真。这个开关不记录补丁改了哪些文件，之后每一次新的 `apply_patch` 都看它，直到某次 `review_done`（与写后软提醒同一套熄灯）。
- 写后质量报告也只针对主路径。

由于预览快照的路径是补丁根目录，而 `pending_review` 与 `needs_reread` 里是第一个目标文件，第 5、6、8 步比较的是根目录而不是文件。实际效果是 `_in_paths(根目录, ...)` 为假，根目录也不等于 `needs_reread` 里的文件。

因此同一次补丁里的第二个文件，马上用另一次预览去改，不会被「先 read」拦住。另一份在这次真写之前已经审过的补丁，代际条件为真，第 6 步和第 7 步都跳过。另一份在这次真写之后才审的补丁，这次审阅会调用 `review_done`，第 6、7 步的条件都已清掉，因此可以提交；如果只 `confirm` 而没有调用 `review_conclusion`，则第 6 步会先拒绝，第 7 步的专用文案到不了——预览路径是补丁根目录，与 `pending_review` 里的文件不相等。

`file_ops` 的记账路径按 `dest`、`source` 的顺序取第一个非空值。移动同时涉及的另一端不记账。这类操作不进入 `needs_reread`，但仍会把 `reviewed_ok` 打回假。

## 行为后果（按设计，不是缺陷）

### 审任意一份都会熄掉写后提醒

`review_conclusion` 非取消审阅成功后调用全局 `review_done`。链路 2、4 里交 B 能过，靠的就是这次熄灯。交 A 之后审 C，C 也可以提交——因为提醒已被勾掉，不是系统认定「C 复核了 A」。

软提醒只要求走过审阅步骤，不要求审阅对象与刚写的文件一致。

### 章可以跨过后来的提醒灯

`confirmed_generation < _write_generation` 只比较次数。预览在真写之前已盖章的，提交时可以跳过第 6 / 7 步的提醒检查。这与「同一批已审预览连续交」一致，也会让「很早盖章、中间写过别的、一直没交」的预览在提醒灯亮着时仍能交——这是代际规则的结果，不是路径级审计。

## 可调整的点

以下三项与「全局软提醒」无关，不改变提醒的会话级设计。

### 一次补丁只记第一个文件

同一次 `apply_patch` 落盘的其余文件：

- 不在 `needs_reread` 里，随后修改不会要求先读当前内容（`needs_reread` 是强约束，这里记账偏窄可能影响「改已落盘文件前先 read」）。
- 不在 `pending_review` 里（对软提醒影响很小：提醒本就不绑「必须审对路径」）。
- 写后语法、JSON、大删除检查也不跑这些路径。

另外，`apply_patch` 的预览路径是补丁根目录，第 8 步按快照路径全等比较，所以即使主路径已进入 `needs_reread`，下一次 `apply_patch` 也不会被重读检查拦住；只有预览路径等于目标文件的工具才命中。

一种更完整的记账方式：结果 `files` 里每个路径都进入 `needs_reread` 与写后检查，并让预览路径按目标文件解析；补丁通道是否仍用全局布尔可单独定，但「任意 `review_conclusion` 熄灯」保持不变。

### 两条规则叠在一起，后一条很少开口

第 6 步的写后提醒和第 7 步的补丁通道用的是同一套「是不是写之前已解锁」。另一份文件在写之后才解锁（只 `confirm`、未调用 `review_conclusion`）时，第 6 步先拒绝，第 7 步的文案到不了。读拒绝原因时，会以为只有跨文件提醒，看不到补丁通道也亮着。文案或提示合并即可解决，状态模型不必改。

### 路径按后缀算同一个文件

`_in_paths` 把 `bar.txt` 和 `foo/bar.txt` 视为命中。跨文件提醒（第 6 步）与红灯限面（第 5 步）可能把不同文件混在一起；第 8 步的重读检查按全等比较，不走 `_in_paths`。斜杠不同的同一路径，用规范化后的全路径相等即可；是否去掉后缀匹配可单独评估。

## 改动约束

- `pending_review` / `reviewed_ok` 保持会话级语义：写成「必须按路径 / 按 `confirm_id` 精确复核才熄灯」会改变软提醒的摩擦成本。
- `review_conclusion` 在解锁一份预览后仍调用 `review_done`；去掉这一步需要另一套「写后提醒熄灯」机制，且保持低摩擦。
- 三步曲服务于「少用工具、写对」与「提醒模型留意文件变化」，不承担合规审计职责。

强约束（`needs_reread`、诊断红灯、未 `confirm` 不能交、补丁多文件记账）与软提醒分层评估，互不绑定。
