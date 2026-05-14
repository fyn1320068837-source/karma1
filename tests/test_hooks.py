"""Hook entrypoints — input/output 集成测试。"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import yaml

from karma.hooks import post_tool_use, stop, user_prompt_submit
from karma import session_state


def _patch_paths(monkeypatch, tmp_path: Path, sticky_items: list[dict] | None = None):
    """让 hook 用 tmp 目录的 sticky/violations 文件。"""
    sticky_path = tmp_path / "sticky.yaml"
    violations_path = tmp_path / "violations.jsonl"
    if sticky_items is not None:
        sticky_path.write_text(yaml.safe_dump(sticky_items, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr("karma.sticky.DEFAULT_PATH", sticky_path)
    monkeypatch.setattr("karma.violations.DEFAULT_PATH", violations_path)
    return sticky_path, violations_path


def test_user_prompt_submit_no_sticky_passthrough(monkeypatch, tmp_path, capsys):
    """sticky.yaml 不存在 → 输出空 JSON（无 additionalContext）。"""
    _patch_paths(monkeypatch, tmp_path, sticky_items=None)
    payload = json.dumps({"prompt": "你好", "session_id": "s"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = user_prompt_submit.main()
    captured = capsys.readouterr()
    assert rc == 0
    out = json.loads(captured.out)
    assert out == {}


def test_user_prompt_submit_injects_sticky_as_context(monkeypatch, tmp_path, capsys):
    _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {"id": "test-rule", "preference": "用长期方案", "violation_keywords": ["补丁"]},
    ])
    payload = json.dumps({"prompt": "开始吧", "session_id": "s"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = user_prompt_submit.main()
    captured = capsys.readouterr()
    assert rc == 0
    out = json.loads(captured.out)
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "UserPromptSubmit"
    ctx = hso["additionalContext"]
    assert "[karma sticky" in ctx
    assert "用长期方案" in ctx


def test_user_prompt_submit_handles_bad_yaml(monkeypatch, tmp_path, capsys):
    """sticky.yaml 配置错 → stderr 报错，输出 passthrough（空 JSON）。"""
    sticky_path = tmp_path / "sticky.yaml"
    sticky_path.write_text("- {{ this is not valid yaml", encoding="utf-8")
    monkeypatch.setattr("karma.sticky.DEFAULT_PATH", sticky_path)
    monkeypatch.setattr("karma.violations.DEFAULT_PATH", tmp_path / "violations.jsonl")
    payload = json.dumps({"prompt": "你好", "session_id": "s"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = user_prompt_submit.main()
    captured = capsys.readouterr()
    assert rc == 0
    out = json.loads(captured.out)
    assert out == {}
    assert "karma:" in captured.err


def test_stop_reads_transcript_and_detects(monkeypatch, tmp_path, capsys):
    """Stop hook 读 transcript 文件，扫最后 assistant message 中违反。"""
    _, violations_path = _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {"id": "no-patch", "preference": "no patches", "violation_keywords": ["先打个补丁"]},
    ])
    # 准备假 transcript
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("\n".join([
        json.dumps({"type": "user", "message": {"content": "你来修一下"}}),
        json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "让我先打个补丁快速搞定"}
                ]
            }
        }),
    ]), encoding="utf-8")
    payload = json.dumps({
        "session_id": "test-session",
        "transcript_path": str(transcript),
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = stop.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert violations_path.exists()
    lines = violations_path.read_text(encoding="utf-8").splitlines()
    assert any(json.loads(ln)["sticky_id"] == "no-patch" for ln in lines)
    assert "⚠️ karma" in captured.err


def test_stop_no_transcript_no_op(monkeypatch, tmp_path, capsys):
    _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {"id": "no-patch", "preference": "x", "violation_keywords": ["补丁"]},
    ])
    payload = json.dumps({"session_id": "s", "transcript_path": "/nonexistent"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = stop.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out) == {}


def test_post_tool_use_write_records_read(monkeypatch, tmp_path, capsys):
    """Write 文件后 post_tool_use 既 record_edit 也 record_read —
    Agent 写过的内容自己知道，后续 Edit 同文件不该被 read_first 多余拦。
    """
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    payload = json.dumps({
        "session_id": "write_then_edit",
        "tool_name": "Write",
        "tool_input": {"file_path": "/x/new.py", "content": "x = 1"},
        "tool_response": "File created successfully",
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = post_tool_use.main()
    assert rc == 0
    # 验证 state 文件里 read_files 含 /x/new.py
    state = session_state.load("write_then_edit", base_dir=tmp_path)
    assert "/x/new.py" in state.read_files, "Write 应该同时 record_read"
    assert "/x/new.py" in state.edit_files


def test_post_tool_use_edit_does_not_imply_read(monkeypatch, tmp_path, capsys):
    """Edit 只改部分内容 → 不该 record_read（read_first 仍要拦未读 Edit）。"""
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    payload = json.dumps({
        "session_id": "edit_only",
        "tool_name": "Edit",
        "tool_input": {"file_path": "/x/existing.py", "old_string": "a", "new_string": "b"},
        "tool_response": "ok",
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = post_tool_use.main()
    assert rc == 0
    state = session_state.load("edit_only", base_dir=tmp_path)
    assert "/x/existing.py" not in state.read_files, "Edit 不应自动 record_read"
    assert "/x/existing.py" in state.edit_files
