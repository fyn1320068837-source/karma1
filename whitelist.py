"""vulture whitelist — names used by tests but not visible to vulture
(因为 CI vulture 只扫 karma/, 不扫 tests/, 看不到 test 引用).

跑 vulture 时把这个文件一起喂进去:
    vulture karma/ whitelist.py --min-confidence 60
"""
from karma import signals as _signals

# tests/test_signals.py 用 reset_cache 隔离测试间的 lru_cache 状态
_signals.reset_cache
