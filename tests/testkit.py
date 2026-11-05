# -*- coding: utf-8 -*-
"""测试共用的小工具。"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

# 测试 auth 根：不让没有 store 的装配把目录落到 cwd 或工程 data/。
_AUTH_TEST_ROOT = tempfile.TemporaryDirectory(prefix="ai_agent_auth_")


def local_auth(app: Any) -> Any:
    """测试服务的显式本机免登录 auth；生产入口不提供该旁路。"""
    from agent.config import DEFAULT_CONFIG_PATH
    from agent.shell.web.auth import AuthRuntime

    root = getattr(app, "data_root", None)
    if not root:
        root = getattr(getattr(app, "store", None), "data_root", None)
    if not root:
        root = _AUTH_TEST_ROOT.name
    auth = AuthRuntime.load(Path(root), config_path=DEFAULT_CONFIG_PATH, host="127.0.0.1")
    auth.local_bypass = True
    auth.authenticator.local_bypass = True
    return auth


def isolate_plugins(case: Any) -> Path:
    """把插件层清空（清单 + 插件根两处），交回临时根。

    插件层有两条入口，两个都得堵：
      装载清单 `plugins.ini` 决定哪些插件进入清单；
      插件根 `plugins/` 决定哪些片段被合并进装配　—— 片段合并只排除清单里
      `enabled = 0` 的插件，未列出的默认启用，所以只清清单等于没隔离。
    漏掉任一入口，装配就会带上本机 `plugins/multi_model` 的模型目录，
    真的建出厂商 provider 并出网（`[anthropic] stop_reason=` 就是逐迹）。

    插件根必须 patch `agent.boot.bootstrap.default_plugins_root`：那里是
    from-import，改 `agent.config` 里的同名函数对已导入的引用不起作用。

    返回临时根：需要显式传 `plugins_dir` 的用例用它（`root / "plugins"`）。
    `case` 可以是用例实例（`self`，清理挂 addCleanup）或类（`cls`，挂
    addClassCleanup），因此在 `setUp` 与 `setUpClass` 里都能直接调。
    """
    add = case.addClassCleanup if isinstance(case, type) else case.addCleanup
    tmp = tempfile.mkdtemp(prefix="ai_agent_noplugins_")
    add(shutil.rmtree, tmp, True)
    base = Path(tmp)
    empty = base / "plugins.ini"
    empty.write_text("; 空清单：本测试不需要任何插件\n", encoding="utf-8")
    plugins_root = base / "plugins"
    plugins_root.mkdir()
    for patcher in (
        mock.patch("agent.config.DEFAULT_PLUGINS_PATH", empty),
        mock.patch("agent.boot.bootstrap.default_plugins_root",
                   lambda: plugins_root),
    ):
        patcher.start()
        add(patcher.stop)
    return base


#: 旧名字：语义就是「插件层清空」。别名而非第二份实现。
no_plugins = isolate_plugins


def isolate_data(case: Any) -> Path:
    """把数据根隔离到临时目录，交回该目录。

    `build_app()` 的缺省数据根在 `agent.boot.bootstrap` 内部解析（该模块把
    `agent.config.default_data_root` from-import 成了本地名字），所以必须
    patch `agent.boot.bootstrap.default_data_root`：
    只 patch `agent.config` 里的同名函数对已 from-import 的引用不起作用。

    实测依据：不 patch 时临时根不会被创建；patch `agent.config.default_data_root`
    同样不创建；patch `agent.boot.bootstrap.default_data_root` 后临时根出现
    `plugin/ session/ wake/` 且唤醒调度成为锁 owner。

    不隔离的后果：测试落仓库 `data/`，与运行中的主进程抢 `data/wake/scheduler.lock`，
    并在仓库 `data/logs/errors.log` 里刷满抢锁记录。

    入口层（`agent/entry/*`、`agent/shell/web/server.py`）各自 from-import 了
    同名函数；测试若走到入口函数需另行处理。当前测试都经 `build_app`，不经过它们。

    `case` 可以是用例实例或类（与 `isolate_plugins` 一致）。返回临时数据根。
    """
    add = case.addClassCleanup if isinstance(case, type) else case.addCleanup
    tmp = tempfile.mkdtemp(prefix="ai_agent_data_")
    add(shutil.rmtree, tmp, True)
    root = Path(tmp) / "data"
    patcher = mock.patch("agent.boot.bootstrap.default_data_root", lambda: root)
    patcher.start()
    add(patcher.stop)
    return root
