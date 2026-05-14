"""PostToolUse hook — 跟踪 session 状态 + 智能 sticky reinject anchor。

Claude Code 实际协议:
- stdin payload: {tool_name, tool_input, tool_response, session_id, ...}
- stdout: {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}
  或者 fail-loud {"decision": "block", "reason": "..."} (我们不用)

v0.4.24（proactive 锚定第一步）：智能 sticky reinject 解决「sticky 注入头部强
尾部弱」真根因。当前 sticky 仅 UserPromptSubmit 注入 1 次/turn，长 response
中段 Agent 注意力漂移导致单 turn 累积违反（实测本回合 33 keep-pushing + 11
chinese-plain）。

策略：**不是每次都注入**（token 成本高），仅当最近 N turn 内**该 sticky 真
触发过**才 reinject 它的简化提醒。这样 sticky 跟违反检测真闭环：
- 违反某 sticky → 下次 tool call 后 reinject 该 sticky anchor
- 多次违反 → 多次 reinject 直到 Agent 真改行为
- 没违反的 sticky → 不注入省 token

性能预算：< 50ms
"""

from __future__ import annotations

import json
import sys

from karma import session_state
from karma.checks.description_context import is_description_context


# tool 失败的字符串前缀 — Claude Code Read/Edit 失败常见返回（启发式）
_FAILURE_STRING_PREFIXES = (
    "Error", "error:", "File does not exist", "does not exist",
    "<system-reminder>", "Tool execution failed",
)


def _tool_failed(tool_response) -> bool:
    """启发式判 tool 调用是否失败 — 失败时跳过 record_read/edit
    防止 Read 失败也 record_read → 后续 Edit 该文件被 read_first 绕过。

    dict 形式：isError / interrupted 标志，或 stderr 含明确错误。
    string 形式：以已知失败前缀开头。
    """
    if isinstance(tool_response, dict):
        if tool_response.get("isError") or tool_response.get("interrupted"):
            return True
        return False
    s = str(tool_response or "").lstrip()
    for prefix in _FAILURE_STRING_PREFIXES:
        if s.startswith(prefix):
            return True
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma PostToolUse: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0


    session_id = payload.get("session_id", "") or "default"
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    tool_response = payload.get("tool_response", "") or ""

    state = session_state.load(session_id)

    # 先 catchup 之前 pending 的 background 任务输出（任务可能在中间完成了）
    # 这样能在后续 record 之前更新 last_test_pass_ts，保证 evidence check 看见
    state.catchup_pending_bg()

    failed = _tool_failed(tool_response)

    if tool_name == "Bash":
        # Bash 失败仍 record — has_recent_test_pass 由 _FAIL_RE 在 record_bash 内部判
        cmd = tool_input.get("command", "") or ""
        is_bg = bool(tool_input.get("run_in_background"))
        state.record_bash(cmd, tool_response, run_in_background=is_bg)
    elif not failed:
        # 非 Bash tool — 只在成功时 record，失败时不动 read_files/edit_files
        # 防 Read 失败也 record_read 让后续 Edit 绕过 read_first 检测
        if tool_name == "Read":
            fp = tool_input.get("file_path", "")
            state.record_read(fp)
        elif tool_name in ("Write", "NotebookEdit"):
            # Write / NotebookEdit 替换或创建整个文件
            # 描述上下文文件（.md / .yaml / tests/ 等）的改不算「代码改动」—
            # 不推 last_edit_ts（避免 docs / 配置 Edit 后 evidence check 误判
            # 「自最近代码改动以来未测试」）。仍 record_read（已知内容不被 read_first 拦）
            fp = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
            is_desc, _ = is_description_context(tool_name, tool_input)
            if not is_desc:
                state.record_edit(fp)
            state.record_read(fp)
        elif tool_name == "Edit":
            # Edit 只改部分 — 仍要求事先 Read 全文
            # 描述上下文文件 Edit 不推 last_edit_ts（同 Write/NotebookEdit 逻辑）
            fp = tool_input.get("file_path", "")
            is_desc, _ = is_description_context(tool_name, tool_input)
            if not is_desc:
                state.record_edit(fp)

    try:
        session_state.save(state)
    except OSError as e:
        print(f"karma PostToolUse: 保存 session_state 失败 ({e})", file=sys.stderr)

    # v0.4.24：智能 sticky reinject anchor — 仅最近触发过的 sticky 注入简化提醒
    additional_context = _build_smart_reinject(session_id, state)
    output = {}
    if additional_context:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": additional_context,
            }
        }
    print(json.dumps(output, ensure_ascii=False))
    return 0


def _build_smart_reinject(session_id: str, state) -> str:
    """智能 sticky reinject — 仅最近 N turn 触发过的 sticky 注入简化提醒。

    返回空字符串 → PostToolUse 不注入 additionalContext（省 token）。
    返回非空 → 给 Claude 看到「最近违反过的 sticky 提醒」作为中段 anchor。
    """
    try:
        from karma.sticky import load as _load_sticky
        from karma.violations import recent_turns
        from karma.config import load as _load_config
    except ImportError:
        return ""
    try:
        sticky_list = _load_sticky()
    except Exception:
        return ""
    if not sticky_list or state.turn_count <= 0:
        return ""
    try:
        cfg = _load_config()
        window_turns = int(cfg.get("recent_violation_turns", 5))
    except Exception:
        window_turns = 5
    recent_v = recent_turns(session_id, state.turn_count, window_turns=window_turns)
    if not recent_v:
        return ""
    # 只注入最近触发过的 sticky 简化提醒（不是全 sticky 重灌）
    triggered_sticky_ids = set(recent_v.keys())
    triggered_sticky = [s for s in sticky_list if s.id in triggered_sticky_ids]
    if not triggered_sticky:
        return ""
    lines = ["[karma 中段提醒 — 最近 turn 触发过的 sticky 别再犯]"]
    for s in triggered_sticky[:3]:  # 最多 3 条避免淹没
        # 只注入 id + 第一行 preference（简化版省 token）
        first_line = s.preference.strip().split("\n")[0]
        lines.append(f"  - {s.id}: {first_line}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
