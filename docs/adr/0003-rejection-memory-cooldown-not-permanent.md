---
status: accepted — not yet implemented (prototype does permanent suppression; see issue)
---

# Rejection memory is a cooldown, not permanent suppression

sensei records every proposal verdict in `decisions.jsonl` and uses it to avoid re-proposing. The intended policy is a **cooldown**: a rejected pattern is suppressed for a window, then allowed to resurface if the evidence recurs — not silenced forever. Permanent suppression risks burying a genuinely good idea that was dismissed once on a bad morning, and grows staler the longer sensei runs.

## Status

The prototype currently implements *permanent* suppression by proposal title, which was a shortcut, not the design. The cooldown model is the decision going forward. Tracked as a GitHub issue.

## Known weakness (to address alongside)

Dedup is keyed on the proposal **title**, which is LLM-generated free text — semantically identical proposals with different wording ("Use ddev for artisan" vs. "Prefix artisan with ddev") slip past the guard. A more stable identity than the raw title string is needed for either the permanent or cooldown model to work reliably.
