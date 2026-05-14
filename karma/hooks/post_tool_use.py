"""PostToolUse hook — 跟踪 session 状态 + 可选 additionalContext。

Claude Code 实际协议:
- stdin payload: {tool_name, tool_input, tool_response, session_id, ...}
- stdout: {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}
  或者 fail-loud {"decision": "block", "reason": "..."} (我们不用)

只写 session_state 文件 + 输出空响应（不需要给 Claude 额外 context）。
性能预算：< 30ms
"""

from __future__ import annotations

import json
import sys

from karma import session_state


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
            # Write / NotebookEdit 替换或创建整个文件 — Agent 完全知道写入后内容
            # 既 record_edit 也 record_read（后续 Edit 不被 read_first 多余拦）
            fp = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
            state.record_edit(fp)
            state.record_read(fp)
        elif tool_name == "Edit":
            # Edit 只改部分 — 仍要求事先 Read 全文
            fp = tool_input.get("file_path", "")
            state.record_edit(fp)

    try:
        session_state.save(state)
    except OSError as e:
        print(f"karma PostToolUse: 保存 session_state 失败 ({e})", file=sys.stderr)

    # 不需要给 Claude 额外 context，输出空响应
    print(json.dumps({}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
