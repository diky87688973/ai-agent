#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""插口字段白名单门禁：只校验节点字段。

允许的名字从代码现算，不手抄：`SlotSpec(...)` 的关键字参数名 →
`dataclasses.fields(SlotSpec)`。集合外的名字一律失败并指文件行。新造词天然被挡：
靠的是「没登记就不存在」，不是一张越写越长的禁词表。

贡献 API 已随旧注册通道移除，本门禁不再校验它。

`--self-check` 造未登记参数的样本，门禁必须把它们抓出来；抓不到即退出码 1。
自检在门禁自身里跑，不依赖外部 fixture。
"""
from __future__ import annotations

import argparse
import ast
import sys
import uuid
from contextlib import suppress
from dataclasses import fields
from pathlib import Path

with suppress(AttributeError, OSError, ValueError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCAN_DIRS = ("agent", "plugins", "tests", "scripts")
SKIP_PARTS = ("__pycache__", "retired")

#: 权威节点声明类型的来源模块。只有从它导入的 `SlotSpec` 才受字段白名单约束：
#: 仓库里另有一个同名类（agent/capabilities/slot_registry.py），字段完全不同，
#: 按类名一律匹配会把它误判成本类型；按导入来源判定才是「同一个类」的真判据。
SPEC_MODULE = "agent.core.slot_spec"
SPEC_CLASS = "SlotSpec"


def registered_spec_params() -> set[str]:
    """节点允许的关键字名：字段表即白名单。"""
    from agent.core.slot_spec import SlotSpec

    return {item.name for item in fields(SlotSpec)}


def scan_source(rel: str, src: str, spec_params: set[str]) -> list[str]:
    """扫一份源码，返回问题列表。纯函数，供自检直接调用。"""
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [f"{rel}:{exc.lineno} 语法错误：{exc.msg}"]
    spec_names = _imported_spec_names(tree)
    problems: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        else:
            continue
        if name not in spec_names:
            continue
        for keyword in node.keywords:
            if keyword.arg is None or keyword.arg in spec_params:
                continue
            problems.append(
                f"{rel}:{keyword.value.lineno} {name} 出现未登记的关键字参数："
                f"{keyword.arg}（允许：{'、'.join(sorted(spec_params))}）")
    return problems


def _imported_spec_names(tree: ast.AST) -> set[str]:
    """本文件里绑定到权威节点类型上的名字（含别名）。"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == SPEC_MODULE:
            for alias in node.names:
                if alias.name == SPEC_CLASS:
                    names.add(alias.asname or alias.name)
    return names


def _unknown_name() -> str:
    """运行时随机未知名。不点名词：闭合白名单下「未登记」与具体拼写无关。"""
    return "zz_unknown_" + uuid.uuid4().hex[:10]


def _self_check(spec_params: set[str]) -> int:
    """负向自检加两条对照，样本均用运行时随机未知名。

    1 集合内真字段：从字段表现取一个，必须放行
    2 集合外随机串：节点与别名导入两处都必须被抓
    3 同名非权威类：必须不误判
    4 白名单来源换成「多一个随机字段」：门禁本体一行不改即跟随
    """
    header = f"from {SPEC_MODULE} import {SPEC_CLASS}\n"

    known = sorted(spec_params)[0]
    ok_sample = header + f'{SPEC_CLASS}(path="app/x", {known}=None)\n'
    if scan_source("<self-check-known>", ok_sample, spec_params):
        print(f"❌ 自检失败：集合内字段 {known} 被误判为未登记")
        return 1

    stranger = _unknown_name()
    node_sample = header + f'{SPEC_CLASS}(path="app/x", {stranger}=True)\n'
    if not any(stranger in item for item in
               scan_source("<self-check-node>", node_sample, spec_params)):
        print(f"❌ 自检失败：节点上未登记的 {stranger} 没有被抓出来")
        return 1
    alias_sample = (f"from {SPEC_MODULE} import {SPEC_CLASS} as Spec\n"
                    f'Spec(path="app/x", {stranger}=True)\n')
    if not any(stranger in item for item in
               scan_source("<self-check-alias>", alias_sample, spec_params)):
        print(f"❌ 自检失败：别名导入的未登记 {stranger} 没有被抓出来")
        return 1

    foreign_sample = (f'class {SPEC_CLASS}:\n    pass\n\n'
                      f'{SPEC_CLASS}(path="a", {stranger}=True)\n')
    if scan_source("<self-check-foreign>", foreign_sample, spec_params):
        print("❌ 自检失败：非权威模块的同名类被误判为权威节点类型")
        return 1

    newcomer = _unknown_name()
    widened_sample = header + f'{SPEC_CLASS}(path="app/x", {newcomer}=True)\n'
    if not scan_source("<self-check-widen-old>", widened_sample, spec_params):
        print("❌ 自检失败：旧白名单下该随机字段本应被拒，样本构造有误")
        return 1
    if scan_source("<self-check-widen-new>", widened_sample,
                   set(spec_params) | {newcomer}):
        print(f"❌ 自检失败：白名单加入 {newcomer} 后仍未放行（来源不可替换）")
        return 1

    print("✅ 自检通过："
          f"集合内字段（{known}）放行；"
          f"集合外随机串（{stranger}）在节点/别名两处都被抓；"
          "同名非权威类不误判；"
          f"白名单加 {newcomer} 后门禁不改即跟随")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="检查插口字段是否已登记")
    ap.add_argument("--self-check", action="store_true",
                    help="跑负向自检：未登记参数必须被抓")
    args = ap.parse_args(argv)

    spec_params = registered_spec_params()
    if args.self_check:
        return _self_check(spec_params)

    problems: list[str] = []
    scanned = 0
    for base in SCAN_DIRS:
        for f in (ROOT / base).rglob("*.py"):
            rel = f.relative_to(ROOT).as_posix()
            if any(p in rel for p in SKIP_PARTS):
                continue
            scanned += 1
            problems.extend(scan_source(
                rel, f.read_text(encoding="utf-8"), spec_params))
    print(f"扫描文件：{scanned}  已登记：节点 {len(spec_params)} 项")
    if problems:
        print("未登记参数：")
        for p in problems:
            print(f"  [FAIL] {p}")
        return 1
    print("✅ 无未登记参数")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
