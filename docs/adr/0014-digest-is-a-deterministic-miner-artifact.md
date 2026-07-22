# The Miner writes the Digest — a human-facing artifact, still deterministic

ADR-0001 confined the Miner to extracting friction into `events.json`, with the LLM stage as the only downstream consumer. We extend it: every night, before the LLM stage runs, the Miner also writes a dated **Digest** — sessions scanned and event counts by type and by project — as a per-day JSON file (`~/.claude/sensei/digests/YYYY-MM-DD.json`). The Digest's *presence* is the proof that the nightly patrol ran; its *absence* is the failure signal the Nudge reads.

## Why

- **Only the deterministic layer can guarantee the artifact exists.** A Digest written by the LLM stage would vanish exactly when the launchd chain breaks (`&&` with no failure branch) — which is precisely the failure we most need to detect. Putting it in the Miner means a broken or skipped LLM stage still leaves a Digest, and a *missing* Digest unambiguously means the run failed or never started.
- **It costs nothing new.** The Digest carries only what the Miner already computes from its single scan — no extra transcript reading. Still zero-token, still deterministic, still the single greppable place that touches raw transcripts. The ADR-0001 property that actually matters — the LLM never sees raw transcripts — is untouched.
- **Durable by construction.** Per-day files mean later runs never overwrite earlier nights, so "was sensei there Tuesday?" stays answerable.

## Considered and rejected

- **LLM stage writes the Digest.** Rejected: it disappears on the one night you need it. The whole point is a signal that survives LLM-stage failure.

## Consequence

- **The Digest never carries proposals.** The Miner runs before the LLM stage and structurally cannot know them. Pending-proposal state is read *live* by the Nudge from `proposals/` + `decisions.jsonl` — which is also strictly more accurate, since proposals may have been decided since the run.
- `events.json` remains the LLM's only input; the Digest is a separate, human-inspectable output, not part of the events contract.
- This refines ADR-0001's "the Miner does extraction, nothing else": the Miner now emits one additional artifact for humans, bounded by the same determinism and zero-token rules.
- **Not to be confused with the Proposal index (ADR-0017).** The LLM stage later writes a structured `proposals/YYYY-MM-DD.json` that the Nudge parses for pending-proposal counts. That index is an *LLM-stage* artifact with no deterministic-presence guarantee — it extends the structured-inter-stage-seam pattern, not this ADR's deterministic-presence pattern. The run-happened signal stays the Digest defined here.
