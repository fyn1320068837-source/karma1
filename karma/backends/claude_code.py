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
    }

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """Claude Code 特有：PreToolUse / PostToolUse / UserPromptSubmit 加
        `matcher: "*"`；Stop / SessionStart 等 lifecycle event 不加（加了会被
        无声忽略可能导致 hook 不生效）。
        """
        wrapper = self.hooks_dir() / f"karma_{hook_name_lower}.py"
        entry: dict[str, object] = {
            "hooks": [{"type": "command", "command": str(wrapper)}]
        }
        if event_name in ("PreToolUse", "PostToolUse", "UserPromptSubmit"):
            entry["matcher"] = "*"
        return entry
