# -*- coding: utf-8 -*-
"""验收：调查与工具 12 件（find_in_file / regex_locate / file_search / text_diff /
data_table / env_probe / unified_diagnose / git_workspace / web_fetch / web_fetch_render /
image_ocr / archive）headless 演示。

场景：① 门控闭环——archive 走完整 id 制四步（预览 → 确认 → 凭 confirm_id 提交 → 落盘复核），
含一次性消费、伪 ID 拒绝、未确认拒绝、list 只读不登记快照、跨文件 review 门控；
② 工具族管道冒烟——12 件经 ToolPipeline 唯一入口，含结构化错误信封（git 非仓库 /
OCR 缺依赖 / web 验收失败）；缺可选依赖的环境分支自动改判提示；
③ 注册与名单一致性——12 件工具注册、catalog 成员与总数、门控预览名单。
运行：python scripts/acceptance_batch_e.py（全部通过退出码 0）
"""
from __future__ import annotations

import http.server
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.tool_call import ToolResult  # noqa: E402
from agent.mechanisms.live_state import LiveState  # noqa: E402
from agent.mechanisms.mesh import MeshState  # noqa: E402

CID_DRIVER = "accept-batch-e"

BATCH_E_TOOLS = [
    "find_in_file",
    "regex_locate",
    "file_search",
    "text_diff",
    "data_table",
    "env_probe",
    "unified_diagnose",
    "git_workspace",
    "web_fetch",
    "web_fetch_render",
    "image_ocr",
    "archive",
]


def _available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


class _HtmlHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # HTTP 动词命名（stdlib 约定）
        body = (
            b"<html><head><title>Batch E Page</title></head>"
            b"<body><p>batch e content marker</p></body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


class Acceptance:
    """headless 验收运行器：经管道唯一入口驱动，逐项打印 PASS/FAIL。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.app = build_app(
            backup_root=root / "backups",
            recycle_root=root / "recycle",
            live_state=LiveState(storage_dir=root / "todo"),
            mesh=MeshState(storage_dir=root / "mesh"),
        )
        self.seq = 0
        self.failures: list = []
        self.srv = None
        self.url = ""

    def start_server(self) -> None:
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _HtmlHandler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/"

    def stop_server(self) -> None:
        if self.srv is not None:
            self.srv.shutdown()

    def call(self, name: str, arguments: dict = None, cid: str = CID_DRIVER) -> ToolResult:
        self.seq += 1
        return self.app.execute_tool(
            name, arguments or {}, conversation_id=cid, call_id=f"c{self.seq}"
        )

    @property
    def gate(self):
        """驱动会话的门控（写盘门控每会话独占；脚本以 CID_DRIVER 驱动全链路）。"""
        return self.app.gate_for(CID_DRIVER)

    def check(self, label: str, cond: bool, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        line = f"  [{status}] {label}"
        if detail and not cond:
            line += f" — {detail}"
        print(line)
        if not cond:
            self.failures.append(label)

    # ── 场景 ① 门控闭环（archive id 制四步）────────────

    def _scenario1_preview(self, src: Path, zip_path: Path) -> str:
        r1 = self.call("archive", {"action": "create", "source": str(src),
                                   "dest": str(zip_path)})
        cid = str((r1.data or {}).get("confirm_id") or "") if r1.ok else ""
        self.check("预览：返回 confirm_id 且不落盘",
                   bool(r1.ok and cid and not zip_path.exists()), str(r1.data))
        return cid

    def _scenario1_commit(self, cid: str, zip_path: Path) -> None:
        bad = self.call("commit_write", {"confirm_id": "nonexistent-id"})
        self.check("提交：伪 ID 拒绝", (not bad.ok) and "无效" in (bad.error or ""),
                   str(bad.error))
        pending = self.call("commit_write", {"confirm_id": cid})
        self.check(
            "提交：未确认先拒（四步第二步强制）",
            (not pending.ok) and "未解锁" in (pending.error or "")
            and "review_conclusion" in (pending.error or ""), str(pending.error))
        self.check("确认：通过门控确认", self.gate.confirm(cid) is True, "confirm")
        done = self.call("commit_write", {"confirm_id": cid})
        self.check(
            "提交：分派 archive 执行并真实落盘",
            done.ok and bool((done.data or {}).get("written")) and zip_path.exists(),
            str(done.data))
        self.check(
            "提交：host_quality 报告随结果回灌",
            done.ok and isinstance((done.data or {}).get("host_quality"), dict),
            str((done.data or {}).get("host_quality")))
        replay = self.call("commit_write", {"confirm_id": cid})
        self.check("提交：一次性消费（重放拒绝）",
                   (not replay.ok) and "无效或已使用" in (replay.error or ""),
                   str(replay.error))
        listed = self.call("archive", {"action": "list", "source": str(zip_path)})
        self.check(
            "list 只读：不登记快照（无 confirm_id）",
            listed.ok and (listed.data or {}).get("needs_commit") is False
            and "confirm_id" not in (listed.data or {}), str(listed.data))
        self.check("list 结果：成员数 2",
                   listed.ok and (listed.data or {}).get("count") == 2, str(listed.data))

    def _scenario1_extract(self, zip_path: Path) -> None:
        dest = self.root / "unpack"
        preview = self.call("archive", {"action": "extract", "source": str(zip_path),
                                        "dest": str(dest)})
        self.check("extract 预览：不落盘",
                   preview.ok and (preview.data or {}).get("confirm_id")
                   and not dest.exists(), str(preview.data))
        cid = str((preview.data or {}).get("confirm_id") or "")
        self.gate.confirm(cid)
        blocked = self.call("commit_write", {"confirm_id": cid})
        self.check("跨文件：写后未 review 先拒",
                   (not blocked.ok) and "review" in (blocked.error or ""),
                   str(blocked.error))
        self.gate.review_done()
        done = self.call("commit_write", {"confirm_id": cid})
        target = dest / "pack" / "a.txt"
        self.check(
            "extract 提交：review 后放行且解压落盘",
            done.ok and target.is_file()
            and target.read_text(encoding="utf-8") == "A", str(done.data))

    def scenario_1(self) -> None:
        print("\n场景① 门控闭环（archive：预览 → 确认 → 凭 ID 提交 → 重读）")
        src = self.root / "pack"
        src.mkdir()
        (src / "a.txt").write_text("A", encoding="utf-8")
        (src / "b.txt").write_text("B", encoding="utf-8")
        zip_path = self.root / "out.zip"
        cid = self._scenario1_preview(src, zip_path)
        self._scenario1_commit(cid, zip_path)
        self._scenario1_extract(zip_path)

    def _scenario2_text(self, note: Path) -> None:
        r = self.call("find_in_file", {"path": str(note), "pattern": "beta|gamma"})
        self.check("find_in_file：字面 | OR 命中 2 处",
                   r.ok and (r.data or {}).get("total_matches") == 2, str(r.data))
        r = self.call("regex_locate", {"path": str(note), "pattern": "alpha"})
        self.check("regex_locate：正则命中 2 处",
                   r.ok and (r.data or {}).get("count") == 2, str(r.data))
        r = self.call("file_search", {"path": str(self.root), "pattern": "gamma",
                                      "glob_pattern": "*.txt"})
        self.check("file_search：目录搜索命中",
                   r.ok and (r.data or {}).get("total_matches", 0) >= 1, str(r.data))
        r = self.call("text_diff", {"left_text": "a\nb\n", "right_text": "a\nB\n"})
        self.check("text_diff：差异计数",
                   r.ok and (r.data or {}).get("summary", {}).get("same") is False,
                   str(r.data))

    def _scenario2_data(self, csv: Path) -> None:
        r = self.call("data_table", {"action": "preview", "path": str(csv)})
        self.check("data_table：预览列与行数",
                   r.ok and (r.data or {}).get("total_rows") == 2
                   and (r.data or {}).get("columns") == ["name", "score"], str(r.data))
        r = self.call("env_probe", {})
        self.check("env_probe：可用环境列表非空",
                   r.ok and bool((r.data or {}).get("available"))
                   and isinstance((r.data or {}).get("available"), list), str(r.data))

    def _scenario2_diagnose(self) -> None:
        good = self.root / "good"
        good.mkdir(exist_ok=True)
        (good / "ok.py").write_text("x = 1\n", encoding="utf-8")
        r = self.call("unified_diagnose", {"path": str(good), "no_ruff": True})
        self.check("unified_diagnose：好目录绿灯",
                   r.ok and (r.data or {}).get("summary", {}).get("errors") == 0,
                   str(r.data))
        bad = self.root / "bad"
        bad.mkdir(exist_ok=True)
        (bad / "broken.py").write_text("def f(:\n    pass\n", encoding="utf-8")
        r = self.call("unified_diagnose", {"path": str(bad), "no_ruff": True})
        self.check("unified_diagnose：坏语法红灯 + 诊断随 data",
                   (not r.ok) and isinstance(r.data, dict)
                   and (r.data or {}).get("summary", {}).get("errors", 0) >= 1,
                   str(r.data))

    def _scenario2_git(self) -> None:
        norepo = self.root / "norepo"
        norepo.mkdir(exist_ok=True)
        r = self.call("git_workspace", {"path": str(norepo)})
        self.check("git_workspace：非仓库结构化错误（E_GIT_WORKSPACE）",
                   (not r.ok) and (r.data or {}).get("code") == "E_GIT_WORKSPACE",
                   str(r.data))
        if not shutil.which("git"):
            self.check("git_workspace：log 模式（环境无 git，跳过）", True)
            return
        repo = self.root / "repo"
        repo.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
        (repo / "a.txt").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit",
             "-q", "-m", "init"], cwd=repo, check=True, capture_output=True)
        r = self.call("git_workspace", {"path": str(repo), "mode": "log"})
        self.check("git_workspace：log 模式（真实仓库）",
                   r.ok and len((r.data or {}).get("entries", [])) == 1, str(r.data))

    def _scenario2_web(self) -> None:
        r = self.call("web_fetch", {"url": self.url})
        self.check("web_fetch：本地假站抓取与正文提取",
                   r.ok and "batch e content marker" in (r.data or {}).get("text", ""),
                   str(r.data)[:200])
        r = self.call("web_fetch", {"url": self.url, "min_chars": 100000})
        self.check("web_fetch：验收失败信封（E_ACCEPTANCE + data 保留）",
                   (not r.ok) and (r.data or {}).get("code") == "E_ACCEPTANCE",
                   str(r.data)[:200])
        if _available("playwright"):
            self.check("web_fetch_render：环境已装 playwright（跳过缺依赖分支）", True)
        else:
            r = self.call("web_fetch_render", {"url": self.url})
            self.check("web_fetch_render：缺依赖安装提示",
                       (not r.ok) and "playwright" in (r.error or ""), str(r.error))

    def _scenario2_ocr(self) -> None:
        img = self.root / "img.png"
        img.write_bytes(b"\x89PNG dummy")
        if _available("pytesseract") or _available("easyocr"):
            self.check("image_ocr：环境已装引擎（跳过缺依赖分支）", True)
        else:
            r = self.call("image_ocr", {"path": str(img)})
            self.check("image_ocr：MissingDependency 结构化信封",
                       (not r.ok) and (r.data or {}).get("type") == "MissingDependency",
                       str(r.data))

    def scenario_2(self) -> None:
        print("\n场景② 工具族管道冒烟（12 件经唯一入口）")
        note = self.root / "note.txt"
        note.write_text("alpha beta\ngamma alpha\n", encoding="utf-8")
        self._scenario2_text(note)
        csv = self.root / "t.csv"
        csv.write_text("name,score\nAlice,90\nbob,70\n", encoding="utf-8")
        self._scenario2_data(csv)
        self._scenario2_diagnose()
        self._scenario2_git()
        self._scenario2_web()
        self._scenario2_ocr()

    def scenario_3(self) -> None:
        print("\n场景③ 注册与名单一致性")
        missing = [n for n in BATCH_E_TOOLS if self.app.registry.get(n) is None]
        self.check("12 件工具均已注册", not missing, str(missing))

        catalog = json.loads((ROOT / "catalog" / "tools.json").read_text(encoding="utf-8"))
        tool_names = [str(t.get("name")) for t in catalog.get("tools", [])]
        not_in_catalog = [n for n in BATCH_E_TOOLS if n not in tool_names]
        self.check("catalog 成员含 12 件工具", not not_in_catalog, str(not_in_catalog))
        self.check("catalog 工具总数 ≥ 36", len(tool_names) >= 36, str(len(tool_names)))
        archive = self.app.registry.get("archive")
        self.check(
            "archive 声明 write_path_keys=dest→source",
            archive is not None
            and tuple(getattr(archive, "write_path_keys", ()) or ())
            == ("dest", "source"),
            str(getattr(archive, "write_path_keys", None)),
        )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        acc = Acceptance(Path(tmp))
        acc.start_server()
        try:
            acc.scenario_1()
            acc.scenario_2()
            acc.scenario_3()
        finally:
            acc.stop_server()
        print()
        if acc.failures:
            print(f"验收失败：{len(acc.failures)} 项未通过")
            for item in acc.failures:
                print(f"  - {item}")
            return 1
        print("验收通过：全部检查项 PASS。")
        return 0


if __name__ == "__main__":
    sys.exit(main())
