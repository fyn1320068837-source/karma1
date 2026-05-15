"""pytest conftest — 全局测试 fixture。

v0.9.5 (CI fix): force KARMA_LOCALE=zh — 测试 fixture 假设 zh locale
(写死中文字面 assert 「默契 / 偏离 / 纯陈述」)。但 CI runner 默认
English locale, `karma.locale_detect.is_chinese_user()` 返回 False
→ i18n 选 en → fixture 断言 fail。

`pytest_configure` 在任何 karma import 之前跑, setenv 让 i18n.tr()
解析到 zh locale。本机用户跑测试也能借这个 force 确保跟 CI 一致。
"""
from __future__ import annotations

import os


def pytest_configure(config):
    """Force zh locale before any karma module is imported."""
    os.environ.setdefault("KARMA_LOCALE", "zh")
