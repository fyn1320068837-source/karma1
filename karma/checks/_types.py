"""violation_check 公共类型 — 抽出来避免子模块 ↔ __init__ 循环依赖。

子模块从这里 import CheckHit 而不是从 karma.checks，
__init__.py 再从这里 import 后 export 到 karma.checks 命名空间。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CheckHit:
    """violation_check 函数的返回 — 一次违反命中。"""

    sticky_id: str
    trigger: str          # 描述什么触发的（"Bash sleep 30"）
    snippet: str          # 上下文片段
    suggested_fix: str    # 给 Agent 看的修复建议


class CheckFn(Protocol):
    def __call__(self, **_) -> CheckHit | None: ...
