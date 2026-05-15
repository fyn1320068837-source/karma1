---
name: Bug Report (English)
about: Report a karma bug / false positive / install issue / hook malfunction
title: '[Bug] '
labels: bug
assignees: ''
---

## What did you encounter

Brief description of the problem. For **false positives** (karma blocks legitimate operations), paste `karma audit` output with the `⚠️ possible false positive` markers.

## Reproduction steps

1. Install via `karma install-hooks ...`
2. ...
3. Observed error / unexpected behavior

## Real state (output of `karma doctor`)

```
(paste complete `karma doctor` output)
```

## Environment

- karma version: (`karma --version`)
- AI client: Claude Code / Codex CLI / Gemini CLI (with version)
- OS: macOS / Linux / WSL
- Python: (`python --version`)
- Shell: zsh / bash / fish

## Key logs (if any)

If hook output schema errors or installation failures occur, paste the stderr / Claude Code UI error section.
