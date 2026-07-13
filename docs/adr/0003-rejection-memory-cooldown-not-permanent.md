---
status: accepted — implemented (issue #1)
---

# Rejection memory is a cooldown, not permanent suppression

sensei records every proposal verdict in `decisions.jsonl` and uses it to avoid re-proposing. The intended policy is a **cooldown**: a rejected pattern is suppressed for a window, then allowed to resurface if the evidence recurs — not silenced forever. Permanent suppression risks burying a genuinely good idea that was dismissed once on a bad morning, and grows staler the longer sensei runs.

## Decision

- **Cooldown, not permanent.** A rejected proposal is suppressed for **30 days** from its most recent rejection, then becomes re-eligible — and only actually resurfaces if the pattern recurs in fresh events. Accepted decisions never expire (the rule is already in the target file). The prototype's permanent, title-keyed suppression was a shortcut, now replaced.
- **Stable dedup key.** Each proposal carries a `key` — `<target-file>::<normalized-rule-slug>` — independent of the LLM-generated title, recorded alongside every verdict in `decisions.jsonl`. Matching a candidate against past decisions is done **semantically**, with the key as a strong hint rather than a string-equality gate, so re-worded duplicates of the same rule ("Use ddev for artisan" vs. "Prefix artisan with ddev") collapse to one identity. Legacy decision lines predate the key and carry only a title; those fall back to a semantic title match.

Both live in the nightly reasoning of the `sensei` skill, not in `mine.py` — the miner stays deterministic and only emits events (see ADR-0001).
