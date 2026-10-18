# -*- coding: utf-8 -*-
"""核对 README 里的事实性数字（防漂移）。

README 里写"多少个验收脚本""多少个用例""data/xxx/"——这些数字没有任何机制核对，
改代码时它们不会跟着变，于是文档开始不可信。

本脚本只核对能从代码里算出来的事实，不核对叙述性内容（那靠人读）。
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_steps import catalog, gate_steps

# 在 GBK 控制台直接跑本脚本时，打印 ✅/中文会抛 UnicodeEncodeError ——
# 表现为「检查全过但退出码 1」（`ci.py` 用 PYTHONIOENCODING 掩盖了它）。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    # 旁路，刻意吞掉：不是所有 stdout 都支持 reconfigure（被重定向/被包装时会抛）。
    # 这只是"让打印别因编码失败"的尽力而为 —— 失败就按原编码走，不该阻断检查本身。
    pass

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


def _ci_acceptance_scripts() -> int:
    """读 ci_steps 清单里的验收脚本数（不是目录里有多少个）。"""
    src = (ROOT / "scripts" / "ci_steps.py").read_text(encoding="utf-8")
    block = src.split("ACCEPTANCE = [", 1)[1].split("]", 1)[0]
    return len([x for x in re.findall(r'"(acceptance_\w+)"', block)])


def _test_method_count() -> int:
    total = 0
    for f in (ROOT / "tests").glob("test_*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                total += 1
    return total


def _path_segments(node: ast.AST) -> list[str]:
    """把 `a / "x" / "y"` 这类路径拼接式解析成字符串段列表（引号段按出现顺序）。"""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _path_segments(node.left) + _path_segments(node.right)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    return []


def _data_dirs() -> list[str]:
    """`data/` 下代码里实际用到的一级子目录名（不是「当前磁盘上存在」的那些）。

    判据必须以代码为准：这些子目录在代码里都真的用，只是按需惰性创建，
    清理 `data/` 之后磁盘上就没有了。运行期目录是状态，不是事实；
    取代码里的引用，才能在「全新克隆（什么都没有）」与「跑过一轮」两种情况下都成立。
    磁盘上真实存在的目录另外并入，万一有代码之外的子目录也不会漏报。

    只取路径链的第一段：`data_root / "temp" / "file_backup"` 里只有 `temp` 是
    `data/` 的一级子目录，`file_backup` 嵌在它下面。把链上每一段都当成一级子目录，
    会要求文档写 `data/file_backup/` —— 一个并不存在的路径。

    判据走 AST：要判定的问题是「这个字符串是不是拼在数据根后面的路径段」，
    正则只能近似（`root = getattr(store, "data_root", None)`、`skills = root / "inbox"`
    都会被误捕，而误捕会让检查器去要求文档写一个不存在的 `data/inbox/`）。
    AST 直接看表达式形状：左侧是数据根（`data_root` 变量，或已知的目录形参），
    右侧是 `/ "字面量"`。
    """
    #: 这些形参的缺省值是数据根下的路径，形状与 `data_root / "xxx"` 等价
    PARAM_NAMES = {
        "storage_dir", "titles_dir", "backup_root", "recycle_root",
        "backups_dir", "recycle_dir", "workspace_root", "sessions_dir", "cache_dir",
    }
    #: 数据根本身的变量名（用于认 `data_root / "xxx"`）
    ROOT_NAMES = {"data_root", "DATA_ROOT"}
    names: set = set()
    for src in sorted((ROOT / "agent").rglob("*.py")):
        try:
            tree = ast.parse(src.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                first = _path_segments(node)
                if not first:
                    continue
                # 只看最外层拼接的第一段（它才是 data/ 的直接子目录）
                left = node.left
                is_root = ((isinstance(left, ast.Name) and left.id in ROOT_NAMES)
                           or (isinstance(left, ast.Attribute) and left.attr in ROOT_NAMES))
                if is_root:
                    names.add(first[0])
            elif isinstance(node, ast.keyword) and node.arg in PARAM_NAMES:
                segs = _path_segments(node.value) if node.value is not None else []
                if segs:
                    names.add(segs[0])
    d = ROOT / "data"
    if d.is_dir():
        names.update(p.name for p in d.iterdir() if p.is_dir())
    return sorted(n for n in names if n.islower() and 2 <= len(n) <= 24)


def _public_docs() -> str:
    """README 与 `docs/` 下全部公开文档拼成的一份文本。

    事实性数字写在 README 或 docs 里都算数 —— 检查器只管数字对不对，
    不管它写在哪个文件。`docs/` 整体不进版本库时返回的只有 README，
    此时匹配不到会如实报错而不是静默放行。
    """
    parts = [README.read_text(encoding="utf-8")]
    docs = ROOT / "docs"
    if docs.is_dir():
        for f in sorted(docs.rglob("*.md")):
            parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def check(readme: str, acceptance: int, tests: int,
          data_dirs: list[str], steps: int, gates: int) -> list[str]:
    """核对文档事实；返回问题列表（空 = 一致）。纯函数，供负向用例直接调用。"""
    problems: list[str] = []

    # ① 流水线步数与门禁数
    m = re.search(r"流水线 (\d+) 步", readme)
    if m is None:
        problems.append("README 与 docs 里都找不到「流水线 N 步」，检查器无法核对")
    elif int(m.group(1)) != steps:
        problems.append(f"文档说流水线 {m.group(1)} 步，ci.py 实际跑 {steps} 步")

    m = re.search(r"(\d+) 项门禁", readme)
    if m is None:
        problems.append("README 与 docs 里都找不到「N 项门禁」，检查器无法核对")
    elif int(m.group(1)) != gates:
        problems.append(f"文档说 {m.group(1)} 项门禁，ci.py 实际跑 {gates} 项")

    # ② 验收脚本数
    m = re.search(r"→ 单测 → (\d+) 个验收脚本", readme)
    if m is None:
        problems.append("README 与 docs 里都找不到「→ 单测 → N 个验收脚本」，检查器无法核对")
    elif int(m.group(1)) != acceptance:
        problems.append(f"文档说 {m.group(1)} 个验收脚本，ci.py 实际跑 {acceptance} 个")

    # ③ 用例数
    # 匹配不到必须报错：只写 `if m and …` 的话，README 一旦改措辞
    # （例如把"个用例"写成"个"），这里就静默放行 —— 检查器自己失效却报"一致"。
    m = re.search(r"单元测试（(\d+) 个用例）", readme)
    if m is None:
        problems.append("README 与 docs 里都找不到「单元测试（N 个用例）」，检查器无法核对")
    elif int(m.group(1)) != tests:
        problems.append(f"文档说 {m.group(1)} 个用例，实际 {tests} 个")

    # ④ data/ 子目录名（README 里出现的每个 data/xxx 都必须是真实目录）
    mentioned = set(re.findall(r"data/([a-z_]+)/", readme))
    real_dirs = set(data_dirs)
    if real_dirs:
        wrong = sorted(mentioned - real_dirs)
        if wrong:
            problems.append(f"文档提到代码里用不到的 data 子目录：{wrong}"
                            f"（代码里用到 {sorted(real_dirs)}）")
        missing = sorted(real_dirs - mentioned)
        if missing:
            problems.append(f"文档漏掉代码里用到的 data 子目录：{missing}")
    return problems


def main() -> int:
    readme = _public_docs()
    real = _ci_acceptance_scripts()
    real_tests = _test_method_count()
    real_dirs = _data_dirs()
    steps = len(catalog())
    gates = len(gate_steps())
    problems = check(readme, real, real_tests, real_dirs, steps, gates)

    if problems:
        print("事实性数字漂移：")
        for p in problems:
            print(f"  [FAIL] {p}")
        print()
        print("修法：改文档里的数字/目录名，而不是改这个脚本。")
        return 1
    print(f"✅ 文档事实一致（流水线 {steps} 步 / 门禁 {gates} 项、"
          f"验收脚本 {real} 个、用例 {real_tests} 个、"
          f"data 子目录 {len(real_dirs)} 个）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
