"""user_prompt_submit hook — 前置注入 sticky 到 user_text 前面。

时机：用户发消息送给模型之前。
输入：stdin JSON payload，含 user_text。
输出：修改后的 user_text 到 stdout。

性能预算：< 50ms。
"""

from __future__ import annotations

import json
import sys

from karma.sticky import StickyConfigError, format_for_injection, load
from karma.violations import recent


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma hook: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        return 1
    user_text = payload.get("user_text", "")

    try:
        sticky_list = load()
    except StickyConfigError as e:
        # fail loud：sticky.yaml 配置错让用户看见，但不阻断 prompt
        print(f"karma: {e}", file=sys.stderr)
        sys.stdout.write(user_text)
        return 0

    if not sticky_list:
        sys.stdout.write(user_text)
        return 0

    recent_v = recent()
    sticky_block = format_for_injection(sticky_list, recent_v)
    sys.stdout.write(sticky_block + "[用户当前消息]\n" + user_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
