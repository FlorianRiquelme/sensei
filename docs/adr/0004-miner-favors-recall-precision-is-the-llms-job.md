# The miner favors recall; precision is the LLM's job

The miner detects corrections with a deliberately crude regex **lexicon** (EN + DE: `no`, `don't`, `stop`, `actually`, `instead`, `never`, `always use`, `nein`, `falsch`, …) and intentionally over-captures. The rule: catch too much cheap junk in the deterministic stage and let the expensive LLM stage discard the noise semantically. The miner is tuned for **recall**; **precision is not its job.**

## Why record this

A future contributor looking at that regex will be tempted to "improve" its precision — negative lookaheads, excluding questions, etc. That is exactly backwards: tightening the miner permanently *loses* signal the LLM could have used, and the miner has no semantic judgment to filter safely anyway. Precision belongs downstream, where there's a model that can read meaning. Don't tighten the regex to reduce false positives; widen it if anything.

## Constraint

The lexicon is bilingual (English + German) because the author works in both languages. This is a personal-config constraint, invisible from the code's logic — not an accident to "clean up."
