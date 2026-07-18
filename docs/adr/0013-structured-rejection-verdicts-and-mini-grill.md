---
status: accepted — implemented (issue #12)
---

# Rejection carries a structured verdict and a probed reason — extends ADR-0003

Rejection stops being a bare 30-day timer with no information content. On reject, review runs a
short **mini-grill** to capture the real reason, records a **structured verdict**, and routes the
reason to where it can actually do work.

## Decision

- **Mini-grill on reject.** Review is already an LLM-driven conversation, so probing "why?" costs
  almost nothing — and it makes *"I don't want this at all"* the **expensive** path (you must justify
  it), not a lazy menu pick that teaches sensei nothing.
- **Structured verdict drives cooldown:**
  - `reject-retry-narrower` → normal cooldown; steer a narrower re-proposal next time.
  - `reject-not-wanted` → **extended (but still finite) cooldown** + deprioritize the whole cluster.
- **Dual exit for the reason.** The mini-grill classifies its outcome:
  - a *steering* reason ("too aggressive for a hard rule") → stored in `decisions.jsonl` for future
    sensei runs;
  - a *config-truth* reason ("we only use ddev on the Laravel projects, not the Python ones") →
    **promoted into a live CLAUDE.md / skill proposal now.** `decisions.jsonl` is read only by
    sensei; a genuinely useful rejection reason is often a *better rule trying to get out*, and the
    only way it reaches normal coding sessions is as a real config edit.

## Consistency with ADR-0003

The extended cooldown is still **finite** — cooldown, not permanent suppression — so 0003's core
invariant holds. This amends only the flat "30 days for every rejection" into a two-tier finite
cooldown keyed on the structured verdict. The stable proposal `key` and semantic matching from 0003
are unchanged.

## Relationship

Implements issue #12. Pairs with ADR-0012, whose loop-closing trigger reads the same accepted /
rejected decision records.
