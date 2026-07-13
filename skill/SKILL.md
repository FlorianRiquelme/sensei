---
name: sensei
description: >
  Self-improving Claude Code config. Mines your own transcripts for friction
  (corrections, tool-use denials, interrupts), proposes concrete diffs to
  CLAUDE.md / skills, and lets you accept/reject them over coffee. Two modes
  via args: "nightly" (headless, run by launchd — mines + writes proposals,
  never edits config) and "review" (interactive, morning — walks proposals
  one at a time and applies what you accept). Use when the user invokes
  "/sensei nightly", "/sensei review", or asks to review sensei's proposals.
argument-hint: "nightly | review"
disable-model-invocation: true
---

# sensei

Miner lives at `/Users/florianriquelme/Repos/mine/claudesetup/sensei/mine.py` (repo-resident,
stdlib-only Python — reads `~/.claude/projects/**/*.jsonl`, writes
`~/.claude/sensei/events.json`). This skill has two modes, chosen by the argument
("nightly" or "review"). If no argument was given, ask which mode.

State lives under `~/.claude/sensei/`:
- `events.json` — latest miner output (overwritten each run).
- `decisions.jsonl` — append-only log of every past verdict: `{"date", "title", "verdict", "target"}`.
- `proposals/YYYY-MM-DD.md` — one report per nightly run.
- `logs/nightly.log` — launchd stdout/stderr.

## Mode: nightly

Headless. Run by launchd at 05:30. **Never edit CLAUDE.md, skills, or any other config file
in this mode — proposals only.** That rule is absolute even if a fix looks trivial or obvious.

1. Run the miner for the last day:
   ```
   python3 /Users/florianriquelme/Repos/mine/claudesetup/sensei/mine.py --days 1
   ```
2. Read `~/.claude/sensei/decisions.jsonl` if it exists. Build the set of previously-decided
   proposal titles. Never re-propose a title that was already rejected.
3. Read `~/.claude/sensei/events.json`. Cluster the events semantically into recurring
   friction patterns (same root cause, not just same event type). A pattern qualifies for a
   proposal only if:
   - it appears in **≥2 independent sessions** (different `session` values), OR
   - it is a **single high-severity event** — e.g. a destructive action the user had to
     interrupt or explicitly deny.
   Discard everything else. Skip any pattern whose title duplicates a decision already in
   `decisions.jsonl`.
4. For each qualifying pattern, before writing anything, **read the current target file**
   (`~/.claude/CLAUDE.md`, the relevant skill's `SKILL.md`, or a per-project `CLAUDE.md`) so
   the proposal fits its existing structure and doesn't duplicate an existing rule. Then draft:
   - **Title** — short, specific.
   - **Evidence** — 2–3 verbatim quotes from `user_text` / `assistant_context`, each tagged
     with its `project`.
   - **Root cause** — one sentence.
   - **Target file** — exact path.
   - **Exact text** — the literal diff to add/change, ready to paste as-is.
5. Write `~/.claude/sensei/proposals/YYYY-MM-DD.md` (today's date) with every qualifying
   proposal in the format above, separated by `---`. If zero patterns qualified, write a
   one-line file: `# YYYY-MM-DD — nothing today (N events scanned, 0 qualifying patterns)`.
6. Notify: `osascript -e 'display notification "N proposals" with title "sensei"'` (N = number
   of proposals written, or 0).

## Mode: review

Interactive, run by the human in the morning.

1. Find the newest file under `~/.claude/sensei/proposals/`. Check `decisions.jsonl` for
   titles from that file already decided — if every proposal in the newest file is already
   decided, fall back to the next-newest file with undecided proposals. If none, say so and
   stop.
2. Walk proposals **one at a time**, in plain text (no dialog tool needed — this is a
   conversation):
   - Show the title, evidence quotes, root cause, target file, and exact text to add/change.
   - Ask: accept / reject / edit?
   - On "edit", let the user redirect the wording, then re-confirm accept/reject.
3. For each accepted proposal, apply the exact text to its target file (read the file fresh
   right before editing — it may have changed since the nightly run). For each proposal
   (accepted, rejected, or edited-then-accepted), append one line to
   `~/.claude/sensei/decisions.jsonl`:
   ```json
   {"date": "YYYY-MM-DD", "title": "...", "verdict": "accepted|rejected", "target": "..."}
   ```
4. When all proposals in the file are decided, tell the user how many were accepted/rejected.
