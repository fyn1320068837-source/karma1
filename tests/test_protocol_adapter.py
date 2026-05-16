"""v0.9.15: cross-backend protocol adapter — tool_name 归一化 + output shape.

Background: codex GPT-5.5 cross-model audit + WebFetch 官方文档 (Gemini hooks
ref / Codex hooks docs) 双验证发现 karma 之前假设三家 backend「字段同名兼容」
有 2 个 critical bug：

1. Gemini BeforeTool output shape 必须顶层 `{decision, reason}` 不是 Claude
   `{hookSpecificOutput: {permissionDecision: ...}}` — karma 之前在 Gemini 下
   拦截全失效（写 violation 但 tool 真执行）
2. Gemini tool_name 用 `run_shell_command` / `read_file` / 等；Codex 编辑用
   `apply_patch` — karma checks 用 Claude `Bash`/`Read`/`Edit`/`Write` 比较，
   完全不识别 → 全部 checks 跳过

protocol_adapter.py 修这个：input normalize + output shape 分流。本测试锁
不变量：未来 PR 加新 Gemini tool / 改 output shape 必须经过 adapter。
"""

from __future__ import annotations

import json

from karma.backends.protocol_adapter import (
    detect_backend,
    emit_allow,
    emit_deny,
    normalize_tool_name,
)


def test_detect_backend_gemini_by_event_name():
    """Gemini stdin payload 含 hook_event_name in {BeforeAgent/BeforeTool/...}."""
    assert detect_backend({"hook_event_name": "BeforeTool"}) == "gemini"
    assert detect_backend({"hook_event_name": "AfterTool"}) == "gemini"
    assert detect_backend({"hook_event_name": "BeforeAgent"}) == "gemini"
    assert detect_backend({"hook_event_name": "AfterAgent"}) == "gemini"


def test_detect_backend_claude_codex_by_event_name():
    """Claude / Codex stdin payload 含 hook_event_name in PreToolUse/Stop/..."""
    assert detect_backend({"hook_event_name": "PreToolUse"}) == "claude"
    assert detect_backend({"hook_event_name": "PostToolUse"}) == "claude"
    assert detect_backend({"hook_event_name": "Stop"}) == "claude"
    assert detect_backend({"hook_event_name": "UserPromptSubmit"}) == "claude"
    # 缺字段 default claude（Codex / Claude 是 majority case 且 output shape 一致）
    assert detect_backend({}) == "claude"


def test_normalize_tool_name_gemini_to_claude_canonical():
    """v0.9.15 critical fix: Gemini tool_name 归一化到 karma canonical（Claude 风格）"""
    gemini_payload = {"hook_event_name": "BeforeTool"}
    assert normalize_tool_name("run_shell_command", gemini_payload) == "Bash"
    assert normalize_tool_name("read_file", gemini_payload) == "Read"
    assert normalize_tool_name("read_many_files", gemini_payload) == "Read"
    assert normalize_tool_name("write_file", gemini_payload) == "Write"
    assert normalize_tool_name("replace", gemini_payload) == "Edit"
    assert normalize_tool_name("edit", gemini_payload) == "Edit"
    assert normalize_tool_name("edit_file", gemini_payload) == "Edit"
    # 未识别 tool（如 Gemini MCP tool）透传
    assert normalize_tool_name("mcp_some_other_tool", gemini_payload) == "mcp_some_other_tool"


def test_normalize_tool_name_codex_apply_patch_to_edit():
    """v0.9.15 critical fix: Codex apply_patch（编辑入口）归一化成 Edit 让
    long_term / testset / bypass_karma 扫 tool_input.command 时真触发。
    之前 apply_patch 漏所有编辑型 check → evidence check 被绕过。"""
    codex_payload = {"hook_event_name": "PreToolUse"}
    assert normalize_tool_name("apply_patch", codex_payload) == "Edit"
    # Codex Bash 已是 canonical
    assert normalize_tool_name("Bash", codex_payload) == "Bash"


def test_normalize_tool_name_claude_passthrough():
    """Claude 原生 tool_name 已是 canonical，透传不变。"""
    claude_payload = {"hook_event_name": "PreToolUse"}
    for tn in ("Bash", "Read", "Edit", "Write", "NotebookEdit", "Agent"):
        assert normalize_tool_name(tn, claude_payload) == tn


def test_emit_deny_gemini_shape_top_level():
    """v0.9.15 critical fix: Gemini deny 必须顶层 {decision, reason}
    （官方 https://geminicli.com/docs/hooks/reference/ 要求）
    karma 之前用 Claude `hookSpecificOutput` shape Gemini 不识别 → 拦截全失效。
    """
    gemini_payload = {"hook_event_name": "BeforeTool"}
    out = emit_deny("test reason", gemini_payload)
    parsed = json.loads(out)
    assert parsed.get("decision") == "deny", f"Gemini deny 必须顶层 decision: 实际 {parsed}"
    assert parsed.get("reason") == "test reason"
    # 不该有 Claude 风格 hookSpecificOutput（Gemini 不识别）
    assert "hookSpecificOutput" not in parsed


def test_emit_deny_claude_codex_shape_hookSpecificOutput():
    """Claude + Codex 用 hookSpecificOutput 新格式（Codex 文档明确支持）."""
    claude_payload = {"hook_event_name": "PreToolUse"}
    out = emit_deny("test reason", claude_payload)
    parsed = json.loads(out)
    hso = parsed.get("hookSpecificOutput", {})
    assert hso.get("permissionDecision") == "deny"
    assert hso.get("permissionDecisionReason") == "test reason"
    assert hso.get("hookEventName") == "PreToolUse"
    # 不该有 top-level decision（避免 schema 模糊）
    assert "decision" not in parsed


def test_emit_allow_gemini_passthrough():
    """Gemini default 允许，无需显式 allow — 输出空对象 {}."""
    gemini_payload = {"hook_event_name": "BeforeTool"}
    out = emit_allow(gemini_payload)
    assert json.loads(out) == {}


def test_emit_allow_claude_explicit_allow():
    """Claude/Codex 用 hookSpecificOutput.permissionDecision: allow 显式表态."""
    claude_payload = {"hook_event_name": "PreToolUse"}
    out = emit_allow(claude_payload)
    hso = json.loads(out).get("hookSpecificOutput", {})
    assert hso.get("permissionDecision") == "allow"


def test_pre_tool_use_under_gemini_payload_emits_gemini_shape(tmp_path, monkeypatch):
    """v0.9.15 集成 lockdown: 跑 pre_tool_use main() 用 Gemini-style payload，
    verify output 真是 Gemini decision shape 而非 Claude hookSpecificOutput。

    构造场景：违反规则的 Bash 命令 + Gemini BeforeTool 入口 → karma 应该
    输出 `{decision: "deny", reason: ...}` 顶层（Gemini 能识别真拦截）。
    """
    import io
    import sys
    from karma.hooks import pre_tool_use

    # patch rules.yaml + violations.jsonl 到 tmp
    sticky_path = tmp_path / "rules.yaml"
    sticky_path.write_text(
        "- id: long-term-fundamental\n"
        "  preference: 用长期方案不打补丁\n"
        "  violation_keywords: ['先打个补丁']\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("karma.rule.DEFAULT_PATH", sticky_path)
    monkeypatch.setattr("karma.violations.DEFAULT_PATH", tmp_path / "v.jsonl")
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)

    # Gemini-style payload: hook_event_name=BeforeTool + Gemini tool_name
    # 关键 keyword 在 command 裸字面（不在 quote 内，否则 strip_shell_quoted_literals
    # 会按 design 剥掉避免 echo 假阳）
    gemini_payload = {
        "session_id": "gemini-test",
        "hook_event_name": "BeforeTool",
        "tool_name": "run_shell_command",  # Gemini name → normalize 到 Bash
        "tool_input": {"command": "先打个补丁 fast"},
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(gemini_payload)))

    # 捕获 stdout
    captured_stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_stdout)
    rc = pre_tool_use.main()
    out = captured_stdout.getvalue()
    parsed = json.loads(out.strip().split("\n")[-1])  # 最后一行是 hook output

    assert rc == 0
    # 关键 assert: Gemini 下输出 top-level decision 不是 hookSpecificOutput
    assert parsed.get("decision") == "deny", (
        f"Gemini BeforeTool 拦截应输出 top-level decision，实际：{parsed}\n"
        f"如果出 hookSpecificOutput → adapter wiring 没生效，Gemini 不识别 → "
        f"karma 拦截在 Gemini 下完全失效（v0.9.15 修的核心 bug）"
    )
    assert "reason" in parsed


def test_post_tool_use_under_gemini_payload_advances_read_state(tmp_path, monkeypatch):
    """v0.9.15 集成 lockdown (codex GPT-5.5 Major #3 推荐): 跑 post_tool_use main()
    用 Gemini AfterTool payload（tool_name=read_file），verify state.read_files
    真推进。如果 normalize_tool_name 没接通 post_tool_use 入口，read_file
    不映射到 Read，record_read 不调用 → state.read_files 空 → 后续 read_first
    check 在 Gemini 下永远把任何 Edit 算「没读过」拦掉。

    这条 lockdown 锁住「Gemini 真实集成」不变量 — adapter wiring 必须
    在 post_tool_use 入口生效。
    """
    import io
    import json
    import sys
    from karma.hooks import post_tool_use
    from karma import session_state

    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    # 预设空 state
    state = session_state.SessionState(session_id="gemini-aftertool")
    session_state.save(state, base_dir=tmp_path)

    # Gemini AfterTool payload: tool_name=read_file → 应该 normalize 成 Read
    gemini_payload = {
        "session_id": "gemini-aftertool",
        "hook_event_name": "AfterTool",
        "tool_name": "read_file",  # Gemini name → 必须 normalize 到 Read
        "tool_input": {"file_path": "/tmp/test-gemini-read.py"},
        "tool_response": "file contents here",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(gemini_payload)))
    captured_stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_stdout)
    rc = post_tool_use.main()

    assert rc == 0
    # 关键 assert: Gemini read_file 真推进 state.read_files
    reloaded = session_state.load("gemini-aftertool", base_dir=tmp_path)
    assert reloaded.has_read("/tmp/test-gemini-read.py"), (
        "Gemini read_file 没归一化到 Read → record_read 漏 → state.read_files 空 → "
        "后续 read_first check 在 Gemini 下永远拦 Edit 假阳。v0.9.15 adapter wiring 没生效。"
    )
