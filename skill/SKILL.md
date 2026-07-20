---
name: sensei
description: >
  Self-improving Claude Code config. Mines your own transcripts for friction
  (corrections, tool-use denials, interrupts) and for habits (directives you
  re-supply every session with no friction at all), proposes concrete diffs to
  CLAUDE.md / skills — or, for a rule that keeps failing after acceptance, a
  proposed hook — and lets you accept/reject them over coffee. Two modes via
  args: "nightly" (headless, run by launchd — mines + writes proposals, never
  edits config) and "review" (interactive, morning — walks proposals one at a
  time, runs a mini-grill on reject, and applies what you accept). Use when the
  user invokes "/sensei nightly", "/sensei review", or asks to review sensei's
  proposals.
argument-hint: "nightly | review"
disable-model-invocation: true
---

# sensei

Miner lives at `~/.claude/skills/sensei/mine.py` (installed alongside this skill by
`install.sh`, stdlib-only Python — reads `~/.claude/projects/**/*.jsonl`, writes
`~/.claude/sensei/events.json`). This skill has two modes, chosen by the argument
("nightly" or "review"). If no argument was given, ask which mode.

State lives under `~/.claude/sensei/`:
- `events.json` — latest miner output (overwritten each run). Each event is a `correction`,
  `denial`, `interrupt`, or `repeat`. `correction`/`interrupt` events carry a raw
  `nth_in_session` ordinal; `interrupt` events also carry `followup_text` (the next plain user
  text after the interrupt, if any). `repeat` events carry `session_count` and `projects`
  instead of a single session — they're already cross-session by construction.
- `decisions.jsonl` — append-only log of every past verdict:
  `{"date", "title", "key", "verdict", "target", "reason", "reason_kind", "tier", "baseline"}`.
  `verdict` is one of `accepted`, `reject-retry-narrower`, `reject-not-wanted`, or the legacy
  bare `rejected`. `reason`/`reason_kind` are only present on the two structured reject
  verdicts (see review step 3). `tier` is only present on an **accepted** decision that came
  from a hook proposal (`tier: "hook"`) — its absence means prose/habit-rule, the default tier.
  `baseline` is the qualifying event count captured on an **accepted** prose/habit-rule decision
  (see review step 3); nothing reads it yet.
- `proposals/YYYY-MM-DD.md` — one report per nightly run.
- `logs/nightly.log` — launchd stdout/stderr.

## Mode: nightly

Headless. Run by launchd at 05:30. **Never edit CLAUDE.md, skills, or any other config file
in this mode — proposals only.** That rule is absolute even if a fix looks trivial or obvious.
The one exception to "proposals only" is the hook branch in step 4, which is still a proposal —
it produces a ready artifact but never writes it.

1. Mining has already run. The launchd job runs the miner in its own shell immediately
   before invoking this skill, so `~/.claude/sensei/events.json` is already current — this
   mode only reads it (step 3), never runs the miner. (Running `/sensei nightly` by hand to
   test? Refresh events first: `python3 ~/.claude/skills/sensei/mine.py --days 14`.)
2. Read `~/.claude/sensei/decisions.jsonl` if it exists — this is sensei's memory of past
   verdicts. Each line carries a stable proposal `key` (see step 4), a `verdict`, and a `date`.
   Use it to decide what may be re-proposed, and whether an already-accepted rule should
   escalate:
   - **accepted** decisions normally never expire — the rule is already in the target file, so
     step 4's "read the target and don't duplicate an existing rule" is what keeps it from
     recurring. **Exception (ADR-0012, loop-closing):** if a pattern matching an accepted
     decision *still independently qualifies* (step 3's bar) **and the decision's `date` is more
     than ~14 days in the past** (today minus `date` > the grace period), don't skip it — flag it
     for **escalation** in step 4 instead. The grace period is a check on the *decision's* age,
     not on individual event timestamps: step 3 only ever hands you events that are already
     current (inside the friction window, or a `repeat` the miner just emitted this run), so any
     qualifying pattern is inherently "recent" — the only question worth asking is whether enough
     time has passed since acceptance for the rule to have had a fair chance to stick. If the
     decision is younger than the grace period, skip as before (still propagating). This is a
     proxy for "the rule didn't stick," not a rate comparison; its worst case is a rejectable
     over-escalation, not a broken system.
     **Terminal case:** if the *most recent* accepted decision for this `key` carries
     `tier: "hook"` (see step 4 and review step 3), do **not** escalate again — treat it exactly
     like a normal accepted decision and skip. A correctly installed hook enforces
     deterministically and cannot "fail to stick" (ADR-0012), so there is no rung above it;
     without this check the same rule would re-escalate forever.
   - **reject-retry-narrower** and the legacy bare **rejected** impose a **normal, finite
     cooldown (default 30 days)**: a pattern matching this decision's `key` is suppressed until
     30 days after the decision's `date` (use the most recent rejection if the same key was
     rejected more than once). Once elapsed, the pattern is re-eligible.
   - **reject-not-wanted** imposes an **extended but still finite cooldown (default 90 days)**
     and **deprioritizes the whole cluster** — don't just wait it out, weight it lower than other
     candidates even once eligible again. Cooldown, never permanent suppression (ADR-0003's
     invariant still holds).
   - A pattern currently within any cooldown window is dropped in step 3, same as before.

   Match a candidate pattern against prior decisions **semantically**, using each decision's
   `key` as a strong hint — do not gate on title string-equality (titles are free text and drift
   between runs). **Legacy compat:** decision lines written before keys existed carry only a
   `title`; fall back to a semantic title match for those. Decision lines written before
   structured verdicts existed carry a bare `rejected`; treat that exactly like
   `reject-retry-narrower` (normal 30-day cooldown).
3. Read `~/.claude/sensei/events.json`. Cluster the events semantically into recurring
   patterns (same root cause, not just same event type) — friction events and `repeat` events
   both participate, but qualify differently:
   - A **friction** pattern (correction/denial/interrupt) qualifies if it appears in **≥2
     independent sessions** (different `session` values), OR is a **single high-severity
     event** — e.g. a destructive action the user had to interrupt or explicitly deny.
   - A **repeat** pattern qualifies simply by the miner having emitted a `repeat` event for it
     plus forming a coherent root-cause cluster (e.g. several worded variants of "use ddev for
     PHP commands"). **Do not re-apply the friction ≥2-sessions gate to repeats** — the miner's
     non-ubiquity test already requires recurrence across ≥N sessions before it ever emits a
     `repeat` event, so re-gating here would silently drop every habit candidate.

   Discard everything else, and drop (or deprioritize, per step 2) any pattern currently
   suppressed by a decision.
4. For each qualifying pattern, before writing anything, **read the current target file**
   (`~/.claude/CLAUDE.md`, the relevant skill's `SKILL.md`, or a per-project `CLAUDE.md`) so
   the proposal fits its existing structure and doesn't duplicate an existing rule. Then draft
   one of three proposal shapes:

   - **Prose proposal** (friction pattern) —
     - **Title** — short, specific.
     - **Key** — a stable identity for this proposal, independent of the title's wording:
       `<target-file>::<normalized-rule-slug>`, where the slug is a short lowercase, hyphenated
       signature of the rule's *intent* (e.g. `~/.claude/CLAUDE.md::ddev-prefix-artisan`). Two
       proposals that would edit the same rule must produce the same key even if their titles
       differ. This is what step 2 matches against and what review records in `decisions.jsonl`.
       Emit the key as its own line, exactly: `- **Key:** <target-file>::<slug>` — this literal
       format is a parse contract the session nudge depends on, and every proposal shape below
       emits it.
     - **Evidence** — 2–3 verbatim quotes from `user_text` / `assistant_context`, each tagged
       with its `project`.
     - **Supporting events** — the qualifying cluster's event count (the size already computed
       in step 3), as its own line: `- **Supporting events:** N`.
     - **Root cause** — one sentence.
     - **Target file** — exact path.
     - **Exact text** — the literal diff to add/change, ready to paste as-is.

   - **Habit-rule proposal** (repeat pattern) — same shape as a prose proposal (title, key,
     evidence, supporting events, root cause, target file, exact text), except evidence is drawn
     from the `repeat` event's re-supplied phrasing (tag each quote with its `project` from the
     event's `projects` list) and root cause reads as "you re-supply this every session" rather
     than "this caused friction." The exact text is still a normal prose rule for CLAUDE.md/SKILL.md.

   - **Hook proposal** (escalation, from step 2's exception) — a pattern already covered by an
     accepted rule but still qualifying past the grace period escalates instead of being skipped.
     Keep the **same `key`** as the original accepted decision (same rule, hardened — not a new
     rule), still emitted as its own `- **Key:**` line per the parse contract above; set
     **`target`** to the hook's install path (e.g. `~/.claude/settings.json` or a
     project-scoped `.claude/settings.json`). Review, when this proposal is accepted, must record
     `tier: "hook"` on the decision line (step 3) — that's what lets a future run's terminal check
     (step 2) recognize this key is already at the hook tier and stop escalating. Produce a
     **complete, ready artifact**, then stop — never write it, never offer to:
     - **Hook script** — the smallest script that enforces the rule (e.g. a `PreToolUse` matcher
       that blocks the specific command pattern).
     - **Exact `settings.json` snippet** — ready to paste into the hooks config, using the
       **narrowest matcher** that catches the pattern.
     - **Placement advice** — inferred from the event's `project` field (project-scoped vs.
       user-level).
     - **A test note** — how to verify the hook actually fires before trusting it.
     - Before drafting, **read the existing hooks config** and prefer **extending** an existing
       hook over adding a new entry; **surface the current hook count** in the proposal so the
       human can weigh hook-bloat. No hard ceiling — this is a heads-up, not a gate.
5. Write `~/.claude/sensei/proposals/YYYY-MM-DD.md` (today's date) with every qualifying
   proposal in the format above, separated by `---`. Label each proposal's kind (prose /
   habit-rule / hook) so review knows how to handle it. If zero patterns qualified, write a
   one-line file: `# YYYY-MM-DD — nothing today (N events scanned, 0 qualifying patterns)`.

## Mode: review

Interactive, run by the human in the morning.

1. Find the newest file under `~/.claude/sensei/proposals/`. Check `decisions.jsonl` for
   proposals from that file already decided (match by `key`) — if every proposal in the newest
   file is already decided, fall back to the next-newest file with undecided proposals. If none,
   say so and stop.
2. Walk proposals **one at a time**, in plain text (no dialog tool needed — this is a
   conversation):
   - Show the kind (prose / habit-rule / hook), title, evidence quotes, root cause, target file,
     and exact text (or, for a hook, the hook script + settings snippet + placement + test note).
   - Ask: accept / reject / edit?
   - On "edit", let the user redirect the wording, then re-confirm accept/reject.
3. Applying the verdict differs by proposal kind:
   - **Prose or habit-rule, accepted (or edited-then-accepted):** apply the exact text to its
     target file (read the file fresh right before editing — it may have changed since the
     nightly run).
   - **Hook, accepted:** **do not edit any file.** Present the artifact as final and tell the
     user to install it themselves (or hand it to a Claude session to install) — this is the one
     proposal kind review never applies, per the prose/code boundary (ADR-0002/ADR-0012:
     executable JSON config is categorically riskier than appending a prose sentence). When
     recording this decision (below), set **`tier: "hook"`** on the line and copy `target` from
     the proposal's hook install path verbatim — nightly step 2's terminal check reads both
     fields to recognize this key is already at the hook tier and stop re-escalating it.
   - **Any kind, rejected:** run a short **mini-grill** — ask "why?" before accepting a bare
     reject. Classify the answer into a **structured verdict**:
     - **`reject-retry-narrower`** — the idea is right but the framing/scope is off (e.g. "too
       aggressive as a hard rule"). Store the reason in `decisions.jsonl` as a **steering**
       reason (`reason_kind: "steering"`) — it informs a future, narrower re-proposal but doesn't
       touch config now.
     - **`reject-not-wanted`** — the user doesn't want this at all, or the *reason itself* is a
       better rule trying to get out (e.g. "we only use ddev on the Laravel projects, not the
       Python ones"). If the reason is **config-truth** (a fact that belongs in CLAUDE.md/SKILL.md
       right now, not just steering for sensei), draft and apply a **live prose proposal from the
       reason itself** in this same review conversation — review is allowed to apply prose, and
       this is the review-mode path for it, not a nightly one. Record `reason_kind: "config-truth"`.
       If the reason doesn't rise to a live edit, record it as `reason_kind: "steering"` instead.
   - For every proposal (accepted, rejected, or edited-then-accepted), append one line to
     `~/.claude/sensei/decisions.jsonl`:
     ```json
     {"date": "YYYY-MM-DD", "title": "...", "key": "...", "verdict": "accepted|reject-retry-narrower|reject-not-wanted", "target": "...", "reason": "...", "reason_kind": "steering|config-truth", "tier": "hook", "baseline": N}
     ```
     Omit `reason`/`reason_kind` on `accepted` lines — they only apply to the two reject
     verdicts. Omit `tier` entirely except on an accepted hook decision. On an **accepted** prose
     or habit-rule line, additionally copy the proposal's `Supporting events` value as
     `baseline: N`; rejected and hook lines carry no `baseline` (nothing reads it yet — it seeds a
     future track-record slice). Copy the `key` verbatim from the proposal — the cooldown, dedup,
     and escalation logic in nightly step 2 all depend on it being stable across runs.
4. When all proposals in the file are decided, tell the user how many were accepted/rejected,
   and call out any hook proposals that still need manual installation.
