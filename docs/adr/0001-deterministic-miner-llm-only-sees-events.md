# Deterministic miner; the LLM only ever sees pre-extracted events

sensei splits transcript processing into a deterministic, zero-token Python **miner** (`mine.py`) that does all raw-transcript scanning and extraction, and an LLM stage that only ever reads the miner's `events.json` — never the transcripts themselves. We chose this primarily for **determinism and auditability**: the miner is plain stdlib Python, reproducible, testable against the real corpus, and is the single, greppable place that touches raw session data. Zero token cost is a welcome secondary benefit (sensei runs on a personal subscription, so cost was not the deciding factor).

## Consequences

- The correction **lexicon** (a regex, EN+DE) bounds recall: friction phrased outside the lexicon is invisible to the LLM. We deliberately accept this and compensate by over-capturing and letting the LLM filter semantically downstream (see the correction-lexicon ADR).
- Every downstream component depends on the `events.json` contract. Changing the event schema is a breaking change across the miner, skill, and any consumer.
- A future temptation — "just let Claude read the transcripts directly" or "add a small LLM pre-filter inside the miner" — is rejected by this decision: the miner stays deterministic.
