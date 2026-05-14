"""Gemini CLI backend — `~/.gemini/settings.json` 含 `hooks` 字段。

继承 `JsonHooksBackend`，差异：① event 名跟 Claude Code / Codex 完全不同
（BeforeAgent / AfterAgent / BeforeTool / AfterTool）② hook entry 加 timeout: 5000ms
③ 默认启用（不像 Codex 要 feature flag）。

stdin payload 差异：Gemini AfterAgent 直接给 `prompt_response` 字段（跟 Codex
`last_assistant_message` 同概念），karma stop.py 已统一适配。

参考：https://geminicli.com/docs/hooks/reference/
"""

from __future__ import annotations

from karma.backends._json_hooks import JsonHooksBackend


class GeminiCLIBackend(JsonHooksBackend):
    name = "gemini-cli"
    display_name = "Gemini CLI"
    _CONFIG_DIR_NAME = ".gemini"
    _SETTINGS_FILENAME = "settings.json"
    _CLIENT_CMD = "gemini"

    # Gemini event 名跟 Claude Code 完全不同 — 但 wrapper basename 保持 karma 内部
    # 规范，让 hook 入口模块（karma/hooks/*.py）跨 backend 完全复用。
    _HOOK_EVENTS: dict[str, str] = {
        "BeforeAgent": "user_prompt_submit",
        "BeforeTool": "pre_tool_use",
        "AfterTool": "post_tool_use",
        "AfterAgent": "stop",
    }

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """Gemini hook entry 加 timeout 5000ms — 跟 vibe-island 已用格式一致。"""
        wrapper = self.hooks_dir() / f"karma_{hook_name_lower}.py"
        return {
            "hooks": [{"type": "command", "command": str(wrapper), "timeout": 5000}]
        }
