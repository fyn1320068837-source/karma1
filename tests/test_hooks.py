"""Hook entrypoints — input/output 集成测试。"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import yaml

from karma.hooks import post_response, user_prompt_submit


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
    """sticky.yaml 不存在 → 原样输出 user_text。"""
    _patch_paths(monkeypatch, tmp_path, sticky_items=None)
    payload = json.dumps({"user_text": "你好"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = user_prompt_submit.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == "你好"


def test_user_prompt_submit_injects_sticky(monkeypatch, tmp_path, capsys):
    _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {"id": "test-rule", "preference": "用长期方案", "violation_keywords": ["补丁"]},
    ])
    payload = json.dumps({"user_text": "开始吧"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = user_prompt_submit.main()
    captured = capsys.readouterr()
    assert rc == 0
    out = captured.out
    assert "[karma sticky" in out
    assert "用长期方案" in out
    assert "[用户当前消息]" in out
    assert "开始吧" in out
    # sticky 在 user_text 前面
    assert out.index("用长期方案") < out.index("开始吧")


def test_user_prompt_submit_handles_bad_yaml(monkeypatch, tmp_path, capsys):
    """sticky.yaml 配置错 → stderr 报错但不阻断 user_text。"""
    sticky_path = tmp_path / "sticky.yaml"
    sticky_path.write_text("- {{ this is not valid yaml", encoding="utf-8")
    monkeypatch.setattr("karma.sticky.DEFAULT_PATH", sticky_path)
    monkeypatch.setattr("karma.violations.DEFAULT_PATH", tmp_path / "violations.jsonl")
    payload = json.dumps({"user_text": "你好"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = user_prompt_submit.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert "你好" in captured.out
    assert "karma:" in captured.err  # fail loud


def test_post_response_detects_and_writes(monkeypatch, tmp_path, capsys):
    sticky_path, violations_path = _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {"id": "no-patch", "preference": "no patches", "violation_keywords": ["先打个补丁"]},
    ])
    payload = json.dumps({
        "agent_response": "让我先打个补丁快速搞定",
        "session_id": "test-session",
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = post_response.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert violations_path.exists()
    lines = violations_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    v = json.loads(lines[0])
    assert v["sticky_id"] == "no-patch"
    assert v["session_id"] == "test-session"
    # stderr 通知
    assert "⚠️ karma" in captured.err


def test_post_response_no_violation_no_write(monkeypatch, tmp_path):
    sticky_path, violations_path = _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {"id": "no-patch", "preference": "x", "violation_keywords": ["先打个补丁"]},
    ])
    payload = json.dumps({"agent_response": "好的，我用长期方案", "session_id": "s"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = post_response.main()
    assert rc == 0
    assert not violations_path.exists()
