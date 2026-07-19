# CLAUDE.md

## Working in this repo

- Nothing runs from this repo: `install.sh` copies `skill/SKILL.md` and `mine.py` to
  `~/.claude/skills/sensei/` (ADR-0009). Edits in the repo are inert until `./install.sh` is
  re-run — if you edit the skill or miner and then test `/sensei nightly`, you're testing the
  stale installed copy.
- To test miner changes, run it straight from the repo against fixtures or with an explicit
  output path: `python3 mine.py --days 7 --out <scratch-path>` — never let a test run overwrite
  the live `~/.claude/sensei/events.json`.
- `~/.claude/sensei/` is live user state. Never edit `decisions.jsonl`, delete proposals, or
  unload/reload the launchd job (`sh.sensei`) during development unless explicitly asked.
- Tests live in `tests/` and are stdlib-only: `python3 -m unittest discover tests`.

## Invariants

- The miner is deterministic, zero-token, and the ONLY component that reads raw transcripts
  (ADR-0001).
- Nightly mode proposes only; it never edits CLAUDE.md, skills, or any config (ADR-0002, enforced
  by the headless allowlist per ADR-0005). Only interactive review applies changes.
- Python is stdlib-only — no dependencies, no venv, ever (ADR-0008).
- macOS-only by design (launchd) — don't add Linux/Windows portability shims (ADR-0007).
- Miner favors recall; precision is the LLM's job — don't "fix" over-capture in the regex
  (ADR-0004).

## Agent skills

### Issue tracker

Issues and PRDs live in this repo's GitHub Issues (via the `gh` CLI); external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles using the default label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Workflow

This repo follows a compound-engineering (CE) lifecycle. A feature moves through these skills in order:

1. `/ce-ideate` and/or `/ce-brainstorm` — explore and frame the product contract; produces the plan under `docs/plans/`.
2. `/grill-with-docs` — relentlessly sharpen the plan; writes/edits ADRs (`docs/adr/`), the glossary (`CONTEXT.md`), and the plan doc.
3. `/ce-plan` — scope the plan into work units.
4. `/goal` — implement a work unit.
5. `/ce-code-review` — review the implementation.

### Stage handoffs

When a stage finishes, proactively copy a kickoff prompt for the **next** stage into the clipboard (`pbcopy`) so a fresh session can start immediately without being asked. The prompt's first line is the next skill's slash command; the body carries the context that session needs — the **repo-relative path to the plan doc** under `docs/plans/` (always include it: every stage after brainstorm operates on that one file, and the fresh session cannot reliably find it otherwise), the branch, the reading order, and the task. The chain is fixed — ideate/brainstorm → `/grill-with-docs` → `/ce-plan` → `/goal` → `/ce-code-review` — so each session already knows what comes next (e.g. finishing `/grill-with-docs` copies a `/ce-plan` prompt that names the plan file).

### Branching

One **feature branch** per feature (`<type>/<short-description>`, e.g. `feat/nightly-digest-session-nudge`), and the whole lifecycle lands on it: the docs from `/grill-with-docs` are the branch's first commits, and `/ce-plan`, `/goal`, and `/ce-code-review` all continue on the **same** branch until it merges to `main` after review. Do **not** create a separate docs-only branch — the docs and the code they describe travel together.
