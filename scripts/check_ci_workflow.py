# -*- coding: utf-8 -*-
"""校验 GitHub workflow 与 `scripts/ci_steps.py` **逐字节一致**。

以前这里只比对步骤名，命令参数少一个 `--flag`、超时改了都发现不了。
现在 `.github/workflows/ci.yml` 由 `scripts/gen_ci_workflow.py` 生成，
本门禁只做一件事：重新渲染并比对。

用法：python scripts/check_ci_workflow.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        # 旧解释器 / 非 TTY：保持默认编码即可
        pass

from ci_steps import ACCEPTANCE, gate_steps  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _display(path: Path) -> str:
    """报错时的路径展示：仓库内显示相对路径，仓库外（测试临时目录）显示绝对路径。"""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def check() -> list[str]:
    """返回问题列表（空 = 通过）。"""
    import gen_ci_workflow

    if not WORKFLOW.is_file():
        return [f"缺少 {_display(WORKFLOW)}"]
    expected = gen_ci_workflow.render()
    actual = WORKFLOW.read_text(encoding="utf-8")
    if actual == expected:
        return []
    # 找第一处差异，报行号：整份 diff 打印出来反而看不清
    actual_lines = actual.splitlines()
    expected_lines = expected.splitlines()
    for lineno, (got, want) in enumerate(zip(actual_lines, expected_lines), start=1):
        if got != want:
            return [
                f"{_display(WORKFLOW)}:{lineno} 与生成结果不一致",
                f"  实际：{got!r}",
                f"  期望：{want!r}",
                "修法：python scripts/gen_ci_workflow.py（不要手改 yml）",
            ]
    if len(actual_lines) != len(expected_lines):
        return [
            f"{_display(WORKFLOW)} 行数不一致："
            f"实际 {len(actual_lines)}，期望 {len(expected_lines)}",
            "修法：python scripts/gen_ci_workflow.py",
        ]
    return ["内容不一致（行级比较未定位，可能是换行符差异）"]


def main() -> int:
    problems = check()
    if problems:
        print("CI 工作流与 ci_steps 不一致：")
        for problem in problems:
            print(f"  [FAIL] {problem}")
        return 1
    print(f"✅ CI 工作流与 ci_steps 逐字节一致"
          f"（门禁 {len(gate_steps())}、验收 {len(ACCEPTANCE)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
