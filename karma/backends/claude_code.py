"""Claude Code backend — `~/.claude/settings.json` + `~/.claude/hooks/`。

继承 `JsonHooksBackend` 通用基类，只填差异：matcher 字段（Stop 不加 matcher）。
"""

from __future__ import annotations

from karma.backends._json_hooks import JsonHooksBackend


class ClaudeCodeBackend(JsonHooksBackend):
    name = "claude-code"
    display_name = "Claude Code"
    _CONFIG_DIR_NAME = ".claude"
    _SETTINGS_FILENAME = "settings.json"
    _CLIENT_CMD = "claude"

    _HOOK_EVENTS: dict[str, str] = {
        "UserPromptSubmit": "user_prompt_submit",
        "PreToolUse": "pre_tool_use",
        "PostToolUse": "post_tool_use",
        "Stop": "stop",
        # v0.4.28（karma v3 第四步）: SessionStart 注入 sticky baseline，每次
        # session 起手 sticky 就在 context 里。`source` 字段区分 startup /
        # resume / clear / compact —— compact 场景特别重要（compact 后 sticky
        # 被压缩淡化，SessionStart 重起时强注入是真根本路径）。
        "SessionStart": "session_start",
        # v0.4.29（karma v3 第五步）: PreCompact 触发前落盘 sticky 完整状态到
        # ~/.claude/karma/pre_compact_snapshot.md，让 SessionStart(source=compact)
        # 重起时读盘加强提醒。两端夹击 compact 失忆。
        # 注：不用 exit 2 阻止 compact — compact 是 Claude Code 保护机制，karma
        # 不该干扰，只做纯落盘 + 提醒。
        "PreCompact": "pre_compact",
    }

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """Claude Code 特有：PreToolUse / PostToolUse / UserPromptSubmit 加
        `matcher: "*"`；PreCompact matcher 区分 manual / auto（用 `*` 匹配两种）；
        Stop / SessionStart 等 lifecycle event 不加 matcher（加了会被无声忽略）。
        """
        wrapper = self.hooks_dir() / f"karma_{hook_name_lower}.py"
        entry: dict[str, object] = {
            "hooks": [{"type": "command", "command": str(wrapper)}]
        }
        if event_name in ("PreToolUse", "PostToolUse", "UserPromptSubmit", "PreCompact"):
            entry["matcher"] = "*"
        return entry
