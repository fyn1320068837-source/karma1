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

    rule_id: str
    trigger: str          # 描述什么触发的（"Bash sleep 30"）
    snippet: str          # 上下文片段
    suggested_fix: str    # 给 Agent 看的修复建议

    # 向后兼容 alias — 旧代码用 hit.sticky_id 仍可读 (v0.6.0 移除)
    @property
    def sticky_id(self) -> str:
        return self.rule_id


class CheckFn(Protocol):
    def __call__(self, **_) -> CheckHit | None: ...
