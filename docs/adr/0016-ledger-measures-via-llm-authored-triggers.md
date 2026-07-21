---
status: accepted — implemented (issue #19)
---

# The effectiveness ledger measures via LLM-authored deterministic triggers

The miner gains a second job. Until now it only **detected** friction (ADR-0001);
now it also **measures** whether an accepted rule reduced that friction. Measurement
is a deterministic, zero-token **join**: for each accepted rule carrying a
machine-checkable **trigger** (tool name, keyword/substring, or path glob — no
arbitrary regex), the miner counts trigger matches — both friction events *and*
**opportunities** (trigger-context occurrences regardless of friction) — and writes
a per-rule track record that `/sensei status` renders as one honest line.

## Why this is *not* an exception to ADR-0004

ADR-0004 says the miner favors recall and never does precision, because it has **no
semantic judgment** — so precision belongs to the LLM downstream. The trigger honors
that exactly: **the LLM authors the trigger at proposal time**, and the miner merely
*executes* a precise instruction it was handed. The friction-detection lexicon is
untouched and stays greedy. The miner is not inventing precision (that would be the
ADR-0011 species of exception); it is running externally-authored precision as a new
*measurement* capability, distinct from *detection*. So this sits orthogonal to 0004,
not as a carve-out from it — 0011 remains the only place the miner thins on its own.

## What the miner computes — honest by construction

Two commitments make the headline claim (*"Working"*) true rather than hopeful:

- **Same instrument on both sides.** The pre-acceptance **baseline is re-derived with
  the same trigger**, not read from the LLM-clustered count that review stored at accept
  time (ADR: `baseline` seed, #16). Comparing an LLM cluster count against a
  deterministic trigger count would compare two rulers and systematically manufacture
  false *Working* (a tight trigger under-counts what a loose cluster captured). The
  stored `baseline` is demoted to a **fallback seed**, used only when the pre-accept
  transcripts have aged out of the read window — in which case the line is flagged as
  mixed-instrument (or downgraded to *Inconclusive*), never printed as a confident
  verdict.
- **Same width on both sides, bounded read.** Both sides are measured over a
  **fixed-width window** (reuse the ~14-day friction window): baseline = trigger matches
  in the 14 days *immediately before* accept; current = trigger matches in the *last* 14
  days. Two equal slices, one at the intervention point, one now. This keeps the read
  **bounded** — the miner reaches back far enough to cover the newest cohort's pre-accept
  slice, never "since the oldest rule ever accepted" — so ADR-0010 holds (recompute a
  bounded window, persist nothing). The consequence is deliberate: a rule accepted 60
  days ago is judged on its *recent* 14 days, not cumulatively; `days-since-accept` is
  reported as context, not as the measurement window.

The **opportunity denominator** is what separates *Working* (opportunities occurred,
friction gone) from *Inconclusive* (the situation never arose). It is accumulated inside
the **existing single transcript walk** — trigger matching is O(records × active
triggers), triggers number in the low dozens, and there is **no second filesystem pass**
(the miner stays the single greppable place that reads transcripts, ADR-0001).

## Small-N humility

sensei lives at small N — friction is rare (ADR-0004). A verdict is only as strong as its
denominator: when opportunities are few or the baseline is tiny, the verdict defaults
*toward Inconclusive*, never toward a confident *Working*/*Not working*. This extends
trust-by-construction to the threshold itself; the exact numeric cutoffs are a planning
detail, but they must implement this bias, not invert it.

## Grace period — one shared constant

A rule accepted more recently than the **grace period** yields no verdict yet
(*Not measurable yet*). This is the **same grace ADR-0012 already uses** for escalation
(~14 days) — it answers the identical question ("has the rule had a fair chance to
stick?"), so it is one shared constant, not a second independent knob.

## Relationships — realizes what ADR-0012 deferred

ADR-0012 chose a proxy trigger ("the rule *re-qualifies* past grace") over the honest
signal ("friction *rate* didn't drop") explicitly because the latter "needs a stored
pre-acceptance rate to compare against — new state," and promised to "ship
rate-comparison only if the proxy proves twitchy." **This ADR builds that
rate-comparison — with no new state** (stateless recompute, ADR-0010), dissolving the
objection that deferred it.

The two run as parallel lenses on the same question and are **deliberately not wired
together in v1**: 0012's fuzzy, LLM-semantic proxy is the *action* arm (it drafts a hook
proposal); this ledger's deterministic verdict is the *measurement* arm (it reports).
Letting a *Not working* verdict drive escalation is *acting on the measurement* and stays
behind the firewall (ADR-0002). Because they use different matchers and windows, they can
disagree on the same rule; `/sensei status`' framing should acknowledge this so a
*Working* line and a same-rule hook proposal in the morning review don't read as
self-contradiction. Convergence is recorded as future work, not built.

## Consequences

- The measurement is **forward-looking**: only rules accepted after trigger-authoring
  ships are ever measured, and only those the LLM could author a trigger for. The ledger
  starts sparse and fills in over weeks; rules without a trigger render *Not measurable
  yet*.
- The trigger is an **additive seam** on the decision record; its absence is the default
  and affects nothing — cooldown and dedup key on the stable `key` (ADR-0011).
- Approach B (LLM semantic attribution of events to rules each night) is rejected for v1:
  its value lands only on the untriggerable prose tail, where every method is noisy. It
  stays a deferred fast-follow, built only if that tail proves annoying in practice.
