"""Stop hook — Agent 响应完成后扫违反。

Claude Code 实际协议:
- stdin payload: {session_id, transcript_path, cwd, ...}（没有 response 字段）
- 要扫 response 需要读 transcript_path JSONL 文件取最后一条 assistant message
- stdout: {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "..."}}
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from karma import session_state
from karma.checks import run_checks
from karma.notify import notify
from karma.sticky import StickyConfigError, load
from karma.violations import Violation, append, count_recent, count_recent_turns, detect

# 累积告警 default 阈值（fallback，实际从 karma.config 读）
# 优先用 turn 维度（更符合 Agent 漂移视角）；ts 维度保留为 fallback
_ESCALATE_WINDOW_TURNS = 3
_ESCALATE_THRESHOLD = 3


def _read_last_assistant_response(transcript_path: str) -> str:
    """读 transcript JSONL，取最后一条 assistant message 的所有 text content。"""
    if not transcript_path:
        return ""
    p = Path(transcript_path)
    if not p.exists():
        return ""
    try:
        # 反向找最后一条 type=assistant
        lines = p.read_text(encoding="utf-8").splitlines()
        for ln in reversed(lines):
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "assistant":
                continue
            msg = d.get("message", {})
            content = msg.get("content")
            if isinstance(content, list):
                text_parts = []
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        text_parts.append(c.get("text", ""))
                return "\n".join(text_parts)
            if isinstance(content, str):
                return content
            return ""
    except OSError:
        return ""
    return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma Stop: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0

    session_id = payload.get("session_id", "") or "default"
    transcript_path = payload.get("transcript_path", "")
    response = _read_last_assistant_response(transcript_path)

    try:
        sticky_list = load()
    except StickyConfigError as e:
        print(f"karma: {e}", file=sys.stderr)
        print(json.dumps({}))
        return 0

    if not sticky_list or not response:
        print(json.dumps({}))
        return 0

    state = session_state.load(session_id)

    check_hits = []
    for s in sticky_list:
        if not s.violation_checks:
            continue
        hits = run_checks(
            s.violation_checks,
            response=response,
            session_state=state,
            sticky_id=s.id,
        )
        check_hits.extend(hits)

    keyword_violations = detect(response, sticky_list, session_id=session_id, turn=state.turn_count)

    if not check_hits and not keyword_violations:
        print(json.dumps({}))
        return 0

    # 写违反
    all_records: list[Violation] = []
    for h in check_hits:
        all_records.append(Violation(
            ts=int(time.time()), session_id=session_id, sticky_id=h.sticky_id,
            trigger=h.trigger, snippet=h.snippet, turn=state.turn_count,
        ))
    seen_ids = {h.sticky_id for h in check_hits}
    for v in keyword_violations:
        if v.sticky_id not in seen_ids:
            all_records.append(v)
    if all_records:
        append(all_records)

    # stderr 通知 + 桌面通知（用户离开 stderr 视野时的补充提示）
    summary_lines = []
    notify_msgs = []
    for h in check_hits:
        line = f"⚠️ karma: Agent 违反 {h.sticky_id!r} — {h.trigger}"
        print(line, file=sys.stderr)
        summary_lines.append(line)
        notify_msgs.append(f"{h.sticky_id} — {h.trigger}")
        if h.suggested_fix:
            print(f"   建议：{h.suggested_fix}", file=sys.stderr)
    for v in keyword_violations:
        if v.sticky_id in seen_ids:
            continue
        line = f"⚠️ karma: Agent 触发关键词 {v.sticky_id!r} (词 {v.trigger!r})"
        print(line, file=sys.stderr)
        summary_lines.append(line)
        notify_msgs.append(f"{v.sticky_id} — {v.trigger}")

    # 桌面通知（合并多条违反到一条 notification 避免轰炸；fail open）
    # 累积告警：本次违反含窗口内已累积超阈值 → 升级严重度（阈值从 config 读）
    if notify_msgs:
        try:
            from karma.config import load as _load_config
            cfg = _load_config()
            window_turns = int(cfg.get("escalate_window_turns", _ESCALATE_WINDOW_TURNS))
            threshold = cfg["escalate_threshold"]
        except Exception:
            window_turns = _ESCALATE_WINDOW_TURNS
            threshold = _ESCALATE_THRESHOLD
        hit_sticky_ids = {h.sticky_id for h in check_hits} | {
            v.sticky_id for v in keyword_violations if v.sticky_id not in seen_ids
        }
        # 按 turn 距离统计（不是人类时钟）— Agent 漂移按 turn 累积
        if state.turn_count > 0:
            counts = count_recent_turns(session_id, state.turn_count, window_turns=window_turns)
        else:
            counts = count_recent(window_sec=1800)  # 早期 fallback
        escalated_ids = [sid for sid in hit_sticky_ids if counts.get(sid, 0) >= threshold]
        if escalated_ids:
            notify(
                f"🚨 karma 严重 — 累积违反 {len(escalated_ids)} 条",
                " / ".join(f"{sid} (×{counts[sid]})" for sid in escalated_ids[:3]),
            )
        else:
            notify("karma 检测违反", " / ".join(notify_msgs[:3]))

    # 也可以通过 additionalContext 让 Claude 看到 — 但 Stop 后 Claude 已停，
    # 主要给下次 UserPromptSubmit 的 sticky 注入加 RECENT_VIOLATION 标记
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": "\n".join(summary_lines) if summary_lines else "",
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
