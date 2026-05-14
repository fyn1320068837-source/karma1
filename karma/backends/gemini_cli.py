"""Gemini CLI backend — `~/.gemini/settings.json` 含 `hooks` 字段。

Gemini CLI 默认启用 hook（不像 Codex 要 feature flag），协议跟 Claude Code /
Codex 类似但 **event 名不同**：

| karma 内部 wrapper | Claude Code event | Codex event | Gemini CLI event |
|---|---|---|---|
| user_prompt_submit | UserPromptSubmit | UserPromptSubmit | **BeforeAgent** |
| pre_tool_use | PreToolUse | PreToolUse | **BeforeTool** |
| post_tool_use | PostToolUse | PostToolUse | **AfterTool** |
| stop | Stop | Stop | **AfterAgent** |

字段差异（stdin payload）：
- Claude Code: camelCase 输出（hookEventName 等）
- Codex / Gemini: snake_case 输出（hook_event_name）
- Gemini Stop hook（即 AfterAgent）直接给 `prompt_response` 字段 — 跟 Codex
  `last_assistant_message` 同概念

参考：https://geminicli.com/docs/hooks/reference/
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from karma.backends._base import SettingsParseError


class GeminiCLIBackend:
    name = "gemini-cli"
    display_name = "Gemini CLI"

    # Gemini event 名 → karma wrapper basename（snake_case）
    # 注意 key 是 Gemini 用的 event 名（写进 ~/.gemini/settings.json），value 是
    # karma 内部 hook 入口模块名 — 让 karma hooks 完全跨 backend 复用。
    _HOOK_EVENTS: dict[str, str] = {
        "BeforeAgent": "user_prompt_submit",
        "BeforeTool": "pre_tool_use",
        "AfterTool": "post_tool_use",
        "AfterAgent": "stop",
    }

    def client_installed(self) -> bool:
        return bool(shutil.which("gemini")) or (Path.home() / ".gemini").exists()

    def hooks_dir(self) -> Path:
        return Path.home() / ".gemini" / "hooks"

    def settings_path(self) -> Path:
        return Path.home() / ".gemini" / "settings.json"

    def settings_backup_path(self) -> Path:
        return Path.home() / ".gemini" / "settings.json.before-karma"

    def hook_events(self) -> dict[str, str]:
        return dict(self._HOOK_EVENTS)

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """Gemini hook entry 格式 — 跟 vibe-island 已用的格式一致（含 timeout ms）。"""
        wrapper = self.hooks_dir() / f"karma_{hook_name_lower}.py"
        return {
            "hooks": [
                {"type": "command", "command": str(wrapper), "timeout": 5000}
            ]
        }

    def is_karma_entry(self, entry: dict) -> bool:
        for h in entry.get("hooks", []):
            if "karma_" in h.get("command", ""):
                return True
        return False

    def load_settings(self) -> dict:
        p = self.settings_path()
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SettingsParseError(
                f"settings.json 解析失败: {e}\n"
                f"路径: {p}\n"
                f"karma 不会覆盖损坏的配置。请手工修复 JSON 后重跑 install-hooks。"
            ) from e

    def save_settings(self, data: dict) -> None:
        p = self.settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + f".karma-tmp.{os.getpid()}")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)

    def pre_install_setup(self) -> list[str]:
        """Gemini CLI hook 默认启用，无额外步骤。"""
        return []
