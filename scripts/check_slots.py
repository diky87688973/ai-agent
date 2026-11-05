# -*- coding: utf-8 -*-
"""插口配置门禁：解析 plugin-slots.json 并跑装配器的全部静态校验。

默认只做静态检查，不 import 任何宿主模块：
路径全局唯一、依赖指向存在、同层 order 不重复、类型与工厂形状合法、
依赖可拓扑求值（成环即失败）、启动期节点不依赖会话级节点、attr 是合法标识符。

两条 factory 写法，只有这两种：

```text
宿主实现   agent.<点分模块>:<属性>    例：agent.boot.host_factories:make_plugin_host
插件实现   <点分相对模块>:<属性>      例：plugin:knowledge_lines（插件目录下 plugin.py）
                                      例：components:make_example（插件目录下 components.py）
```

宿主实现在任何 path 上都可用；插件相对名只允许出现在 `app/plugins/<名>/` 下。
插件相对名不带 `plugins.` 前缀、不带斜杠、不带 `.py`。装配期把点换成目录分隔符
再补 `.py` 落到插件目录内，见 `agent/boot/plugin_assembly.py` 的 `_factory`。

`--resolve` 额外真实 import 并检查可调用。插件实现无法在此解析（插件不是 Python
包），只统计并跳过，不算失败。默认关闭，不进 CI。

用法：python scripts/check_slots.py [--resolve]
退出码：0 = 通过；1 = 配置非法。
"""
from __future__ import annotations

import argparse
import importlib
import re
import sys
from pathlib import Path
from typing import Callable, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.core.slot_config import (  # noqa: E402
    SlotConfig,
    load_config,
    topo_order,
)
from agent.core.slot_fragments import load_merged  # noqa: E402
from agent.core.slot_spec import (  # noqa: E402
    HOST_OWNER,
    SCOPE_APP,
    SCOPE_SESSION,
    SlotConfigError,
)

CONFIG_PATH = ROOT / "plugin-slots.json"
#: 宿主实现的模块前缀。
HOST_PREFIX = "agent."
#: 插件节点的路径前缀；只有落在其下的节点才允许用插件相对模块名。
PLUGIN_PATH_PREFIX = "app/plugins/"
#: 不接受的写法：插件实现写成包前缀。
REJECTED_PREFIXES = ("plugins.",)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_QUALIFIED = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def is_host_factory(spec: str) -> bool:
    """factory 是否指向宿主实现。"""
    return str(spec or "").strip().partition(":")[0].startswith(HOST_PREFIX)


def is_plugin_path(path: str) -> bool:
    """节点是否位于插件主插口下。"""
    return str(path or "").strip().startswith(PLUGIN_PATH_PREFIX)


def factory_shape(spec: str, path: str = "", owner: str = HOST_OWNER) -> str:
    """校验 factory 的静态形状；返回空串表示合法，否则返回原因。

    插件相对模块名允许的判据是「这份资产归插件」，不是「节点路径在 app/plugins/ 下」：
    设置类资产由插件提供、但节点落在 `app/settings/**`（owner 为插件名），
    拿路径前缀判会把它们全判错。
    """
    text = str(spec or "").strip()
    module, sep, attr = text.partition(":")
    if not sep:
        return f"factory 必须是 module:attr：{text!r}"
    if not module or not attr:
        return f"factory 的 module 或 attr 为空：{text!r}"
    if ":" in attr:
        return f"factory 的 attr 段含冒号：{text!r}"
    if not _IDENTIFIER.match(attr):
        return f"factory 的 attr 不是合法标识符：{attr!r}"
    for bad in REJECTED_PREFIXES:
        if module.startswith(bad):
            return (f"factory 不接受 {bad} 前缀，插件实现写成点分相对模块名："
                    f"{module!r}")
    if "/" in module or "\\" in module:
        return f"factory 的 module 段不能含路径分隔符：{module!r}"
    if module.endswith(".py"):
        return f"factory 的 module 段不能带 .py：{module!r}"
    if not _QUALIFIED.match(module):
        return f"factory 的 module 不是合法点分名称：{module!r}"
    if module.startswith(HOST_PREFIX):
        return ""
    if is_plugin_path(path) or owner != HOST_OWNER:
        return ""
    return (f"只有插件自有资产可用插件相对模块名"
            f"（{PLUGIN_PATH_PREFIX} 下的节点，或 owner 为插件的节点），"
            f"其他节点须写 {HOST_PREFIX}*：{module!r}")


def factory_shapes(config: SlotConfig) -> List[str]:
    """逐节点校验 factory 形状；纯声明类型与无 factory 的容器不参与。

    本函数只判已给出 factory 的节点形状；「缺 factory」由加载期校验负责
    （`SlotConfig.parse` 与 `slot_fragments.load_merged` 都跑 `spec_problems`）。
    """
    problems: List[str] = []
    for spec in config.specs.values():
        if not spec.factory:
            continue
        reason = factory_shape(spec.factory, spec.path, spec.owner)
        if reason:
            problems.append(f"{spec.path}：{reason}")
    return problems


def _importer(spec: str) -> Callable[..., object]:
    module_name, _sep, attr = spec.partition(":")
    return getattr(importlib.import_module(module_name), attr)


def resolvable(config: SlotConfig, importer: Callable[[str], object] = _importer,
               ) -> Tuple[List[str], List[str], List[str]]:
    """真实解析宿主 factory；返回 (问题列表, 已解析的工厂, 跳过的插件工厂)。

    插件相对模块名不在这里解析：plugins 不是 Python 包，只能由插件加载器
    按插件目录注册后再解析。跳过并计数，不算失败。
    """
    problems: List[str] = []
    checked: List[str] = []
    skipped: List[str] = []
    cache: dict = {}
    for spec in config.specs.values():
        name = spec.factory
        if not name:
            continue
        if not is_host_factory(name):
            if name not in skipped:
                skipped.append(name)
            continue
        if name in cache:
            ok, reason = cache[name]
        else:
            try:
                target = importer(name)
            except (ImportError, AttributeError) as exc:
                ok, reason = False, f"{type(exc).__name__}: {exc}"
            else:
                ok = callable(target)
                reason = "" if ok else "属性不可调用"
            cache[name] = (ok, reason)
            checked.append(name)
        if not cache[name][0]:
            problems.append(f"{spec.path}：factory 无法解析（{name}）：{cache[name][1]}")
    return problems, checked, skipped


def scope_leaks(config: SlotConfig) -> List[str]:
    """启动期节点不得依赖会话级节点：后者在启动装配时还不存在。"""
    leaks: List[str] = []
    for spec in config.specs.values():
        if spec.scope != SCOPE_APP:
            continue
        for port, target in spec.requires.items():
            if config.specs[target].scope == SCOPE_SESSION:
                leaks.append(f"{spec.path} 的 {port} 指向会话级节点 {target}")
    return leaks


def static_paths(config: SlotConfig) -> List[str]:
    """静态片段不得含插件路径：插件的东西一律由插件自己的片段提供。"""
    return [f"静态片段不应包含插件路径：{spec.path}"
            for spec in config.specs.values()
            if spec.path.startswith(PLUGIN_PATH_PREFIX)]


def check(path: Path = CONFIG_PATH, *, resolve: bool = False,
          merged: bool = True,
          importer: Callable[[str], object] = _importer) -> List[str]:
    """返回问题列表；空列表表示配置可用。`resolve` 为真时额外做真实导入。

    `merged` 为真时额外校验「静态片段 + 全部插件片段」的合并结果：
    只查静态片段会让插件片段里的空壳、坏 factory、坏 requires、owner 越权
    永远无人把关，所以默认开。
    """
    if not path.is_file():
        return [f"配置不存在：{path}（运行 python scripts/gen_plugin_slots.py 生成）"]
    try:
        config = load_config(path)
    except SlotConfigError as exc:
        return [str(exc)]
    problems: List[str] = factory_shapes(config)
    problems.extend(static_paths(config))
    try:
        topo_order(config)
    except SlotConfigError as exc:
        problems.append(str(exc))
    problems.extend(scope_leaks(config))
    if resolve:
        found, _checked, _skipped = resolvable(config, importer)
        problems.extend(found)
    if merged:
        problems.extend(merged_problems(path.resolve().parent))
    return problems


def merged_problems(repo_root: Path) -> List[str]:
    """合并路径的校验问题。

    `load_merged` 的报错本身已按「路径 + 来源片段」措辞，这里只把异常转成
    问题列表，并对合并结果再跑一遍配置级校验，不重写它的判据。

    不查「静态片段不得含插件路径」：合并结果本来就包含插件路径。
    """
    try:
        config = load_merged(repo_root)
    except SlotConfigError as exc:
        return [f"合并片段校验未通过：{exc}"]
    except OSError as exc:
        return [f"合并片段读取失败：{repo_root}：{exc}"]
    problems: List[str] = factory_shapes(config)
    try:
        topo_order(config)
    except SlotConfigError as exc:
        problems.append(str(exc))
    problems.extend(scope_leaks(config))
    return problems


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="插口配置一致性检查")
    parser.add_argument("--resolve", action="store_true",
                        help="真实 import 宿主工厂并检查可调用（默认关闭）")
    parser.add_argument("--merged", dest="merged", action="store_true",
                        default=True,
                        help="额外校验静态片段与全部插件片段的合并结果（默认开）")
    parser.add_argument("--no-merged", dest="merged", action="store_false",
                        help="只校验静态片段")
    args = parser.parse_args(argv)
    problems = check(resolve=args.resolve, merged=args.merged)
    if problems:
        print("插口配置校验未通过：")
        for line in problems:
            print(" - " + line)
        return 1
    config = load_config(CONFIG_PATH)
    app = sum(1 for spec in config.specs.values() if spec.scope == SCOPE_APP)
    session = len(config.specs) - app
    scope = f"{len(config.specs)} 个节点（app {app} / session {session}）"
    if args.merged:
        scope += f"，合并后 {len(load_merged(CONFIG_PATH.parent).specs)} 个节点"
    suffix = ""
    if args.resolve:
        _found, checked, skipped = resolvable(config)
        suffix = f"，宿主工厂可解析 {len(checked)} 个"
        if skipped:
            suffix += f"，插件实现 {len(skipped)} 个（需插件加载器注册后才能解析）"
    print(f"插口配置有效：{scope}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
