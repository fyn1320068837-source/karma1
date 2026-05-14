"""session_state IO + 状态跟踪测试。"""

from __future__ import annotations

from karma.session_state import SessionState, load, save


def test_round_trip(tmp_path):
    s = SessionState(session_id="abc")
    s.record_read("/tmp/a.py")
    s.record_read("/tmp/b.py")
    s.record_edit("/tmp/a.py")
    s.record_bash("pytest tests/", "==== 10 passed in 0.1s ====")
    s.record_bash("ls", "a.txt b.txt")
    save(s, base_dir=tmp_path)

    loaded = load("abc", base_dir=tmp_path)
    assert loaded.read_files == {"/tmp/a.py", "/tmp/b.py"}
    assert loaded.edit_files == ["/tmp/a.py"]
    assert len(loaded.recent_bash) == 2
    assert loaded.recent_bash[0].is_test_cmd
    assert loaded.recent_bash[0].output_passed
    assert not loaded.recent_bash[1].is_test_cmd


def test_has_read(tmp_path):
    s = SessionState(session_id="s")
    s.record_read("/tmp/x.py")
    assert s.has_read("/tmp/x.py")
    assert not s.has_read("/tmp/y.py")


def test_has_recent_test_pass(tmp_path):
    s = SessionState(session_id="s")
    s.record_bash("ls", "a")
    s.record_bash("pytest", "10 passed")
    assert s.has_recent_test_pass()


def test_has_recent_test_pass_failed_not_counted(tmp_path):
    s = SessionState(session_id="s")
    s.record_bash("pytest", "1 failed, 2 passed")
    assert not s.has_recent_test_pass()


def test_has_recent_test_pass_no_test(tmp_path):
    s = SessionState(session_id="s")
    s.record_bash("ls -la", "files...")
    assert not s.has_recent_test_pass()


def test_has_recent_test_pass_survives_many_non_test_bashes(tmp_path):
    """测试通过后跑 N 次普通 Bash 仍算通过 — 不受计数窗口限制。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "10 passed in 0.1s")
    for i in range(20):
        s.record_bash(f"ls dir{i}", "files")
    assert s.has_recent_test_pass()


def test_has_recent_test_pass_invalidated_after_edit(tmp_path):
    """测试通过后改了代码 → 通过证据失效（代码变了没重测）。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "10 passed")
    assert s.has_recent_test_pass()
    s.record_edit("/tmp/x.py")
    assert not s.has_recent_test_pass(), "Edit 后应该失效"


def test_has_recent_test_pass_after_edit_then_retest(tmp_path):
    """改代码后重新测试通过 → 又算通过。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "10 passed")
    s.record_edit("/tmp/x.py")
    assert not s.has_recent_test_pass()
    s.record_bash("pytest", "10 passed")
    assert s.has_recent_test_pass()


def test_zero_errors_in_output_not_failed(tmp_path):
    """pytest 输出 '0 errors' 不应误认为 failed。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "75 passed in 0.05s, 0 errors, 0 warnings")
    assert s.has_recent_test_pass(), "0 errors 不算 fail"


def test_traceback_is_failed(tmp_path):
    """Python traceback 应被认成 failed。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "Traceback (most recent call last):\n  File ...")
    assert not s.has_recent_test_pass()


def test_pytest_failed_line_is_failed(tmp_path):
    """pytest 单测失败行 'FAILED tests/...' 应被认成 failed。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "FAILED tests/test_x.py::test_y - AssertionError")
    assert not s.has_recent_test_pass()


def test_word_error_alone_not_failed(tmp_path):
    """单独 'error' 字眼（如帮助文本 'show errors' / 路径含 error）不算 failed。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest --show-errors", "10 passed in 0.1s")
    assert s.has_recent_test_pass()


# -------- background 任务输出 catch-up --------

def test_record_bg_task_then_catchup(tmp_path):
    """background 任务启动 → pending；任务完成 → catchup 读用户重定向 log。

    Claude Code 真实 tool_response 是 dict {stdout, stderr, backgroundTaskId, ...}。
    catchup 从 command 解析 `> /path` 重定向取真实输出。
    """
    s = SessionState(session_id="s")
    log_path = tmp_path / "bg.log"
    s.record_bash(
        f"pytest tests/ > {log_path} 2>&1",
        {"stdout": "", "stderr": "", "backgroundTaskId": "abc"},
        run_in_background=True,
    )
    # background 启动 stdout 是空，还没 PASS 信号
    assert not s.has_recent_test_pass()
    # 任务真完成，写入 log
    log_path.write_text("===== 99 passed in 0.05s =====")
    # catchup
    n = s.catchup_pending_bg()
    assert n == 1
    assert s.has_recent_test_pass()


def test_catchup_skips_missing_log(tmp_path):
    """log 文件还不存在 / 空 → 保留在 pending，不算通过。"""
    s = SessionState(session_id="s")
    log_path = tmp_path / "never_written.log"
    s.record_bash(
        f"pytest tests/ > {log_path} 2>&1",
        {"stdout": "", "backgroundTaskId": "abc"},
        run_in_background=True,
    )
    n = s.catchup_pending_bg()
    assert n == 0
    assert not s.has_recent_test_pass()


def test_bg_failed_task_catchup_marks_failed(tmp_path):
    """background 任务失败 → catchup 读到 FAILED → 不算通过。"""
    s = SessionState(session_id="s")
    log_path = tmp_path / "bg.log"
    s.record_bash(
        f"pytest tests/ > {log_path} 2>&1",
        {"stdout": "", "backgroundTaskId": "abc"},
        run_in_background=True,
    )
    log_path.write_text("FAILED tests/test_x.py::test_y\n1 failed, 5 passed")
    s.catchup_pending_bg()
    assert not s.has_recent_test_pass()


def test_bg_no_redirect_no_pending(tmp_path):
    """background 任务命令没有 > 重定向 → pending 不能定位 output file，跳过 record。

    （catchup 没有可读的真实输出，evidence check 无法接到通过证据 — 用户应该总是
    重定向 background 任务的 stdout）。
    """
    s = SessionState(session_id="s")
    s.record_bash(
        "pytest tests/",
        {"stdout": "", "backgroundTaskId": "abc"},
        run_in_background=True,
    )
    assert s.pending_bg_tasks == []


def test_bg_dict_with_stdout_passed_synchronous(tmp_path):
    """run_in_background=False 时 tool_response dict 的 stdout 字段被正确读取。"""
    s = SessionState(session_id="s")
    s.record_bash(
        "pytest tests/",
        {"stdout": "===== 99 passed in 0.05s =====", "stderr": ""},
        run_in_background=False,
    )
    assert s.has_recent_test_pass()


def test_parse_redirect_target():
    """从 shell 命令字符串解析 > 重定向路径。"""
    from karma.session_state import _parse_redirect_target
    assert _parse_redirect_target("pytest > /tmp/x.log") == "/tmp/x.log"
    assert _parse_redirect_target("pytest > /tmp/x.log 2>&1") == "/tmp/x.log"
    assert _parse_redirect_target("pytest 2>&1 > /tmp/x.log") == "/tmp/x.log"
    assert _parse_redirect_target("pytest >> /tmp/x.log") == "/tmp/x.log"
    assert _parse_redirect_target("pytest tests/") is None
    # 不要被 fd 重定向（2>&1）误捕
    assert _parse_redirect_target("pytest 2>&1") is None


def test_write_implies_read_for_same_file(tmp_path):
    """Write 一个文件后，has_read 应为 True — Agent 写过的内容自己当然知道。

    post_tool_use hook 对 Write/NotebookEdit 既 record_edit 也 record_read，
    避免后续 Edit 同文件被 read_first 多余拦。
    """
    # 这个测试验证 has_read 逻辑 — 真实 record_read 由 post_tool_use 触发
    s = SessionState(session_id="s")
    s.record_edit("/x/new.py")
    s.record_read("/x/new.py")  # 模拟 post_tool_use 对 Write 做的事
    assert s.has_read("/x/new.py")


def test_load_missing_returns_empty(tmp_path):
    loaded = load("never-exists", base_dir=tmp_path)
    assert loaded.read_files == set()
    assert loaded.recent_bash == []


def test_session_id_with_unsafe_chars(tmp_path):
    """session_id 含特殊字符 → 清洗成文件名安全。"""
    s = SessionState(session_id="/var/some/path with spaces")
    s.record_read("/tmp/a")
    save(s, base_dir=tmp_path)
    # 加载用同样 id 应该能拿到
    loaded = load("/var/some/path with spaces", base_dir=tmp_path)
    assert loaded.read_files == {"/tmp/a"}
