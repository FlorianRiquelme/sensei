# sensei — the self-improving Claude Code setup

Nightly agent that mines your own transcripts for friction (corrections, denials, interrupts),
clusters recurring patterns, and proposes concrete diffs to `~/.claude/CLAUDE.md` / skills.
You review over coffee; your config learns from every session.

## Architecture (3 parts)

### 1. Miner — `sensei/mine.py` (this repo; deterministic, zero tokens)

Python 3 stdlib only, style-matched to `claude-retro.py` in the repo root.

Input: `~/.claude/projects/<project>/<session-uuid>.jsonl` — main sessions ONLY
(exclude anything under `*/subagents/` and any path whose session is a subagent sidechain;
also skip records with `"isSidechain": true` and `"isMeta": true`).

CLI: `python3 mine.py --days 1` (default 1; `--days 0` = all time; `--out PATH` default
`~/.claude/sensei/events.json`).

Extract these event types by scanning records in order (keep a rolling pointer to the last
assistant text block so every event can carry context):

- **interrupt** — user message whose text contains `[Request interrupted by user`.
- **denial** — a `tool_result` whose content contains `doesn't want to proceed` or
  `user rejected` (case-insensitive). Look up the matching `tool_use` (by tool_use_id in the
  prior assistant record) and capture tool name + first ~200 chars of its input.
- **correction** — user text message (not meta, not a `<command-name>` local-command record,
  not tool_result) matching a correction lexicon, case-insensitive, EN + DE:
  `\b(no+pe?|don'?t|stop|wrong|not (what|like) (i|that))\b`, `actually`, `instead`, `i said`,
  `i meant`, `why did you`, `you should have`, `never`, `always use`, `nein`, `nicht so`,
  `falsch`, `doch nicht`. Over-capture is fine — the analyzer filters semantically.
  Skip messages > 2000 chars (likely pasted content, not a correction).

Each event object:
```json
{"ts": "...", "project": "-Users-...-reponame", "session": "uuid", "type": "correction",
 "user_text": "<=1000 chars", "assistant_context": "<=500 chars of preceding assistant text",
 "tool": "Bash", "tool_input": "<=200 chars"}   // tool fields only for denials
```

Caps: max 15 events per session, max 400 total (newest first). Output JSON:
`{"generated_at": ..., "days": N, "sessions_scanned": N, "events": [...]}`.

Must run clean on the real corpus (~1600 jsonl files) in seconds. TEST IT on the real
`~/.claude/projects` and eyeball 10 sample events for sanity before finishing.

### 2. Skill — `~/.claude/skills/sensei/SKILL.md` (+ this repo keeps the canonical copy in `sensei/skill/SKILL.md`; install = copy)

One skill, two modes via args:

**`/sensei nightly`** (run headless by launchd):
1. Run the miner for `--days 1`.
2. Read `~/.claude/sensei/decisions.jsonl` (past accepted/rejected proposal titles) — never
   re-propose something previously rejected.
3. Analyze events: cluster semantically; a pattern qualifies only with ≥2 independent
   occurrences (different sessions) OR one clearly high-severity event (e.g. a destructive
   action the user had to interrupt).
4. For each qualifying pattern write a proposal: title, 2–3 evidence quotes (with project
   name), root cause in one sentence, target file (`~/.claude/CLAUDE.md` section, a skill's
   SKILL.md, or a per-project CLAUDE.md path), and the EXACT text to add/change, ready to
   paste. Read the current target file first so the proposal fits its existing structure and
   doesn't duplicate an existing rule.
5. Write report to `~/.claude/sensei/proposals/YYYY-MM-DD.md`. If zero qualifying patterns,
   write a one-line "nothing today" report (so the cron is observably alive).
6. Notify: `osascript -e 'display notification "N proposals" with title "sensei"'`.
7. HARD RULE: nightly mode NEVER edits CLAUDE.md, skills, or any config — proposals only.

**`/sensei review`** (interactive, morning):
1. Open the newest unreviewed proposals file.
2. Walk proposals one at a time in plain text: show evidence + exact diff, ask
   accept/reject/edit.
3. Apply accepted edits to their target files; append every verdict to
   `~/.claude/sensei/decisions.jsonl` as `{"date", "title", "verdict", "target"}`.

### 3. Scheduler — launchd

`~/Library/LaunchAgents/com.florian.sensei.plist`: daily 05:30, runs
`claude -p --model sonnet "/sensei nightly"` with cwd `$HOME`, stdout/stderr to
`~/.claude/sensei/logs/nightly.log`. Check `claude --help` for the right flags to allow the
needed tools headlessly (it needs Bash for the miner + Read + Write under ~/.claude/sensei);
prefer an `--allowedTools` allowlist over skipping permissions entirely. Also add an
`install.sh` in `sensei/` that copies the skill, creates `~/.claude/sensei/{proposals,logs}`,
and loads the plist (idempotent). Do NOT run install.sh yourself — the human decides.

## Guardrails
- Proposals only at night; edits only in interactive review.
- Rejected proposals stay rejected (decisions.jsonl is the memory).
- Miner reads transcripts, writes only under `~/.claude/sensei/`.
- Keep everything boring and stdlib — no deps, no venv.

## Definition of done
- `python3 sensei/mine.py --days 7` runs on the real corpus, emits plausible events
  (show 5 in your final report).
- Skill file + plist + install.sh exist and are internally consistent (paths, flags).
- Nothing installed/loaded — installation is a human step.
