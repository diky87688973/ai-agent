# -*- coding: utf-8 -*-
"""模块抽象父类（`ModuleBase`）：行为面只有 `execute`。

所有模块继承同一父类，由父类抽象行为接口；宿主只遍历模块列表，
逐个调用每个模块的 `execute`。
不同的规则接口就是不同的模块——模块身份由它需要的接口定义，
不由它在链上的位置定义。

## `execute` 是生成器

普通函数 + 返回值的形态做不到流式：

    `execute` 若是普通函数，它会跑完整个流才返回；
    宿主只能在它返回之后才拿到控制权 → 期间产出的事件全堆在内存里
    → 观察面（UI）在整段生成期间收不到任何增量
    （界面一直"思考中"，直到回合结束才一次性闪出全部内容）。

所以 `execute` 写成生成器：`yield` 事实，`return` 控制信号。三条要点不变：

- 父类锁行为（只有 `execute`）、返回四态/五态控制信号；
- 数据走事件（`yield` 出来的就是事件）、控制走返回值（`return`）；
- 宿主只遍历、只读控制信号，不理解任何模块语义。

宿主侧的用法（`StopIteration.value` 拿到控制信号）由 `chain.py` 的 `_Pass` 封装。
"""
from __future__ import annotations

from typing import Any, Iterator

from agent.core.ports import Ports


class ModuleBase:
    """模块抽象父类：子类实现 `execute`（生成器）。

    子类契约（不由断言强制，靠评审守）：

    - 只经端口访问外界：不持有上下文对象，不 import 别的模块；
    - 数据 `yield`、控制 `return`：返回值里不带数据；控制信号也不被吞掉；
    - 无跨回合状态：需要跨轮存活的信息一律落事实（`ports.log`）。
      模块实例可能在多回合之间复用，靠实例字段记忆会让"重启后恢复"失效。
    """

    #: 诊断用名；不参与调度（链的顺序由装配方决定）
    name: str = "module"

    #: 声明本模块需要哪些端口（装配方可据此校验；可选）
    requires: tuple = ()

    def execute(self, ports: Ports) -> Iterator[Any]:
        """执行一步：`yield` 事实，`return Outcome`。

        本方法不阻塞等待外部输入。需要外部输入就 `return Outcome.suspend(...)`
        ——宿主会交出控制权，恢复时另起一个回合。
        """
        raise NotImplementedError(f"{type(self).__name__} 必须实现 execute(ports)")
        yield  # pragma: no cover - 让子类实现天然成为生成器

    # ── 供装配与诊断 ───────────────────────────────────────

    def describe(self) -> str:
        """一行描述（`/health` 与日志用）。"""
        needs = ("，需要端口：" + "、".join(self.requires)) if self.requires else ""
        return f"{self.name}{needs}"

    def __repr__(self) -> str:  # pragma: no cover - 诊断用
        return f"<{type(self).__name__} name={self.name!r}>"
