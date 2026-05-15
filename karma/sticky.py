"""Deprecated module — use ``karma.rule`` instead. Will be removed in v0.6.0.

2026-05-15 起 karma.sticky 改名 karma.rule（用户原话「将 sticky 字样改成 rule」）。
此 compat shim 让老 import `from karma.sticky import ...` 继续工作 — 但每次
import 会发 stderr deprecation warning。

迁移：
- ``from karma.sticky import Sticky`` → ``from karma.rule import Rule``
- ``from karma.sticky import StickyConfigError`` → ``from karma.rule import RuleConfigError``
- ``from karma.sticky import MAX_STICKY`` → ``from karma.rule import MAX_RULES``

全部 alias 在 karma.rule 都保留向后兼容，所以 import 出来的对象等价。
"""

from __future__ import annotations

import sys
import warnings

# 跨 import 只 warn 一次，避免 hook 每秒触发 stderr 刷屏
_DEPRECATION_WARNED = False


def _warn_once() -> None:
    global _DEPRECATION_WARNED
    if _DEPRECATION_WARNED:
        return
    _DEPRECATION_WARNED = True
    print(
        "karma DeprecationWarning: `karma.sticky` 已改名 `karma.rule`，"
        "将在 v0.6.0 移除。更新 import 路径。",
        file=sys.stderr,
    )


_warn_once()

# Re-export 全部 karma.rule 公开符号（保留 Sticky / StickyConfigError / MAX_STICKY alias）
from karma.rule import (  # noqa: E402, F401
    DEFAULT_PATH,
    HARD_MAX,
    MAX_RULES,
    MAX_STICKY,
    Rule,
    RuleConfigError,
    Sticky,
    StickyConfigError,
    format_for_injection,
    load,
)

# 同时支持 `warnings.warn` 形式让程序化检测（pytest filterwarnings 等）也能抓到
warnings.warn(
    "`karma.sticky` is deprecated, use `karma.rule`. Removed in v0.6.0.",
    DeprecationWarning,
    stacklevel=2,
)
