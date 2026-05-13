"""violations.jsonl 读写 + 违反检测。"""

from __future__ import annotations

from pathlib import Path

from karma.sticky import Sticky
from karma.violations import Violation, append, detect, load_all, recent


def _make_sticky() -> list[Sticky]:
    return [
        Sticky(
            id="long-term",
            preference="用长期方案",
            violation_keywords=("先打个补丁", "硬编码"),
        ),
        Sticky(
            id="chinese-only",
            preference="用中文",
            violation_keywords=("F1", "precision"),
        ),
    ]


def test_detect_finds_violation() -> None:
    response = "让我先打个补丁快速解决"
    out = detect(response, _make_sticky(), session_id="s1", now=1000)
    assert len(out) == 1
    assert out[0].sticky_id == "long-term"
    assert out[0].trigger == "先打个补丁"
    assert "先打个补丁" in out[0].snippet


def test_detect_multiple_stickies() -> None:
    response = "用 F1 看，先硬编码一下"
    out = detect(response, _make_sticky(), now=1000)
    sids = {v.sticky_id for v in out}
    assert sids == {"long-term", "chinese-only"}


def test_detect_same_sticky_multiple_keywords_records_first() -> None:
    """同一 sticky 多关键词命中只记第一个。"""
    response = "先打个补丁，再硬编码一个"
    out = detect(response, _make_sticky(), now=1000)
    assert len(out) == 1
    assert out[0].sticky_id == "long-term"


def test_detect_case_insensitive() -> None:
    response = "用 f1 score"
    out = detect(response, _make_sticky(), now=1000)
    assert len(out) == 1
    assert out[0].sticky_id == "chinese-only"


def test_detect_empty_response() -> None:
    assert detect("", _make_sticky()) == []


def test_detect_no_violation() -> None:
    response = "好的，开始干活了"
    assert detect(response, _make_sticky()) == []


def test_append_and_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=1000, session_id="s1", sticky_id="r1", trigger="x", snippet="..."),
        Violation(ts=2000, session_id="s1", sticky_id="r2", trigger="y", snippet="..."),
    ]
    append(items, path=p)
    loaded = load_all(p)
    assert len(loaded) == 2
    assert loaded[0].ts == 1000
    assert loaded[1].sticky_id == "r2"


def test_recent_filters_old(tmp_path: Path) -> None:
    p = tmp_path / "violations.jsonl"
    # 一条 25h 前，一条 1h 前
    items = [
        Violation(ts=1000, session_id="s", sticky_id="old-rule", trigger="x", snippet="."),
        Violation(ts=1000 + 24 * 3600, session_id="s", sticky_id="new-rule", trigger="y", snippet="."),
    ]
    append(items, path=p)
    out = recent(p, window_sec=24 * 3600, now=1000 + 25 * 3600)
    assert "new-rule" in out
    assert "old-rule" not in out


def test_recent_takes_latest_ts_per_sticky(tmp_path: Path) -> None:
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=1000, session_id="s", sticky_id="r1", trigger="x", snippet="."),
        Violation(ts=2000, session_id="s", sticky_id="r1", trigger="x", snippet="."),
        Violation(ts=1500, session_id="s", sticky_id="r1", trigger="x", snippet="."),
    ]
    append(items, path=p)
    out = recent(p, window_sec=10000, now=3000)
    assert out["r1"] == 2000


def test_recent_no_file(tmp_path: Path) -> None:
    assert recent(tmp_path / "no.jsonl") == {}


def test_append_empty_list_noop(tmp_path: Path) -> None:
    p = tmp_path / "violations.jsonl"
    append([], path=p)
    assert not p.exists()
