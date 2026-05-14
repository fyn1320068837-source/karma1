"""假阴回归测试 — M3 第一波降假阳改动后，验证真违反仍被拦。

每个 case 是「真违反应当被任何一层（关键词 / 工程 check）捕获」。
红阶段：跑这些测试看 M3 第一波改动是否新增了假阴漏报。
"""

from __future__ import annotations

from karma.checks import REGISTRY
from karma.session_state import SessionState


# ============================================================
# #2 _FAIL_RE 假阴 — 自定义错误信号
# 直接验 BashSnapshot.output_failed（避免 has_recent_test_pass 初始 False 的 false-pass）
# ============================================================

def test_fail_signal_error_prefix():
    """'ERROR:' 行首前缀是明确的错误信号，output_failed 应为 True。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest tests/", "ERROR: collection failed\nE   ImportError: no module")
    snap = s.recent_bash[-1]
    assert snap.output_failed, "ERROR: 行首前缀应识别为失败"


def test_fail_signal_fatal_prefix():
    """'FATAL:' 行首是严重失败信号。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest tests/", "FATAL: unable to start session")
    snap = s.recent_bash[-1]
    assert snap.output_failed, "FATAL: 行首应识别为失败"


def test_fail_signal_n_errors_count():
    """'N error(s)' 计数（N >= 1）应识别为失败 — 跟 '0 errors' 区分开。"""
    s = SessionState(session_id="s")
    s.record_bash("go test ./...", "10 tests run, 3 errors")
    snap = s.recent_bash[-1]
    assert snap.output_failed, "'3 errors' (N>=1) 应识别为失败"


def test_fail_signal_zero_errors_still_passes():
    """反向：'0 errors' 不算失败（保留 M3 修复的语义）。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "5 passed in 0.1s, 0 errors")
    snap = s.recent_bash[-1]
    assert not snap.output_failed, "'0 errors' 不应算失败"
    assert s.has_recent_test_pass()


# ============================================================
# #4 关键词层放弃后 — Write/Edit 含意图注释 long_term 仍应拦
# ============================================================

def test_long_term_intent_comment_quick_fix():
    """Agent 在代码里写 '# 先打个补丁' 注释 → 真违反，工程层应拦。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/handler.py",
            "content": "def handle(req):\n    # 先打个补丁，下个 sprint 再优化\n    return req.legacy()",
        },
    )
    assert hit is not None, "「先打个补丁」注释应被识别为打补丁意图"


def test_long_term_intent_comment_workaround():
    """'workaround' 注释字面 → 真违反。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/handler.py",
            "content": "def f():\n    # workaround for upstream bug #123\n    return None",
        },
    )
    assert hit is not None, "「workaround」注释应被识别"


def test_long_term_intent_comment_临时方案():
    """中文「临时方案」注释 → 真违反。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/handler.py",
            "content": "def f():\n    # 临时方案，凑数应付 demo\n    pass",
        },
    )
    assert hit is not None, "「临时方案」中文注释应被识别"


# ============================================================
# #5 长名单 hint 假阴 — 全大写常量 + 多元素字符串列表
# ============================================================

def test_long_term_uppercase_constant_string_list():
    """常见真黑名单变量名（BAD_USERS / SPECIAL_IDS / KNOWN_BOTS）应被识别。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/filter.py",
            "content": 'BAD_USERS = ["spammer1", "bot2", "fake3", "abuser4", "shill5"]',
        },
    )
    assert hit is not None, "BAD_USERS 全大写常量 + 5 元素字符串列表应被识别为硬编码名单"


# ============================================================
# #6 testset 长 hash list 字面假阴
# ============================================================

def test_testset_gold_list_long_hash_literals():
    """gold_cases / eval_ids 等列表里写死 case ID 是真违反。"""
    fn = REGISTRY["no_testset_no_future_leakage"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/eval.py",
            "content": 'gold_cases = ["a1b2c3d4e5f6a7b8", "deadbeef12345678"]',
        },
    )
    assert hit is not None, "gold_cases 列表里长 hex 字面应被识别为测试集 case ID 写死"


# ============================================================
# #9 non_blocking 剥引号假阴 — bash -c '...' 间接执行
# ============================================================

def test_non_blocking_bash_c_sleep():
    """`bash -c 'sleep 30'` 是真要 sleep — 剥引号后字面被剥但意图仍是阻塞。"""
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(
        tool_name="Bash",
        tool_input={"command": "bash -c 'sleep 30 && echo done'"},
    )
    assert hit is not None, "bash -c 间接 sleep 仍应识别为阻塞"


def test_non_blocking_sh_c_pytest():
    """`sh -c 'pytest tests/'` 是真要跑长任务。"""
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(
        tool_name="Bash",
        tool_input={"command": "sh -c 'pytest tests/'"},
    )
    assert hit is not None, "sh -c 间接 pytest 仍应识别为长任务"


# ============================================================
# #3 描述上下文豁免 — tests/ 下真违反仍应否被拦的边界 case
# ============================================================

def test_tests_conftest_hardcoded_id_currently_exempt():
    """记录现状：tests/conftest.py 含真硬编码 ID 当前被豁免（descriptive context）。

    这个测试不 assert 拦或不拦 — 只记录当前行为。
    如果决定要在 conftest 里也拦（更严格），把 assert 改成 'is not None'。
    """
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/tests/conftest.py",
            "content": 'if request.param == "abc-def-12345678":\n    return "special"',
        },
    )
    # 当前：豁免 → hit is None。如果要更严格，改成 assert hit is not None
    assert hit is None, "tests/ 目录当前 catch-all 豁免（M3 决策）"
