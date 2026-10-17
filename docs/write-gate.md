# 写盘门控：当前链路与后续优化

本文记录 2026-10-17 代码的真实行为，并给出一份尚未实施的优化方案。优化落地前，以 `agent/mechanisms/quality_gate.py` 与 `agent/capabilities/builtin/review_conclusion.py` 为准。

相关代码：

| 位置 | 作用 |
|---|---|
| `QualityGate.check_write` | 提交前按固定顺序决定放行或拒绝 |
| `QualityGate.confirm` | 给一份预览盖章，章上是当时的真写次数 |
| `QualityGate.review_done` | 清空全部待复核，并关闭补丁通道 |
| `QualityGate.note_committed` | 一次提交成功后的记账 |
| `review_conclusion` | 先 `confirm` 这份预览，再无条件 `review_done` |
| `build_pipeline_gate` | `commit_write` 成功后只把结果里的主路径交给 `note_committed` |

## 当前状态

这些字段是会话级的，不是按文件各记一份：

| 字段 | 含义 |
|---|---|
| `_pending[confirm_id]` | 一份预览快照。`confirmed` 表示已审，`confirmed_generation` 是审阅当时的真写次数。登记时同路径只留最新；条数上限 `MAX_PENDING_PREVIEWS`（100），满则按登记顺序挤掉最旧的 |
| `_write_generation` | 成功提交的次数，从 0 起 |
| `pending_review` | 已落盘、被视为尚未复核的路径列表 |
| `reviewed_ok` | 为假时，跨文件规则生效 |
| `needs_reread` | 刚写过、再次改之前必须 `read` 的路径 |
| `apply_patch_pending` | 是否有一次 `apply_patch` 已经落盘且尚未被 `review_done` 清掉 |
| `pending_diagnose_red` / `fixable_paths` | 写后诊断失败时，只允许改列出的路径 |

`review_conclusion` 的顺序固定：

1. `cancel_preview` 为真时只丢弃这份预览，不解锁。
2. 带 `confirm_id` 时 `confirm`：快照标为已审，`confirmed_generation = 当前真写次数`。
3. 无论这次审的是哪一个文件，都调用 `review_done`：`pending_review` 清空，`reviewed_ok = True`，`apply_patch_pending = False`。大删除红灯一并解除。诊断红灯（语法、JSON 失败）不因这次调用解除。

`commit_write` 成功后的 `note_committed`：

1. `_write_generation` 先加一。
2. 内容类工具（`write_file`、`replace_in_file`、`apply_patch`、`read_write`、`file_undo`）把主路径放进 `needs_reread`。删除、移动、复制不要求重读。
3. 主路径追加进 `pending_review`，`reviewed_ok` 设为假。
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
| 预览 A → 审 A → 预览 B → 交 A → 审 B → 交 B | 通过 | 交 A 之后审 B。B 自己的章并不早于这次真写，放行是因为审 B 调用了 `review_done`，把 A 的待复核清掉了 |
| 预览 A → 预览 B → 审 A → 审 B → 交 A → 交 B | 通过 | 与第一条相同，两份都在真写前盖章 |
| 预览 A → 预览 B → 审 A → 交 A → 审 B → 交 B | 通过 | 与第二条相同，靠审 B 时的全局清空 |

未审阅就提交仍然拒绝。同一路径刚写过、尚未 `read` 就再交一次，被第 8 步拦住，与上面四条不是同一条规则。

## 批量修改的当前行为

一次 `apply_patch` 是一个 `confirm_id`、一次审阅、一次提交。门控在提交前只检查这一次，补丁内部的多个文件不再逐个过 `check_write`。

提交成功后：

- `pending_review` 与 `needs_reread` 只增加第一个目标文件。
- `apply_patch_pending` 变成真。这个开关不记录补丁改了哪些文件，之后每一次新的 `apply_patch` 都看它。
- 写后质量报告也只针对主路径。

因此同一次补丁里的第二个文件，马上用另一次预览去改，不会被「先 read」拦住。另一份在这次真写之前已经审过的补丁，代际条件为真，第 6 步和第 7 步都跳过。另一份在这次真写之后才审的补丁，通常先死在第 6 步的跨文件文案上；只有路径被 `_in_paths` 算成同一个文件时，才会落到第 7 步的补丁专用文案。

`file_ops` 的记账路径按 `dest`、`source` 的顺序取第一个非空值。移动同时涉及的另一端不记账。这类操作不进入 `needs_reread`，但仍会把 `reviewed_ok` 打回假。

## 不合理之处

### 审一份预览会清掉已落盘的账

`review_conclusion` 在解锁「这份还没落盘的预览」之后，固定把全局待复核和补丁通道清掉。链路 2、4 里交 B 能过，靠的是这次清空，不是「B 的审阅只授权 B」。

连带效果：交 A 之后，预览 C 也已经解锁，此时只审 B，C 也可以提交。C 没有在 A 落盘之后被审过，A 落盘后的复核同样被这次调用勾销。大删除红灯也按同一条全局清空解除。

### 章的有效期是整个会话

`confirmed_generation < _write_generation` 只比较次数，不比较「这是不是同一批」。预览 C 在会话开头审过、一直没交，中间再写多少别的文件，C 的章仍然早于最近一次真写，可以跳过后来积下的全部复核账。

这比「同一批里已经审过的预览可以连续交」宽。章不会过期，也不会在别的文件落盘后要求重审。

### 一次补丁只记第一个文件

同一次 `apply_patch` 落盘的其余文件：

- 不在 `needs_reread` 里，随后修改不会要求先读当前内容。
- 不在 `pending_review` 里，跨文件规则的「同一路径」判断看不到它们。
- 写后语法、JSON、大删除检查也不跑这些路径。

补丁通道是一个布尔值。一次补丁落盘之后，任何目录里的下一次 `apply_patch` 都受它约束，直到某次 `review_done`。它不表示「这个补丁改过的文件还没复核」。

### 两条规则叠在一起，后一条很少开口

第 6 步的跨文件复核和第 7 步的补丁通道用的是同一套「是不是写之前已解锁」。另一份文件在写之后才解锁时，第 6 步先拒绝，第 7 步的文案到不了。读拒绝原因时，会以为只有跨文件复核，看不到补丁通道也亮着。

### 路径按后缀算同一个文件

`_in_paths` 把 `bar.txt` 和 `foo/bar.txt` 视为命中。跨文件规则因此会把不同文件当成「还在改上次那个文件」而放行，或把本应分开的重读、红灯范围混在一起。斜杠不同的同一路径，用规范化后的全路径相等就能识别，不必做后缀匹配。

## 优化方案

目标：复核跟着 `confirm_id` 走，重读跟着已经落盘的路径走。不相干的文件不因为另一份文件的提交或审阅而互相开锁、关锁。下面四条继续必须通过；未审阅的提交继续拒绝；同一路径刚写过必须先 `read`。

### 状态改成两份独立记录

预览记录，按 `confirm_id`：

- 工具名、参数、涉及的全部路径。
- `reviewed`：只有针对这个 `confirm_id` 的 `review_conclusion` 把它设为真。
- 消费标记：提交成功后这份预览作废，不能再交一次。

落盘记录，按规范化后的全路径：

- `needs_reread`：内容类写入成功后，这次实际改到的每个路径都加入。`read` 该路径后移除。
- 诊断红灯仍按路径限制。语法或 JSON 失败的文件修完之前，不借别的文件的审阅把红灯关掉。
- 大删除标记挂在触发它的路径上。解除它的审阅必须点名这个路径，而不是任意一次 `review_conclusion`。

去掉会话级的 `reviewed_ok`、`pending_review`、`_write_generation`、`confirmed_generation`、`apply_patch_pending`。它们把「这一份预览审过没有」和「上一次真写复核过没有」叠成一把全局锁。

### 提交前只问这几件事

1. `confirm_id` 仍在，且已针对它审阅。
2. 这次要写的每个路径都不在 `needs_reread`。
3. 诊断红灯若亮着，目标路径必须落在允许修复的范围内。
4. `replace_in_file` 的体积限制保持不变。

不再有「上一次真写尚未 review，所以别的文件不能交」。另一份文件只要自己审过，且自己的路径不需要重读，就可以交。审 B 只把 B 的 `reviewed` 设为真，不清除 A 的重读标记，也不让未审的 C 变成可提交。

四条链路在这套规则下的原因：

| 顺序 | 原因 |
|---|---|
| 审 A、审 B 都在两次提交之前 | 交 A、交 B 时各自 `reviewed` 已为真，B 的路径不在重读集合里 |
| 交 A 之后才审 B | 审 B 只解锁 B。交 B 时 B 已审，且 B 没被写过 |
| 先预览两份再连续审、连续交 | 与第一条相同 |
| 先审 A 并交 A，再审 B 并交 B | 与第二条相同 |

交 A 之后若直接交一个从未审阅的 C，仍然拒绝。交 A 之后对 A 再预览再提交，在 `read` A 之前拒绝。

### 批量修改按实际写入的路径记账

一次 `apply_patch` 仍是一个 `confirm_id`、一次审阅、一次提交。审阅授权的是这一次提交整体，不要求补丁里的文件再逐个审。

提交成功后，结果 `files` 里的每个路径都进入 `needs_reread`，写后检查也对每个路径跑。不再只记第一个文件，也不再设全局补丁开关。之后：

- 另一个已经审过的 `confirm_id`，只要它的路径都不在 `needs_reread`，可以提交。
- 再改补丁里已经落盘的某个文件，先 `read` 这个文件。
- `file_ops` 的移动、复制把源路径和目标路径都计入落盘记录；删除把被删路径计入。不要求重读的操作仍然不进 `needs_reread`，但不再因此把全局 `reviewed_ok` 打回假。

### 路径比较

待复核、重读、红灯范围都用规范化后的全路径全等。同一路径的 `/` 与 `\` 仍视为同一个文件。不再用后缀包含关系。

### 落地时要动的地方

- `QualityGate.confirm`、`review_done`、`check_write`、`note_committed` 改成上面的两份记录。`review_conclusion` 不再在解锁一个 `confirm_id` 之后调用全局 `review_done`。
- `build_pipeline_gate` 的提交后处理改为把这次结果里的全部路径交给记账，而不是只交 `path`。
- 保留并改写现有测试：四条顺序、未审拒绝、同一路径重读、写后才解锁的第三份文件、补丁多文件都进入重读、审 B 不会让未审的 C 通过。
- 诊断红灯、大删除、替换体积这三条安全限制保留，只把「任意审阅即全局解除」改成按路径解除。
