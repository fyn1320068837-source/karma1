"""model_threshold 模块守护测试 — 按模型自动适配中段全量 reinject 阈值。

v0.9.0 阈值调整: Opus 80K → 60K / Sonnet 60K → 40K / Haiku 30K 不变 /
DEFAULT 60K → 40K。理由：v0.9.0 架构是 SessionStart 一次全量 baseline +
每 turn 精简 anchor + 累积达阈值中段全量补。SessionStart baseline 在
history 顶部累积久了会被稀释，需要更早补回完整规则维持 attention 锚定。
"""

from __future__ import annotations

from karma.model_threshold import threshold_for_model, DEFAULT_THRESHOLD


def test_opus_returns_60k():
    """Opus 阈值 60K (v0.9.0 从 80K 收紧)。"""
    assert threshold_for_model("claude-opus-4-7") == 60_000
    assert threshold_for_model("claude-opus-4-6") == 60_000
    assert threshold_for_model("opus") == 60_000


def test_sonnet_returns_40k():
    """Sonnet 阈值 40K (v0.9.0 从 60K 收紧)。"""
    assert threshold_for_model("claude-sonnet-4-6") == 40_000
    assert threshold_for_model("claude-sonnet-4-5") == 40_000
    assert threshold_for_model("sonnet") == 40_000


def test_haiku_returns_30k():
    """Haiku 小模型衰减更快 → 阈值 30K (v0.9.0 不变)。"""
    assert threshold_for_model("claude-haiku-4-5") == 30_000
    assert threshold_for_model("haiku") == 30_000


def test_old_models_return_8k_backward_compat():
    """老模型 (GPT-3.5 / Claude-1.3 时代) 实际在 8K 衰减 — Liu 2023 数据。"""
    assert threshold_for_model("gpt-3.5-turbo") == 8_000
    assert threshold_for_model("claude-1.3") == 8_000
    assert threshold_for_model("claude-instant-1") == 8_000


def test_unknown_model_falls_back_to_40k():
    """未知模型 / None / 空 → 40K 默认 (v0.9.0 跟 sonnet 一致)。"""
    assert threshold_for_model(None) == DEFAULT_THRESHOLD
    assert threshold_for_model("") == DEFAULT_THRESHOLD
    assert threshold_for_model("unknown-model-2030") == DEFAULT_THRESHOLD
    assert DEFAULT_THRESHOLD == 40_000


def test_case_insensitive():
    """模型 ID 大小写不影响识别。"""
    assert threshold_for_model("CLAUDE-OPUS-4-7") == 60_000
    assert threshold_for_model("Sonnet-4-6") == 40_000


def test_keyword_priority_long_matches_first():
    """关键词顺序敏感 — opus / sonnet 先于潜在子串误命中。"""
    # 防御性：如果未来加 'son' 类短关键词，'sonnet' 不该被截断
    assert threshold_for_model("claude-sonnet-x") == 40_000
