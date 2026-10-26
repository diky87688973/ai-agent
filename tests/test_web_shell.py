# -*- coding: utf-8 -*-
"""Web 壳测试——HTTP/SSE 端点、写盘门控闭环、多会话隔离。

覆盖经 Web 层可验证的条目：端点清单 / SSE 单流多路复用 / 按 cid 分派 /
门控确认按会话解析 / 并发 409 与停止。

运行形态：起真实 HTTP 服务（127.0.0.1，临时端口），用标准库 urllib 打真实请求；
provider 用脚本替身（不触网），故测试离线可跑。
SSE 连接与背压由 `tests/test_web_frontend.py` 的 `Channel` 用例覆盖，
前端渲染边界与注入防线由 `scripts/acceptance_web.py` 的实时场景覆盖。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.model_call import StreamDelta  # noqa: E402
from agent.core.tool_call import ToolCallRequest  # noqa: E402
from agent.mechanisms.live_state import LiveState  # noqa: E402
from agent.mechanisms.session_store import SessionStore  # noqa: E402
from agent.shell.web.server import create_server  # noqa: E402
from tests.testkit import local_auth, no_plugins  # noqa: E402


class ScriptedProvider:
    """脚本 provider 替身：首步预览写盘 → 之后每步尝试凭 id 提交。

    关键：`write_file` 预览在同一步内同步执行完毕（管道），其 tool 结果已进
    `request.messages`（tool 结果按 json.dumps 落进消息），故下一步可安全取回
    confirm_id——与真实模型"上一步看到工具结果、下一步据此行动"一致。

    行为与步号无关，故同一会话连续多次 `runner.start()` 语义稳定（未确认时提交必被门控拒）。
    """

    def __init__(self, target: Path) -> None:
        self.target = target
        self.confirm_id = ""

    @staticmethod
    def _extract_confirm_id(request) -> str:
        import json as _json

        for message in reversed(list(request.messages)):
            if not isinstance(message, dict) or message.get("role") != "tool":
                continue
            content = message.get("content")
            if not isinstance(content, str):
                continue
            try:
                data = _json.loads(content)
            except Exception as exc:
                print(f"[tests.test_web_shell.ScriptedProvider._extract_confirm_id] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                continue
            if not isinstance(data, dict):
                continue
            # 模型侧信封：`{"ok":true,"data":{…confirm_id…}}`；兼容旧裸 data
            inner = data.get("data") if isinstance(data.get("data"), dict) else data
            if isinstance(inner, dict) and inner.get("confirm_id"):
                return str(inner["confirm_id"])
        return ""

    def stream(self, request):
        found = self._extract_confirm_id(request)
        if found:
            self.confirm_id = found
        if not self.confirm_id:
            yield StreamDelta(kind="text", text="先预览：")
            yield StreamDelta(
                kind="tool_call",
                tool_call=ToolCallRequest(
                    call_id="call-preview",
                    name="write_file",
                    arguments={"path": str(self.target), "content": "web-gate-ok"},
                ),
            )
            return
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
    """最小回声 provider（冒烟用；不调用工具）。"""

    def stream(self, request):
        yield StreamDelta(kind="text", text="收到。")

class _ServerFixture(unittest.TestCase):
    """起真实 HTTP 服务 + SSE 收集线程；退出时彻底收摊。"""

    provider_factory = staticmethod(lambda target: EchoProvider())
    # 可见根（fs_root）：默认钉在临时目录，子类可覆盖成别处（如仓库根）
    fs_root_override: "Path | None" = None

    def setUp(self) -> None:
        # 不装插件：本文件钉的是壳层端点与门控，替身 provider 必须真的被调用。
        # 开发者本机的多模型配置会让插件目录接管路由，替身收不到请求（还会真的触网）。
        no_plugins(self)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.target = self.root / "out.txt"
        self.provider = self.provider_factory(self.target)
        # 会话状态显式钉在临时目录：模型 / 模式 / 档位都会落盘，
        # 用缺省数据根会让同一用例第二次运行读到上一次写的值。
        # data_root 也必须显式钉：队列 / 协作网格只认它，而它缺省会回落到
        # `PROJECT_ROOT/data`——只靠 `AI_AGENT_DATA_ROOT` 的话，绕开 ci.py
        # 直跑 unittest 会把队列项攒进工程 data/（历史上就是这么多出 20 多个）。
        self.app = build_app(
            provider=self.provider,
            store=SessionStore(self.root / "data"),
            live_state=LiveState(storage_dir=self.root / "session_state"),
            backup_root=self.root / "bk",
            recycle_root=self.root / "rc",
            data_root=self.root,
        )
        # 端口 0：由系统分配空闲端口，避免测试间抢端口
        # fs_root 显式钉在临时目录：文件查看器的越界判定才可复现（不依赖进程 cwd）
        self.server, self.shell = create_server(
            self.app,
            host="127.0.0.1",
            port=0,
            fs_root=self.fs_root_override or self.root,
            auth=local_auth(self.app),
        )
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        self.addCleanup(self._teardown)
        self.frames: list = []
        self._stop = threading.Event()
        self._reader = threading.Thread(target=self._read_sse, daemon=True)
        self._reader.start()
        self._wait_channels(1)

    def _teardown(self) -> None:
        self._stop.set()
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception as exc:
            print(f"[tests.test_web_shell._ServerFixture._teardown] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        try:
            self.app.dispose()
        except Exception as exc:
            print(f"[tests.test_web_shell._ServerFixture._teardown] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    def _read_sse(self) -> None:
        try:
            # `format=kernel`：取内核原生事件。默认那条流是适配层翻译过的经典 UI 事件
            # （`conversation`/`llm_round`/`tool_start`…），本文件要验的是内核行为，
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
                            except Exception as exc:
                                print(f"[tests.test_web_shell._ServerFixture._read_sse] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        except Exception as exc:
            print(f"[tests.test_web_shell._ServerFixture._read_sse] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    def _wait_channels(self, count: int, timeout: float = 5.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.shell.channel_count >= count:
                return
            time.sleep(0.02)

    # ── HTTP 帮助函数 ────────────────────────────────────

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
        except Exception as exc:
            print(f"[tests.test_web_shell._ServerFixture.get_json] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            return status, {}

    def put_json(self, path: str, payload: dict):
        """PUT JSON 并解析响应（写盘门控的 PUT 端点用）。"""
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            response = urllib.request.urlopen(request, timeout=10)
            status, body = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read()
        try:
            return status, json.loads(body.decode("utf-8"))
        except Exception as exc:
            print(f"[tests.test_web_shell._ServerFixture.put_json] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            return status, {}

    def post(self, path: str, payload: dict):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=10)
            return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw.decode("utf-8"))
            except Exception as exc:
                print(f"[tests.test_web_shell._ServerFixture.post] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                return exc.code, {}

    def wait_turn(self, cid: str, timeout: float = 25.0) -> None:
        self.app.runner.wait_idle(cid, timeout=timeout)
        time.sleep(0.35)  # 让 SSE 帧到达收集线程

    def types_of(self, cid: str = "") -> list:
        return [
            f.get("type")
            for f in self.frames
            if not cid or f.get("conversation_id") == cid
        ]

class EndpointTest(_ServerFixture):
    """端点清单可达性与显著错误码。"""

    def test_pages_and_assets_served(self) -> None:

        # 首页是经典界面单页：素材内联，原件仍按原名躺在 `web_assets/classic/` 下，
        # 可用 `/assets/classic/...` 直接取到。
        for path, needle in (
            ("/", "AI Agent"),                     # 经典 UI 标题
            ("/", "id=\"chatTabs\""),              # 顶部会话标签栏
            ("/", "id=\"usage-bottom\""),          # 用量底栏
            ("/", "global.AIA"),                   # 附件链路（image-lightbox）内联在单页里
            ("/assets/classic/agent-ui.html", "{{CSS}}"),
            ("/assets/classic/css/theme-light.css", 'html[data-ui-theme="light"]'),
            ("/assets/classic/js/core/boot.js", "normalizeConversationId"),
            ("/assets/classic/js/image-lightbox.js", "AIA"),
            ("/assets/classic/js/vendor/highlight.min.js", "hljs"),
            ("/favicon.ico", ""),
        ):
            with self.subTest(path=path):
                status, body = self.get(path)
                self.assertEqual(status, 200, msg=path)
                if needle:
                    self.assertIn(needle, body.decode("utf-8", errors="replace"))

    def test_health_endpoint(self) -> None:

        status, payload = self.get_json("/health")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("service"), "agent.web")
        self.assertGreater(payload.get("tools", 0), 40)

    def test_setup_route_is_removed(self) -> None:
        status, _body = self.get("/setup")
        self.assertEqual(status, 404)

    def test_unknown_path_404(self) -> None:

        status, payload = self.get_json("/api/nope")
        self.assertEqual(status, 404)
        self.assertIn("error", payload)

    def test_send_rejects_bad_input(self) -> None:

        status, payload = self.post("/api/chat/send", {"message": "   "})
        self.assertEqual(status, 400)
        status, payload = self.post(
            "/api/chat/send", {"message": "hi", "conversation_id": "../escape"}
        )
        self.assertEqual(status, 400)
        status, payload = self.post(
            "/api/chat/send", {"message": "hi", "conversation_id": "ok-conv-12345678", "mode": "bogus"}
        )
        self.assertEqual(status, 400)

    def test_media_endpoint_guards_root(self) -> None:

        inside = self.root / "pic.png"
        inside.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.shell.media_root = self.root
        status, body = self.get("/api/media?path=" + urllib.parse.quote(str(inside)))
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"\x89PNG"))
        status, payload = self.get_json(
            "/api/media?path=" + urllib.parse.quote(str(_ROOT / "README.md"))
        )
        self.assertEqual(status, 403)

    def test_media_missing_file_404(self) -> None:

        self.shell.media_root = self.root
        status, payload = self.get_json(
            "/api/media?path=" + urllib.parse.quote(str(self.root / "nope.png"))
        )
        self.assertEqual(status, 404)

class DateGroupTest(unittest.TestCase):
    """会话日期分组。"""

    def test_groups_by_natural_day(self) -> None:

        from agent.shell.timefmt import date_group as date_group

        now = time.time()
        self.assertEqual(date_group(now, now), "今天")
        self.assertEqual(date_group(now - 86400, now), "昨天")
        self.assertEqual(date_group(0, now), "")

    def test_older_is_grouped_by_date(self) -> None:

        from agent.shell.timefmt import date_group as date_group

        now = time.time()
        # 更早的按具体日期分组（「本周」「更早」看不出是哪天）。
        day = time.localtime(now - 3 * 86400)
        self.assertEqual(date_group(now - 3 * 86400, now),
                         f"{day.tm_mon}月{day.tm_mday}日")
        old_day = time.localtime(now - 40 * 86400)
        self.assertEqual(date_group(now - 40 * 86400, now),
                         f"{old_day.tm_mon}月{old_day.tm_mday}日")

class FileViewerContractTest(_ServerFixture):
    """文件读取端点的路径解析与越界边界。"""

    def _write(self, rel: str, text: str = "hello\nworld\n") -> "Path":
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def test_relative_path_reads_text(self) -> None:

        self._write("pkg/core/events.py", "TURN = 'turn'\n")
        status, payload = self.get_json(
            "/api/fs/read?path=" + urllib.parse.quote("pkg/core/events.py")
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["kind"], "text")
        self.assertEqual(payload["lang"], "python")
        self.assertIn("TURN", payload["content"])

    def test_absolute_path_inside_root_is_accepted(self) -> None:
        """工具参数常给绝对路径；落在 fs_root 内必须能直接打开。"""

        target = self._write("pkg/a.md", "# 标题\n")
        status, payload = self.get_json(
            "/api/fs/read?path=" + urllib.parse.quote(str(target))
        )
        self.assertEqual(status, 200, msg=str(payload))
        self.assertIn("标题", payload["content"])

    def test_absolute_path_outside_root_is_forbidden(self) -> None:

        outside = Path(tempfile.gettempdir()).parent / "definitely-not-in-root.txt"
        status, payload = self.get_json(
            "/api/fs/read?path=" + urllib.parse.quote(str(outside))
        )
        self.assertEqual(status, 403)

    def test_traversal_cannot_escape_roots(self) -> None:
        """穿越语义：不允许逃出可见根（不是"禁止 `..`"）。

        多根模型下 `..` 可能仍落在某个根内（例如根是 D:\\ 与 C:\\，`../x` 从
        C:\\Temp\\a 上跳仍在 C:\\）——那是允许的；真正的边界是"出不了根集合"。
        这里用一个不在任何根内的绝对路径来验证边界，并用穿越写法复验。
        """

        outside = Path(tempfile.gettempdir()).parent  # 仍可能在根内
        # 1) 绝对路径：构造一个必然不在任何根内的路径。
        #    Windows 用根集合之外的盘符；POSIX 没有盘符，根就是 `/` 之下，
        #    所以改用一个不存在的顶层目录 —— 两者都是"确定不在可见根内"。
        if os.name == "nt":
            escaped = Path("Z:/definitely-not-a-root/secret.txt")
        else:
            escaped = Path("/definitely-not-a-root/secret.txt")
        status, _ = self.get_json("/api/fs/read?path=" + urllib.parse.quote(str(escaped)))
        self.assertEqual(status, 403)
        # 2) 穿越写法：从根出发反复上跳，终点必须仍被根约束
        deep = self.root / "a" / "b"
        deep.mkdir(parents=True, exist_ok=True)
        status2, _ = self.get_json(
            "/api/fs/read?path=" + urllib.parse.quote(str(deep / ".." / ".." / ".." / ".." / "nope.txt"))
        )
        # 解析后要么落在根内（404 不存在），要么被拒（403）；绝不能读出根外内容
        self.assertIn(status2, (403, 404), msg=str(outside))

    def test_missing_file_inside_root_is_404_not_403(self) -> None:
        """不存在的文件与越界必须分开报告：预览期未落盘的文件是 404，不是越权。"""

        status, payload = self.get_json(
            "/api/fs/read?path=" + urllib.parse.quote(str(self.root / "not-yet.md"))
        )
        self.assertEqual(status, 404, msg=str(payload))

    def test_max_chars_zero_returns_full_file(self) -> None:
        """文件查看器显式传 0：不截断；默认调用仍保留 400000 字符保护。"""
        text = "x" * 500000
        self._write("large.txt", text)
        status, payload = self.get_json(
            "/api/fs/read?path=" + urllib.parse.quote("large.txt")
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["truncated"])
        self.assertEqual(len(payload["content"]), 400000)
        status, payload = self.get_json(
            "/api/fs/read?max_chars=0&path=" + urllib.parse.quote("large.txt")
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["truncated"])
        self.assertEqual(len(payload["content"]), len(text))

    def test_binary_is_reported_not_dumped(self) -> None:

        target = self.root / "blob.bin"
        target.write_bytes(bytes(range(256)) * 4)
        status, payload = self.get_json(
            "/api/fs/read?path=" + urllib.parse.quote("blob.bin")
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["kind"], "binary")
        self.assertNotIn("content", payload)

    def test_list_returns_entries_with_rel_and_type(self) -> None:

        self._write("pkg/a.md")
        self._write("pkg/b.txt")
        status, payload = self.get_json(
            "/api/fs/list?path=" + urllib.parse.quote("pkg")
        )
        self.assertEqual(status, 200, msg=str(payload))
        names = {e["name"]: e for e in payload["entries"]}
        self.assertEqual(set(names), {"a.md", "b.txt"})
        self.assertEqual(names["a.md"]["type"], "file")
        self.assertEqual(names["a.md"]["rel"], str(Path("pkg") / "a.md"))

    def test_list_absolute_path_inside_root(self) -> None:

        self._write("pkg/a.md")
        status, payload = self.get_json(
            "/api/fs/list?path=" + urllib.parse.quote(str(self.root / "pkg"))
        )
        self.assertEqual(status, 200, msg=str(payload))
        self.assertEqual(len(payload["entries"]), 1)

    def test_list_outside_root_is_forbidden(self) -> None:

        status, payload = self.get_json(
            "/api/fs/list?path=" + urllib.parse.quote(str(Path(tempfile.gettempdir()).parent))
        )
        self.assertEqual(status, 403)

class MultiRootFileViewerTest(unittest.TestCase):
    """多可见根——agent 能写多盘，查看器必须看得见它们写的文件。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        # 两个互不相属的根（模拟 D:\ 与 E:\）
        self.root_a = base / "driveA"
        self.root_b = base / "driveB"
        self.root_a.mkdir(parents=True)
        self.root_b.mkdir(parents=True)
        (self.root_a / "only-a.md").write_text("A 盘的文件\n", encoding="utf-8")
        (self.root_b / "only-b.txt").write_text("B 盘的文件\n", encoding="utf-8")
        self.app = build_app(
            provider=EchoProvider(),
            store=SessionStore(base / "data"),
            live_state=LiveState(storage_dir=base / "session_state"),
            backup_root=base / "bk",
            recycle_root=base / "rc",
            data_root=base,
        )
        self.server, self.shell = create_server(
            self.app, host="127.0.0.1", port=0, fs_root=[self.root_a, self.root_b],
            auth=local_auth(self.app),
        )
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self._teardown)

    def _teardown(self) -> None:
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception as exc:
            print(f"[tests.test_web_shell.MultiRootFileViewerTest._teardown] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        try:
            self.app.dispose()
        except Exception as exc:
            print(f"[tests.test_web_shell.MultiRootFileViewerTest._teardown] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    def _get(self, path: str):
        try:
            with urllib.request.urlopen(self.base + path, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            body = exc.read()
            return exc.code, (json.loads(body) if body else {})

    def test_absolute_path_in_first_root(self) -> None:

        status, payload = self._get(
            "/api/fs/read?path=" + urllib.parse.quote(str(self.root_a / "only-a.md")))
        self.assertEqual(status, 200, msg=str(payload))
        self.assertIn("A 盘", payload["content"])

    def test_absolute_path_in_second_root(self) -> None:
        """第二个根同样可达——单根实现会把它判成越界。"""

        status, payload = self._get(
            "/api/fs/read?path=" + urllib.parse.quote(str(self.root_b / "only-b.txt")))
        self.assertEqual(status, 200, msg=str(payload))
        self.assertIn("B 盘", payload["content"])

    def test_relative_path_resolves_against_each_root(self) -> None:
        """相对路径逐个根试：命中哪个根就用哪个。"""

        status_a, payload_a = self._get("/api/fs/read?path=only-a.md")
        self.assertEqual(status_a, 200, msg=str(payload_a))
        status_b, payload_b = self._get("/api/fs/read?path=only-b.txt")
        self.assertEqual(status_b, 200, msg=str(payload_b))

    def test_outside_all_roots_is_forbidden(self) -> None:

        status, _ = self._get(
            "/api/fs/read?path=" + urllib.parse.quote(str(Path(tempfile.gettempdir()) / "any.txt")))
        self.assertEqual(status, 403)

    def test_missing_in_a_root_is_404_not_403(self) -> None:

        status, _ = self._get(
            "/api/fs/read?path=" + urllib.parse.quote(str(self.root_a / "nope.md")))
        self.assertEqual(status, 404)

    def test_list_reports_rel_against_matched_root(self) -> None:

        status, payload = self._get(
            "/api/fs/list?path=" + urllib.parse.quote(str(self.root_b)))
        self.assertEqual(status, 200, msg=str(payload))
        names = {e["name"]: e for e in payload["entries"]}
        self.assertIn("only-b.txt", names)
        self.assertEqual(names["only-b.txt"]["rel"], "only-b.txt")

    def test_roots_are_resolved_and_deduplicated_by_normalize(self) -> None:

        from agent.shell.fspaths import normalize_roots

        self.assertEqual(normalize_roots(None), [])
        self.assertEqual(normalize_roots(self.root_a), [self.root_a.resolve()])
        self.assertEqual(
            normalize_roots([self.root_a, str(self.root_b)]),
            [self.root_a.resolve(), self.root_b.resolve()],
        )

class SseContractTest(_ServerFixture):
    """ / ：单流多路复用与事件信封。"""

    def test_turn_events_reach_the_stream(self) -> None:

        cid = "sse-contract-01"
        status, payload = self.post(
            "/api/chat/send", {"message": "你好", "conversation_id": cid}
        )
        self.assertEqual(status, 200, msg=str(payload))
        self.assertTrue(payload.get("run_id"))
        self.wait_turn(cid)

        types = self.types_of(cid)
        for expected in (
            # 内核原生词汇：
            # step_started/step_ended → llm_started/llm_ended
            "turn_started",
            "input_claimed",
            "llm_started",
            "assistant_delta",
            "model_message",
            "llm_ended",
            "turn_ended",
        ):
            self.assertIn(expected, types, msg=f"{expected} 未出现在事件流：{types}")
        # 事件信封：type + data
        first = [f for f in self.frames if f.get("conversation_id") == cid][0]
        self.assertIsInstance(first.get("type"), str)
        self.assertIn("conversation_id", first)

    def test_every_frame_carries_conversation_id(self) -> None:

        cid = "sse-cid-01"
        self.post("/api/chat/send", {"message": "你好", "conversation_id": cid})
        self.wait_turn(cid)
        frames = [f for f in self.frames if f.get("type")]
        self.assertTrue(frames)
        missing = [f.get("type") for f in frames if not f.get("conversation_id")]
        self.assertEqual(missing, [], msg=f"缺 cid 的帧：{missing}")

    def test_two_sessions_do_not_cross(self) -> None:

        self.post("/api/chat/send", {"message": "a", "conversation_id": "sse-a-00000001"})
        self.wait_turn("sse-a-00000001")
        self.post("/api/chat/send", {"message": "b", "conversation_id": "sse-b-00000002"})
        self.wait_turn("sse-b-00000002")
        self.assertTrue(self.types_of("sse-a-00000001"))
        self.assertTrue(self.types_of("sse-b-00000002"))
        # 同一事件流承载两会话，但事件各归其 cid
        self.assertEqual(set(self.types_of("sse-a-00000001")) & {"turn_started"}, {"turn_started"})

    def test_history_and_sessions_endpoints(self) -> None:

        cid = "sse-hist-01"
        self.post("/api/chat/send", {"message": "留个记录", "conversation_id": cid})
        self.wait_turn(cid)
        status, payload = self.get_json(f"/api/chat/history?conversation_id={cid}")
        self.assertEqual(status, 200)
        # 回显只给 items / context_layout / todo_list；逐条老事件归 SSE 流。
        self.assertGreater(len(payload.get("items", [])), 0)
        self.assertNotIn("events", payload)
        status, payload = self.get_json("/api/chat/sessions")
        self.assertEqual(status, 200)
        # `sessions` 是字典列表（`id`/`title`/`date_group`）：经典 UI 读 `s.id`
        # 而不是 `conversation_id`；纯 cid 列表另给 `conversation_ids`，方便非 UI 消费者。
        ids = [row.get("id") for row in payload.get("sessions", [])]
        self.assertIn(cid, ids)
        self.assertIn(cid, payload.get("conversation_ids", []))

    def test_sessions_carry_derived_title_not_raw_id(self) -> None:
        """会话名录须带派生标题（首条用户输入），否则侧栏只能显示裸 UUID。"""

        cid = "sse-title-0001"
        text = "帮我检查一下当前目录并输出路径"
        self.post("/api/chat/send", {"message": text, "conversation_id": cid})
        self.wait_turn(cid)
        status, payload = self.get_json("/api/chat/sessions")
        self.assertEqual(status, 200)
        items = {i["conversation_id"]: i for i in payload.get("items", [])}
        self.assertIn(cid, items, msg=str(payload.get("items")))
        item = items[cid]
        self.assertEqual(item["title"], text)
        self.assertEqual(item["short_id"], cid[:8])
        self.assertGreater(item["mtime"], 0)

    def test_derived_title_truncates_and_flattens(self) -> None:

        cid = "sse-title-0002"
        long_text = "第一行\n第二行 " + "很长" * 40
        self.post("/api/chat/send", {"message": long_text, "conversation_id": cid})
        self.wait_turn(cid)
        status, payload = self.get_json("/api/chat/sessions")
        item = {i["conversation_id"]: i for i in payload["items"]}[cid]
        self.assertLessEqual(len(item["title"]), 41, msg=item["title"])
        self.assertNotIn("\n", item["title"])
        self.assertTrue(item["title"].endswith("…"))

    def test_sessions_sorted_by_recent_activity(self) -> None:

        self.post("/api/chat/send", {"message": "早的", "conversation_id": "sse-order-000a"})
        self.wait_turn("sse-order-000a")
        time.sleep(0.05)
        self.post("/api/chat/send", {"message": "晚的", "conversation_id": "sse-order-000b"})
        self.wait_turn("sse-order-000b")
        status, payload = self.get_json("/api/chat/sessions")
        order = [i["conversation_id"] for i in payload["items"]]
        self.assertLess(order.index("sse-order-000b"), order.index("sse-order-000a"))

    def test_sessions_carry_date_group(self) -> None:
        """会话名录须带 date_group（会话菜单按它插分组标题）。"""

        self.post("/api/chat/send", {"message": "分组用", "conversation_id": "sse-group-0001"})
        self.wait_turn("sse-group-0001")
        status, payload = self.get_json("/api/chat/sessions")
        item = {i["conversation_id"]: i for i in payload["items"]}["sse-group-0001"]
        self.assertEqual(item["date_group"], "今天", msg=str(item))

    def test_health_reports_model_for_header(self) -> None:
        """`/health` 须给出 model / allowed_models / 全局默认档位（顶栏与模型菜单）。"""

        status, payload = self.get_json("/health")
        self.assertEqual(status, 200)
        self.assertIn("model", payload)
        self.assertIn("allowed_models", payload)
        self.assertIsInstance(payload["allowed_models"], list)
        # 全局默认档位：会话状态回来之前，顶栏的「思考 · X」先按它显示。
        self.assertIn(payload["reasoning_effort"], ("high", "max"))

    def test_reasoning_effort_roundtrip(self) -> None:
        """推理档位 GET/PUT 往返。"""

        cid = "effort-roundtrip-01"
        status, payload = self.get_json(f"/api/reasoning-effort?conversation_id={cid}")
        self.assertEqual(status, 200)
        self.assertIn("global_default", payload)
        # 全局默认由配置决定（`[agent] reasoning_effort`），所以这里断言"两者一致"
        # 而不是写死某个档位 —— 写死会在改默认值时变成假失败。
        self.assertEqual(payload["reasoning_effort"], payload["global_default"])
        self.assertIn(payload["reasoning_effort"], ("high", "max"))

        status, payload = self.put_json("/api/reasoning-effort", {"conversation_id": cid, "effort": "max"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["reasoning_effort"], "max")

        status, payload = self.get_json(f"/api/reasoning-effort?conversation_id={cid}")
        self.assertEqual(payload["reasoning_effort"], "max")

        # 会话级覆盖之后，换一个会话仍应回到全局默认
        status, payload = self.get_json("/api/reasoning-effort?conversation_id=effort-other-02")
        self.assertEqual(payload["reasoning_effort"], payload["global_default"])

    def test_reasoning_effort_rejects_invalid(self) -> None:
        """非法档位拒设且保留原值；缺 cid 报错。"""

        cid = "effort-invalid-01"
        self.put_json("/api/reasoning-effort", {"conversation_id": cid, "effort": "max"})
        status, payload = self.put_json(
            "/api/reasoning-effort", {"conversation_id": cid, "effort": "ultra"})
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["reasoning_effort"], "max", msg="非法值不得改状态")

        status, payload = self.put_json("/api/reasoning-effort", {"effort": "max"})
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "conversation_id required")

    def test_reasoning_effort_is_per_conversation(self) -> None:
        """会话级档位不串会话：改一个不影响另一个（另一个回全局默认）。"""

        self.put_json(
            "/api/reasoning-effort", {"conversation_id": "effort-a", "effort": "max"})
        _, payload = self.get_json("/api/reasoning-effort?conversation_id=effort-b")
        self.assertEqual(
            payload["reasoning_effort"], payload["global_default"],
            msg="不得串到别的会话")
        self.assertIn(payload["reasoning_effort"], ("high", "max"))

    def test_dir_browse_drives_layer(self) -> None:
        """`path=_drives_` 返回「计算机」层。"""

        status, payload = self.get_json("/api/dir-browse?path=_drives_")
        self.assertEqual(status, 200)
        self.assertEqual(payload["current"], "计算机")
        self.assertEqual(payload["parent"], "")
        self.assertIsInstance(payload["items"], list)

    def test_dir_browse_root_parent_is_drives(self) -> None:
        """盘符根的 parent 是 `_drives_`，可从盘根回到计算机层。"""

        status, payload = self.get_json("/api/dir-browse?path=_drives_")
        items = payload["items"]
        if not items:
            self.skipTest("本机无可用盘符")
        drive_root = items[0]["path"]
        _, root = self.get_json(f"/api/dir-browse?path={drive_root}")
        self.assertEqual(root["parent"], "_drives_", msg=f"{drive_root} 的上一级应为计算机层")

    def test_dir_browse_item_shape_and_ordering(self) -> None:
        """条目形状 {name,type,ext,path}；目录排前。"""

        repo = str(_ROOT).replace("\\", "/")
        status, payload = self.get_json(f"/api/dir-browse?path={repo}")
        self.assertEqual(status, 200)
        self.assertTrue(payload["items"], msg="仓库根不应为空")
        first = payload["items"][0]
        for key in ("name", "type", "ext", "path"):
            self.assertIn(key, first)
        self.assertIn(first["type"], ("dir", "file"))
        # 目录必须全部排在文件之前
        types = [item["type"] for item in payload["items"]]
        if "file" in types and "dir" in types:
            self.assertLess(types.index("dir"), types.index("file"))

    def test_dir_browse_missing_path_falls_back(self) -> None:
        """访问不到的路径回落（不报错）——补全不能因为一个坏路径卡死。"""

        status, payload = self.get_json("/api/dir-browse?path=Z:/definitely-not-here")
        self.assertEqual(status, 200)
        self.assertTrue(payload["current"])
        self.assertIsInstance(payload["items"], list)

    def test_dir_browse_relative_path_uses_workspace_base(self) -> None:
        """相对路径应基于可见根解析，且不得落到盘根。"""

        _, payload = self.get_json("/api/dir-browse?path=agent/core")
        current = payload["current"]
        self.assertTrue(current.startswith(self.root.as_posix()),
                        msg=f"相对路径应落在夹具根内：{current}")
        self.assertFalse(is_drive_root_text(current),
                         msg=f"相对路径被钉在盘根上了：{current}")

def is_drive_root_text(path_text: str) -> bool:
    """路径文本是否盘符根（如 `C:/`）——这种根太宽，不适合作相对路径基准。"""
    text = str(path_text or "").replace("\\", "/").rstrip("/")
    return len(text) == 2 and text[1] == ":"

class DirBrowseDriveRootTest(_ServerFixture):
    """可见根是盘根时（默认情形），相对路径不能被钉死在盘根。

    可见根取「本机各盘根」时，`agent/core` 会解析成 `C:/` —— 相对路径因此被钉在盘根上。

    「计算机」层是盘符模型的产物：只有 Windows 有盘符，POSIX 的根是 `/`，它的上一级
    不是任何虚拟层。所以整类只在 Windows 上跑；与平台无关的那条用例在
    `DirBrowseQueryTest`。
    """

    fs_root_override = Path("C:/") if os.name == "nt" else Path("/")

    @classmethod
    def setUpClass(cls) -> None:
        if os.name != "nt":
            raise unittest.SkipTest("盘符模型只在 Windows 上成立")

    def test_relative_path_prefers_concrete_workspace_root(self) -> None:

        root = str(self.fs_root_override)
        if not Path(root).is_dir():
            self.skipTest("本机无 C: 盘")
        _, payload = self.get_json("/api/dir-browse?path=agent/core")
        self.assertNotEqual(payload["current"].rstrip("/"), root.rstrip("/"),
                            msg="相对路径被钉在盘根上了")

    def test_drive_root_parent_is_drives_layer(self) -> None:

        root = str(self.fs_root_override).replace("\\", "/")
        if not Path(self.fs_root_override).is_dir():
            self.skipTest("本机无 C: 盘")
        _, payload = self.get_json(f"/api/dir-browse?path={root}")
        self.assertEqual(payload["parent"], "_drives_")


class DirBrowseQueryTest(_ServerFixture):
    """路径查询串按整串解析，不按首字符。"""

    def test_dir_browse_single_char_path_not_truncated(self) -> None:
        """`_query()` 必须返回整串：路由若用 `[0]` 取首字符，值会被截断。"""

        _, payload = self.get_json("/api/dir-browse?path=_drives_")
        self.assertNotEqual(payload["current"], "C:/",
                            msg="path 被截断成 '_' 时会回落到盘根")

    def test_ui_state_roundtrip(self) -> None:

        cid = "sse-ui-01"
        status, payload = self.post(
            "/api/chat/send", {"message": "x", "conversation_id": cid, "mode": "plan"}
        )
        self.assertEqual(status, 200)
        self.wait_turn(cid)
        status, payload = self.get_json(f"/api/chat/ui-state?conversation_id={cid}")
        self.assertEqual(status, 200)
        self.assertEqual(payload.get("mode"), "plan")

class ConcurrencyTest(_ServerFixture):
    """同会话并发发送进入待发送队列；停止请求可下发。"""

    def test_concurrent_send_queues(self) -> None:

        cid = "conc-00000001"
        self.app.mesh.try_begin_run(cid)  # 占住会话
        try:
            status, payload = self.post(
                "/api/chat/send", {"message": "再来", "conversation_id": cid}
            )
            self.assertEqual(status, 200, msg=str(payload))
            self.assertTrue(payload.get("queued"))
            self.assertEqual(payload["queue_item"]["content"], "再来")
            self.assertEqual(self.app.mesh.queue_size(cid), 1)
            item_id = payload["queue_item"]["id"]
            _, queue = self.get_json(f"/api/chat/queue?conversation_id={cid}")
            self.assertEqual(queue["items"][0]["id"], item_id)
            status, inserted = self.post(
                f"/api/chat/queue/{item_id}/insert",
                {"conversation_id": cid},
            )
            self.assertEqual(status, 200, msg=str(inserted))
            self.assertEqual(inserted["item"]["state"], "inserting")
            status, recalled = self.post(
                f"/api/chat/queue/{item_id}/recall",
                {"conversation_id": cid},
            )
            self.assertEqual(status, 200, msg=str(recalled))
            self.assertEqual(recalled["item"]["content"], "再来")
            self.assertEqual(self.app.mesh.queue_size(cid), 0)
        finally:
            self.app.mesh.end_run(cid)

    def test_stop_endpoint_shape(self) -> None:

        status, payload = self.post("/api/chat/stop", {"conversation_id": "conc-00000002"})
        self.assertEqual(status, 200)
        self.assertIn("stop_requested", payload)
        status, payload = self.post("/api/chat/stop", {})
        self.assertEqual(status, 400)

    def test_stop_cancels_a_running_turn(self) -> None:
        """停止是真取消：经 SessionRunner 的停止检查，让内核在检查点停下。"""

        cid = "conc-cancel-0001"
        started = self.app.runner.start(cid, {"content": "跑"})
        self.assertTrue(started)
        requested = self.app.runner.request_cancel(cid)
        self.assertTrue(requested)
        self.app.runner.wait_idle(cid, timeout=25)
        # 取消后占位被释放、会话可再次提交
        self.assertFalse(self.app.mesh.is_running(cid))
        self.assertFalse(self.app.runner.request_cancel(cid))

def _pending_confirm_ids(gate) -> list:
    """从门控里取未提交的预览快照 id。

    预览结果不回传 `confirm_id`；写盘走三步
    （`write_file` 预览 → `review_conclusion` 审阅并解锁 → `commit_write` 落盘），
    它由门控持有，解锁后再用同一个 id 提交，所以测试直接问门控要。
    """
    pending = getattr(gate, "_pending", None)
    return list(pending.keys()) if isinstance(pending, dict) else []

class WriteGateOverWebTest(_ServerFixture):
    """写盘门控闭环经 Web 层 —— 三步写盘（预览 → review 解锁 → 提交落盘）。"""

    provider_factory = staticmethod(lambda target: ScriptedProvider(target))

    def _gate(self):
        """本会话的门控（预览快照 / 待 review 都在它手里）。"""
        cid = "gate-web-01"
        return self.app.gate_for(cid) if hasattr(self.app, "gate_for") else self.app.gate

    def test_unconfirmed_commit_rejected_then_review_unlocks(self) -> None:

        cid = "gate-web-01"
        status, _ = self.post("/api/chat/send", {"message": "写文件", "conversation_id": cid})
        self.assertEqual(status, 200)
        self.wait_turn(cid)
        self.assertFalse(self.target.exists(), msg="预览阶段不应落盘")

        gate = self.app.gate_for(cid)
        ids = _pending_confirm_ids(gate)
        self.assertTrue(ids, msg="门控里应有未提交的预览快照")
        confirm_id = str(ids[-1])

        # 未 review 直接提交 → 门控拒绝，且不落盘
        self.app.runner.start(cid, {"content": "提交"})
        self.wait_turn(cid)
        rejected = [f for f in self.frames
                    if f.get("type") == "tool_failed" and f.get("name") == "commit_write"]
        self.assertTrue(rejected, msg="未 review 的提交应被门控拒绝")
        self.assertIn("未解锁", str(rejected[-1].get("error") or ""))
        self.assertFalse(self.target.exists(), msg="被拒的提交不得落盘")

        # 经 review_conclusion 解锁（三步链路的第二步；须走 ToolPort / 会话桶）
        unlocked = self.app.execute_tool(
            "review_conclusion",
            {
                "conclusion": "review结论：本次预览为新建 out.txt，内容与预期一致，"
                              "路径在临时目录内、无覆盖风险，验证通过。",
                "file_name": "out.txt",
                "confirm_id": confirm_id,
            },
            conversation_id=cid,
        )
        self.assertTrue(unlocked.ok, msg=str(unlocked.error))
        self.assertTrue(gate.peek(confirm_id).get("confirmed"), msg="review 后预览应已解锁")

    def test_confirm_is_session_scoped(self) -> None:

        cid = "gate-web-scope"
        self.post("/api/chat/send", {"message": "写文件", "conversation_id": cid})
        self.wait_turn(cid)
        ids = _pending_confirm_ids(self.app.gate_for(cid))
        self.assertTrue(ids, msg="门控里应有未提交的预览快照")
        confirm_id = str(ids[-1])

        # 别的会话的门控不能解锁它（会话隔离）
        other = self.app.gate_for("some-other-conv")
        self.assertFalse(other.confirm(confirm_id), msg="跨会话不得解锁预览快照")

