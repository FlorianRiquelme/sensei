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

Miner lives at `~/.claude/skills/sensei/mine.py` (installed alongside this skill by
`install.sh`, stdlib-only Python — reads `~/.claude/projects/**/*.jsonl`, writes
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

1. Mining has already run. The launchd job runs the miner in its own shell immediately
   before invoking this skill, so `~/.claude/sensei/events.json` is already current — this
   mode only reads it (step 3), never runs the miner. (Running `/sensei nightly` by hand to
   test? Refresh events first: `python3 ~/.claude/skills/sensei/mine.py --days 1`.)
2. Read `~/.claude/sensei/decisions.jsonl` if it exists — this is sensei's memory of past
   verdicts. Each line carries a stable proposal `key` (see step 4), a `verdict`, and a `date`.
   Use it to decide what may be re-proposed:
   - **accepted** decisions never expire — the rule is already in the target file, so step 4's
     "read the target and don't duplicate an existing rule" is what keeps it from recurring.
   - **rejected** decisions impose a **30-day cooldown**, not permanent suppression. A pattern
     matching a rejected decision is suppressed until 30 days after that decision's `date` (use
     the most recent rejection if the same key was rejected more than once). Once the window has
     elapsed the pattern is re-eligible — and will only actually resurface if it recurs in fresh
     events, which the daily mine surfaces naturally.

   Match a candidate pattern against prior decisions **semantically**, using each decision's
   `key` as a strong hint — do not gate on title string-equality (titles are free text and drift
   between runs). Legacy decision lines written before keys existed carry only a `title`; fall
   back to a semantic title match for those.
3. Read `~/.claude/sensei/events.json`. Cluster the events semantically into recurring
   friction patterns (same root cause, not just same event type). A pattern qualifies for a
   proposal only if:
   - it appears in **≥2 independent sessions** (different `session` values), OR
   - it is a **single high-severity event** — e.g. a destructive action the user had to
     interrupt or explicitly deny.
   Discard everything else, and drop any pattern currently suppressed by a decision (step 2).
4. For each qualifying pattern, before writing anything, **read the current target file**
   (`~/.claude/CLAUDE.md`, the relevant skill's `SKILL.md`, or a per-project `CLAUDE.md`) so
   the proposal fits its existing structure and doesn't duplicate an existing rule. Then draft:
   - **Title** — short, specific.
   - **Key** — a stable identity for this proposal, independent of the title's wording:
     `<target-file>::<normalized-rule-slug>`, where the slug is a short lowercase, hyphenated
     signature of the rule's *intent* (e.g. `~/.claude/CLAUDE.md::ddev-prefix-artisan`). Two
     proposals that would edit the same rule must produce the same key even if their titles
     differ. This is what step 2 matches against and what review records in `decisions.jsonl`.
     Emit the key as its own line, exactly: `- **Key:** <target-file>::<slug>` — this literal
     format is a parse contract the session nudge depends on.
   - **Evidence** — 2–3 verbatim quotes from `user_text` / `assistant_context`, each tagged
     with its `project`.
   - **Supporting events** — the qualifying cluster's event count (the size already computed
     in step 3), as its own line: `- **Supporting events:** N`.
   - **Root cause** — one sentence.
   - **Target file** — exact path.
   - **Exact text** — the literal diff to add/change, ready to paste as-is.
5. Write `~/.claude/sensei/proposals/YYYY-MM-DD.md` (today's date) with every qualifying
   proposal in the format above, separated by `---`. If zero patterns qualified, write a
   one-line file: `# YYYY-MM-DD — nothing today (N events scanned, 0 qualifying patterns)`.

## Mode: review

Interactive, run by the human in the morning.

1. Find the newest file under `~/.claude/sensei/proposals/`. Check `decisions.jsonl` for
   proposals from that file already decided (match by `key`) — if every proposal in the newest
   file is already decided, fall back to the next-newest file with undecided proposals. If none,
   say so and stop.
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
   {"date": "YYYY-MM-DD", "title": "...", "key": "...", "verdict": "accepted|rejected", "target": "..."}
   ```
   Copy the `key` verbatim from the proposal — the cooldown and dedup in nightly step 2 depend
   on it being stable across runs. When the proposal is **accepted**, additionally copy its
   `Supporting events` value into the decision as `"baseline": N`:
   ```json
   {"date": "YYYY-MM-DD", "title": "...", "key": "...", "verdict": "accepted", "target": "...", "baseline": N}
   ```
   Rejected decisions carry no `baseline` field. This seeds a future track-record slice; nothing
   reads it yet.
4. When all proposals in the file are decided, tell the user how many were accepted/rejected.
