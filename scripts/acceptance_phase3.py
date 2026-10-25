# -*- coding: utf-8 -*-
"""插件回归验收：插件开 / 关两态均可运行。

场景：
  A 全开态：ai_speak / knowledge 全量启用 → 报告全 loaded、事件订阅与各类贡献到位、
    headless 冒烟跑通；
  B 全关态：白名单空 → 零加载、装配不受影响、冒烟跑通；
  C 热卸态：全开 → unload_all → 订阅 / 注入源 / 面板 / 动作 / 端点全部回收、
    冒烟仍跑通。
以真实 plugins/ 目录装载（不执行外部网络 / CLI；语音引擎缺依赖时按插件内降级路径处理）。

两个插件各自覆盖不同的贡献面：`ai_speak` 贡献工具、两个只读端点、两个开屏脚本与
事件订阅；`knowledge` 贡献注入源、面板、动作与端点。知识库的一切（配置判定、
文件访问、表格解析、勾选状态、注入、界面）都在插件自己里，不依赖内核额外注册的服务。
运行：python scripts/acceptance_phase3.py（全部通过退出码 0）
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402
from agent.mechanisms.live_state import LiveState  # noqa: E402
from agent.mechanisms.mesh import MeshState  # noqa: E402

ALL_PLUGINS = ["ai_speak", "knowledge"]


class Acceptance:
    """headless 验收运行器：真实装配 + mock 启用名单，逐项打印 PASS/FAIL。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.failures: list = []

    def check(self, label: str, cond: bool, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        line = f"  [{status}] {label}"
        if detail and not cond:
            line += f" — {detail}"
        print(line)
        if not cond:
            self.failures.append(label)

    def build(self, enabled):
        """按名字清单装配。清单即本场景的开关，不读私人配置里的 enable。"""
        from agent.capabilities import plugins as plugin_mod

        real_fields = plugin_mod.plugin_config_fields

        def _force_on(root):
            fields = real_fields(root)
            fields["enable"] = "1"
            return fields

        with mock.patch("agent.app.get_plugins", return_value=[{"name": n} for n in enabled]), \
                mock.patch.object(plugin_mod, "plugin_config_fields", side_effect=_force_on):
            return build_app(
                backup_root=self.root / "backups",
                recycle_root=self.root / "recycle",
                live_state=LiveState(storage_dir=self.root / "todo"),
                mesh=MeshState(storage_dir=self.root / "mesh"),
                plugins_dir=ROOT / "plugins",
            )

    def smoke(self, app, cid: str) -> list:
        """跑一个 Echo 回合，返回事件类型列表。"""
        engine = app.session(cid)
        return [ev.type for ev in engine.start_turn("插件回归冒烟：你好")]

    def subs_total(self, app) -> int:
        return sum(len(v) for v in app.event_bus._subs.values())

    def sources_total(self, app) -> int:
        return len(app.context_sources._sources)

    # ── 场景 A：全开态 ──

    def scenario_a(self) -> None:
        print("\n场景 A 全开态（ai_speak / knowledge 全量启用）")
        app = self.build(ALL_PLUGINS)
        reports = {r.name: r.status for r in app.plugin_host.reports()}
        self.check("插件报告全 loaded", all(reports.get(n) == "loaded" for n in ALL_PLUGINS), str(reports))
        self.check("已加载名单一致", app.plugin_host.loaded_names() == sorted(ALL_PLUGINS), str(app.plugin_host.loaded_names()))
        subs = self.subs_total(app)
        self.check("AI说话事件订阅已挂（=2）", subs == 2, f"subs={subs}")
        self.check("AI说话工具已注册", app.registry.get("ai_speak") is not None)
        self.check("AI说话运行时已登记",
                   app.plugin_host.runtime("ai_speak") is not None)
        boots = [item for item in app.plugin_host.contributions.all_boot_scripts()
                 if item.plugin == "ai_speak"]
        self.check("AI说话开屏脚本已贡献（=2）", len(boots) == 2,
                   str([item.rel_path for item in boots]))
        sources = self.sources_total(app)
        self.check("KB 注入源已挂（=1）", sources == 1, f"sources={sources}")
        contribs = app.plugin_host.contributions
        self.check("KB 面板已贡献（=1）", len(contribs.all_panels()) == 1,
                   str([p.as_dict()["id"] for p in contribs.all_panels()]))
        self.check("KB 动作已贡献（=1）", len(contribs.all_actions()) == 1,
                   str([a.as_dict()["id"] for a in contribs.all_actions()]))
        self.check("插件端点已贡献（=6）", len(contribs.all_routes()) == 6,
                   str([r.full_path for r in contribs.all_routes()]))
        self.check("KB 面板资产已声明（样式 + 脚本）",
                   all((p.as_dict()["style"] and p.as_dict()["script"])
                       for p in contribs.all_panels()))
        types = self.smoke(app, "accept-phase3-a")
        self.check("冒烟回合跑通（turn_ended）", "turn_ended" in types, str(types[-3:]))

    # ── 场景 B：全关态 ──

    def scenario_b(self) -> None:
        print("\n场景 B 全关态（白名单空）")
        app = self.build([])
        self.check("零加载", app.plugin_host.loaded_names() == [], str(app.plugin_host.loaded_names()))
        self.check("无注入源", self.sources_total(app) == 0, f"sources={self.sources_total(app)}")
        self.check("无面板贡献", len(app.plugin_host.contributions.all_panels()) == 0)
        types = self.smoke(app, "accept-phase3-b")
        self.check("冒烟回合跑通（turn_ended）", "turn_ended" in types, str(types[-3:]))

    # ── 场景 C：开 → 热卸 → 关 ──

    def scenario_c(self) -> None:
        print("\n场景 C 热卸态（全开 → unload_all）")
        app = self.build(ALL_PLUGINS)
        self.check("卸前：KB 面板在", len(app.plugin_host.contributions.all_panels()) == 1)
        app.plugin_host.unload_all()
        self.check("卸后：名单清空", app.plugin_host.loaded_names() == [])
        self.check("卸后：AI说话工具回收", app.registry.get("ai_speak") is None)
        subs = self.subs_total(app)
        self.check("卸后：AI说话订阅回收（=0）", subs == 0, f"subs={subs}")
        # 注入源、面板、动作、端点都是插件的贡献，卸载必须一起撤掉 ——
        # 留一个就是死标签 / 指向已卸载插件的死端点 / 卸了还在注入的幽灵上下文。
        sources = self.sources_total(app)
        self.check("卸后：KB 注入源回收（=0）", sources == 0, f"sources={sources}")
        contribs = app.plugin_host.contributions
        self.check("卸后：面板回收（=0）", len(contribs.all_panels()) == 0,
                   str([p.panel_id for p in contribs.all_panels()]))
        self.check("卸后：动作回收（=0）", len(contribs.all_actions()) == 0,
                   str([a.action_id for a in contribs.all_actions()]))
        self.check("卸后：端点回收（=0）", len(contribs.all_routes()) == 0,
                   str([r.path for r in contribs.all_routes()]))
        self.check("卸后：开屏脚本回收（=0）", len(contribs.all_boot_scripts()) == 0)
        types = self.smoke(app, "accept-phase3-c")
        self.check("卸后冒烟仍跑通（turn_ended）", "turn_ended" in types, str(types[-3:]))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        acc = Acceptance(Path(tmp))
        acc.scenario_a()
        acc.scenario_b()
        acc.scenario_c()
    fail = len(acc.failures)
    print(f"\n插件回归验收：{'全部通过' if fail == 0 else '存在失败'}（失败 {fail} 项）")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
