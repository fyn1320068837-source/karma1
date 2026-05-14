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

    if tool_name == "Read":
        fp = tool_input.get("file_path", "")
        state.record_read(fp)
    elif tool_name in ("Write", "NotebookEdit"):
        # Write / NotebookEdit 替换或创建整个文件 — Agent 完全知道写入后内容
        # 既 record_edit（推 last_edit_ts）也 record_read（后续 Edit 不被 read_first 多余拦）
        fp = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
        state.record_edit(fp)
        state.record_read(fp)
    elif tool_name == "Edit":
        # Edit 只改部分内容 — 仍要求事先 Read 全文（read_first 检测真违反）
        fp = tool_input.get("file_path", "")
        state.record_edit(fp)
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "") or ""
        is_bg = bool(tool_input.get("run_in_background"))
        # 不强转 str — record_bash 内部判 dict (Claude Code 真实格式) 或 string
        state.record_bash(cmd, tool_response, run_in_background=is_bg)

    try:
        session_state.save(state)
    except OSError as e:
        print(f"karma PostToolUse: 保存 session_state 失败 ({e})", file=sys.stderr)

    # 不需要给 Claude 额外 context，输出空响应
    print(json.dumps({}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
