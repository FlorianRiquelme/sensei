# The in-session Nudge is sensei's sole announcement surface

sensei previously announced each nightly run with an `osascript` notification fired at 05:30. The user never saw it — it fires while they sleep and evaporates. We replace it with the **Nudge**: a once-per-day line shown at the start of the first Claude Code session of each calendar day, delivered by a `SessionStart` hook registered in the user's `~/.claude/settings.json`. The `osascript` notification is removed outright.

## Why

- **Announce when the user is present.** The original notification's flaw was timing, not medium: fired at 05:30, nobody is looking. Tying the announcement to session-start shows it exactly when the user opens Claude Code to work.
- **Top-level `systemMessage`, not stdout, not nested.** A `SessionStart` hook's plain stdout is *context-only* — not rendered in the user's terminal. The user-visible channel is a **top-level** `systemMessage` field in the hook's JSON stdout: `{"systemMessage": "..."}`. All three states were tested empirically (2026-07-19, Claude Code v2.1.215): plain stdout is invisible; `systemMessage` **nested inside `hookSpecificOutput` is also invisible**; only the **top-level** form renders. (`additionalContext` is the only field that belongs in `hookSpecificOutput`.) `nudge.py` builds this JSON with stdlib `json` (no `jq`, ADR-0008 intact). **This is load-bearing and fails silently: a bare `echo`, or nesting `systemMessage` under `hookSpecificOutput`, stops the Nudge reaching the user with no error — we hit exactly this during design.**
- **A day with no session says nothing — accepted.** Review happens in-session anyway; there is no value in announcing a patrol to a user who isn't there.

## Considered and rejected

- **`osascript` fired at session-start** (instead of at 05:30). Rejected: still a banner that auto-dismisses, and `systemMessage` gives a persistent visible line the user prefers.
- **A sensei statusline.** Rejected: it collides with the user's existing statusline tool (only one statusline), and its every-prompt semantics don't fit a once-per-day line.
- **stdout → context, and let Claude relay it.** Rejected: relies on Claude's discretion — exactly the "ask a separate Claude session to find out" cost this feature exists to remove.

## Consequence

- **sensei now writes into `~/.claude/settings.json`** — the first time it touches config outside its own directory. `install.sh` adds the hook idempotently (upsert by marker via a repo-resident, unit-tested `settings_hook.py`); a new `uninstall.sh` removes it. State under `~/.claude/sensei/` is preserved on uninstall.
- **Self-trigger guard.** The nightly's own `echo "/sensei nightly" | claude -p` fires `SessionStart` too. The launchd command sets `SENSEI_NIGHTLY=1` on the `claude` invocation (not as a prefix on `mine.py`, which would scope it away from `claude`); `nudge.py` exits immediately when it is set, so the nightly run never consumes the user's real first-session-of-day.
- **Missing Digest is the failure signal** (with ADR-0014). Absence of the expected Digest — `today` if `now ≥ 05:30` local, else `yesterday` — produces the loud "nightly did not run" line.
- **Once per day when healthy; the failure line repeats.** A success Nudge consumes the day (tracked in a state file); the failure line is exempt and reprints every session until the Digest appears or the day turns over — a broken patrol stays loud, and a transient wake-race warning self-heals.
