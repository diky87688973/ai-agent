# -*- coding: utf-8 -*-
"""验收：集成与外围 4 件（ip_geolocate / open_meteo_weather / review_conclusion /
skills）headless 演示。

场景：① 工具族管道冒烟——网络类以 mock 替换模块 HTTP 层；
② 注册与一致性——4 件工具注册、catalog 成员、discard 在位。
运行：python scripts/acceptance_batch_f.py（全部通过退出码 0）
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402
from agent.capabilities.builtin import geo_weather_tools  # noqa: E402
from agent.core.tool_call import ToolResult  # noqa: E402
from agent.mechanisms.live_state import LiveState  # noqa: E402
from agent.mechanisms.mesh import MeshState  # noqa: E402

CID_DRIVER = "accept-batch-f"

BATCH_F_TOOLS = ["ip_geolocate", "open_meteo_weather", "review_conclusion", "skills"]

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

    # ── 场景 ① 工具族管道冒烟 ──────────────────────────

    def scenario_1(self) -> None:
        print("\n场景① 工具族管道冒烟（网络 mock）")

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

    # ── 场景 ② 注册与一致性 ────────────────────────────

    def scenario_2(self) -> None:
        print("\n场景② 注册与一致性")
        missing = [n for n in BATCH_F_TOOLS if self.app.registry.get(n) is None]
        self.check("4 件工具均已注册", not missing, str(missing))

        catalog = json.loads((ROOT / "catalog" / "tools.json").read_text(encoding="utf-8"))
        tool_names = [str(t.get("name")) for t in catalog.get("tools", [])]
        not_in_catalog = [n for n in BATCH_F_TOOLS if n not in tool_names]
        self.check("catalog 成员含 4 件工具", not not_in_catalog, str(not_in_catalog))
        self.check("catalog 工具总数 ≥ 41", len(tool_names) >= 41, str(len(tool_names)))
        skill = self.app.registry.get("skills")
        self.check(
            "skills 只读且 discard 在位",
            skill is not None
            and not getattr(skill, "needs_preview", False)
            and hasattr(self.gate, "discard"),
            str(getattr(skill, "write_path_keys", None)),
        )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        acc = Acceptance(Path(tmp))
        try:
            acc.scenario_1()
            acc.scenario_2()
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
