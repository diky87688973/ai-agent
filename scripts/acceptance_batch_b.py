# -*- coding: utf-8 -*-
"""验收：命令执行两件（run_command / python_inline）headless 演示。

场景：① 正向——真实命令执行（stdout / exit_code / cwd / python_inline）；
② 反向——安全防线（黑名单 / safe_mode / 脚本内容 / base64 / 无效 shell）；
③ 生命周期——超时强杀 + 登记清空。
命令执行安全：黑名单 / 脚本内容 / safe_mode / 进程生命周期 / 输出净化。
运行：python scripts/acceptance_batch_b.py（全部通过退出码 0）
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.tool_call import ToolCallRequest, ToolResult  # noqa: E402
from agent.mechanisms import command_safety as cs  # noqa: E402


def _norm(path_text: str) -> str:
    """路径归一（大小写 / 真实路径），用于 Windows 路径比较。"""
    return os.path.normcase(os.path.realpath(path_text))


class Acceptance:
    """headless 验收运行器：经管道唯一入口驱动，逐项打印 PASS/FAIL。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.app = build_app()
        self.seq = 0
        self.failures: list = []

    def call(self, name: str, arguments: dict) -> ToolResult:
        self.seq += 1
        call = ToolCallRequest(call_id=f"c{self.seq}", name=name, arguments=arguments)
        return self.app.pipeline.execute(self.app.registry, call, None)

    def check(self, label: str, cond: object, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        line = f"  [{status}] {label}"
        if detail:
            line += f" — {detail}"
        print(line)
        if not cond:
            self.failures.append(label)

    # ── 场景 ① 正向 ────────────────────────────────────────

    def scenario_1(self) -> None:
        print("\n场景① 正向：真实命令执行（stdout / exit_code / cwd / python_inline）")
        r = self.call("run_command", {"command": "echo batch-b-ok"})
        self.check(
            "echo：exit_code=0 + stdout",
            r.ok and r.data["exit_code"] == 0 and "batch-b-ok" in r.data["stdout"],
        )
        r = self.call("run_command", {"command": "python -c \"import sys; sys.exit(3)\"", "safe_mode": False})
        self.check("exit_code 透传（3）", r.ok and r.data["exit_code"] == 3)
        # 打印当前目录的写法按平台分：Windows 是 `%CD%`，POSIX 是 `pwd`。
        cwd_probe = "echo %CD%" if os.name == "nt" else "pwd"
        r = self.call("run_command", {"command": cwd_probe, "cwd": str(self.root)})
        self.check("cwd 参数生效", r.ok and _norm(r.data["stdout"].strip()) == _norm(str(self.root)))
        r = self.call("python_inline", {"code": "print('inline-ok')"})
        self.check(
            "python_inline：捕获 stdout",
            r.ok and r.data["exit_code"] == 0 and "inline-ok" in r.data["stdout"],
        )

    # ── 场景 ② 反向 ────────────────────────────────────────

    def scenario_2(self) -> None:
        print("\n场景② 反向：安全防线（黑名单 / safe_mode / 内容级）")
        r = self.call("run_command", {"command": "del x.txt"})
        self.check(
            " 黑名单拦截 + delete_file 建议",
            (not r.ok) and ("CommandBlacklisted" in str(r.error)) and ("delete_file" in str(r.error)),
        )
        r = self.call("run_command", {"command": "rm -rf build", "safe_mode": False})
        self.check(" safe_mode 关闭仍拦截", (not r.ok) and ("CommandBlacklisted" in str(r.error)))
        r = self.call("run_command", {"command": "echo a && echo b"})
        self.check(" safe_mode 字符拦截", (not r.ok) and ("safe_mode" in str(r.error)))
        r = self.call("run_command", {"command": "echo a && echo b", "safe_mode": False})
        self.check(
            " safe_mode=false 放行链式",
            r.ok and ("a" in r.data["stdout"]) and ("b" in r.data["stdout"]),
        )
        script = self.root / "sc.py"
        script.write_text("import base64\n", encoding="utf-8")
        r = self.call("run_command", {"command": "python sc.py", "cwd": str(self.root)})
        self.check(" 脚本内容检查（含文件名）", (not r.ok) and ("sc.py" in str(r.error)))
        r = self.call("run_command", {"command": "python -c \"import base64\""})
        self.check(" base64 内联拦截", (not r.ok) and ("CommandBlacklisted" in str(r.error)))
        r = self.call("run_command", {"command": "echo hi", "shell": "bash"})
        self.check(" 无效 shell 拒绝", (not r.ok) and ("shell" in str(r.error)))

    # ── 场景 ③ 生命周期 ────────────────────────────────────

    def scenario_3(self) -> None:
        print("\n场景③ 生命周期：超时强杀 + 登记清空")
        r = self.call(
            "run_command",
            {"command": "python -c \"import time; time.sleep(30)\"", "timeout_sec": 1, "safe_mode": False},
        )
        self.check(
            "超时强杀进程树",
            r.ok and r.data["timed_out"] and ("超时" in r.data["stderr"]),
        )
        # 它强杀登记在册的进程、清空登记、返回处理数量。返回 0 = 登记里没有残留
        # （超时路径已在 `finally` 里注销过 PID）。留作脚本收尾的兜底清账。
        self.check(" 登记清空（无残留活动进程）", cs.force_kill_active_shell_process() == 0)

    # ── 运行 ───────────────────────────────────────────────

    def run(self) -> int:
        print("=== 验收：命令执行两件（headless）===")
        self.scenario_1()
        self.scenario_2()
        self.scenario_3()
        print()
        if self.failures:
            print(f"验收未通过：{len(self.failures)} 项失败")
            for name in self.failures:
                print(f"  - {name}")
            return 1
        print("验收通过：全部检查项 PASS。")
        return 0


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        return Acceptance(Path(tmp)).run()


if __name__ == "__main__":
    raise SystemExit(main())
