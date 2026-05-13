"""violations.jsonl 读写 + 违反检测。

violations.jsonl 是 append-only 文件，每行一条 JSON：
{"ts": int, "session_id": str, "sticky_id": str, "trigger": str, "snippet": str}
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from karma.sticky import Sticky

DEFAULT_PATH = Path.home() / ".claude" / "karma" / "violations.jsonl"
RECENT_WINDOW_SEC = 24 * 3600  # 24h 内的违反在 sticky 注入时标 ⚠️
SNIPPET_RADIUS = 30  # 触发词前后多少字符当 snippet


@dataclass(slots=True, frozen=True)
class Violation:
    ts: int
    session_id: str
    sticky_id: str
    trigger: str
    snippet: str

    def to_json(self) -> str:
        return json.dumps({
            "ts": self.ts,
            "session_id": self.session_id,
            "sticky_id": self.sticky_id,
            "trigger": self.trigger,
            "snippet": self.snippet,
        }, ensure_ascii=False)


def detect(
    response: str,
    sticky_list: list[Sticky],
    session_id: str = "unknown",
    now: int | None = None,
) -> list[Violation]:
    """扫 response 看违反哪些 sticky。

    简单 substring 匹配（不区分大小写）。同一 sticky 多关键词命中只记第一个。
    """
    if not response or not sticky_list:
        return []
    now = now or int(time.time())
    response_lower = response.lower()
    out: list[Violation] = []
    for s in sticky_list:
        for kw in s.violation_keywords:
            idx = response_lower.find(kw.lower())
            if idx < 0:
                continue
            start = max(0, idx - SNIPPET_RADIUS)
            end = min(len(response), idx + len(kw) + SNIPPET_RADIUS)
            out.append(Violation(
                ts=now,
                session_id=session_id,
                sticky_id=s.id,
                trigger=kw,
                snippet=response[start:end],
            ))
            break  # 同一 sticky 多关键词命中只记第一个
    return out


def append(violations: list[Violation], path: Path | None = None) -> None:
    """append 违反到 jsonl。path=None 时用 module-level DEFAULT_PATH。"""
    if not violations:
        return
    if path is None:
        path = DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for v in violations:
            f.write(v.to_json() + "\n")


def recent(
    path: Path | None = None,
    window_sec: int = RECENT_WINDOW_SEC,
    now: int | None = None,
    tail_lines: int = 500,
) -> dict[str, int]:
    """返回最近违反过的 sticky_id → 最近 ts dict。

    只读尾部 N 行（违反频率不会太高，500 行够）。
    """
    if path is None:
        path = DEFAULT_PATH
    if not path.exists():
        return {}
    now = now or int(time.time())
    cutoff = now - window_sec
    out: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-tail_lines:]
    except OSError:
        return {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            ts = int(d.get("ts", 0))
            sid = d.get("sticky_id", "")
        except (json.JSONDecodeError, ValueError):
            continue
        if ts >= cutoff and sid:
            out[sid] = max(out.get(sid, 0), ts)
    return out


def load_all(path: Path | None = None) -> list[Violation]:
    """读全部 violations（CLI stats 用）。"""
    if path is None:
        path = DEFAULT_PATH
    if not path.exists():
        return []
    out: list[Violation] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            out.append(Violation(
                ts=int(d["ts"]),
                session_id=d.get("session_id", "unknown"),
                sticky_id=d["sticky_id"],
                trigger=d.get("trigger", ""),
                snippet=d.get("snippet", ""),
            ))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return out
