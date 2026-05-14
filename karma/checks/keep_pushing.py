"""#7 keep-pushing-no-stop — 不主动停下问用户。

检测的行为模式（post_response / Stop hook 扫 Agent response）：
末尾 60 字含问号（? 或 ？）+ 没有明确推进信号（「我现在/立刻/马上 + 动词」）
→ 疑似停下等用户决定，违反 sticky #7「立即选下个推进点继续做」。

设计权衡：
- 真问号 + 真推进信号 → 不算（如「我现在去做 X。要是 Y 失败了怎么办？」末尾问号但前有推进）
- 真问号 + 无推进信号 → 命中（如「下一步要 X 还是 Y？」）
- 短回复无问号 → 不算（可能简短确认，可能内含推进，工程层难判，让关键词层兜底）
"""

from __future__ import annotations

import re

_STICKY_ID = "keep-pushing-no-stop"

# 末尾问号（中英文）— 限定 response 最后 80 字（多数「停下问」signal 在末尾）
_TAIL_QUESTION_RE = re.compile(r"[?？]")

# 停顿语气词 — Agent 明确表达「暂停 / 等下次 / 告一段落」类
# 这些词出现在末尾窗口且无推进信号 → 沉默式停下（用户的「没问号也停了」反馈）
_STOP_HINT_RE = re.compile(
    r"(?:"
    r"等下次|下次跑|下次看|下次再|下次见|下次有"
    r"|先到这|先到此|告一段落|暂告一段落|暂停一下|停一下|这阶段(?:完|结束)"
    r"|当前(?:状态|进度)是|当前节点|本轮 OK"
    r"|累积到一定量再"
    r"|看新出现什么"
    r")",
    re.IGNORECASE,
)

# 明确「推进信号」字眼 — 表达 Agent 主动继续推进
_PUSH_SIGNAL_RE = re.compile(
    r"(?:"
    r"我(?:现在|立刻|马上|立即|继续|先|来|接着|顺手)\s*(?:做|改|加|修|跑|去|开始|实施|实现|动手|推|搞|写|发|提交|测试|验证|跑测|读)"
    r"|立刻\s*(?:做|开始|实施|推|继续|动手)"
    r"|马上\s*(?:做|开始|实施|推|继续|动手)"
    r"|继续推进"
    r"|开始做"
    r"|直接(?:做|改|开始|实施|推|动手|去做)"
    r"|不停"
    r"|一并(?:做|改|实施)"
    r")",
    re.IGNORECASE,
)

# 末尾扫描窗口（字符数）— 80 字平衡覆盖跟假阳
_TAIL_WINDOW = 80


def check(*, response: str = "", **_):
    """Agent response 末尾窗口扫两类停下信号 + 无推进信号 → 疑似停下等用户：
    1. 问号（? 或 ？）— 显式询问
    2. 停顿语气词（下次 / 先到这 / 告一段落 等）— 沉默式停下（用户反馈：没问号也停）
    """
    if not response or not response.strip():
        return None
    text = response.strip()
    tail = text[-_TAIL_WINDOW:]

    # 末尾窗口有明确推进信号 → 直接放过（无论有无问号 / 停顿词）
    if _PUSH_SIGNAL_RE.search(tail):
        return None

    from karma.checks import CheckHit

    # 信号 1：问号
    if _TAIL_QUESTION_RE.search(tail):
        return CheckHit(
            sticky_id=_STICKY_ID,
            trigger="response 末尾问句无明确推进信号 — 疑似停下等用户决定",
            snippet=tail[:200],
            suggested_fix="去掉末尾问句，立即选下个推进点开始做 + 简短汇报。"
                          "如确需用户决策，明确标出「这一步需要你定」。",
        )

    # 信号 2：停顿语气词（用户的「没问号也停」反馈）
    m_stop = _STOP_HINT_RE.search(tail)
    if m_stop:
        return CheckHit(
            sticky_id=_STICKY_ID,
            trigger=f"response 末尾含停顿语气 {m_stop.group()!r} — 沉默式停下，没立即推下个推进点",
            snippet=tail[:200],
            suggested_fix="去掉「下次/先到这/告一段落」等停顿词，直接说明现在去做啥。"
                          "汇报跟推进并行：写完汇报立刻开始下个 tool 调用。",
        )
    return None
