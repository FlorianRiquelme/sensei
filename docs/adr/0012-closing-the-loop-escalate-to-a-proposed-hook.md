---
status: accepted — implemented (issues #10, #11)
---

# Closing the loop: escalate a non-sticking rule to a *proposed* hook

sensei stops treating "accepted" as done forever. When a rule it installed keeps failing, it
escalates — but the escalation target is a **hook**, and sensei only ever **proposes** it.

## Trigger — a proxy, not rate-tracking

A pattern escalates when it **already qualifies** (≥2 independent sessions in the wide window),
**semantically matches an accepted decision** in `decisions.jsonl`, and its events are **dated past
a ~14-day grace period** after that acceptance. Mechanically this is a small flip of nightly's
step 2: "an accepted rule already covers this → skip" becomes "accepted **but still qualifying
after grace** → escalate."

The honest signal would be "friction *rate* didn't drop," but that needs a stored pre-acceptance
rate to compare against — new state. The proxy — *does the pattern independently re-clear the
qualifying bar weeks later* — reuses every existing threshold and the acceptance date sensei
already has, for zero new state. Its worst case is a **rejectable over-escalation** (a mostly-working
rule that occasionally re-qualifies → you decline → cooldown), not a broken system. Ship
rate-comparison only if the proxy proves twitchy. Grace period ~14 days, tunable, so a rule isn't
judged before it has propagated.

## Target — hooks only; permissions are out of scope

Broadening beyond prose (issue #11) narrows, on inspection, to exactly one target. Permission
rules (`deny`/`allow` in `settings.json`) are worthless for this project's workflow: auto-accept
and `--dangerously-skip-permissions` mean the permission prompt rarely or never fires, so there is
nothing to deny and no approvals to harvest. A **hook is the only enforcement that survives bypass
mode** — a PreToolUse hook executes regardless of permission mode. Prose is advisory; permissions
are skipped; the hook is the one lever that actually holds. So the enforcement ladder is
**prose → hook**, and it terminates there: a correctly-installed hook is deterministic and cannot
"fail to stick," so there is no rung above it. Reject → cooldown (ADR-0003).

## Boundary — review applies prose, but only *proposes* code

This refines ADR-0002's bright line. A hook is executable code that runs forever on every matching
call, is project-scoped, and lives in structured JSON where a malformed edit breaks *all* config
loading — categorically unlike appending a prose sentence. So the hook escalation produces a
complete, ready artifact — the **hook script + the exact `settings.json` snippet + placement advice
inferred from the event `project` field + a note on what to test** — and **stops**. The human
installs it (or, being in a Claude session already, tells that session to). sensei never writes it
and never *offers* to.

## Governance — soft, against hook bloat

Hooks add per-call latency, so proliferation matters. But the funnel (only twice-proven-stubborn
rules reach a hook) keeps volume in the low single digits. On top of that: propose the **narrowest
matcher** that catches the pattern, **read existing hooks and prefer extending** one over adding a
new entry, and **surface the current count**. No hard ceiling — a numeric cap is arbitrary and
would block a legitimately valuable hook.

## Relationships

Collapses issue #11 into this mechanism; extends ADR-0002 (applies prose, proposes code); consumes
accepted-decision dates from ADR-0003 / `decisions.jsonl`; fed by events from ADR-0010/0011.
