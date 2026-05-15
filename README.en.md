# karma

**[🇨🇳 中文](./README.md) · [🇬🇧 English (current)](./README.en.md)**

[![CI](https://github.com/jhaizhou-ops/karma/actions/workflows/ci.yml/badge.svg)](https://github.com/jhaizhou-ops/karma/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](https://github.com/jhaizhou-ops/karma/actions)
[![Latest Release](https://img.shields.io/github/v/release/jhaizhou-ops/karma?label=release)](https://github.com/jhaizhou-ops/karma/releases)
[![Last Commit](https://img.shields.io/github/last-commit/jhaizhou-ops/karma)](https://github.com/jhaizhou-ops/karma/commits/main)

> **Andrej Karpathy's 60k stars [CLAUDE.md](https://github.com/forrestchang/andrej-karpathy-skills) teaches AI how to write good code. karma solves the other half — how to make AI never violate your rules in long tasks, and most importantly, how to auto-correct violations before they frustrate you.**
>
> **Measured violation rate in long-running tasks: ≈ 0%.**
>
> Works with Claude Code / Codex CLI / Gemini CLI. Pure engineering, zero LLM dependency, violation monitoring response < 60ms.

---

> ⚠️ **This English README is a work-in-progress placeholder** — full English translation lands in v0.5.3 per [`docs/REFACTOR_PLAN_RULE_AND_I18N.md`](./docs/REFACTOR_PLAN_RULE_AND_I18N.md). Chinese version ([README.md](./README.md)) is complete and reflects the latest state.

---

## What karma solves

When you tell an AI agent "use long-term solutions, no quick patches" at turn 1, will it still remember after 50 turns / 60K tokens of context? **Without karma — usually no.** Your high-priority preferences get diluted by new content.

karma pins your 5–10 core preferences in the most prominent position of every conversation, automatically re-injects at adaptive thresholds per model (Opus 80K / Sonnet 60K / Haiku 30K), intercepts violations in real-time, and uses "collaborative agreement" tone (rather than rule-enforcement tone) so the AI's first reaction is "adjust to align" instead of "find a way around."

## 30-second install

```bash
git clone https://github.com/jhaizhou-ops/karma.git ~/karma
cd ~/karma && python -m venv .venv && .venv/bin/python -m pip install -e .
.venv/bin/karma init && .venv/bin/karma install-hooks
```

Restart your AI client (Claude Code / Codex / Gemini) — takes effect immediately.

## Key design principles

1. **Pure engineering, zero LLM** — single dependency (PyYAML, a 15-year-old Python ecosystem standard YAML parser). No API key, no network calls, no ML framework.
2. **User-controlled rules** — 5-10 rules you write yourself. karma doesn't auto-distill or guess your preferences.
3. **Collaborative tone, not rule system** — proven in long real-world use: "the user trusts you to..." invites cooperation, while "you must always follow X" triggers defensive reactions and workarounds.
4. **8 hook positions, full monitoring coverage** — UserPromptSubmit / PreToolUse / PostToolUse / Stop / SessionStart / PreCompact / SubagentStart / SubagentStop, all strictly compliant with Claude Code's hook protocol schema.
5. **Cross-compact persistence** — PreCompact dumps rules state to disk, SessionStart (compact) re-reads on restart. Rules survive context compaction.

## Why karma is **complementary** to Andrej Karpathy's CLAUDE.md (not competing)

- **Karpathy's 12 rules** are **universal coding principles** (cross-user, cross-project): "Think before coding," "Simplicity first," "Surgical changes," etc.
- **karma's rules** are **per-user personal preferences** (each user differs): "I prefer Chinese over jargon," "I want full-delegation, don't stop to ask," etc.

**Recommended setup**: install Karpathy 12 rules in CLAUDE.md (project-shared) + install your personal rules via karma (user-level `~/.claude/karma/rules.yaml`). They run on the same Claude Code instance without conflict.

## Roadmap

- ✅ **v0.5.0** — `sticky` → `rule` rename + backward-compat migration (current)
- 🔜 **v0.5.1** — `karma rule add` CLI + Claude Code skill for natural-language rule creation
- 🔜 **v0.5.2** — i18n infrastructure (zh + en starter)
- 🔜 **v0.5.3** — Full English translations for all user-facing texts (CLI output / hook injection / suggested fixes)

## Status

karma is in **early real-user phase**. Author has been dogfooding on own projects for ~12 months. New users' first-install pain points will drive v0.5.x+ improvements.

See [Chinese README](./README.md) for the complete documentation including:
- Detailed pain point analysis with 6 "before/after" scenarios
- Usage effects across 6 typical hook activation scenarios
- Performance metrics (memory / token / latency)
- 8 built-in violation_check functions
- 9 design anti-patterns we tried and rejected
- FAQ + design philosophy

## License

MIT
