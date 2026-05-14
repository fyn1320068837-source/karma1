"""UserPromptSubmit hook — 给 Claude 注入 sticky 提示作为 additionalContext。

Claude Code 实际协议（2026-05）：
- stdin payload 字段: prompt (不是 user_text), session_id, transcript_path, cwd, ...
- stdout 输出: {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "..."}}
- additionalContext 作为 system message context 给 Claude 看（不修改 user_text 本身）

性能预算：< 50ms
"""

from __future__ import annotations

import json
import sys

from karma import session_state
from karma.session_state import purge_old_states
from karma.sticky import StickyConfigError, format_for_injection, load
from karma.violations import recent, recent_turns


def _output_passthrough() -> None:
    """没 sticky / 配置错 → 不输出 additionalContext，passthrough。"""
    print(json.dumps({}))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma UserPromptSubmit: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        _output_passthrough()
        return 0

    # 实际 prompt 在 'prompt' 字段
    _ = payload.get("prompt", "")  # 不需要 — 我们只注入 additionalContext

    # 每 turn 清理一次老 session-state 文件（清理周期从 config 读，默认 30 天）。
    # 异常不该阻塞 sticky 注入。
    try:
        from karma.config import load as _load_config
        cfg = _load_config()
        purge_old_states(max_age_days=cfg["session_state_max_age_days"])
    except Exception:
        try:
            purge_old_states(max_age_days=30)
        except Exception:
            pass

    try:
        sticky_list = load()
    except StickyConfigError as e:
        print(f"karma: {e}", file=sys.stderr)
        _output_passthrough()
        return 0

    if not sticky_list:
        _output_passthrough()
        return 0

    # 每 turn 给 session_state.turn_count + 1 — 给后续按 turn 距离的违反统计
    # 同时重置 stop_block_count（新 user prompt = 新 turn，干预计数清 0）
    # 顺便 catchup pending background 任务（task #8：catchup 之前只在 PostToolUse
    # 跑，bg 完成后第一个触发的 hook 可能是这里 / pre_tool_use，要多 hook 都跑）
    session_id = payload.get("session_id", "") or "default"
    try:
        state = session_state.load(session_id)
        state.catchup_pending_bg()
        state.turn_count += 1
        state.stop_block_count = 0
        session_state.save(state)
        current_turn = state.turn_count
    except Exception:
        current_turn = 0

    # ⚠️ 标记 — 按 turn 距离查最近违反（不是人类时钟）
    # 默认 5 turn 内违反过的 sticky 标 ⚠️。窗口可配。
    try:
        from karma.config import load as _load_config
        cfg = _load_config()
        window_turns = int(cfg.get("recent_violation_turns", 5))
    except Exception:
        window_turns = 5
    if current_turn > 0:
        recent_v = recent_turns(session_id, current_turn, window_turns=window_turns)
    else:
        recent_v = recent()  # 早期 fallback 用人类时钟（首次 install 没 turn 计数）
    additional_context = format_for_injection(sticky_list, recent_v)

    # 额外检测：上一 response 末尾是否含推进信号（fallback for Stop hook
    # 在 user 立刻接 prompt 时不跑的协议 limitation）
    # 如果上一 response default 命中 keep_pushing → 注入强提醒
    transcript_path = payload.get("transcript_path", "")
    if transcript_path:
        try:
            from pathlib import Path as _Path
            from karma.checks.keep_pushing import check as _kp_check
            tp = _Path(transcript_path)
            if tp.exists():
                # 反向找 last assistant message
                lines = tp.read_text(encoding="utf-8").splitlines()
                last_text = ""
                for ln in reversed(lines):
                    try:
                        d = json.loads(ln.strip())
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") != "assistant":
                        continue
                    msg = d.get("message", {})
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        parts = [c.get("text", "") for c in content
                                 if isinstance(c, dict) and c.get("type") == "text"]
                        last_text = "\n".join(parts)
                    elif isinstance(content, str):
                        last_text = content
                    break
                if last_text:
                    hit = _kp_check(response=last_text)
                    if hit:
                        additional_context += (
                            f"\n\n[karma 强提醒 — sticky #7/#8 keep-pushing 检测]\n"
                            f"上一 response 末尾没推进信号 / 没询问决策 = 你上次停下了。\n"
                            f"本 turn 完成第一波后**立即**选下一推进点开始，不要再停下汇报完等我反馈。\n"
                            f"格式：[做的事] + [我接下来去做 X] + 立即下个 tool 调用。"
                        )
        except Exception:
            pass

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": additional_context,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
