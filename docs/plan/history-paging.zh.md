[English](history-paging.md) | **中文**

**状态：** 设计提案，当前代码尚未实现。

# 会话历史分页

## 1. 背景与目标

刷新页面时，经典界面调用 `GET /api/chat/history` 一次取回整份会话历史。该端点把 `.raw` 事实日志整体折成 `items`（用户气泡、思考、助手正文、工具卡及其结果报文、附件），前端再把每个 item 建成 DOM 节点。会话越大，刷新越慢，DOM 越多，内存压力越大。

目标：

1. 首屏只渲染最新一页，页面刷新与内存占用与会话总长度解耦。
2. 向上滚动时按需取更早的页，取完为止。
3. 不改变事实日志格式，不改变内核事件接口，不改变 SSE 重放语义。
4. 页边界落在用户轮次上，任何一页都不出现“半个轮次”。

## 2. 术语

| 词 | 含义 |
|---|---|
| 轮次（round） | 一条 `input_claimed` 事实开始，到下一个 `input_claimed` 之前为止的全部内容 |
| 轮 ID | 该轮 `input_claimed` 事实的 `_seq`，即全局存储坐标，单调唯一 |
| `before` | 页的**排他**边界：只返回轮 ID 小于它的轮次 |
| `next_before` | 本页最早一轮的轮 ID，即下一次请求的 `before`；`has_more=false` 时为 `null` |
| 页 | 由若干**连续完整轮次**组成的条目序列 |
| 字符成本 | 一个 `item` 折算成文本后的字符数，口径见 5.3 |

本设计不使用 `cursor` 一词：本工程的 `cursor` 专指 SSE 断线续传的全局存储坐标（`cursor_of` / `replay_after` / `Last-Event-ID`）。分页边界是轮 ID，二者含义不同，混用会让“翻到更早”与“从断点重放”相混。

一条轮次可以包含：用户气泡与其附件、思考块、若干条助手正文、若干张工具卡（参数、结果 `preview`、diff、图片）。

## 3. 不变量

1. 分页单位是轮次，不是消息条数，也不是事件条数。
2. 一页从最新一轮向旧累加，累计字符成本**达到或超过** `10000` 时停止；跨过阈值的这一轮**整轮纳入**。页的实际大小因此是“累计不低于 `10000` 字符的最小整轮集合”。
3. 轮 ID 取 `input_claimed._seq`。不新增 round 字段，不改落盘格式。
4. 分页只发生在经典界面投影层。内核的原始事件接口（`SessionActions.history`）不参与分页。
5. `context_layout` 与 `todo_list` 是整会话汇总态，任何一页都完整返回，不参与分页。
6. `before` 是排他边界：轮 ID **小于**它的轮次才属于结果。

## 4. 接口契约

### 4.1 请求

```text
GET /api/chat/history?conversation_id=<cid>[&before=<seq>][&meta=1]
```

| 参数 | 必填 | 语义 |
|---|---|---|
| `conversation_id` | 是 | 会话 ID |
| `before` | 否 | 排他边界（轮 ID）。缺省返回最新一页 |
| `meta` | 否 | `1` 表示只要 `context_layout` 与 `todo_list`，不折 `items`，也不返回 `page` |

### 4.2 响应

```json
{
  "ok": true,
  "conversation_id": "…",
  "items": [
    { "role": "user", "content": "…" },
    { "role": "tool", "tool_call_id": "…", "script": "…", "status": "done" }
  ],
  "page": {
    "budget_chars": 10000,
    "chars": 9832,
    "has_more": true,
    "next_before": 1203
  },
  "context_layout": {},
  "todo_list": []
}
```

字段约定：

1. `next_before` 是本页**最早一轮**的轮 ID，同时就是下一次请求的 `before`。
2. `has_more` 为 `false` 时，`next_before` 必须是 `null`。
3. `page.chars` 是本页各 item 字符成本之和，用于诊断，前端不读。
4. `items` 的顺序与全量折叠时完全一致，前插不会改变相对顺序。
5. 普通请求的 `page` 键集合固定为 `budget_chars` / `chars` / `has_more` / `next_before`。

`page` 是新增的可选键，只向前兼容：

- `meta=1` 不返回 `page`，也不返回 `items`；
- 前端先判断 `j.page` 存在再读取；忽略该键的客户端仍能渲染本页 `items`，但无法继续向旧翻页；
- 服务端不因请求缺少 `before` 而失败，缺省即最新页；
- 不新增 `page_version` 字段：当前没有消费方，加了就是死契约。

### 4.3 错误与降级

| 情况 | 行为 |
|---|---|
| `before` 不是非负整数 | `ok:false`、`error:"invalid before"`、`items:[]`、无 `page` |
| `before` 比最早轮次还旧 | `items:[]`、`page.has_more:false`、`page.next_before:null` |
| 会话不存在或没有事件 | `items:[]`、空 `page`，`context_layout` / `todo_list` 照常返回 |
| `meta=1` | `items:[]`、无 `page`，汇总字段照常返回 |

该端点保持既有的 `ok` 语义：非 `true` 时前端一律不渲染、不继续翻页。

`before` 的**解析与拒绝只发生在 `web_routes.py` 一处**：缺失 → `None`，非法 → 早退为 `ok:false`。适配层收到的是已校验的 `int | None`，自身不再判形。校验点分裂会让非法输入在两条路径上给出两种结果。

## 5. 后端设计

### 5.1 模块与依赖

新增 `agent/shell/classic_adapter/history_page.py`。该模块是**纯函数模块**：

- 不 import `store`、`http`、`adapter`，也不 import 任何 `agent.capabilities` 之上的层；
- 输入是事件及其存储坐标，输出是轮次与页；
- 事件到 item 的折叠规则只有一份实现，`classic_adapter/history.py` 的 `history_items` 改为对它的薄包装。

依赖方向保持 `shell → capabilities → mechanisms → core`。

### 5.2 数据结构

```python
@dataclass(frozen=True)
class Round:
    anchor: int | None                 # 轮 ID；None 表示首个 input_claimed 之前的残留事件
    items: tuple[dict, ...]
    attachments: tuple[dict, ...]
    chars: int

@dataclass(frozen=True)
class Page:
    items: tuple[dict, ...]
    attachments: tuple[dict, ...]
    start: int
    end: int
    chars: int
    has_more: bool
    next_before: int | None
```

`frozen=True` 只挡赋值，挡不住 `page.items.append(...)`——那样会造出“内部可见、观察面不可见”的隐藏状态。所有集合字段一律是 `tuple`，构造前用 `tuple(...)` 收敛。`Round` 与 `Page` 都是**纯值**：拿到它们的调用方无法改写分页结果。

`items` 内的 `dict`、`attachments` / `images` 内的 `list` 仍是可变对象，因此分页函数在返回前复制出参：顶层 `dict` 与嵌套的 `list` 都新建，附件缓存与出参不共享可变对象，调用方改返回值不影响下一次调用。JSON 需要 `list`，不能用 `MappingProxyType`（`json.dumps` 不认）。

`attachments` 只收集本页需要登记到附件缓存的字节，避免翻页时把整会话附件重新登记一遍。工具结果里的图片仍以内联 `data_base64` 存在于 `items`，不进入 `attachments`。

### 5.3 字符成本

`item_cost(item)` 的口径接近界面报文区的文本量：

| item | 计入 |
|---|---|
| `user` | `content` 长度；附件按公开 `name` 长度 |
| `think` | `content` 长度 |
| `assistant` | `content` 长度 |
| `tool` | `script` + 紧凑 JSON 化的 `args` + `preview` + `error`；图片只计公开元数据 |

约定：

1. JSON 用 `ensure_ascii=False` 与无空格分隔符。界面报文区会把 `preview` 再格式化成缩进 JSON，因此该口径是下界，不是逐字符相等。
2. 用户附件不在 `items` 里带字节，字节由附件端点单独取，不计入字符成本；工具图片按图片渲染，只计 `mime` 等公开元数据，不计 `data_base64`。
3. `None` 与缺失字段按 0 计。
4. 阈值常量 `HISTORY_PAGE_CHARS = 10_000` 定义在该模块内，不读配置文件。

### 5.4 轮次折叠

`fold_rounds(events)`：

1. 顺序扫描事件，沿用现有折叠规则（即原 `history_items` 的实现）产出 item；
2. 遇到 `input_claimed` 就开新一轮，`anchor = event.data["_seq"]`；
3. `tool_started` 创建工具 item；其后的 `tool_done` / `tool_failed` / `tool_canceled` / `tool_suspended` / `tool_ended` 与 `tool_progress` 按 `call_id` 归并到已有工具 item，仍留在当前轮；
4. 首个 `input_claimed` 之前的事件收进一个 `anchor=None` 的残留轮，排在最前；
5. 每轮累加 `chars`，保证 `chars == sum(item_cost(i) for i in items)`。

`history_items(events)` 保留原签名，先对缺少 `_seq` 的事件按位置补号，再调用 `flatten(fold_rounds(events))`，返回 `(items, resolved_attachments)`，使现有调用方与既有用例的输出保持不变。

### 5.5 页选择

```python
def select_page(rounds, *, before, budget=HISTORY_PAGE_CHARS):
    end = len(rounds)
    if before is not None:
        end = len(rounds)
        for index, rnd in enumerate(rounds):
            if rnd.anchor is not None and rnd.anchor >= before:
                end = index
                break

    start = end
    chars = 0
    while start > 0:
        start -= 1
        chars += rounds[start].chars
        if chars >= budget:
            break

    page = rounds[start:end]
    has_more = start > 0
    return Page(
        items=tuple(flatten(page)),
        attachments=tuple(collect_attachments(page)),
        start=start,
        end=end,
        chars=chars,
        has_more=has_more,
        next_before=rounds[start].anchor if has_more else None,
    )
```

边界：

1. 单轮成本超过 `budget` 时该轮整轮返回，`chars` 如实大于预算。
2. 残留轮（`anchor=None`）只能作为最后一页被包含；一旦包含它，`has_more` 为假。
3. `before` 恰好等于某轮 ID 时，该轮不返回。
4. `end == 0` 返回空页，`start == end == 0`，`has_more` 为假。
5. 轮 ID 取 `event.data["_seq"]`；历史装载走 `store.load_with_seq()`（返回 `(seq, event)`）：落盘行有 `s` 用它，缺 `s` 的旧行按行位置补号，并在折叠前写回 `_seq`。`store.load()` 丢掉行位置补号，缺 `s` 的旧行读回后不带 `_seq`。

### 5.6 适配层与路由

1. `classic_adapter/inbound.py`
   - `history(cid, store=None, *, before=None, meta=False)`；`before` 已是校验过的 `int | None`，`store` 供子会话历史传入自己的存储。
   - `meta=True`：只算 `context_layout` 与 `todo_list`，跳过折叠。
   - 否则：`fold_rounds` → `select_page` → 用 `Page.items` 组织响应；附件按 5.7 合并登记。
   - 响应体新增 `page`，其余字段与既有形状一致。
2. `classic_adapter/adapter.py`：`ClassicAdapter` 直接继承 `Inbound.history`，不另设转发层；`before` / `meta` 随方法签名生效。
3. `web_routes.py`：解析 `before`，非法即早退为 `ok:false`；合法则透传。
4. `web_sessions.py` 的 `SessionActions.history`（内核原始事件接口）不变。

### 5.7 附件登记

`ClassicState.put_attachments` 是**整体替换**（`attachments[cid] = list(items)`），不是追加。分页后若每页只带本页字节直接调用它，第 2 页会把第 1 页已渲染气泡的附件从缓存里清掉。附件端点在 id 缺失时会重跑一次 `history(cid)` 兜底，但分页后它只重取最新一页，旧页附件不会再被登记，那些 `<img>` 随即 404，而界面不会报错。

因此新增 `ClassicState.merge_attachments(cid, items)`：

1. 按 `id` 合并；同一 `id` 以本次为准，其余保持原顺序追加在后。
2. 单次登记的条数与单张字节上限沿用既有 `ATTACH_REGISTER_MAX_COUNT` / `ATTACH_REGISTER_MAX_BYTES`（定义在 `classic_adapter/history.py`）。它们的语义本来就是“每次 history 最多登记多少”，翻页后自然变成“每页最多登记多少”。
3. 不做全局裁剪：缓存总量上界 = 每页 24 张 × 已加载页数，且单张 ≤ 2 MB。出现内存压力时再加全局上限，并按“已离开视口的页”淘汰——那需要新增淘汰集合，属于另一项设计，不在本设计内。
4. 唯一权威仍是 `ClassicState`：`inbound` 只提供本页增量，不自己再存一份。
5. 会话切换与清空继续走 `clear_attachments`，语义不变。
6. `remember_attachments`（发送图片时的登记）同样改走合并：若继续调用 `put_attachments`，分页后会清掉已加载页的附件。
7. `merge_attachments` 与 `get_attachment` 在同一把锁内完成；翻页与发送图片并发时，已登记附件不会被整体替换清掉。

## 6. 前端设计

### 6.1 每会话状态

`historyLoaded` 已在 `loadConversationHistory` 中用作首屏标记；分页再增加两个字段，并在 `makeConversationTab` 里显式初始化：

```js
historyLoaded: false,     // 首屏是否已渲染
historyBefore: null,      // 下一次翻页的 before；null 表示还没取到
historyState: "idle"      // "idle" | "loading" | "exhausted" | "error"
```

`historyState` 是**穷尽的四态**，不拆成两个布尔：

| 状态 | 含义 | 滚到顶时的行为 |
|---|---|---|
| `idle` | 还可以取更早的页 | 发请求 |
| `loading` | 正在取 | 不发第二个请求 |
| `exhausted` | 没有更早的轮次 | 不发请求 |
| `error` | 上一次失败，未恢复 | **不发请求**，等用户点重试 |

用 `historyHasMore` + `historyLoading` 两个布尔表达不出 `error`：失败后 `hasMore` 仍为真，滚到顶会无限重试，把一次网络失败变成死循环。

四态随 `saveRuntimeStateToTab` / `loadRuntimeStateFromTab` 一起保存与恢复；恢复时 `loading` 一律降级为 `idle`（刷新前的那次请求已经不存在了）。

### 6.2 首屏

1. `loadConversationHistory(t)` 请求不带 `before`。
2. 成功后写入 `historyBefore = j.page.next_before`，并按 `has_more` 置 `exhausted` 或 `idle`；失败置 `error`、复位 `historyLoaded` 并显示一次可重试提示。
3. 沿用既有判据：消息区已有实时内容时不清空，只渲染本页。
4. 首屏渲染完成后滚到底部。

### 6.3 向上翻页

触发条件同时满足：

- 滚动容器的 `scrollTop <= 4`；
- `t.historyState === "idle"`。

两个入口共用一个函数 `loadOlderHistory(t)`：

1. 复用现有的 `document` 捕获阶段 `scroll` 代理，按容器找到所属 tab，不新增逐面板监听。
2. 增加一个全局 `wheel` 捕获监听（`passive: true`）：已经在顶部继续向上滚时不产生 `scroll` 事件，需要 `deltaY < 0` 才能继续取页。
3. 请求带 `before = t.historyBefore`；`historyBefore` 为 `null` 时不发请求。
4. 请求期间置 `loading`，在消息区顶部显示一行轻量提示，完成后移除。
5. 成功后前插并保持视口锚点：

```js
var anchor = msgs.scrollHeight - msgs.scrollTop;
msgs.prepend(fragment);
msgs.scrollTop = msgs.scrollHeight - anchor;
```

6. 失败时置 `error`，顶部提示行变成“加载更早的对话失败 · 点击重试”并留在原处；点击重试才回到 `idle` 并重新请求。失败必须留痕：`console.error` 带上 `cid`、`before`、HTTP 状态，不允许 `catch(e){}` 静默返回。失败**不自动重试**：自动重试会让“网络断了”表现为“滚不动且 CPU 在转”。

停止条件（任一命中即置 `exhausted`）：

1. `has_more` 为假；
2. `next_before` 与本次 `before` 相同（防服务端边界不前进）；
3. 返回空 `items`。

### 6.4 渲染上下文切换

`add()`、`onToolStart()`、`onToolEnd()`、`appendChatToolRow()`、`appendStep()` 都读写全局 `msgs` / `steps` / `streamAssistantEl`。翻页时用一个守卫函数临时切换：

```js
function withRenderContext(msgsEl, stepsEl, fn) {
  var prevMsgs = msgs, prevSteps = steps;
  var prevStream = streamAssistantEl, prevText = streamAssistantText;
  msgs = msgsEl;
  steps = stepsEl;
  streamAssistantEl = null;
  streamAssistantText = "";
  try {
    return fn();
  } finally {
    msgs = prevMsgs;
    steps = prevSteps;
    streamAssistantEl = prevStream;
    streamAssistantText = prevText;
  }
}
```

渲染目标是两个游离容器，渲染完成后把子节点分别前插到真实消息区与步骤区。工具卡、思考块、附件条因此与实时路径共用同一套渲染函数，不出现两套实现。该守卫的保存与恢复方式与 `withConversationContext` 一致，只把目标换成游离容器。

### 6.5 超长工具报文的延迟渲染

1. `chat-tool-views.js` 增加常量 `LAZY_TOOL_TEXT_CHARS = 20000`。
2. 所有写长文本的入口统一走 `setLazyText(el, text)`：
   - 未超阈值：直接写入；
   - 超出：只写入摘要行，原文挂在元素上，展开时再落 DOM。
3. 现有委托的展开点击（`.chat-tool-head`）在展开时调用 `materializeLazy(el)`。
4. 该机制按文本长度判定，不按工具名分支，实时路径与历史路径共用。
5. 折叠只影响 DOM 写入时机，不改变字符预算与分页结果。

### 6.6 汇总态刷新

`refreshConversationContextLayout(t)` 改为请求 `?meta=1`，避免每次刷新汇总态都折一页 `items`。

## 7. 文件清单

| 动作 | 文件 |
|---|---|
| 新增 | `agent/shell/classic_adapter/history_page.py` |
| 修改 | `agent/shell/classic_adapter/history.py` |
| 修改 | `agent/shell/classic_adapter/inbound.py` |
| 修改 | `agent/shell/classic_adapter/state.py` |
| 修改 | `agent/shell/web/web_routes.py` |
| 新增 | `agent/shell/web/web_assets/classic/js/history-paging.js` |
| 修改 | `agent/shell/web/web_assets/classic/js/chat/conversation.js` |
| 修改 | `agent/shell/web/web_assets/classic/js/chat-tool-views.js` |
| 修改 | `agent/shell/web/web_assets/classic/css/chat-messages.css` |
| 修改 | `agent/shell/web/ui_bundle.py` |

分页逻辑放进新文件 `history-paging.js`，不继续往会话模块里堆：经典界面的主脚本已按职责拆成多个模块（见 `ui_bundle.UI_JS_MODULES`），单文件普遍在数百行内。

新文件必须登记进 `UI_JS_MODULES`：`scripts/check_ui_js.py` 从同一份清单取文件，不需要单独登记；模块共用同一个 `<script>` 作用域，可直接调用主脚本函数。启动代码在 `core/boot.js` 与 `layout/splitters.js`，新文件若依赖同作用域全局，位置要排在这些模块之后。

`setLazyText` / `materializeLazy` 属于工具视图，落在 `chat-tool-views.js`，不放进分页文件：它们服务的是“任何长文本”，与“历史翻页”无关。

## 8. 测试与验收

单元测试（`tests/test_history_page.py`）：

1. 字符成本：各类 item 与附件、空字段、超长 `preview`。
2. 轮次折叠：单轮、多轮、工具跨事件归并、首个 `input_claimed` 之前的残留事件、缺 `_seq` 的旧行按行位置补号。
3. 页选择：
   - 阈值恰好落在轮边界；
   - 阈值落在轮中间时整轮纳入；
   - 单轮超预算；
   - `before` 排他；
   - `before` 超出范围；
   - 最后一页 `has_more` 与 `next_before`。
4. `items` 顺序与全量折叠一致。
5. 返回值不可变：`page.items` / `round.items` 是 `tuple`，`append` 应抛 `AttributeError`；改 `page.items[0]["content"]` 后再次请求，结果与基线一致；改 `page.items[0]["attachments"]` 的元素后，`get_attachment` 仍返回原对象。
6. 附件合并：连续两次 `merge_attachments` 后，第一次的 `id` 仍可 `get_attachment` 到；同一 `id` 第二次覆盖；超过单次上限时只截断本次。
7. `before` 非法值在路由层被拒，适配层不会被调用（打桩断言调用次数为 0）。
8. 分页请求与 `merge_attachments` 并发：每页 `items` 自洽、附件 id 不丢、不出现页内引用已被清掉的附件。

前端行为：

1. 断网状态下滚到顶：出现“加载更早的对话失败 · 点击重试”，不再发请求；恢复网络后点重试才继续翻页。
2. `next_before` 与本次 `before` 相同时立即 `exhausted`，不发第二个请求。

集成与手工验收：

1. 约 5 万字符、10 轮的会话：首屏只含最新若干整轮，累计不低于 `10000`，最早一轮完整。
2. 滚到顶自动前插，视口内容不跳动；连续翻到最早一页后不再发请求。
3. 单轮 5 万字符的工具输出：整轮返回，报文默认折叠，展开后出现全文。
4. 刷新 10MB 会话：首屏 DOM 只含一页条目，`history` 响应不含全量 `items`。
5. `meta=1` 只返回 `context_layout` 与 `todo_list`。
6. 回合进行中翻旧页：流式气泡仍在底部，前插不打断。

## 9. 边界与代价

1. 每次翻页服务端仍读取全量事件并折一遍，复杂度 O(n)。本设计不引入轮次索引；只有出现明显延迟时才值得为它单独设计索引结构。
2. 不实现视口虚拟化，已加载的旧页不卸载。旧页只在用户主动翻页后出现。
3. 不新增 `round` 字段，轮次由前端与服务端都不额外记账。
4. 不改内核事件接口，不改 SSE 断线重放。
5. 分页只影响经典界面投影；其它客户端读内核原始事件接口，行为不变。
6. 字符预算只约束文本。工具结果里的图片仍以内联 `data_base64` 随 `items` 返回，不计入预算；一页的图片字节量由轮数与单轮内容决定，不由字符阈值约束。
7. 进程重启后附件缓存为空，附件端点的兜底只重取最新一页；已加载旧页里的图片在这些页被重新取回前可能 404。
8. 子会话历史路由（`/api/subagents/history`）不带 `before`，只返回最新一页；它的向上翻页不在本设计内。
