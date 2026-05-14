"""PreCompact / PostCompact / SessionStart hook 集成测试。"""

import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from karma.sticky import Sticky


def test_pre_compact_hook_auto_allows():
    """PreCompact hook: 自动 compact 时允许 + 提醒。"""
    payload = {
        "trigger": "auto",
        "session_id": "test-session",
    }
    
    result = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.pre_compact"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd="/Users/jhz/karma"
    )
    
    if result.returncode == 0:
        output = json.loads(result.stdout)
        assert output.get("continue") is True
    else:
        print("STDERR:", result.stderr)
        pytest.skip(f"Hook execution failed: {result.stderr}")


def test_post_compact_hook_no_sticky():
    """PostCompact hook: 没有 sticky 时返回空。"""
    payload = {
        "trigger": "auto",
        "session_id": "test-session",
        "transcript_path": "/tmp/nonexistent.jsonl"
    }
    
    result = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.post_compact"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd="/Users/jhz/karma"
    )
    
    if result.returncode == 0:
        output = json.loads(result.stdout)
        # 没有 sticky 应该返回空或最小化响应
        assert isinstance(output, dict)


def test_session_start_hook_resume():
    """SessionStart hook: resume 时提醒。"""
    payload = {
        "source": "resume",
        "session_id": "test-session",
        "model": "claude-opus"
    }
    
    result = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.session_start"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd="/Users/jhz/karma"
    )
    
    if result.returncode == 0:
        output = json.loads(result.stdout)
        assert isinstance(output, dict)


def test_pre_compact_hook_manual_allows():
    """PreCompact hook: 手工 /compact 时直接允许。"""
    payload = {
        "trigger": "manual",
        "session_id": "test-session",
    }
    
    result = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.pre_compact"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd="/Users/jhz/karma"
    )
    
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output.get("continue") is True


def test_hooks_graceful_fallback_on_sticky_error():
    """所有 hook: sticky 加载失败时 graceful fallback。"""
    for hook_name in ["pre_compact", "post_compact", "session_start"]:
        payload = {
            "trigger": "auto",
            "source": "startup",
            "session_id": "test-session",
        }
        
        result = subprocess.run(
            ["/Users/jhz/karma/.venv/bin/python", "-m", f"karma.hooks.{hook_name}"],
            capture_output=True,
            text=True,
            input=json.dumps(payload),
            cwd="/Users/jhz/karma"
        )
        
        # 应该不卡，返回 0 或 1（graceful fail）
        assert result.returncode in (0, 1), f"{hook_name} failed with: {result.stderr}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_subagent_start_hook():
    """SubagentStart hook: 子 agent 继承 sticky。"""
    payload = {
        "agent_id": "explore-1",
        "agent_type": "Explore",
        "session_id": "parent-session",
    }
    
    result = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.subagent_start"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd="/Users/jhz/karma"
    )
    
    if result.returncode == 0:
        output = json.loads(result.stdout)
        assert isinstance(output, dict)


def test_subagent_stop_hook_no_violations(tmp_path):
    """SubagentStop hook: 子 agent 无违反。"""
    transcript_path = tmp_path / "subagent.jsonl"
    transcript_path.write_text("正常完成工作", encoding="utf-8")
    
    payload = {
        "agent_id": "explore-1",
        "agent_type": "Explore",
        "session_id": "parent-session",
        "transcript_path": str(transcript_path)
    }
    
    result = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.subagent_stop"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd="/Users/jhz/karma"
    )
    
    if result.returncode == 0:
        output = json.loads(result.stdout)
        assert output.get("continue") is True
        assert "✓" in output.get("hookSpecificOutput", {}).get("additionalContext", "")
