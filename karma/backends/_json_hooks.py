"""JSON-hooks backend 通用基类 — 让加新 AI 客户端 backend 变成「填表」工作。

设计动机：vibe-island 这种「跨 AI 客户端通用桥」实证 8+ 个客户端都用类似模式：
- 配置文件 JSON 含顶层 `hooks` 字段
- 每个 event 是 array of entry，每个 entry 含 `hooks` array 含命令
- karma wrapper 路径含 `karma_` 前缀识别自己装的

3 个现有 backend（Claude Code / Codex / Gemini CLI）共用以下逻辑：
- load_settings / save_settings JSON 原子写
- is_karma_entry 用前缀识别
- client_installed 检测命令在 PATH 或配置目录存在

抽到基类后，加新 backend 只需填 6 个类属性 + 可选 override build_event_entry /
pre_install_setup。

参考 vibe-island 实证的 9 家清单（详 CHANGELOG v0.4.0+ notes）：
Cursor / Factory / Qoder / Copilot / CodeBuddy / Kimi 等都能继承本基类。
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from karma.backends._base import SettingsParseError


class JsonHooksBackend:
    """AI 客户端 JSON hooks 配置 backend 共用实现。

    子类需填以下类属性：

    - `name`: str — backend 注册名（如 'claude-code' / 'codex' / 'gemini-cli'）
    - `display_name`: str — 给用户看的名字（如 'Claude Code'）
    - `_CONFIG_DIR_NAME`: str — `~/` 下配置目录名（如 '.claude' / '.codex' / '.gemini'）
    - `_SETTINGS_FILENAME`: str — 配置文件名（如 'settings.json' / 'hooks.json'）
    - `_CLIENT_CMD`: str — 客户端命令名用于 PATH 检测（如 'claude' / 'codex' / 'gemini'）
    - `_HOOK_EVENTS`: dict[str, str] — backend native event 名 → karma wrapper basename

    子类可选 override：
    - `build_event_entry(hook_name, event_name)` — 不同 backend matcher / timeout 不同
    - `pre_install_setup()` — Codex 类需要启用 feature flag
    """

    # 子类必填的类属性（默认空，让 mypy 不报 attribute access）
    name: str = ""
    display_name: str = ""
    _CONFIG_DIR_NAME: str = ""
    _SETTINGS_FILENAME: str = "settings.json"
    _CLIENT_CMD: str = ""
    _HOOK_EVENTS: dict[str, str] = {}

    def client_installed(self) -> bool:
        """检测客户端：命令在 PATH 或 ~/<config_dir> 存在。"""
        if self._CLIENT_CMD and shutil.which(self._CLIENT_CMD):
            return True
        return (Path.home() / self._CONFIG_DIR_NAME).exists()

    def hooks_dir(self) -> Path:
        return Path.home() / self._CONFIG_DIR_NAME / "hooks"

    def settings_path(self) -> Path:
        return Path.home() / self._CONFIG_DIR_NAME / self._SETTINGS_FILENAME

    def settings_backup_path(self) -> Path:
        return Path.home() / self._CONFIG_DIR_NAME / f"{self._SETTINGS_FILENAME}.before-karma"

    def hook_events(self) -> dict[str, str]:
        return dict(self._HOOK_EVENTS)

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """默认 entry 格式 — 无 matcher / 无 timeout，子类 override 加 backend 特有字段。"""
        wrapper = self.hooks_dir() / f"karma_{hook_name_lower}.py"
        return {"hooks": [{"type": "command", "command": str(wrapper)}]}

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
                f"{self._SETTINGS_FILENAME} 解析失败: {e}\n"
                f"路径: {p}\n"
                f"karma 不会覆盖损坏的配置。请手工修复 JSON 后重跑 install-hooks。"
            ) from e

    def save_settings(self, data: dict) -> None:
        """原子写 — tmp + os.replace 防中断 truncate。"""
        p = self.settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + f".karma-tmp.{os.getpid()}")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)

    def pre_install_setup(self) -> list[str]:
        """默认无需启用 — Codex 类 override 启用 features 标志。"""
        return []
