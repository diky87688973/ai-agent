# -*- coding: utf-8 -*-
"""控制信号（`Outcome`）：模块执行结果的唯一形状。

四态，一个都不能少：

- `ok`      我这一步做完了，不要求下一趟
- `next`    我这一步做完了，但请宿主再跑一趟（"我还需要下一回合"）
- `halt`    立刻停止整条链（错误、或被拒绝）
- `suspend` 挂起，把控制权交回宿主（等外部输入），恢复后另起一个回合

"成功"与"请求续行"分成两个值：若合成一个，每条链都会永远要求续行，
宿主直接撞上护栏上限（`max_passes`）。"能不能就这样结束"与"要不要下一回合"
是两件事。

`suspend` 是终态，不是等待：它是终态——宿主循环就此退出，内存里不留任何
游标；恢复靠新回合循环 + 从事实源重建，所以它不需要携带"回到哪"之类的位置信息。

本类型只承载控制信号：数据走事件（`Ports.emit`）。返回值只回答"接下来怎么办"。
把正文、用量、进度塞进返回值，就等于让宿主理解模块的内部——那正是要避免的。
"""
from __future__ import annotations

from dataclasses import dataclass

#: 四种状态的字面量（供外部按值判断，例如从持久化记录里恢复控制流时）
OK = "ok"
NEXT = "next"
HALT = "halt"
SUSPEND = "suspend"
#: 用户主动停止（协作式取消）。不是 `halt`——`halt` 是"出错了、被拒了"，
#: 而 `stopped` 是"用户叫停"。观察面要能分辨这两件事（前者该报错、后者不该）。
STOPPED = "stopped"

STATUSES = (OK, NEXT, HALT, SUSPEND, STOPPED)


@dataclass(frozen=True)
class Outcome:
    """模块执行结果：只是控制信号。

    冻结（`frozen=True`）：构造后不再被修改，模块与宿主都按只读使用。
    """

    status: str
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"未知的控制状态：{self.status!r}（应为 {STATUSES} 之一）")

    # ── 常用构造 ──────────────────────────────────────────

    @staticmethod
    def ok() -> "Outcome":
        """没有后续诉求：本步做完即可收尾。"""
        return Outcome(OK)

    @staticmethod
    def next() -> "Outcome":
        """有后续诉求：本步做完后还需再跑一趟。"""
        return Outcome(NEXT)

    @staticmethod
    def halt(reason: str = "") -> "Outcome":
        """立刻停止整条链。"""
        return Outcome(HALT, reason)

    @staticmethod
    def suspend(reason: str = "") -> "Outcome":
        """挂起：交回控制权（终态，不阻塞）。"""
        return Outcome(SUSPEND, reason)

    @staticmethod
    def stopped(reason: str = "") -> "Outcome":
        """用户主动停止（终态）。与 `halt` 分开，好让观察面分辨"叫停"与"出错"。"""
        return Outcome(STOPPED, reason)

    # ── 便捷判定（宿主与测试都读它）──────────────────────

    @property
    def is_terminal(self) -> bool:
        """是否让宿主停止本回合循环（`halt` / `suspend` / `stopped` 都是终态）。"""
        return self.status in (HALT, SUSPEND, STOPPED)

    @property
    def wants_another_pass(self) -> bool:
        """是否请求宿主再跑一趟。"""
        return self.status == NEXT
