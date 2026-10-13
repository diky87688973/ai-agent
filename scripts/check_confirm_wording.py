# -*- coding: utf-8 -*-
"""「确认」歧义自检：写盘链路涉及 confirm_id / 确认 的文案必须无歧义。

## 为什么需要这道检查

`commit_write` 在没有 review 确认时返回「预览尚未确认：请先完成确认，再凭同一 ID 提交」，
模型会把"确认"理解成**去问用户**，于是发起一次无效的 `user_confirm`；
用户确认后 `commit_write` 仍被拒 —— 解锁预览的入口只有 `review_conclusion`。

**「确认」有两种完全不同的含义，`confirm_id` 也是同名不同物**：

| 名字 | 门控（`quality_gate`） | `user_confirm` 工具 |
|---|---|---|
| `confirm_id` | **预览快照 ID**（解锁后凭它提交） | **宿主确认单 ID**（次段回显） |
| 「确认」 | **review 确认**（`review_conclusion` 解锁预览） | **用户确认**（停下来问用户） |

这类缺陷**不报错、不抛异常，只把模型带偏** —— 靠功能测试抓不到，只能靠文案断言。
所以本检查钉三类硬规则：

  ① 写盘链路的工具描述（`write_file` / `commit_write` / `review_conclusion`）
     要求出现 `review_conclusion` —— 否则模型不知道该找谁解锁；
  ② 门控拒绝文案必须给出**可执行的下一步**（工具名 + 参数名）；
  ③ 指引里**不得出现解释性内容**（说它"不是什么"、解释 id 含义…）。

用法：python scripts/check_confirm_wording.py（工程根运行）
退出码：0 = 指引合格；1 = 指引含糊或含解释性内容（含定位）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GATE = ROOT / "agent/mechanisms/quality_gate.py"
WRITE_FILE = ROOT / "agent/capabilities/builtin/write_file.py"
COMMIT_WRITE = ROOT / "agent/capabilities/builtin/commit_write.py"
REVIEW = ROOT / "agent/capabilities/builtin/review_conclusion.py"

#: 写盘链路必须点明解锁入口的文件
MUST_NAME_REVIEW = {
    WRITE_FILE: "write_file 的工具描述",
    COMMIT_WRITE: "commit_write 的工具描述",
    REVIEW: "review_conclusion 的工具描述",
}

#: 「只说确认、不说哪种」的含糊写法（出现在写盘链路文案里即判不合格）
VAGUE = (
    "请先完成确认",          # 只说"确认"不说哪种的典型含糊写法
    "确认后使用",
    "确认后用",
    "已确认的写预览",
)


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def check() -> list[str]:
    """返回问题列表（空 = 无歧义）。"""
    problems: list[str] = []

    # ── ① 写盘链路必须点明 review_conclusion ──
    for path, label in MUST_NAME_REVIEW.items():
        text = _read(path)
        if not text:
            problems.append(f"{label}：文件读不到（{path.relative_to(ROOT)}）")
            continue
        if "review_conclusion" not in text:
            problems.append(
                f"{label} 没有点明 `review_conclusion` —— "
                "模型将不知道「确认」该找谁，会误发起 `user_confirm`"
            )

    # ── ② 门控拒绝文案：给**可执行的下一步**（工具 + 参数）──
    gate = _read(GATE)
    m = re.search(r'if not rec\.get\("confirmed"\):(.*?)\n        args = ', gate, re.S)
    block = m.group(1) if m else ""
    if "review_conclusion" not in block:
        problems.append(
            "quality_gate.py 的拒绝文案没有告诉模型**下一步调哪个工具** —— "
            "只说「未解锁」而不给工具名，模型只能自己猜（会猜成 user_confirm）"
        )
    if "confirm_id" not in block:
        problems.append(
            "quality_gate.py 的拒绝文案没有告诉模型**要带哪个参数**（confirm_id）"
        )

    # ── ③ 写盘链路里不得出现含糊写法 ──
    for path, label in MUST_NAME_REVIEW.items():
        text = _read(path)
        for vague in VAGUE:
            if vague in text:
                ln = text[: text.find(vague)].count("\n") + 1
                problems.append(
                    f"{label} 第 {ln} 行出现含糊写法「{vague}」—— "
                    "「确认」有歧义，必须写明是 review 确认还是用户确认"
                )

    # ── ④ 指引里**不得有解释性内容** ──
    # 给模型看的文案是**行动指引**，不是说明文档。说它"不是什么"、
    # 解释某个 id 指什么，都是废话 —— 它要的是照着做。
    EXPLANATORY = (
        "不是等用户确认",
        "指的是",
        "不需要",
        "这是写盘链路里",
        "同名不同物",
    )
    targets = dict(MUST_NAME_REVIEW)
    targets[GATE] = "quality_gate.py 的拒绝文案"
    for path, label in targets.items():
        text = _read(path)
        for phrase in EXPLANATORY:
            if phrase in text:
                ln = text[: text.find(phrase)].count("\n") + 1
                problems.append(
                    f"{label} 第 {ln} 行出现解释性内容「{phrase}」—— "
                    "指引只写下一步做什么，不要写解释"
                )
    return problems


def main() -> int:
    problems = check()
    if problems:
        print("写盘指引自检：发现 %d 处问题" % len(problems))
        for p in problems:
            print(f"  [FAIL] {p}")
        print()
        print("修法：给模型看的文案只写**下一步做什么** —— 调哪个工具（`review_conclusion`）、"
              "带什么参数（`confirm_id` / `file_name` / `conclusion`）。"
              "不要写解释（说它不是什么、解释 id 含义），也不要含糊到让模型自己猜。")
        return 1
    print("写盘指引自检：✅ 指引可执行、无解释性内容"
          "（`review_conclusion` + 参数名已给全，未出现解释性表述）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
