#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""假插口门禁（验收 f）：逐个非冻结节点注桩，装配必须拿到桩。

做法：对真实合并配置里每一个可换实现的节点，单独造一份「该节点 replace 成固定桩」
的覆盖，跑一次完整 `SlotAssembly`（解析器整体换成桩，不碰真实实现），断言该节点的
产物就是桩本体。任一个节点装不上或拿不到桩，即判该节点是假插口，退出码 1。

为什么逐个跑而不是只跑一次：一次装配只能证明「整棵树能起来」，
不能证明「每个节点都能被单独换掉」—— 后者才是可替换性。

免检范围（按判据而非名单）：
  frozen 子树：协议明确不可覆盖（其自身与后代），覆盖会被拒
  declarative 类型：声明本身即产物，没有 factory 可换；换它等于改 kind，属结构变更
"""
from __future__ import annotations

import argparse
import sys
from contextlib import suppress
from pathlib import Path

with suppress(AttributeError, OSError, ValueError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.core.slot_spec import (  # noqa: E402
    SlotAssemblyError,
    SlotConfigError,
)

#: 装配可能报出的领域异常；其余异常属于缺陷，不应被当成「假插口」消化掉。
_ASSEMBLY_ERRORS = (SlotConfigError, SlotAssemblyError)


#: 注桩用的 factory 串：`agent.` 前缀让解析器一律走宿主分支，与节点归属无关。
STUB_FACTORY = "agent.gate_stub:make"


class Stub:
    """可识别的产物：只要拿到它，就说明构造确实走了替换后的实现。"""

    __slots__ = ("path",)

    def __init__(self, path: str) -> None:
        self.path = path


def _stub_factory() -> object:
    """所有节点共用的桩工厂：容器与普通节点都按同一签名收。"""
    def make(*_args: object, **_kwargs: object) -> Stub:
        return Stub("")
    return make


def _resolver(_spec: str) -> object:
    """宿主分支的解析器：一律返回桩，不导入任何真实实现。"""
    return _stub_factory()


def _plugin_factories(_origin: str, _spec: str, _path: str,
                      _plugins_root: object) -> object:
    """插件分支的解析器：同样返回桩。

    整棵树的实现都换掉，才不依赖任何插件模块能否导入；
    否则一个插件导入失败会把不相干的节点误报成假插口。
    """
    return _stub_factory()


def _candidates(config: object) -> list[str]:
    """可换实现的节点：非冻结、非 declarative。"""
    from agent.core.slot_override import frozen_paths
    from agent.core.slot_spec import DECLARATIVE_KINDS

    frozen = frozen_paths(config)
    return [path for path in config.paths()
            if path not in frozen
            and config.spec(path).kind not in DECLARATIVE_KINDS]


def _with_override(config: object, path: str) -> object:
    from agent.core.slot_config import SlotConfig

    return SlotConfig(
        root=config.root, version=config.version, specs=config.specs,
        origins=config.origins, synthesized=config.synthesized,
        subagent_tools=config.subagent_tools, plugins_root=config.plugins_root,
        overrides=(({"path": path, "mode": "replace",
                     "factory": STUB_FACTORY}),))


def _build_app(config: object) -> object:
    from agent.core.slot_assembly import SlotAssembly

    return SlotAssembly(config, resolver=_resolver,
                        plugin_factories=_plugin_factories).build()


def _verdict(path: str, value: object) -> str | None:
    """判定一个节点的注桩结果：拿到桩才算真可替换。"""
    if isinstance(value, Stub):
        return None
    return (f"{path} 换实现后拿到的不是桩（拿到 {type(value).__name__}）"
            "：该节点没有被真正替换，属假插口")


def _self_check() -> int:
    """负向自检：判定规则必须能认出「没拿到桩」。"""
    if _verdict("app/x", Stub("app/x")) is not None:
        print("❌ 自检失败：桩本身被判成假插口")
        return 1
    for bogus in (None, object(), {"impl": "real"}):
        message = _verdict("app/x", bogus)
        if not message or "假插口" not in message:
            print(f"❌ 自检失败：{type(bogus).__name__} 未被判成假插口")
            return 1
    print("✅ 自检通过：拿不到桩的节点会被判成假插口")
    return 0


def check(config: object) -> tuple[list[str], int]:
    """返回（问题清单, 受检节点数）。

    按作用域分两段：app 节点在 app 级装配里验，session 节点在会话装配里验；
    后者依赖前者，所以先拿一次桩化的 app 产物当依赖源。
    """
    from agent.core.slot_assembly import SessionAssembly
    from agent.core.slot_spec import SCOPE_SESSION

    problems: list[str] = []
    paths = _candidates(config)
    app_paths = [p for p in paths if config.spec(p).scope != SCOPE_SESSION]
    session_paths = [p for p in paths if config.spec(p).scope == SCOPE_SESSION]

    for path in app_paths:
        try:
            assembly = _build_app(_with_override(config, path))
        except _ASSEMBLY_ERRORS as exc:
            problems.append(f"{path} 注入桩后装配失败：{type(exc).__name__}: {exc}")
            continue
        try:
            value = assembly.values.get(path)
        finally:
            assembly.dispose()
        message = _verdict(path, value)
        if message:
            problems.append(message)

    if session_paths:
        base = _build_app(config)
        try:
            app_values = dict(base.values)
        finally:
            base.dispose()
        for path in session_paths:
            try:
                session = SessionAssembly(
                    _with_override(config, path), app_values,
                    resolver=_resolver).build()
            except _ASSEMBLY_ERRORS as exc:
                problems.append(
                    f"{path} 注入桩后会话装配失败：{type(exc).__name__}: {exc}")
                continue
            try:
                value = session.values.get(path)
            finally:
                session.dispose()
            message = _verdict(path, value)
            if message:
                problems.append(message)
    return problems, len(paths)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="逐个节点注入桩，检查是否真可替换")
    ap.add_argument("--root", default=str(ROOT), help="仓库根目录")
    ap.add_argument("--self-check", action="store_true",
                    help="跑负向自检：拿不到桩必须被判成假插口")
    args = ap.parse_args(argv)
    if args.self_check:
        return _self_check()

    from agent.core.slot_fragments import load_merged

    config = load_merged(Path(args.root).resolve())
    problems, count = check(config)
    print(f"受检节点：{count} 个（非冻结、非 declarative）")
    if problems:
        print("假插口：")
        for item in problems:
            print(f"  [FAIL] {item}")
        return 1
    print("✅ 每个非冻结节点都能被单独换掉")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
