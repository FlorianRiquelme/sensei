# sensei — the self-improving Claude Code setup

A nightly agent that mines your own Claude Code transcripts — for friction (corrections,
tool-use denials, interrupts) *and* for habits (directives you re-supply every session with no
friction at all) — clusters the recurring patterns, and drafts concrete diffs to your
`~/.claude/CLAUDE.md` and skills. If a rule it already installed keeps failing to stick, it
escalates to a proposed hook instead of a prose edit. You review everything over coffee; nothing
changes your config, and no hook is ever installed, until you accept it.

## Requirements

- **macOS.** The scheduler is a launchd agent — macOS-only, by design (ADR-0007). There is no
  Linux/Windows fallback.
- **Python 3** (system Python is fine — the miner is standard-library only, no deps, no venv; ADR-0008).
- **Claude Code** on your `PATH` (the `claude` CLI).

## Install

```
./install.sh
```

Idempotent. It copies the skill, miner, and session nudge into `~/.claude/skills/sensei/`,
creates the state dirs under `~/.claude/sensei/`, registers a SessionStart hook in
`~/.claude/settings.json` (preserving any hooks already there), resolves the launchd job for
your user, and loads it. The job runs daily at **05:30**. The clone is disposable afterward —
nothing runs from the repo (ADR-0009).

To uninstall, from the clone: `./uninstall.sh`. Removes the hook, launchd job, and skills dir;
preserves everything under `~/.claude/sensei/` (decisions, proposals, digests, logs).

## How it works (three parts)

1. **Miner** — `mine.py`. Deterministic, zero-token, stdlib-only Python. The only component that
   reads raw transcripts (`~/.claude/projects/**/*.jsonl`); it emits friction and repeat events to
   `~/.claude/sensei/events.json` and touches nothing else (ADR-0001).
2. **Skill** — `~/.claude/skills/sensei/`. Two modes:
   - `/sensei nightly` — headless, run by launchd. Reads the mined events, clusters them, and
     writes a proposal report to `~/.claude/sensei/proposals/YYYY-MM-DD.md` — a prose edit, a
     habit-rule, or (if an already-accepted rule keeps failing to stick) a proposed hook.
     **Never edits config** — it physically can't (ADR-0002, ADR-0005).
   - `/sensei review` — interactive, run by you in the morning. Walks the proposals one at a time,
     runs a short "why?" on any reject, and applies the prose/habit-rule proposals you accept. A
     hook proposal is presented, never applied — you install it.
3. **Scheduler** — a launchd agent (`sh.sensei`) that runs the miner and then `/sensei nightly`
   at 05:30, logging to `~/.claude/sensei/logs/nightly.log`. The miner also writes a dated
   Digest (`~/.claude/sensei/digests/YYYY-MM-DD.json`) — its presence is proof the patrol ran.
4. **Nudge** — `nudge.py`, a SessionStart hook. Prints one line in your first Claude Code
   session of the day: a quiet heartbeat, a pending-proposals reminder, or a loud warning if
   last night's Digest is missing.

## Other languages

The correction lexicon ships **English + German**. To detect push-back in your language, edit
`CORRECTION_RE` in `mine.py` (it's marked as the one place to edit) and re-run `install.sh`. This
only affects `correction` recall — interrupt and denial detection are language-independent, so
sensei works with an unedited lexicon regardless of your language.

## Design decisions

The *why* behind the shape of this project lives in `docs/adr/`; the domain vocabulary lives in
`CONTEXT.md`.
