"""SubagentStart hook — Subagent 启动时继承父 sticky 约束。

Claude Code 协议:
- stdin payload: {agent_id, agent_type, session_id, transcript_path, ...}
- stdout: {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": "..."}}

策略：
- 将父 session sticky 信息通过 additionalContext 传给子 agent
- 子 agent 在隔离 context 中仍遵守父 sticky 约束
- v0.6.0 first pass：简单序列化 sticky 摘要
"""

from __future__ import annotations

import json
import sys

from karma.sticky import load as load_sticky


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma SubagentStart: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0
    
    agent_type = payload.get("agent_type", "")
    agent_id = payload.get("agent_id", "")
    
    try:
        sticky_list = load_sticky()
    except Exception as e:
        print(f"karma SubagentStart: sticky 加载失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0
    
    if not sticky_list:
        print(json.dumps({}))
        return 0
    
    # 序列化 sticky 约束传给子 agent
    sticky_context = "📋 子 Agent 继承的核心方向：\n"
    for s in sticky_list:
        first_line = s.preference.strip().split("\n")[0]
        sticky_context += f"  • {s.id}: {first_line}\n"
    
    sticky_context += "\n这些约束在子 Agent 中也会生效。违反时主 Agent 会收到通知。"
    
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SubagentStart",
            "additionalContext": sticky_context
        }
    }))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
