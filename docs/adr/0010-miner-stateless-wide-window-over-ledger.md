---
status: accepted — implemented (issues #8, #9)
---

# The miner stays stateless: a wide re-read window, not a persistent ledger

Slow-burn friction and cross-session repetition are surfaced by **widening the miner's
read window and recomputing every run** — never by persisting state across runs. The friction
pass widens from `--days 1` to ~14 days; the repeat signal (ADR-0011) reads ~30 days. The miner
still reads transcripts fresh each night and overwrites `events.json` (ADR-0001) — it holds no
memory of its own past runs.

## Why

A pattern that fires once on Tuesday and once the following Thursday never reaches the
≥2-independent-sessions bar inside a 1-day window, so the most valuable friction — the kind the
user has stopped consciously noticing — never surfaces. The obvious fix is a persistent
"observations ledger" that accumulates sub-threshold patterns across runs (the original shape of
issue #8). Rejected: it introduces cross-run state, and with it a **stable-identity problem** —
clustering is LLM-semantic and non-deterministic run to run, so there is no reliable key to match
tonight's events against last week's ledger entry — plus unbounded growth to police.

Widening the window gets the same result with **zero new state**: Tuesday's and Thursday's events
land in one window together, the LLM clusters them, the pattern qualifies. Recompute beats
reconcile. The only cost is local read I/O, which is cheap and zero-token.

## Bounds

The agent-facing output stays capped and deduped exactly as today (`MAX_TOTAL`, plus dedup against
`decisions.jsonl` and the target files). A wider *read* window does not enlarge the LLM's *context*
— it only widens what the deterministic stage considers. Volume to the model is bounded by
threshold, not by elapsed days.

## Considered and rejected

The persistent observations ledger (issue #8 as sketched). Reopen only if real usage shows valuable
friction recurring on a horizon longer than the read window is willing to cover — an edge we defer
under a "wide window until it shows problems" stance.
