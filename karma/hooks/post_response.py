"""post_response hook — 扫违反，写 violations.jsonl，通知用户。

时机：Agent 响应完成后。
输入：stdin JSON payload，含 agent_response + session_id。
输出：stderr 通知 (可选)，violations.jsonl 写入。

性能预算：< 200ms。
"""

from __future__ import annotations

import json
import sys

from karma.sticky import StickyConfigError, load
from karma.violations import append, detect


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma hook: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        return 1
    response = payload.get("agent_response", "")
    session_id = payload.get("session_id", "unknown")

    try:
        sticky_list = load()
    except StickyConfigError as e:
        print(f"karma: {e}", file=sys.stderr)
        return 0

    if not sticky_list or not response:
        return 0

    violations = detect(response, sticky_list, session_id=session_id)
    if not violations:
        return 0

    append(violations)
    # 用户通知 (stderr)
    for v in violations:
        print(
            f"⚠️ karma: Agent 违反 \"{v.sticky_id}\" "
            f"(触发: {v.trigger!r}, snippet: ...{v.snippet[:60]}...)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
