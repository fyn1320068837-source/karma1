"""SessionStart hook — Session 开始 / 恢复时加载 sticky。

Claude Code 协议:
- stdin payload: {source: "startup"|"resume"|"clear"|"compact", session_id, model, ...}
- stdout: {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}

策略：
- startup：首次加载 sticky（可选，只做日志）
- resume：重加载 sticky.yaml，检查版本 drift，防过期 sticky 复活
- clear：重置 session state
- compact：同步 compact 后的状态
"""

from __future__ import annotations

import json
import sys

from karma.sticky import load as load_sticky, StickyConfigError


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma SessionStart: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0
    
    source = payload.get("source", "")
    model = payload.get("model", "")
    
    try:
        sticky_list = load_sticky()
    except StickyConfigError as e:
        # sticky 配置错误，fail loud
        print(f"karma SessionStart: {e}", file=sys.stderr)
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": f"❌ sticky 配置错误：{e}"
            }
        }))
        return 0
    except Exception as e:
        print(f"karma SessionStart: sticky 加载失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0
    
    # 根据 source 生成提醒
    if source == "resume":
        if sticky_list:
            ids = ", ".join(s.id for s in sticky_list)
            context = f"Session 已恢复。已加载 {len(sticky_list)} 条核心方向：{ids}"
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context
                }
            }))
        else:
            print(json.dumps({}))
    elif source == "startup":
        if sticky_list:
            context = f"新 session 已启动。已加载 {len(sticky_list)} 条核心方向。"
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context
                }
            }))
        else:
            print(json.dumps({}))
    elif source == "compact":
        if sticky_list:
            context = f"Context compact 已完成。{len(sticky_list)} 条核心方向重新加载。"
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context
                }
            }))
        else:
            print(json.dumps({}))
    else:
        # source == "clear" or unknown
        print(json.dumps({}))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
