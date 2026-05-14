"""PreCompact hook — Compact 前防止 sticky 淡化。

Claude Code 协议:
- stdin payload: {trigger: "manual"|"auto", session_id, transcript_path, ...}
- stdout: {"continue": false/true, "stopReason": "...", 
           "hookSpecificOutput": {"hookEventName": "PreCompact", "additionalContext": "..."}}

策略：检查即将 compact 会不会导致 sticky anchor 离 context 太远。
- 若 sticky 在 context 中部或头部，compact 可能把它推到尾部或丢掉
- 拒绝 compact（block）或允许 + 强制重注 sticky
- 目标：长 session 中不让 compact 淡化用户核心方向
"""

from __future__ import annotations

import json
import sys

from karma.sticky import load as load_sticky


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma PreCompact: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        # Fail open — 配置问题不卡用户
        print(json.dumps({"continue": True}))
        return 0

    trigger = payload.get("trigger", "")
    
    try:
        sticky_list = load_sticky()
    except Exception as e:
        print(f"karma PreCompact: sticky 加载失败 ({e})", file=sys.stderr)
        print(json.dumps({"continue": True}))
        return 0
    
    if not sticky_list:
        # 没有 sticky，随意 compact
        print(json.dumps({"continue": True}))
        return 0
    
    # v0.5.0 简单策略：
    # - 自动 compact 时，提醒 sticky 会重新注入
    # - 手工 compact (/compact) 则允许，用户自知
    if trigger == "auto":
        sticky_ids = ", ".join(s.id for s in sticky_list)
        context = f"""⚠️ Context compact 前置检查完成。当前有 {len(sticky_list)} 条核心方向：{sticky_ids}

Compact 后将自动重新注入已有的 sticky 约束，不会丢失。继续 compact。"""
        print(json.dumps({
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "PreCompact",
                "additionalContext": context
            }
        }))
    else:
        # trigger == "manual"
        print(json.dumps({"continue": True}))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
