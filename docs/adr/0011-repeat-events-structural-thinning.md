---
status: proposed — from ideas triage (issue #9)
---

# `repeat` events use structural thinning — a bounded exception to ADR-0004

The miner gains a fourth event type, `repeat`: an imperative or config directive the user
re-supplies across sessions **with no friction at all** ("use ddev", "branch off develop", "run
the tests first"). Unlike the three friction types, the miner **thins repeats structurally before
emitting them**: a small glue blocklist (~20 acknowledgment tokens — yes/ok/next/continue/…), a
length floor, and a **non-ubiquity** test (a phrase recurs across ≥N sessions but is *not* present
in nearly all of them — inverse-frequency, TF-IDF-ish, stdlib-trivial). No directive allowlist,
ever. Output is hard-capped top-K and deduped like every other signal.

## Why this is an exception to ADR-0004

ADR-0004 says the miner favors recall and never does precision, because friction is **rare** —
a greedy regex over rare events still leaves a manageable pile. Repeats are the opposite:
**ubiquitous.** Greedy capture of "any recurring message" floods `events.json` with conversational
glue and crowds real friction out of caps sized for rare events. So for repeats the miner *must*
thin — but **structurally, never lexically.**

A directive allowlist (a catalogue of imperative verbs) would crater recall — it only catches
directives phrased the way we guessed — and re-import the exact bilingual-lexicon maintenance
burden ADR-0004 warns about, in a second place. Distribution-based thinning is language-agnostic
and keeps recall wide: *any* substantive phrase in *any* language can qualify. The discriminator
between "use ddev" and "yes/continue" isn't vocabulary, it's **distribution** — glue is trivial and
appears everywhere; a directive is concentrated. Precision ("is this actually a rule?") stays the
LLM's job.

## Why record this

This is the one place the deterministic stage does more than crude over-capture, and a future
contributor will read it as a violation of ADR-0004. It isn't: 0004's "over-capture is free" logic
holds only while the subject is rare. Change the subject to something common and the same greed
becomes fatal. The exception is scoped precisely to `repeat`; friction detection stays greedy.

Turns sensei from "learn from my pain" into "learn from my habits" — the larger surface.
