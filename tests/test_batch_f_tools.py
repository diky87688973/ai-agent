# -*- coding: utf-8 -*-
"""集成与外围测试：ip 定位 / 天气 / review 提交 / Skills 库与工具 / GitHub。

网络类以 unittest.mock 替换模块内 HTTP 层；storage 类（Skills 库）用临时目录。
"""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.builtin import (  # noqa: E402
    geo_weather_tools,
    github_tools,
    review_conclusion,
)
from plugins.skills import tools as skill_tools  # noqa: E402
from plugins.skills.library import SkillManager, SkillMeta  # noqa: E402


def _ipwho_payload(**overrides: object) -> dict:
    payload = {
        "success": True,
        "ip": "1.2.3.4",
        "city": "TestCity",
        "region": "TestRegion",
        "country": "TestCountry",
        "latitude": 1.5,
        "longitude": 2.5,
        "timezone": {"id": "Asia/Shanghai"},
    }
    payload.update(overrides)
    return payload

def _forecast_payload() -> dict:
    return {
        "current": {"temperature_2m": 20, "relative_humidity_2m": 50, "precipitation": 0.0, "weather_code": 0},
        "daily": {
            "time": ["2026-10-10", "2026-10-11"],
            "precipitation_probability_max": [10, 20],
            "precipitation_sum": [0.0, 1.0],
            "weather_code": [0, 3],
        },
        "timezone": "Asia/Shanghai",
    }

class IpGeolocateTest(unittest.TestCase):
    """ip 定位。"""

    def setUp(self) -> None:
        self.tool = geo_weather_tools.IpGeolocateTool()

    def test_private_ip_normalized_to_export_lookup(self) -> None:
        captured = {}

        def fake_http(url: str, timeout_sec: int, user_agent: str) -> dict:
            captured["url"] = url
            return _ipwho_payload()

        with mock.patch.object(geo_weather_tools, "_http_json", side_effect=fake_http):
            r = self.tool.execute({"ip": "192.168.1.1"})
        self.assertEqual(captured["url"], geo_weather_tools.IP_API_URL)
        self.assertEqual(r["display_region_zh"], "【IP定位地区】TestCity,TestRegion,TestCountry")
        self.assertIn("时区 Asia/Shanghai", r["summary_zh"])

    def test_public_ip_path_with_loopback_variants(self) -> None:
        seen = []

        def fake_http(url: str, timeout_sec: int, user_agent: str) -> dict:
            seen.append(url)
            return _ipwho_payload()

        with mock.patch.object(geo_weather_tools, "_http_json", side_effect=fake_http):
            self.tool.execute({"ip": "8.8.8.8"})
            self.tool.execute({"ip": "127.0.0.1"})
        self.assertEqual(seen[0], geo_weather_tools.IP_API_URL + "/8.8.8.8")
        self.assertEqual(seen[1], geo_weather_tools.IP_API_URL)

    def test_success_false_structured_error(self) -> None:
        with mock.patch.object(geo_weather_tools, "_http_json", return_value={"success": False, "message": "reserved range"}):
            with self.assertRaises(geo_weather_tools.GeoServiceError) as ctx:
                self.tool.execute({"ip": "8.8.8.8"})
        self.assertEqual(ctx.exception.data["type"], "GeoLocateError")
        self.assertTrue(ctx.exception.data["retryable"])

class WeatherTest(unittest.TestCase):
    """天气查询。"""

    def setUp(self) -> None:
        self.tool = geo_weather_tools.OpenMeteoWeatherTool()

    def test_cn_alias_direct_resolution(self) -> None:
        seen = []

        def fake_http(url: str, timeout_sec: int, user_agent: str) -> dict:
            seen.append(url)
            return _forecast_payload()

        with mock.patch.object(geo_weather_tools, "_http_json", side_effect=fake_http):
            r = self.tool.execute({"location": "北京"})
        self.assertEqual(r["source"], "location")
        self.assertEqual(r["resolved_name"], "北京")
        self.assertEqual(len(seen), 1)  # 别名直解：仅预报一次请求
        self.assertIn("latitude=39.9042", seen[0])
        self.assertIn("forecast_days=2", seen[0])
        self.assertIn("【解析地区】北京（北京市，中国）", r["summary_zh"])

    def test_coordinates_and_days_clamp(self) -> None:
        seen = []

        def fake_http(url: str, timeout_sec: int, user_agent: str) -> dict:
            seen.append(url)
            return _forecast_payload()

        with mock.patch.object(geo_weather_tools, "_http_json", side_effect=fake_http):
            r = self.tool.execute({"latitude": "10", "longitude": "20", "forecast_days": 99})
        self.assertEqual(r["source"], "coordinates")
        self.assertIn("latitude=10.0", seen[0])
        self.assertIn("forecast_days=7", seen[0])

    def test_location_not_found(self) -> None:
        with mock.patch.object(geo_weather_tools, "_http_json", return_value={"results": []}):
            with self.assertRaises(geo_weather_tools.GeoServiceError) as ctx:
                self.tool.execute({"location": "不存在的地方xyz"})
        self.assertEqual(ctx.exception.data["type"], "NotFound")

    def test_scoring_prefers_exact_and_major(self) -> None:
        hit_major = {
            "name": "北京",
            "admin1": "北京市",
            "country": "中国",
            "country_code": "CN",
            "feature_code": "PPLC",
            "population": 20000000,
        }
        hit_minor = {
            "name": "北京镇",
            "admin1": "",
            "country": "中国",
            "country_code": "CN",
            "feature_code": "PPL",
            "population": 1000,
        }
        self.assertGreater(
            geo_weather_tools._score_geo_result("北京", hit_major),
            geo_weather_tools._score_geo_result("北京", hit_minor),
        )

class ReviewConclusionTest(unittest.TestCase):
    """review 提交与解锁（经 ToolTurnContext.session.gate）。"""

    def setUp(self) -> None:
        from agent.core.context import ToolTurnContext
        from agent.core.session_context import SessionContexts
        from agent.core.session_scope import reset_tool_turn_context, set_tool_turn_context
        from tests.gate_fixtures import make_gate

        self._contexts = SessionContexts(lambda cid: make_gate())
        self.session = self._contexts.resolve_sync("review-test")
        self.gate = self.session.gate
        self.tool = review_conclusion.build()
        self._ctx_token = set_tool_turn_context(
            ToolTurnContext(app=None, session=self.session, turn=None, call=None)
        )
        self.addCleanup(lambda: reset_tool_turn_context(self._ctx_token))

    def test_short_conclusion_and_missing_file_name_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.tool.execute({"conclusion": "太短", "file_name": "a.py"})
        with self.assertRaises(ValueError):
            self.tool.execute({"conclusion": "x" * 40, "file_name": ""})

    def test_call_is_submit_not_format_check(self) -> None:
        """调用即提交：没有"仅格式校验"档；返回里不含 dry_run。"""
        r = self.tool.execute({"conclusion": "x" * 40, "file_name": "a.py"})
        self.assertTrue(r["reviewed"])
        self.assertNotIn("dry_run", r)

    def test_confirm_unlock_and_review_done(self) -> None:
        cid = self.gate.register_preview("write_file", {"path": "p.txt", "content": "c"})
        r = self.tool.execute({"conclusion": "x" * 40, "file_name": "p.txt", "confirm_id": cid})
        self.assertTrue(r["reviewed"])
        self.assertTrue(self.gate.peek(cid)["confirmed"])
        self.gate.note_committed("some.py", tool="write_file")
        self.assertTrue(self.gate.pending_review)
        self.tool.execute({"conclusion": "x" * 40, "file_name": "some.py"})
        self.assertFalse(self.gate.pending_review)

    def test_cancel_preview_and_invalid(self) -> None:
        cid = self.gate.register_preview("archive", {"action": "create", "dest": "o.zip"})
        r = self.tool.execute({"file_name": "o.zip", "confirm_id": cid, "cancel_preview": True})
        self.assertTrue(r["reviewed"])
        self.assertIsNone(self.gate.peek(cid))
        with self.assertRaises(ValueError):
            self.tool.execute({"file_name": "o.zip", "confirm_id": cid, "cancel_preview": True})

class SkillsLibraryTest(unittest.TestCase):
    """Skills 库。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.skills_dir = self.root / "skills"
        self.skills_dir.mkdir()
        (self.skills_dir / "alpha.md").write_text(
            "---\nname: alpha\ndescription: Alpha skill\n---\n\n# Alpha\ncontent here\n",
            encoding="utf-8",
        )
        sub = self.skills_dir / "opencli"
        sub.mkdir()
        (sub / "beta.md").write_text("no frontmatter content\n", encoding="utf-8")
        auto = self.skills_dir / "auto_load"
        auto.mkdir()
        (auto / "always.md").write_text("---\nname: always\ndescription: Always\n---\nbody\n", encoding="utf-8")

    def test_scan_list_and_matching(self) -> None:
        mgr = SkillManager(self.skills_dir)
        listed = [s["name"] for s in mgr.list_skills()]
        self.assertIn("alpha", listed)
        self.assertIn("opencli/beta", listed)
        self.assertNotIn("always", listed)  # auto_load 不入普通清单
        self.assertEqual(mgr.get_skill("alpha"), "# Alpha\ncontent here")
        self.assertIsNone(mgr.get_skill("beta"))  # 子目录 stem 不匹配根
        self.assertIn("no frontmatter content", mgr.get_skill("opencli/beta"))

    def test_truncation_and_incremental_rescan(self) -> None:
        small = SkillManager(self.skills_dir, max_file_size=50)
        self.assertIn("已截断", small.get_skill("alpha"))
        (self.skills_dir / "gamma.md").write_text("---\nname: gamma\n---\ng\n", encoding="utf-8")
        names = [s["name"] for s in small.list_skills()]
        self.assertIn("gamma", names)

    def test_copy_plan_execute_and_conflict(self) -> None:
        mgr = SkillManager(self.skills_dir)
        src = self.root / "incoming"
        src.mkdir()
        (src / "new1.md").write_text("---\nname: n1\n---\nx\n", encoding="utf-8")
        (src / "note.txt").write_text("skip me", encoding="utf-8")
        plan = mgr.plan_copy(src)
        self.assertEqual(plan["files"], ["new1.md"])
        self.assertEqual(plan["conflicts"], [])
        self.assertEqual(plan["skipped"], 1)
        self.assertFalse((self.skills_dir / "new1.md").exists())
        res = mgr.execute_copy(src)
        self.assertEqual(res["copied"], 1)
        self.assertTrue((self.skills_dir / "new1.md").exists())
        (src / "new1.md").write_text("changed\n", encoding="utf-8")
        self.assertTrue(mgr.plan_copy(src)["conflicts"])

class SkillManageToolTest(unittest.TestCase):
    """skill_manage 工具。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.skills_dir = self.root / "skills"
        self.skills_dir.mkdir()
        (self.skills_dir / "alpha.md").write_text("---\nname: alpha\ndescription: A\n---\nbody\n", encoding="utf-8")
        self.library = SkillManager(self.skills_dir)
        self.tool = skill_tools.build(self.library)

    def test_list_read_and_lookup_error(self) -> None:
        r = self.tool.execute({"action": "list"})
        self.assertFalse(r["needs_commit"])
        self.assertEqual(r["count"], 1)
        r = self.tool.execute({"action": "read", "name": "alpha"})
        self.assertFalse(r["needs_commit"])
        self.assertEqual(r["content"], "body")
        with self.assertRaises(skill_tools.SkillLookupError) as ctx:
            self.tool.execute({"action": "read", "name": "nope"})
        self.assertEqual(ctx.exception.data["available"], ["alpha"])

    def test_copy_preview_and_executor(self) -> None:
        src = self.root / "in2"
        src.mkdir()
        (src / "c1.md").write_text("z\n", encoding="utf-8")
        pv = self.tool.execute({"action": "copy", "source": str(src)})
        self.assertTrue(pv["preview"])
        self.assertEqual(pv["would_copy"], 1)
        self.assertFalse((self.skills_dir / "c1.md").exists())
        executors = skill_tools.build_executors(self.library)
        done = executors["skill_manage"]({"action": "copy", "source": str(src)})
        self.assertTrue(done["written"])
        self.assertTrue((self.skills_dir / "c1.md").exists())
        # 冲突预览标注（name 源已存在）
        pv2 = self.tool.execute({"action": "copy", "name": "alpha"})
        self.assertTrue(pv2["would_overwrite"])

    def test_copy_missing_source(self) -> None:
        with self.assertRaises(ValueError):
            self.tool.execute({"action": "copy"})

class GithubApiTest(unittest.TestCase):
    """github_api。"""

    def setUp(self) -> None:
        self.tool = github_tools.build()

    def test_login_required_and_param_validation(self) -> None:
        with mock.patch.object(github_tools, "_find_token", return_value=""):
            with self.assertRaises(github_tools.GitHubError) as ctx:
                self.tool.execute({"action": "get_repo", "repo": "owner/repo"})
        self.assertEqual(ctx.exception.data["type"], "LoginRequired")
        self.assertEqual(ctx.exception.data["action"], "login_required")
        with self.assertRaises(github_tools.GitHubError) as ctx2:
            self.tool.execute({"action": "get_repo"})
        self.assertEqual(ctx2.exception.data["type"], "ValueError")
        with self.assertRaises(github_tools.GitHubError) as ctx3:
            self.tool.execute({"action": "nope", "repo": "a/b"})
        self.assertEqual(ctx3.exception.data["type"], "ValueError")

    def test_create_pr_payload_and_url(self) -> None:
        captured = {}

        def fake_http(url: str, **kwargs: object) -> dict:
            captured["url"] = url
            captured.update(kwargs)
            return {"number": 1}

        with mock.patch.object(github_tools, "_find_token", return_value="tok"), mock.patch.object(
            github_tools, "_http_json", side_effect=fake_http
        ):
            r = self.tool.execute(
                {"action": "create_pr", "repo": "owner/repo", "title": "T", "head": "f:b", "base": "main"}
            )
        self.assertEqual(r, {"number": 1})
        self.assertTrue(captured["url"].endswith("/repos/owner/repo/pulls"))
        self.assertEqual(captured["json_body"], {"title": "T", "head": "f:b", "base": "main", "body": ""})
        self.assertEqual(captured["method"], "POST")

    def test_update_pr_requires_a_field(self) -> None:
        with self.assertRaises(github_tools.GitHubError) as ctx:
            self.tool.execute({"action": "update_pr", "repo": "a/b", "pr_number": 3})
        self.assertIn("至少提供一个要更新的字段", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()


class SkillsListNeverDoublesTest(unittest.TestCase):
    """清单翻倍防线：库内出现重复条目时，清单仍只列一份。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.skills_dir = self.root / "skills"
        self.skills_dir.mkdir()
        (self.skills_dir / "alpha.md").write_text(
            "---\nname: alpha\ndescription: 甲\n---\nA\n", encoding="utf-8")
        (self.skills_dir / "beta.md").write_text(
            "---\nname: beta\ndescription: 乙\n---\nB\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_duplicate_entries_do_not_double_the_catalog(self) -> None:
        mgr = SkillManager(self.skills_dir)
        base = mgr.list_skills()
        self.assertEqual(len(base), 2)
        # 模拟"扫描被打断留下的残留"：同一文件在库内出现两次
        mgr.skills.append(mgr.skills[0])
        self.assertEqual(len(mgr.skills), 3)
        names = [s["name"] for s in mgr.list_skills()]
        self.assertEqual(sorted(names), ["alpha", "beta"])
        text = mgr.build_registry_message_parts()[0]
        self.assertEqual(text.count("- alpha:"), 1)
        self.assertEqual(text.count("- beta:"), 1)

    def test_rescan_does_not_append_twice(self) -> None:
        mgr = SkillManager(self.skills_dir)
        before = len(mgr.skills)
        mgr._scan()          # 再扫一次必须整表换上，不能在旧表上追加
        self.assertEqual(len(mgr.skills), before)

    def test_different_path_spelling_counts_once(self) -> None:
        """同一文件的两种路径写法不能让 `len(list_skills())` 变成两倍。"""
        mgr = SkillManager(self.skills_dir)
        first = mgr.skills[0]
        weird = first.file_path.parent / "." / first.file_path.name
        mgr.skills.append(SkillMeta(first.name, first.description, weird, False))
        self.assertGreater(len(mgr.skills), 2)
        self.assertEqual(len(mgr.list_skills()), 2)
        text = mgr.build_registry_message_parts()[0]
        self.assertEqual(text.count(f"- {first.name}:"), 1)

    def test_auto_load_count_ignores_duplicate_entries(self) -> None:
        auto = self.skills_dir / "auto_load"
        auto.mkdir()
        (auto / "resident.md").write_text(
            "---\nname: resident\ndescription: 常\n---\n正文\n", encoding="utf-8")
        mgr = SkillManager(self.skills_dir)
        self.assertEqual(mgr.auto_load_count(), 1)
        resident = next(s for s in mgr.skills if s.is_auto_load)
        mgr.skills.append(SkillMeta(resident.name, resident.description,
                                    resident.file_path, True))
        self.assertEqual(len(mgr.skills), 4)
        self.assertEqual(mgr.auto_load_count(), 1)
        self.assertEqual(len(mgr.build_auto_load_messages()), 1)

    def test_concurrent_rescan_replaces_the_list(self) -> None:
        mgr = SkillManager(self.skills_dir)
        target = self.skills_dir / "alpha.md"

        def work() -> None:
            target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            mgr.list_skills()
            mgr.auto_load_count()

        threads = [threading.Thread(target=work) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(mgr.skills), 2)
        self.assertEqual(len(mgr.list_skills()), 2)
