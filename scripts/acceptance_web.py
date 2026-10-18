# -*- coding: utf-8 -*-
"""Web 壳验收：端到端（真实 HTTP 服务 + 真实 SSE 流）。

场景：
  ① 服务与静态资源：页面 / 样式 / 脚本 / vendor 素材全部可达，健康检查正常；
  ② 协议闭环：send → 后台回合 → SSE 单流多路复用（每帧带 cid）→ history / sessions / ui-state；
  ③ 门控闭环：预览回传 confirm_id（未落盘）→ 未确认提交被拒 → 经 Web 确认端点确认 →
     提交落盘 → 跨会话确认被拒（`/api/chat/user-confirm` 的协议侧）；
  ④ 并发与停止：同会话并发 send → 409；stop 下发协作式取消；
  ⑤ **Markdown 注入防线**（浏览器，需 Playwright）：XSS 向量在真实页面上必须被转义。

运行：python scripts/acceptance_web.py（全部通过退出码 0；场景 ⑤ 需 Playwright）
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.tool_call import ToolCallRequest  # noqa: E402
from agent.mechanisms.model_provider import StreamDelta  # noqa: E402
from agent.mechanisms.session_store import SessionStore  # noqa: E402
from agent.shell.web import create_server  # noqa: E402

#: XSS 向量 → (名称, 断言说明)
#: 判据统一为：**渲染结果里不得出现可执行的注入面**。
XSS_VECTORS = [
    ("script 标签", "<script>alert(1)</script>text"),
    ("带事件处理器的标签", '<img src=x onerror="alert(1)">'),
    ("javascript: 链接", "[点我](javascript:alert(1))"),
    ("svg onload", "<svg/onload=alert(1)>"),
    ("iframe", '<iframe src="javascript:alert(1)"></iframe>'),
]


class ScriptedProvider:
    """**三步写盘**的 provider 替身：

    ① write_file 预览（不落盘）→ ② review_conclusion 审阅并解锁 → ③ commit_write 落盘。
    每步在**各自的回合**里发一个工具调用（脚本按序驱动多个回合）。
    """

    def __init__(self, target: Path) -> None:
        self.target = target
        self.confirm_id = ""
        self.reviewed = False
        #: 置 True 时：拿到 confirm_id 就**直接提交**（跳过 review），用于验证门控拒绝
        self.commit_before_review = False

    @staticmethod
    def _confirm_from(request) -> str:
        for message in reversed(list(request.messages)):
            if not isinstance(message, dict) or message.get("role") != "tool":
                continue
            try:
                data = json.loads(message.get("content") or "{}")
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            # 模型侧信封：`{"ok":true,"data":{…confirm_id…}}`；兼容旧裸 data
            inner = data.get("data") if isinstance(data.get("data"), dict) else data
            if isinstance(inner, dict) and inner.get("confirm_id"):
                return str(inner["confirm_id"])
        return ""

    def stream(self, request):
        found = self._confirm_from(request)
        if found:
            self.confirm_id = found
        if not self.confirm_id:
            # 第①步：预览
            yield StreamDelta(kind="text", text="先预览：")
            yield StreamDelta(
                kind="tool_call",
                tool_call=ToolCallRequest(
                    call_id="call-preview",
                    name="write_file",
                    arguments={"path": str(self.target), "content": "web-accept-ok"},
                ),
            )
            return
        if self.commit_before_review:
            # 负例：跳过 review 直接提交（门控必须拒绝）
            yield StreamDelta(
                kind="tool_call",
                tool_call=ToolCallRequest(
                    call_id="call-early-commit",
                    name="commit_write",
                    arguments={"confirm_id": self.confirm_id},
                ),
            )
            return
        if not self.reviewed:
            # 第②步：审阅并解锁（门控要求结论有实际内容与证据）
            self.reviewed = True
            yield StreamDelta(
                kind="tool_call",
                tool_call=ToolCallRequest(
                    call_id="call-review",
                    name="review_conclusion",
                    arguments={
                        "file_name": self.target.name,
                        "conclusion": (
                            "review 结论：本次预览为新建文件，路径在允许根内、无覆盖风险，"
                            "内容与任务要求一致，验证证据为预览返回的行数与字节数，准予落盘。"
                        ),
                        "confirm_id": self.confirm_id,
                    },
                ),
            )
            return
        # 第③步：提交落盘
        yield StreamDelta(
            kind="tool_call",
            tool_call=ToolCallRequest(
                call_id="call-commit",
                name="commit_write",
                arguments={"confirm_id": self.confirm_id},
            ),
        )
        yield StreamDelta(kind="text", text="已提交。")


class EchoProvider:
    def stream(self, request):
        yield StreamDelta(kind="text", text="收到。")


class Acceptance:
    """headless 验收运行器：真实 HTTP 服务 + 真实 SSE 流，逐项打印 PASS/FAIL。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.failures: list = []
        self.target = root / "out.txt"
        self.provider = ScriptedProvider(self.target)
        self.app = build_app(
            provider=self.provider,
            store=SessionStore(root / "data"),
            backup_root=root / "bk",
            recycle_root=root / "rc",
        )
        # 显式钉住媒体根与文件根：默认值跟随宿主机（多盘），
        # 只有自己掌控边界才能验证"根内可读 / 根外被拒"。
        self.server, self.shell = create_server(
            self.app, host="127.0.0.1", port=0, media_root=root, fs_root=root
        )
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.frames: list = []
        self._stop = threading.Event()

    def check(self, label: str, cond: bool, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        line = f"  [{status}] {label}"
        if detail and not cond:
            line += f" — {detail}"
        print(line)
        if not cond:
            self.failures.append(label)

    # ── 基础设施 ─────────────────────────────────────────

    def start(self) -> None:
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self._read_sse, daemon=True).start()
        deadline = time.time() + 5.0
        while time.time() < deadline and self.shell.channel_count < 1:
            time.sleep(0.02)

    def close(self) -> None:
        self._stop.set()
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass
        try:
            self.app.dispose()
        except Exception:
            pass

    def _read_sse(self) -> None:
        try:
            # `format=kernel`：要**内核原生事件**。默认那条流是适配层翻译过的经典 UI 事件
            # （conversation / llm_round / tool_start…），本脚本验的是内核行为，
            # 所以显式要原生格式——这也是未来其它交互层（命令行等）观察内核的入口。
            response = urllib.request.urlopen(
                self.base + "/api/events/stream?format=kernel", timeout=30
            )
            buf = b""
            while not self._stop.is_set():
                chunk = response.read(1)
                if not chunk:
                    break
                buf += chunk
                while b"\n\n" in buf:
                    block, buf = buf.split(b"\n\n", 1)
                    for line in block.split(b"\n"):
                        if line.startswith(b"data:"):
                            try:
                                self.frames.append(json.loads(line[5:].decode("utf-8")))
                            except Exception:
                                pass
        except Exception:
            pass

    def get(self, path: str, timeout: float = 10.0):
        try:
            response = urllib.request.urlopen(self.base + path, timeout=timeout)
            return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def get_json(self, path: str):
        status, body = self.get(path)
        try:
            return status, json.loads(body.decode("utf-8"))
        except Exception:
            return status, {}

    def post(self, path: str, payload: dict):
        return self._send("POST", path, payload)

    def put_json(self, path: str, payload: dict):
        """PUT 变体：经典 UI 的布局端点用 PUT（且返回体形状与内核那套不同）。"""
        return self._send("PUT", path, payload)

    def _send(self, method: str, path: str, payload: dict):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            response = urllib.request.urlopen(request, timeout=15)
            return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw.decode("utf-8"))
            except Exception:
                return exc.code, {}

    def wait_turn(self, cid: str) -> None:
        self.app.runner.wait_idle(cid, timeout=25)
        time.sleep(0.35)

    def confirm_id_of(self, cid: str) -> str:
        """从**内核原生帧**里取最近一个预览的 `confirm_id`。

        本脚本用 `?format=kernel` 要内核原生事件，工具结果是 `tool_done`，
          `confirm_id` 在它的 `data` 里。
        成功提交后门控会**清掉**预览快照，所以判据不是"门控里还有没有"。
        """
        found = ""
        for frame in self.frames:
            if frame.get("type") != "tool_done" or frame.get("conversation_id") != cid:
                continue
            data = frame.get("data")
            if isinstance(data, dict) and data.get("confirm_id"):
                found = str(data["confirm_id"])
        return found

    # ── 场景 ─────────────────────────────────────────────

    def scenario_1(self) -> None:
        print("\n场景① 服务与静态资源")
        # 首页是**经典界面**（素材，内联成单页）。素材按原名躺在
        # `web_assets/classic/` 下，可经 `/assets/classic/...` 直接取到。
        for path, needle, label in (
            ("/", "AI Agent", "主界面（经典 UI）"),
            ("/", 'id="chatTabs"', "顶部会话标签栏"),
            ("/", 'id="usage-bottom"', "用量底栏"),
            ("/", "global.AIA", "附件链路（image-lightbox 已内联）"),
            ("/assets/classic/agent-ui.html", "{{CSS}}", "经典 UI 模板（原名）"),
            ("/assets/classic/css/theme-light.css", 'html[data-ui-theme="light"]', "经典 UI 主题样式"),
            ("/assets/classic/js/core/boot.js", "normalizeConversationId", "经典 UI 启动脚本"),
            ("/assets/classic/js/vendor/highlight.min.js", "hljs", "vendor 高亮（直取）"),
        ):
            status, body = self.get(path)
            self.check(
                f"{label}可达：{path}",
                status == 200 and needle in body.decode("utf-8", errors="replace"),
                f"status={status}",
            )
        status, payload = self.get_json("/health")
        self.check(
            "健康检查",
            status == 200 and payload.get("ok") is True and payload.get("tools", 0) > 40,
            str(payload),
        )
        status, _ = self.get_json("/api/nope")
        self.check("未知路径 404", status == 404, str(status))
        # 越界读盘：目标在 media_root（默认服务进程工作目录）之外
        outside = Path(tempfile.gettempdir()) / "accept_web_outside_probe.txt"
        outside.write_text("outside", encoding="utf-8")
        status, body = self.get("/api/media?path=" + urllib.parse.quote(str(outside)))
        self.check("媒体越界读盘被拒", status == 403, str(status))
        inside = self.root / "inside_probe.png"
        inside.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.shell.media_root = self.root  # 便于验证根内可读
        status, body = self.get("/api/media?path=" + urllib.parse.quote(str(inside)))
        self.check(
            "媒体根内文件可读",
            status == 200 and body.startswith(b"\x89PNG"),
            str(status),
        )
        self.shell.media_root = Path.cwd()

    def scenario_2(self) -> None:
        print("\n场景② 协议闭环")
        cid = "accept-web-01"
        status, payload = self.post(
            "/api/chat/send", {"message": "写个文件", "conversation_id": cid}
        )
        self.check("send 返回 ok + run_id", status == 200 and bool(payload.get("run_id")), str(payload))
        self.wait_turn(cid)

        types = [f.get("type") for f in self.frames if f.get("conversation_id") == cid]
        # 内核原生词汇：模型轮用 llm_started / llm_ended，工具用 tool_started / tool_done。
        for expected in ("turn_started", "input_claimed", "llm_started", "tool_started", "tool_done", "turn_ended"):
            self.check(f"事件流含 {expected}", expected in types, str(types))
        frames = [f for f in self.frames if f.get("type")]
        self.check(
            "每帧都带 conversation_id（单流多路复用前提）",
            bool(frames) and all(f.get("conversation_id") for f in frames),
            str([f.get("type") for f in frames if not f.get("conversation_id")]),
        )

        status, payload = self.get_json(f"/api/chat/history?conversation_id={cid}")
        # 经典 UI 靠 `items` 渲染气泡（`renderHistoryItems`），`context_layout` 在顶层。
        self.check(
            "history 带 items（经典 UI 气泡来源）",
            status == 200 and len(payload.get("items", [])) > 0,
            str(payload.get("items"))[:120],
        )
        self.check(
            "history 不下发 events（逐条老事件由 SSE 流负责）",
            status == 200 and "events" not in payload,
            str(sorted(payload))[:120],
        )
        self.check(
            "history 顶层带 context_layout",
            isinstance(payload.get("context_layout"), dict),
            str(type(payload.get("context_layout"))),
        )
        status, payload = self.get_json("/api/chat/sessions")
        # `sessions` 是经典 UI 要的形状（`id` + `date_group`）；纯 cid 列表另给 `conversation_ids`
        ids = [row.get("id") for row in payload.get("sessions", [])]
        self.check("sessions 含本会话", cid in ids, str(payload.get("conversation_ids")))
        status, payload = self.post(
            "/api/chat/send", {"message": "x", "conversation_id": "accept-web-02", "mode": "plan"}
        )
        self.wait_turn("accept-web-02")
        status, payload = self.get_json("/api/chat/ui-state?conversation_id=accept-web-02")
        self.check("ui-state 按会话记模式", payload.get("mode") == "plan", str(payload))
        # 布局端点**不再存任何东西**：激活哪个会话是客户端本地状态，服务端一个
        # 全局字段表示不了"两个客户端各自激活不同会话"。这里验它确实不存。
        self.put_json("/api/chat/ui-state", {
            "tabs": [{"id": cid, "title": "验收"}], "active_conversation_id": cid,
        })
        status, payload = self.get_json("/api/chat/ui-state")
        state = payload.get("state", {})
        self.check(
            "ui-state 不存布局（服务端无客户端状态）",
            status == 200 and "active_conversation_id" not in state and "tabs" not in state,
            str(payload)[:140],
        )
        # 适配层端点
        status, payload = self.get_json(f"/api/usage-accumulator?conversation_id={cid}")
        self.check(
            "usage-accumulator 用 total_* 字段",
            status == 200 and "total_prompt_tokens" in payload,
            str(payload)[:120],
        )
        # 知识库勾选走**插件自己的端点**，内核不再代持这条通道
        status, payload = self.get_json(
            f"/api/plugin/knowledge/checked?conversation_id={cid}")
        self.check(
            "知识库勾选经插件端点",
            status == 200 and isinstance(payload.get("checked"), list),
            str(payload)[:120],
        )

    def scenario_3(self) -> None:
        print("\n场景③ 写盘门控闭环经 Web 层—— 三步写盘")

        # ── (a) 正常链路：一个回合内走完 预览 → review 解锁 → 提交落盘 ──
        cid = "accept-gate-01"
        self.frames.clear()
        self.app.session_contexts.close_all()
        self.provider.confirm_id = ""
        self.provider.reviewed = False
        self.provider.commit_before_review = False
        self.target.unlink(missing_ok=True)
        self.target.parent.mkdir(parents=True, exist_ok=True)

        self.post("/api/chat/send", {"message": "写文件", "conversation_id": cid})
        self.wait_turn(cid)
        confirm_id = self.confirm_id_of(cid)
        self.check("预览产生 confirm_id（三步链路第一环）", bool(confirm_id), repr(confirm_id))
        names = [f.get("name") for f in self.frames if f.get("type") == "tool_started"]
        self.check(
            "链路顺序为 预览 → review → 提交",
            names[:3] == ["write_file", "review_conclusion", "commit_write"],
            str(names),
        )
        self.check(
            "三步走完后内容已落盘且正确",
            self.target.is_file() and self.target.read_text(encoding="utf-8") == "web-accept-ok",
            f"exists={self.target.exists()}",
        )
        self.check(
            "落盘后门控不再持有该预览快照",
            self.app.gate_for(cid).peek(confirm_id) is None,
        )

        # ── (b) 负例：跳过 review 直接提交 → 门控必须拒绝 ──
        cid2 = "accept-gate-02"
        self.frames.clear()
        self.app.session_contexts.close_all()
        self.provider.confirm_id = ""
        self.provider.reviewed = False
        self.provider.commit_before_review = True
        self.target.unlink(missing_ok=True)

        self.post("/api/chat/send", {"message": "写文件", "conversation_id": cid2})
        self.wait_turn(cid2)
        failed = [f for f in self.frames if f.get("type") == "tool_failed"]
        self.check(
            "跳过 review 的提交被门控拒绝",
            any(f.get("name") == "commit_write" for f in failed),
            str([(f.get("name"), (f.get("error") or "")[:70]) for f in failed]),
        )
        self.check("被拒提交未落盘", not self.target.exists())
        self.provider.commit_before_review = False

        # ── (c) 跨会话隔离：别的会话解锁不了本会话的预览 ──
        status, payload = self.post(
            "/api/chat/user-confirm", {"conversation_id": "other-conv", "confirm_id": confirm_id}
        )
        self.check("跨会话确认同 ID 被拒", status == 404, f"{status} {payload}")

    def scenario_4(self) -> None:
        print("\n场景④ 并发与停止")
        cid = "accept-conc-01"
        self.app.mesh.try_begin_run(cid)
        status, payload = self.post("/api/chat/send", {"message": "再来", "conversation_id": cid})
        self.check("同会话并发 send → 409", status == 409, f"{status} {payload}")
        self.app.mesh.end_run(cid)

        status, payload = self.post("/api/chat/stop", {"conversation_id": cid})
        self.check("stop 返回 stop_requested", status == 200 and "stop_requested" in payload, str(payload))

        started = self.app.runner.start("accept-conc-02", {"content": "跑"})
        requested = self.app.runner.request_cancel("accept-conc-02")
        self.app.runner.wait_idle("accept-conc-02", timeout=25)
        self.check("停止检查可置位并释放占位", bool(started) and requested and not self.app.mesh.is_running("accept-conc-02"))

        status, payload = self.post("/api/chat/send", {"message": "  "})
        self.check("空消息 400", status == 400, str(payload))
        status, payload = self.post(
            "/api/chat/send", {"message": "hi", "conversation_id": "../escape"}
        )
        self.check("非法会话 id 400", status == 400, str(payload))

    # ── 场景 ⑤：Markdown 注入防线（真实页面）─────────────────

    def scenario_5(self) -> None:
        """XSS 向量在**真实页面的真实渲染器**上必须被转义。

        经典 UI 的 `renderMarkdown` 依赖 `renderMarkdownBlocks` / `hljsCodeClass` /
        代码高亮 / diff 卡片等一整套（同一个 168 KB 文件里），无法单独抽出，
        所以向量经浏览器里的真实页面渲染判定。"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("  [SKIP] Markdown 注入防线（未安装 playwright：pip install -e \".[ui]\"）")
            return

        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch()
            except Exception as exc:                      # 浏览器二进制缺失
                print(f"  [SKIP] Markdown 注入防线（Chromium 不可用：{type(exc).__name__}）")
                return
            try:
                page = browser.new_page()
                page.goto(self.base + "/", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1500)
                has = page.evaluate("() => typeof renderMarkdown")
                self.check("真实页面暴露 renderMarkdown", has == "function", f"typeof={has}")
                if has != "function":
                    return

                for label, payload in XSS_VECTORS:
                    # **判据必须看真实 DOM**，不能看 HTML 字符串：
                    # 转义后的 `&lt;img onerror=…&gt;` 里仍然**包含** "onerror=" 这几个字符，
                    # 字符串包含判断会把"正确转义"误判成"存在注入面"。
                    # 正确做法：把渲染结果塞进真实 DOM，再问浏览器
                    # "有没有生成元素 / 有没有真的执行"。
                    probe = page.evaluate(
                        """(p) => {
                          const html = renderMarkdown(p);
                          const host = document.createElement('div');
                          host.innerHTML = html;
                          document.body.appendChild(host);
                          const out = {
                            html: html,
                            // 判据是**可执行面**，不是标签名：
                            // `img` / `video` 是正文刻意支持的（`![alt](path)` 要能显示），
                            // 标记它存在本身不构成注入；能执行的是脚本类元素。
                            elements: host.querySelectorAll('script,iframe,svg,object,embed').length,
                            handlers: host.querySelectorAll('*').length
                              ? [...host.querySelectorAll('*')]
                                  .reduce((n, el) => n + [...el.attributes]
                                    .filter(a => /^on/i.test(a.name)).length, 0)
                              : 0,
                            jsLinks: [...host.querySelectorAll('a,img,video,source')]
                                        .filter(el => /^\\s*(javascript|vbscript|data|file)\\s*:/i
                                          .test(el.getAttribute('href') || el.getAttribute('src') || '')).length,
                          };
                          host.remove();
                          return out;
                        }""",
                        payload,
                    )
                    bad = []
                    if probe["elements"]:
                        bad.append(f"生成了 {probe['elements']} 个危险元素")
                    if probe["handlers"]:
                        bad.append(f"存在 {probe['handlers']} 个事件处理器属性")
                    if probe["jsLinks"]:
                        bad.append(f"存在 {probe['jsLinks']} 个 javascript: 链接")
                    self.check(f"XSS 防线：{label}", not bad,
                               f"{bad}；渲染={probe['html'][:90]!r}")

                # 而且**脚本必须真的没执行**：注入一个会置全局标志的向量
                executed = page.evaluate(
                    """() => {
                      window.__xssProbe = 0;
                      const host = document.createElement('div');
                      host.innerHTML = renderMarkdown(
                        '<img src=x onerror="window.__xssProbe=1">' +
                        '<script>window.__xssProbe=2<\\/script>');
                      document.body.appendChild(host);
                      const v = window.__xssProbe;
                      host.remove();
                      delete window.__xssProbe;
                      return v;
                    }"""
                )
                self.check("XSS 向量未真正执行（无脚本落地）", executed == 0,
                           f"__xssProbe={executed}（非 0 = 有代码被执行）")

                # 正常语法仍要能渲染：防线只转义危险构造，
                # 不能把 Markdown 整体当纯文本
                normal = str(page.evaluate(
                    "() => renderMarkdown('**加粗** 与 `代码`')"))
                self.check("正常 Markdown 仍可渲染",
                           "<strong>" in normal or "<b>" in normal,
                           f"渲染结果={normal[:120]!r}")
            finally:
                browser.close()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="accept-web-") as tmp:
        acc = Acceptance(Path(tmp))
        acc.start()
        try:
            acc.scenario_1()
            acc.scenario_2()
            acc.scenario_3()
            acc.scenario_4()
            acc.scenario_5()
        finally:
            acc.close()
        print()
        if acc.failures:
            print(f"验收未通过：{len(acc.failures)} 项失败")
            for item in acc.failures:
                print(f"  - {item}")
            return 1
        print("Web 壳验收：全部检查项 PASS。")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
