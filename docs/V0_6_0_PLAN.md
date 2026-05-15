# karma v0.6.0 plan — remove backward-compat scaffolding

**[🇬🇧 English (current)](./V0_6_0_PLAN.md) · [🇨🇳 中文](./V0_6_0_PLAN.zh.md)**

**Draft date**: 2026-05-15
**Drafter**: Claude Opus 4.7 (audit-driven)
**Status**: 📝 **Draft — not implemented**. Listed here as the explicit deprecation contract so users get one release cycle of warning before any breaking change.

---

## Why v0.6.0 exists

v0.5.0 renamed `sticky` → `rule` across the codebase and shipped backward-compat aliases everywhere (module, classes, properties, CLI subcommand, file paths). v0.5.13 cleaned the **attribute-level** `.sticky_id` callsites inside karma itself, but a follow-up audit found that **module-level** `from karma.sticky import ...` lingers in 6 internal locations — and a dozen more aliases sit in `karma/rule.py`, `karma/cli.py`, `karma/checks/_types.py`, `karma/violations.py`.

v0.6.0's job: **delete the scaffolding**. Result: a codebase where `sticky` only appears in (a) historical CHANGELOG entries and (b) the migration path that handles legacy on-disk data (`sticky.yaml` → `rules.yaml`, old `violations.jsonl` rows with `sticky_id` key). Nothing else.

This is a **breaking change for users who imported `karma.sticky` directly or accessed `.sticky_id` on `CheckHit`/`Violation`**. The deprecation warning has been live since v0.5.0; v0.6.0 is the cliff. Users have had the v0.5.x cycle to migrate.

## What v0.6.0 removes

### Group A — internal scaffolding (zero external impact, just code cleanup)

These are referenced only by karma's own code; removing them is purely an internal refactor.

| Item | Location | v0.5.13 status |
|---|---|---|
| `MAX_STICKY = MAX_RULES` alias | `karma/rule.py:43` | Used by `cli.py:54` |
| `Sticky = Rule` alias | `karma/rule.py:62` | Possibly used in tests |
| `StickyConfigError = RuleConfigError` alias | `karma/rule.py:76` | Used by `cli.py:54`, `hooks/stop.py:24` |
| `EXAMPLE_STICKY = EXAMPLE_RULES` alias | `karma/cli.py:69` | Internal only |
| `EXAMPLE_STICKY_MINIMAL = EXAMPLE_RULES_MINIMAL` alias | `karma/cli.py:70` | Internal only |
| ~~11 internal `from karma.sticky import ...` callsites~~ | ~~`cli.py` (4), `hooks/*.py` (6), `karma/sticky.py` self-ref~~ | ✅ **Cleaned in v0.5.15** (11 source + 4 test files migrated to `from karma.rule import ...`; `pytest -W error::DeprecationWarning` runs clean) |

**Action for v0.6.0**: the `from karma.sticky` cleanup is already done (v0.5.15). Now safe to delete the alias module + aliases below without breaking karma's own code.

### Group B — public API breaking changes (deprecation contract)

These have been deprecated since v0.5.0 with stderr warnings. Removing them in v0.6.0 honors the deprecation contract.

| Item | Effect of removal | User-facing |
|---|---|---|
| `karma/sticky.py` compat shim module | `from karma.sticky import ...` raises `ModuleNotFoundError` | **Yes** — users with custom scripts importing `karma.sticky` will break |
| `Violation.sticky_id` @property (alias to `.rule_id`) | `violation.sticky_id` raises `AttributeError` | **Yes** — analysis scripts accessing this attribute |
| `CheckHit.sticky_id` @property (alias to `.rule_id`) | `hit.sticky_id` raises `AttributeError` | **Yes** — custom violation_check authors |
| `karma sticky <subcommand>` CLI alias | `karma sticky list` etc. exit 1 with "unknown command" | **Yes** — muscle memory / scripts running `karma sticky list` |

### Group C — legacy data migration (KEEP — these handle real user state, not API surface)

**Do not remove these in v0.6.0.** They handle on-disk data written by older karma versions; they're not deprecation aliases, they're correctness shims.

| Item | Location | Why keep |
|---|---|---|
| `sticky.yaml` → `rules.yaml` auto-migration in `cmd_init` | `cli.py:191-197` | Users upgrading from v0.4.x still have `sticky.yaml` on disk |
| `_extract_rule_id` fallback to old `sticky_id` jsonl field | `karma/violations.py` | Historical `violations.jsonl` rows from v0.4.x have `sticky_id` field, not `rule_id`. `karma audit` / `stats` must still read them. |
| `karma init` legacy-sticky.yaml fallback path for `DEFAULT_PATH` | `karma/rule.py` | Same — old install paths |

These cost ~20 lines and stay forever (or until a separate "drop v0.4.x data compat" release with its own deprecation cycle).

## Execution order (when v0.6.0 actually happens)

To avoid breaking karma's own tests mid-refactor, the order must be:

1. **Pre-v0.6.0 cleanup commit** (could ship as v0.5.15 doc-only): grep verifies zero `from karma.sticky` in karma's own code. If any found, fix them as a v0.5.x release first.
2. **v0.6.0-rc1**: replace the 6 internal `from karma.sticky` imports with `from karma.rule` (Group A). Run full test suite — should still pass since `karma.sticky` is still a working shim.
3. **v0.6.0**: delete `karma/sticky.py`, delete the 4 aliases in `karma/rule.py` (`MAX_STICKY` / `Sticky` / `StickyConfigError`), delete `EXAMPLE_STICKY` / `EXAMPLE_STICKY_MINIMAL` in `cli.py`, delete `.sticky_id` @property on `CheckHit` + `Violation`, delete `karma sticky` CLI alias dispatch in `cli.py`. Test suite must still pass (zero internal callsites should remain after step 2).

## Test coverage expectations

After v0.6.0:
- All 410 v0.5.14 tests should still pass (none should have been relying on the aliases — v0.5.13 cleaned those)
- If any test breaks, it's a v0.5.x cleanup miss — fix the test, not the code
- Add 1 regression test confirming `import karma.sticky` raises `ModuleNotFoundError` (lock the deletion in)
- Add 1 regression test confirming `karma sticky list` exits 1 with "unknown command" (lock the CLI deletion in)

## Announcement timing

- v0.5.14 (current): this plan doc is live in `docs/V0_6_0_PLAN.md` — users searching the repo can preview the cliff
- v0.5.15 (suggested next step): pre-v0.6.0 cleanup commit + add `print()` warning in `karma --version` / `karma doctor` output saying "v0.6.0 will remove `karma.sticky` module and `.sticky_id` attribute aliases — see `docs/V0_6_0_PLAN.md`"
- v0.6.0: actual breaking change. CHANGELOG entry must be top-of-fold + GitHub release notes flag breaking change

## What v0.6.0 is NOT

- Not a feature release. No new functionality. Pure cleanup of v0.5.0's renaming scaffolding.
- Not "remove all backward compat forever." Group C (on-disk data shims) stays.
- Not a chance to slip other breaking changes in. SemVer major bump means *one* breaking-change theme — alias removal — not a kitchen sink.

## Risk assessment

| Risk | Mitigation |
|---|---|
| User script imports `karma.sticky` and breaks on upgrade | Deprecation warning has been firing since v0.5.0 (≥ 1 release cycle of notice). Migration is mechanical: one-line `s/karma\.sticky/karma.rule/`. |
| `karma sticky list` muscle memory breaks | CLI dispatch can emit a one-line "did you mean `karma rule list`?" hint on `unknown command: sticky` — costs 3 lines, saves user confusion |
| Old `violations.jsonl` data becomes unreadable | Mitigated — Group C `_extract_rule_id` fallback stays. Users keep all historical audit data. |
| Internal test references `Sticky` class directly | Audit step 1 (pre-v0.6.0 cleanup) catches this — fix before deletion |

## Open questions

1. **Should the `karma sticky` CLI alias survive longer?** Different from module/attribute aliases because it's user-facing muscle memory (typing on the command line). Could keep one more release cycle. **Tentative answer**: drop it in v0.6.0 with a "did you mean?" hint — same cliff as the rest is cleaner.
2. **Should v0.6.0 also drop the `chinese_plain_no_jargon` check for non-Chinese users by default?** Currently the check ships installed but gets stripped via `karma init` template selection. Not really a backward-compat issue, more a scope question. **Tentative answer**: out of scope for v0.6.0 — separate decision.
