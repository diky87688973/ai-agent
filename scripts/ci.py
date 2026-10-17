#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一条命令跑完全部校验（CI 入口）。

三层检查、全部单测、全部验收脚本的顺序固定在这里，避免漏跑任何一项。

## 顺序的由来

1. **依赖方向**（`check_imports`）与 **架构洁癖**（`check_architecture_hygiene`）——
   先跑它们：分层错了、跨层偷私有名、内核点名插件，后面的结果都不值得看；
   接着 **ruff 静态检查**（未定义名/未使用导入这类真 bug）与 **静默异常检查**
   （静默吞异常全部已说明：要么写了判据、要么属已登记惯用法；具体条数以该脚本输出为准）——这些都是"秒级、抓真问题"的，放最前面；
2. **文档与注册表一致性**（`check_readme` / `check_catalog`）—— 文档数字漂了、
   装配集与注册文件漂了，都会让后面的验证失真；
3. **单元测试**；
4. **验收脚本**（行为等价）—— 最慢的放最后。

任一步非零退出即停（`--keep-going` 可改为跑完全部再汇总）。

验收脚本返回 **2** 表示"本机跑不了"（例：要真模型凭据而 `config.ini` 是 gitignore 的），
按**跳过**处理、不算失败 —— 与"跑了但没通过"（1）区分开。跳过项在结尾单独列出。

## 用法

    python scripts/ci.py                 # 全跑，遇错即停
    python scripts/ci.py --keep-going    # 全跑，最后汇总
    python scripts/ci.py --fast          # 跳过验收脚本
    python scripts/ci.py --list          # 只列出会跑什么
"""
from __future__ import annotations

import argparse
import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

# 控制台编码兜底：Windows 中文控制台默认 GBK，输出里有 ✅/❌ 等字符，
# 直接 print 会 UnicodeEncodeError 把本脚本自己弄崩。
# 这里显式把 stdout/stderr 设成 UTF-8（Python 3.7+ 支持 reconfigure）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[union-attr]
    except Exception:
        # **旁路，刻意吞掉**：设不了编码就保持原样继续跑——总比因为
        # "打印不了勾号"而整个校验脚本崩掉强。
        pass

#: 本清单决定 CI 真正跑哪些验收脚本；脚本名与 `scripts/` 下的文件名必须对应，
#: 否则该步直接报"文件不存在"而整条 CI 停下。
#:
#: **不含 `acceptance_ui.py`**：它断言的自定义三栏界面在现役壳里不存在
#: （`id="frame"` / `sidebarCol` / …），跑它必然失败，与产品质量无关。
#: 该脚本位于 `scripts/retired/`，其中记录了它不列入本清单的原因。
ACCEPTANCE = [
    "acceptance_batch_a", "acceptance_batch_b", "acceptance_batch_c",
    "acceptance_batch_d", "acceptance_batch_e", "acceptance_batch_f",
    "acceptance_mvp2", "acceptance_mvp3", "acceptance_phase3",
    "acceptance_web",
]

#: 验收脚本"本机跑不了"的退出码（例：`acceptance_mvp3` 要真模型凭据，
#: 而 `config.ini` 是 gitignore 的 —— 克隆到 CI 上必然没有）。
#:
#: 与"跑了但没通过"（1）严格区分：缺凭据是环境不满足，不是产品有问题；
#: 混为一谈会让 CI 常红，于是没人再看它。
SKIPPED = 2


def _data_files() -> set:
    """工程 `data/` 下当前的文件（相对路径集合）—— CI 前后各取一次，比出新增。"""
    d = ROOT / "data"
    if not d.is_dir():
        return set()
    return {str(p.relative_to(ROOT)) for p in d.rglob("*") if p.is_file()}


def _steps(fast: bool) -> list[tuple[str, list[str]]]:
    # ⚠️ 写盘类测试/验收默认会落进工程 `data/`。
    # 这里把**数据根**指到一个临时目录：跑完 CI 工程目录保持干净。
    # `build_app` 只在**没显式传 data_root** 时读这个环境变量，
    # 所以显式注入的用例（`test_core` 等）行为完全不变。
    _tmp_data = tempfile.mkdtemp(prefix="fan_ci_data_")
    os.environ["AI_AGENT_DATA_ROOT"] = _tmp_data
    atexit.register(shutil.rmtree, _tmp_data, True)
    steps: list[tuple[str, list[str]]] = [
        ("依赖方向", [PY, "scripts/check_imports.py"]),
        ("架构洁癖", [PY, "scripts/check_architecture_hygiene.py"]),
        ("静态检查", [PY, "-m", "ruff", "check", "agent", "tests", "scripts"]),
        ("Python 下限", [PY, "scripts/check_python_floor.py"]),
        ("UI JS 自检", [PY, "scripts/check_ui_js.py"]),
        ("静默异常", [PY, "scripts/check_silent_except.py", "--all-strict"]),
        ("README 一致性", [PY, "scripts/check_readme.py"]),
        # 「确认」有两种含义（review 确认 / 用户确认），`confirm_id` 也是
        # 同名不同物（预览快照 ID / 宿主确认单 ID）。文案含糊**不报错、只把模型带偏**，
        # 功能测试抓不到，只能靠文案断言。
        ("确认文案无歧义", [PY, "scripts/check_confirm_wording.py"]),
        # 该步检查注释里是否留有"谁提出的 / 哪一轮发现的 / 当时代码怎么坏"这类过程叙述。
        ("注释文案", [PY, "scripts/check_comment_style.py"]),
        ("注册表一致性", [PY, "scripts/check_catalog.py"]),
        ("单元测试", [PY, "-m", "unittest", "discover",
                      "-s", "tests", "-p", "test_*.py", "-t", str(ROOT / "tests")]),
    ]
    if not fast:
        steps += [(name.replace("_", " "), [PY, f"scripts/{name}.py"])
                  for name in ACCEPTANCE]
    return steps


def _run(label: str, cmd: list[str]) -> tuple[str, str]:
    """跑一步，返回 `(状态, 报告行)`；状态是 `"ok"` / `"failed"` / `"skipped"`。"""
    t0 = time.perf_counter()
    # **必须给子进程也指定 UTF-8**：本文件顶部的 `reconfigure` 只护住
    # 自己的 stdout/stderr，**对子进程无效**。Windows 中文控制台默认 GBK，
    # 而门禁脚本会打印 `✅`（`U+2705` 在 GBK 里没有）→ 子进程自己在**成功路径上**
    # `UnicodeEncodeError` 崩溃，返回码 1，于是后面的单测与验收脚本**一步都不会执行**，
    # 却得到一份"全过"的报告。
    #
    # 子进程编码与这里 `encoding="utf-8"` 的读取必须对齐：两边不一致时，
    # 失败输出会变乱码、只剩 stderr 一行，连"哪个文件违规"都看不到。
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    dt = time.perf_counter() - t0
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == SKIPPED:
        # 脚本自己声明"这台机器上跑不了"，附上原因（末行），不当失败。
        reason = (out.strip().splitlines() or [""])[-1][:80]
        return "skipped", f"{dt:6.2f}s  SKIP  {label}（{reason}）"
    ok = proc.returncode == 0
    tail = ""
    if not ok:
        # 只留关键行：失败时信息在末尾，全量刷屏反而看不见
        lines = [x for x in out.splitlines()
                 if "FAIL" in x or "ERROR" in x or "Error" in x or "Traceback" in x]
        tail = "\n".join((lines or out.splitlines())[-12:])
    return ("ok" if ok else "failed"), (
        f"{dt:6.2f}s  {'OK  ' if ok else 'FAIL'}  {label}" + (f"\n{tail}" if tail else ""))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="跑完全部校验")
    ap.add_argument("--keep-going", action="store_true", help="出错也继续，最后汇总")
    ap.add_argument("--fast", action="store_true", help="跳过验收脚本")
    ap.add_argument("--list", action="store_true", help="只列出会跑什么")
    args = ap.parse_args(argv)

    steps = _steps(args.fast)
    if args.list:
        for label, cmd in steps:
            print(f"  {label:16} {' '.join(cmd[1:])}")
        return 0

    print(f"=== 校验开始（{len(steps)} 步）===")
    data_before = _data_files()
    failed: list[str] = []
    skipped: list[str] = []
    for label, cmd in steps:
        status, line = _run(label, cmd)
        print("  " + line)
        if status == "skipped":
            skipped.append(label)
        elif status == "failed":
            failed.append(label)
            if not args.keep_going:
                print(f"\n❌ 在「{label}」失败，已停止（--keep-going 可跑完）")
                return 1

    if failed:
        print(f"\n❌ 失败 {len(failed)} 项：{', '.join(failed)}")
        return 1
    if skipped:
        print(f"\n⚠️ 跳过 {len(skipped)} 项（本机环境不满足，非产品问题）："
              f"{', '.join(skipped)}")
    # **比对 CI 前后的 `data/` 文件集**：数据根本身已指向临时目录
    # （见 `_steps` 顶部），所以正常情况下这里是 0；
    # 若不为 0，说明某条测试路径没走 `default_data_root()` —— 列出来便于定位。
    if not args.fast:
        left = sorted(_data_files() - data_before)
        if left:
            print(f"\n⚠️ 工程 `data/` 多了 {len(left)} 个文件"
                  f"（不是运行期数据，删掉即可）：")
            for p in left[:10]:
                print(f"     {p}")
            if len(left) > 10:
                print(f"     …还有 {len(left) - 10} 个")
        else:
            print("\n✅ 工程 `data/` 无新增文件")

    passed = len(steps) - len(skipped)
    print(f"\n✅ 通过 {passed} 步" + (f"，跳过 {len(skipped)} 步" if skipped else "（全部）"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
