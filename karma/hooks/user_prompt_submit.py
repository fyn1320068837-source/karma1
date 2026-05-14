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

from karma.session_state import purge_old_states
from karma.sticky import StickyConfigError, format_for_injection, load
from karma.violations import recent


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

    # 每 turn 清理一次 30 天前的 session-state 文件（低频任务，user_prompt_submit
    # 每 turn 跑一次正合适）。异常不该阻塞 sticky 注入。
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

    recent_v = recent()
    additional_context = format_for_injection(sticky_list, recent_v)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": additional_context,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
