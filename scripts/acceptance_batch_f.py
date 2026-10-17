# -*- coding: utf-8 -*-
"""验收：集成与外围 5 件（ip_geolocate / open_meteo_weather / review_conclusion /
skill_manage / github_api）headless 演示。

场景：① 门控闭环——skill_manage copy 走完整 id 制四步；跨文件写后经 review_conclusion
放行；cancel_preview 取消；短结论拒绝；
② 工具族管道冒烟——5 件经 ToolPipeline 唯一入口；网络类以 mock 替换模块 HTTP 层；
③ 注册与一致性——5 件工具注册（41 工具）、catalog 成员、门控预览名单含 skill_manage、discard 在位。
运行：python scripts/acceptance_batch_f.py（全部通过退出码 0）
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402
from agent.capabilities.builtin import geo_weather_tools, github_tools  # noqa: E402
from agent.core.tool_call import ToolCallRequest, ToolResult  # noqa: E402
from agent.mechanisms import quality_gate  # noqa: E402
from agent.mechanisms.live_state import LiveState  # noqa: E402
from agent.mechanisms.mesh import MeshState  # noqa: E402

CID_DRIVER = "accept-batch-f"

BATCH_F_TOOLS = ["ip_geolocate", "open_meteo_weather", "review_conclusion", "skill_manage", "github_api"]

_LONG_CONCLUSION = "review结论：验收链路复核通过，落盘内容已 read 复核，ast 与 py_compile 检查通过。"


class Acceptance:
    """headless 验收运行器：经管道唯一入口驱动，逐项打印 PASS/FAIL。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.skills_dir = root / "skills"
        self.skills_dir.mkdir()
        # Skills 目录由 `skills` 插件装载时解析：经环境变量指到本次的临时目录，
        # 否则插件读到的是工程配置里那个真目录。
        self._skills_env_old = os.environ.get("AI_AGENT_SKILLS_DIR")
        os.environ["AI_AGENT_SKILLS_DIR"] = str(self.skills_dir)
        self.app = build_app(
            backup_root=root / "backups",
            recycle_root=root / "recycle",
            live_state=LiveState(storage_dir=root / "todo"),
            mesh=MeshState(storage_dir=root / "mesh"),
        )
        self.seq = 0
        self.failures: list = []

    def call(self, name: str, arguments: dict = None, cid: str = CID_DRIVER) -> ToolResult:
        self.seq += 1
        call = ToolCallRequest(call_id=f"c{self.seq}", name=name, arguments=arguments or {})
        ctx = SimpleNamespace(conversation_id=cid) if cid else None
        return self.app.pipeline.execute(self.app.registry, call, ctx)

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

    # ── 场景 ① 门控闭环（skill_manage + review_conclusion）──────

    def scenario_1(self) -> None:
        print("\n场景① 门控闭环（skill_manage copy 四步 + review_conclusion）")
        incoming = self.root / "incoming"
        incoming.mkdir()
        (incoming / "one.md").write_text("---\nname: one\ndescription: demo\n---\n\n正文一\n", encoding="utf-8")

        r1 = self.call("skill_manage", {"action": "copy", "source": str(incoming)})
        cid = (r1.data or {}).get("confirm_id") if r1.ok else None
        self.check(
            "copy 预览：confirm_id 发出且不落盘",
            r1.ok and cid and not (self.skills_dir / "one.md").exists() and (r1.data or {}).get("would_copy") == 1,
            str(r1.data),
        )

        r_bad = self.call("commit_write", {"confirm_id": "nonexistent-id"})
        self.check("提交：伪 ID 拒绝", (not r_bad.ok) and "无效" in (r_bad.error or ""), str(r_bad.error))

        r_unconf = self.call("commit_write", {"confirm_id": cid})
        self.check(
            "提交：未确认先拒（四步第二步强制）",
            (not r_unconf.ok)
            and "未解锁" in (r_unconf.error or "")
            and "review_conclusion" in (r_unconf.error or ""),
            str(r_unconf.error),
        )

        confirmed = self.gate.confirm(cid)
        self.check("确认：通过门控确认", confirmed is True, str(confirmed))

        r2 = self.call("commit_write", {"confirm_id": cid})
        self.check(
            "提交：复制落盘",
            r2.ok and (self.skills_dir / "one.md").is_file() and bool((r2.data or {}).get("written")),
            str(r2.data),
        )
        self.check(
            "提交：host_quality 报告随结果回灌",
            r2.ok and isinstance((r2.data or {}).get("host_quality"), dict),
            str((r2.data or {}).get("host_quality")),
        )

        r3 = self.call("commit_write", {"confirm_id": cid})
        self.check("提交：一次性消费（重放拒绝）", (not r3.ok) and "无效或已使用" in (r3.error or ""), str(r3.error))

        r_list = self.call("skill_manage", {"action": "list"})
        names = [s["name"] for s in (r_list.data or {}).get("skills", [])]
        self.check(
            "list 只读：不登记快照且含新 Skills",
            r_list.ok and (r_list.data or {}).get("needs_commit") is False and "confirm_id" not in (r_list.data or {}) and "one" in names,
            str(r_list.data),
        )
        r_read = self.call("skill_manage", {"action": "read", "name": "one"})
        self.check(
            "read：返回正文（frontmatter 剥离）",
            r_read.ok and (r_read.data or {}).get("content") == "正文一",
            str(r_read.data),
        )

        incoming2 = self.root / "incoming2"
        incoming2.mkdir()
        (incoming2 / "two.md").write_text("---\nname: two\n---\n\n正文二\n", encoding="utf-8")
        r4 = self.call("skill_manage", {"action": "copy", "source": str(incoming2)})
        cid2 = str((r4.data or {}).get("confirm_id") or "")
        self.gate.confirm(cid2)
        r_blocked = self.call("commit_write", {"confirm_id": cid2})
        self.check(
            "跨文件：写后未 review 先拒",
            (not r_blocked.ok) and "review" in (r_blocked.error or ""),
            str(r_blocked.error),
        )

        r_review = self.call("review_conclusion", {"conclusion": _LONG_CONCLUSION, "file_name": "one.md"})
        self.check(
            "review_conclusion：提交后放行",
            r_review.ok and (r_review.data or {}).get("reviewed") is True and not self.gate.pending_review,
            str(r_review.data),
        )
        r5 = self.call("commit_write", {"confirm_id": cid2})
        self.check(
            "review 后重试：复制落盘",
            r5.ok and (self.skills_dir / "two.md").is_file(),
            str(r5.data),
        )
        self.gate.review_done()

        r_short = self.call("review_conclusion", {"conclusion": "太短", "file_name": "two.md"})
        self.check("review_conclusion：短结论拒绝", (not r_short.ok) and "至少 30 字" in (r_short.error or ""), str(r_short.error))

        incoming3 = self.root / "incoming3"
        incoming3.mkdir()
        (incoming3 / "three.md").write_text("---\nname: three\n---\n\n正文三\n", encoding="utf-8")
        r6 = self.call("skill_manage", {"action": "copy", "source": str(incoming3)})
        cid3 = str((r6.data or {}).get("confirm_id") or "")
        r_cancel = self.call("review_conclusion", {"file_name": "three.md", "confirm_id": cid3, "cancel_preview": True})
        self.check(
            "cancel_preview：快照释放",
            r_cancel.ok and (r_cancel.data or {}).get("message") == "预览已取消。" and self.gate.peek(cid3) is None,
            str(r_cancel.data),
        )
        r7 = self.call("commit_write", {"confirm_id": cid3})
        self.check("取消后提交：拒绝", (not r7.ok) and "无效或已使用" in (r7.error or ""), str(r7.error))

    # ── 场景 ② 工具族管道冒烟 ──────────────────────────

    def scenario_2(self) -> None:
        print("\n场景② 工具族管道冒烟（5 件经唯一入口；网络 mock）")

        def fake_ip(url: str, timeout_sec: int, user_agent: str) -> dict:
            return {
                "success": True,
                "ip": "203.0.113.9",
                "city": "Demo",
                "region": "Region",
                "country": "Country",
                "latitude": 1.0,
                "longitude": 2.0,
                "timezone": {"id": "Asia/Shanghai"},
            }

        with mock.patch.object(geo_weather_tools, "_http_json", side_effect=fake_ip):
            r = self.call("ip_geolocate", {"ip": "10.0.0.1"})
        self.check(
            "ip_geolocate：内网归一化 + 摘要",
            r.ok and (r.data or {}).get("display_region_zh") == "【IP定位地区】Demo,Region,Country",
            str(r.data),
        )

        def fake_weather(url: str, timeout_sec: int, user_agent: str) -> dict:
            return {
                "current": {"temperature_2m": 21, "relative_humidity_2m": 40, "precipitation": 0.0, "weather_code": 0},
                "daily": {"time": ["2026-10-10"], "precipitation_probability_max": [10], "precipitation_sum": [0.0], "weather_code": [0]},
                "timezone": "Asia/Shanghai",
            }

        with mock.patch.object(geo_weather_tools, "_http_json", side_effect=fake_weather):
            r = self.call("open_meteo_weather", {"location": "北京"})
        self.check(
            "open_meteo_weather：别名直解 + 摘要",
            r.ok and (r.data or {}).get("resolved_name") == "北京" and "【解析地区】北京" in (r.data or {}).get("summary_zh", ""),
            str(r.data),
        )

        with mock.patch.object(github_tools, "_find_token", return_value=""):
            r = self.call("github_api", {"action": "get_repo", "repo": "owner/repo"})
        self.check(
            "github_api：无 token → LoginRequired",
            (not r.ok) and (r.data or {}).get("type") == "LoginRequired",
            str(r.data),
        )
        r = self.call("github_api", {"action": "nope", "repo": "owner/repo"})
        self.check(
            "github_api：非法 action 拒绝",
            (not r.ok) and (r.data or {}).get("type") == "ValueError",
            str(r.data),
        )

    # ── 场景 ③ 注册与一致性 ────────────────────────────

    def scenario_3(self) -> None:
        print("\n场景③ 注册与一致性")
        missing = [n for n in BATCH_F_TOOLS if self.app.registry.get(n) is None]
        self.check("5 件工具均已注册", not missing, str(missing))

        catalog = json.loads((ROOT / "catalog" / "tools.json").read_text(encoding="utf-8"))
        tool_names = [str(t.get("name")) for t in catalog.get("tools", [])]
        not_in_catalog = [n for n in BATCH_F_TOOLS if n not in tool_names]
        self.check("catalog 成员含 5 件工具", not not_in_catalog, str(not_in_catalog))
        self.check("catalog 工具总数 ≥ 41", len(tool_names) >= 41, str(len(tool_names)))
        self.check(
            "门控：预览名单含 skill_manage 且 discard 在位",
            quality_gate._TOOL_PATH_KEYS.get("skill_manage") == ("source", "name")
            and hasattr(self.gate, "discard"),
            str(quality_gate._TOOL_PATH_KEYS.get("skill_manage")),
        )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        acc = Acceptance(Path(tmp))
        try:
            acc.scenario_1()
            acc.scenario_2()
            acc.scenario_3()
        finally:
            # 环境变量是本脚本自己设的，用完还原，别影响同一进程里后续的东西。
            if acc._skills_env_old is None:
                os.environ.pop("AI_AGENT_SKILLS_DIR", None)
            else:
                os.environ["AI_AGENT_SKILLS_DIR"] = acc._skills_env_old
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
