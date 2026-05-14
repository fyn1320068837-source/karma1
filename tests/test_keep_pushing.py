"""keep_pushing_no_stop check 测试 — 末尾问句无推进信号 = 疑似停下等用户。"""

from __future__ import annotations

from karma.checks import REGISTRY


def _check(response: str):
    return REGISTRY["keep_pushing_no_stop"](response=response)


def test_response_ending_with_question_blocked():
    """末尾问句 + 无推进信号 → 命中。"""
    hit = _check("做完了。要不要继续做下一步？")
    assert hit is not None


def test_response_with_push_signal_exempted():
    """末尾问句但有明确推进字眼 → 不命中（推进 + 提问混合是合理）。"""
    hit = _check("做完了。我现在开始做下一步，如果 X 失败再问你？")
    assert hit is None


def test_no_question_passes():
    """无问号 → 不命中。"""
    hit = _check("做完了。我接着推下一波。")
    assert hit is None


def test_pure_chinese_question_mark_blocked():
    """中文问号 ？也算。"""
    hit = _check("两个方向都可以，您想要哪个？")
    assert hit is not None


def test_question_in_middle_not_at_tail_passes():
    """问号在中间不在末尾 → 不算（不影响后续推进）。"""
    hit = _check("是否要做 X？要的。我现在去做 X 然后推进 Y。")
    assert hit is None


def test_empty_response_passes():
    assert _check("") is None
    assert _check("   ") is None


def test_long_response_short_tail_window():
    """末尾窗口只看最后 80 字 — 中段问号不算。"""
    middle_q = "前面讨论问题：要 X 吗？" + " 后面 " * 50 + "我马上开始做实施。"
    hit = _check(middle_q)
    assert hit is None  # 末尾「我马上开始做实施。」是推进信号


# ---- 用户反馈：「没问号也停了」— 沉默式停下检测 ----

def test_silent_stop_with_next_time_phrase_blocked():
    """末尾「下次跑 X 看」— 沉默式停下，命中。"""
    hit = _check("M3 完成了，commit 推完了。下次跑 audit 看新出现什么。")
    assert hit is not None
    assert "停顿" in hit.trigger or "下次" in hit.trigger


def test_silent_stop_xianzheli_blocked():
    """末尾「先到这」— 命中。"""
    hit = _check("一波改完了，测试 187 全过。先到这。")
    assert hit is not None


def test_silent_stop_gaoyiduanluo_blocked():
    """末尾「告一段落」— 命中。"""
    hit = _check("这阶段任务完成。告一段落，等真实数据再迭代。")
    assert hit is not None


def test_silent_stop_with_push_signal_exempted():
    """末尾有「下次」字眼但同时有推进信号 → 不命中。"""
    hit = _check("commit 推了。我现在开始改下一个文件，下次跑测试前确认 X。")
    assert hit is None


def test_summary_without_stop_hint_passes():
    """纯总结无停顿词无推进信号 → 不命中（避免简短汇报假阳）。"""
    hit = _check("commit ffcbd07 已推 origin/main。")
    assert hit is None
