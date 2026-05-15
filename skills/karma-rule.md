# karma-rule skill — Natural-language rule input

**Install location**: copy this file to `~/.claude/skills/karma-rule.md` (Claude Code looks here for user skills)

**Trigger**: When user types `/karma rule <natural-language description>` in Claude Code

---

## Your job (Agent)

When the user invokes `/karma rule <description>`, you (the Agent) refine their natural-language description into karma's validated structure, test it, then add to their rules.yaml.

**Critical constraints — do NOT skip any step**:
1. Refine user's natural language into karma's "collaborative agreement" tone (not rule-system tone)
2. Format `violation_keywords` (if any) in "intent-prefix + action" format (e.g., "I'll skip this" not "skip")
3. Decide whether to attach `violation_checks` (engine-layer hook detection) — this is **optional**
4. Test via `karma rule preview` before writing
5. Confirm with user before calling `karma rule add`
6. After adding, report: refined content + test passed + current rule library count + suggest deletions/modifications

## karma rule design principles (apply these when refining)

### Tone: "collaborative agreement" not "rule system"

✅ "The user trusts you to dig into root causes. They want you to pause and think 'what's the cleanest solution?' rather than 'fastest patch'..."

❌ "You must always use long-term solutions. Don't patch."

The first activates cooperation, the second activates fight-or-flight defensive reactions.

### preference text structure

Open with user perspective:
- "The user trusts/hopes/needs..."
- "The user you're collaborating with is..."
- "When [situation], the user..."

Explain **why** (short-term vs. long-term trust):
- "Short-term [behavior] looks fine but [user perspective consequence]"
- "[Honest behavior] beats [evasive behavior] for trust-building"

Provide **exception channel** anchored to concrete scenarios:
- "If [significant disagreement], raise it for alignment"
- "Exception: user explicitly says X → only then..."

### violation_keywords format (if needed)

**Use "intent-prefix + action" format** to distinguish from discussion:

✅ "I'll patch this quickly" / "let me hardcode" / "I'll wait for tests"

❌ "patch" / "hardcode" / "wait" (too broad, false positives in discussions)

Cap at ~5-10 keywords per rule. More keywords ≠ better detection (LLMs tend to pattern-match "keyword list exists" not actually read).

### violation_checks (optional — engine-layer hook detection)

karma has 8 built-in engine-layer check functions. Attach one if the rule fits:

| Function | Detects |
|---|---|
| `long_term_fundamental` | git `--no-verify` / hardcoded long-hash if-branches / TODO comments |
| `non_blocking_parallel` | `sleep N` / long tasks without `run_in_background` |
| `loud_failure_with_evidence` | Completion words + no test pass evidence in session |
| `no_testset_no_future_leakage` | Eval data backfeeding training / cross-split copying |
| `read_before_write` | Edit/Write before Read on same file path |
| `bypass_karma_detection` | Bash commands with karma internal state + write ops |
| `keep_pushing_no_stop` | Agent silent-stop → reflective continuation prompt |
| `chinese_plain_no_jargon` | Chinese ratio < 40% / English jargon (Chinese users only) |

**If no engine check fits**, leave `violation_checks: []` — the rule still injects in headers, just without real-time interception. **Don't fabricate check function names** — only use the 8 above.

### force_block_exempt (optional)

Set `force_block_exempt: true` only for "should keep pushing / non-blocking" type rules where cumulative penalty would be self-contradictory (e.g., `non-blocking-parallel`, `keep-pushing-no-stop`).

## Workflow when user invokes `/karma rule <description>`

### Step 1: Understand intent

Ask clarifying questions if needed:
- What scenario triggers this rule?
- What Agent behavior do you want to prevent?
- Is this a one-off request or a long-term direction?

If it's a one-off request, suggest they handle it via in-context prompt instead — karma is for **long-term directional preferences**, not single-task instructions.

### Step 2: Check existing rules

Run `karma rule list` to see if existing rules already cover this case. If so, suggest the user modify the existing rule instead of adding a new one.

### Step 3: Refine into yaml

Draft a yaml snippet with:
- `id` — kebab-case slug (e.g., `must-run-tests-before-done`)
- `preference` — multi-line in collaborative-agreement tone (~3-5 lines)
- `violation_keywords` — intent-prefix + action format (3-8 entries)
- `violation_checks` — pick 0 or 1 of the 8 built-in functions
- `force_block_exempt` — usually omit (default false)

Save to a temp file (e.g., `/tmp/karma-new-rule.yaml`).

### Step 4: Preview test

Run:
```bash
karma rule preview --from-yaml /tmp/karma-new-rule.yaml
```

Shows: schema validation + how the rule looks in the injection header.

### Step 5: Confirm with user

Show the refined yaml + preview output. Ask:
- "Does this match your intent?"
- "Want to adjust the wording, add keywords, or attach an engine-layer check?"

If user wants changes, iterate (back to Step 3).

### Step 6: Write to rules.yaml

Once user confirms:
```bash
karma rule add --from-yaml /tmp/karma-new-rule.yaml
```

This re-validates schema + checks for id conflicts + verifies any violation_checks exist in REGISTRY + appends to `~/.claude/karma/rules.yaml`.

### Step 7: Report results

After `karma rule add` succeeds, summarize for the user:

1. **What was added** — show the final yaml (refined from their natural language)
2. **karma tests passed** — schema validation + violation_checks existence verified
3. **Current rule library count** — X of soft cap 10 / hard cap 12
4. **Suggest deletions/modifications**:
   - If close to soft cap (8+), suggest reviewing existing rules for duplicates/merging
   - If any existing rule seems related, suggest adjusting it instead of keeping both
   - Ask: "Do you want to remove or modify any existing rules?"

## Example walkthrough

**User**: `/karma rule When the Agent says "this is done", I want it to actually attach test pass evidence — don't just say done`

**Agent**:

> Got it. Let me check existing rules first.
>
> [Runs `karma rule list`]
>
> I see you have `loud-failure-with-evidence` already, which partially covers this. But your new request adds specificity: "must attach actual test pass evidence." Let me refine into a yaml:
>
> ```yaml
> - id: must-show-test-evidence-on-done
>   preference: |
>     The user trusts your "done" signal but needs to see actual evidence.
>     When you say "this is done" for code tasks, attach test-pass output /
>     build OK / data / screenshots so they can directly verify the result.
>     If you skipped a test or used mocks, honestly state it rather than
>     fake completion — this builds more trust than pretending.
>     Loud failure beats quiet covering-up.
>   violation_keywords:
>     - "this is done"
>     - "I'm done with this"
>     - "task complete"
>   violation_checks:
>     - loud_failure_with_evidence
> ```
>
> [Runs `karma rule preview --from-yaml /tmp/...`]
>
> ✓ Schema validation passed. Here's the injection preview:
>
> ```
> 4. must-show-test-evidence-on-done
>    The user trusts your "done" signal but needs to see actual evidence.
>    ...
> ```
>
> Does this match your intent? Two questions before I write it:
> 1. Should the keyword list also include "all set" or "all good"?
> 2. The existing `loud-failure-with-evidence` rule overlaps — want me to modify that one instead, or add this as a separate, more specific rule?

**User**: Add it. Also include "all set".

**Agent**:

> [Adds "all set" to violation_keywords, runs `karma rule add --from-yaml /tmp/...`]
>
> ✓ Rule added. Summary:
>
> **Added** `must-show-test-evidence-on-done`:
> - preference: (the refined text above)
> - violation_keywords: ["this is done", "I'm done with this", "task complete", "all set"]
> - violation_checks: ["loud_failure_with_evidence"] (engine-layer detection enabled)
>
> ✓ karma schema test passed
>
> 📊 **Current rule library**: 8 of soft cap 10 / hard cap 12
>
> 📋 **Existing rules**:
> - [long-term-fundamental] ✓ engine
> - [non-blocking-parallel] ✓ engine
> - [chinese-plain-no-jargon] preference-only
> - [loud-failure-with-evidence] ✓ engine
> - [no-testset-no-future-leakage] ✓ engine
> - [read-before-write] ✓ engine
> - [deep-fix-not-bypass] ✓ engine
> - [must-show-test-evidence-on-done] ✓ engine ← new
>
> 💡 **Suggestion**: You're at 8 of soft cap 10. The new rule overlaps with `loud-failure-with-evidence` in concept (both about evidence). If you find one redundant after a few days of use, consider running `karma rule remove <id>`. Want to do that now?

## Restart Claude Code after `karma rule add`

The new rule takes effect on the **next** UserPromptSubmit — restart Claude Code or just send a new message to see it injected.

## Common mistakes to avoid

- ❌ Don't write rules in "rule-system" tone ("you must always...")
- ❌ Don't use noun-only violation_keywords ("hardcoding" — too broad)
- ❌ Don't fabricate `violation_checks` function names — only use the 8 built-in ones
- ❌ Don't skip the preview step — always preview before `add`
- ❌ Don't add a new rule without checking for overlap with existing ones
- ❌ Don't exceed the soft cap 10 / hard cap 12 — too many rules backfire (LLMs pattern-match rule existence instead of truly reading)
