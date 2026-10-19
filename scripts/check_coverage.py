# -*- coding: utf-8 -*-
"""分包覆盖率下限校验（X5 / X6）。

读 `.coverage`（`run_coverage.py` 发布的产物），按顶层包分别算语句覆盖率，
与 `scripts/quality_budgets.py` 的 `COVERAGE_FLOORS` 比对。

用法：
    python scripts/check_coverage.py            # 校验（低于下限退出 1）
    python scripts/check_coverage.py --print    # 只打印测得值（确定基线用）

`.coverage` 不存在 / `coverage` 未安装 / 数据正在被写入 → 退出码 2（CI 记为 SKIP，可见）。
校验期间数据文件被改写同样按 SKIP 处理：半份数据不能用来判下限。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_lock import ArtifactLock, LockBusy  # type: ignore
from quality_budgets import COVERAGE_FLOORS  # type: ignore

#: 等写者放手的最长时间：超过就按"数据不可用"跳过，不拿半份数据出结论
LOCK_WAIT_S = 5.0

ROOT = Path(__file__).resolve().parent.parent

#: 统计口径：顶层包 → 路径前缀（按顺序匹配，先具体后宽泛）。
_GROUPS: Tuple[Tuple[str, str], ...] = (
    ("agent/core", "/agent/core/"),
    ("agent/mechanisms", "/agent/mechanisms/"),
    ("agent/capabilities", "/agent/capabilities/"),
    ("agent/shell", "/agent/shell/"),
    ("agent/entry", "/agent/entry/"),
    ("agent (top-level)", "/agent/"),
    ("plugins", "/plugins/"),
)

#: 不参与 Python 覆盖率统计的路径（JS/CSS 资产由 `check_ui_js.py` 负责）。
_OMIT_MARKERS = ("/web_assets/", "/__pycache__/")


def _group_of(filename: str) -> str | None:
    normalized = filename.replace("\\", "/")
    if any(marker in normalized for marker in _OMIT_MARKERS):
        return None
    for name, marker in _GROUPS:
        if marker in normalized:
            return name
    return None


def measure(data_file: Path = ROOT / ".coverage") -> Dict[str, Tuple[int, int]]:
    """返回 `{包: (语句数, 未覆盖数)}`；没有数据时返回空字典。"""
    import coverage  # 延迟导入：未安装时由 main 转成 SKIP

    cov = coverage.Coverage(data_file=str(data_file))
    cov.load()
    data = cov.get_data()
    out: Dict[str, List[int]] = {}
    for filename in data.measured_files():
        group = _group_of(filename)
        if group is None:
            continue
        analysis = cov.analysis2(filename)
        statements, missing = len(analysis[1]), len(analysis[3])
        bucket = out.setdefault(group, [0, 0])
        bucket[0] += statements
        bucket[1] += missing
    return {name: (values[0], values[1]) for name, values in out.items()}


def percent(statements: int, missing: int) -> float:
    if statements <= 0:
        return 100.0
    return 100.0 * (statements - missing) / statements


def check(measured: Dict[str, Tuple[int, int]],
          floors: Dict[str, float] | None = None) -> List[str]:
    """返回问题列表（空 = 通过）。缺数据与低于下限都算问题。"""
    floors = COVERAGE_FLOORS if floors is None else floors
    problems: List[str] = []
    for group, floor in sorted(floors.items()):
        if group not in measured:
            problems.append(f"{group}: 没有覆盖率数据（该包未被任何用例导入？）")
            continue
        statements, missing = measured[group]
        actual = percent(statements, missing)
        if actual + 1e-9 < float(floor):
            problems.append(
                f"{group}: {actual:.1f}% < 下限 {float(floor):.1f}%"
                f"（语句 {statements}，未覆盖 {missing}）"
            )
    return problems


def stamp(data_file: Path) -> Tuple[int, int] | None:
    """数据文件的 (mtime_ns, size)；不存在时返回 None。"""
    try:
        info = data_file.stat()
    except OSError:
        # 文件不存在或被别的进程挪走
        return None
    return info.st_mtime_ns, info.st_size


def report(measured: Dict[str, Tuple[int, int]]) -> None:
    """打印分包覆盖率表。"""
    print("分包语句覆盖率：")
    for group in sorted(measured):
        statements, missing = measured[group]
        floor = COVERAGE_FLOORS.get(group)
        mark = "" if floor is None else f"  下限 {float(floor):.1f}%"
        print(f"  {group:20} {percent(statements, missing):6.1f}%"
              f"（语句 {statements}，未覆盖 {missing}）{mark}")


def main() -> int:
    data_file = ROOT / ".coverage"
    lock = ArtifactLock(ROOT, "coverage", purpose="check_coverage")
    try:
        lock.acquire(wait_s=LOCK_WAIT_S)
    except LockBusy as exc:
        print(f"[SKIP] 覆盖率数据正在被写入：{exc}")
        return 2
    try:
        return _check_locked(data_file)
    finally:
        lock.release()


def _check_locked(data_file: Path) -> int:
    before = stamp(data_file)
    try:
        measured = measure(data_file)
    except ImportError:
        print("[SKIP] 未安装 coverage（pip install coverage 后重试）")
        return 2
    except Exception as exc:
        print(f"[SKIP] 读不到 .coverage：{type(exc).__name__}: {exc}")
        return 2
    if stamp(data_file) != before:
        print("[SKIP] .coverage 在校验期间被改写（并发写），本次不出结论")
        return 2
    if not measured:
        print("[SKIP] .coverage 里没有 agent/plugins 的数据")
        return 2

    report(measured)

    if "--print" in sys.argv[1:]:
        return 0
    problems = check(measured)
    if problems:
        print("\n覆盖率未达标：")
        for problem in problems:
            print(f"  [FAIL] {problem}")
        print("修法：补测试，或在 quality_budgets.py 里说明下调理由（只允许有据下调）。")
        return 1
    print("\n✅ 分包覆盖率均达标")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
