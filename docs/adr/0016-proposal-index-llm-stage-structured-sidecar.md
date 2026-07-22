# The Proposal index — an LLM-stage structured artifact the Nudge parses, distinct from the miner's Digest

The nightly **LLM stage** writes a dated **Proposal index** (`~/.claude/sensei/proposals/YYYY-MM-DD.json`) every run, listing each proposal's `key` and `kind`. `nudge.py`'s `compute_pending` reads it via `load_json` instead of regexing the human-facing `.md`. This retires the pipeline's last prose seam: the `- **Key:**` "parse contract" that forced a fuzzy LLM writer and a rigid `KEY_RE` reader to agree on markdown.

## Why

- **It removes the only prose seam in an all-JSON pipeline.** Every other inter-stage contract is already structured JSON read through `load_json` — `events.json` (miner→LLM), `decisions.jsonl`, `digests/*.json`. Pending-proposal state was the lone exception, authored as LLM prose in `SKILL.md` and consumed by a regex ~200 lines deep in `nudge.py`. The index defines the format **once as a schema** — the writer fills slots, the reader does `load_json`. Format drift can no longer silently mis-count.
- **This extends the structured-inter-stage-seam pattern — NOT ADR-0014's deterministic-presence pattern.** This is the load-bearing distinction. The index is an **LLM-stage** artifact and inherits the same durability as the `.md` it sits beside — it vanishes exactly when the LLM stage breaks. It therefore carries **no** deterministic-presence guarantee. ADR-0014's property — that *only the deterministic miner can guarantee an artifact exists* — is why the **run-happened signal stays the miner's Digest**, unchanged. The index only refines pending-*proposal* counting; it never becomes a "did nightly run" signal.
- **A broken LLM run stays loud, correctly.** A night where the miner ran but the LLM stage failed now surfaces as **Digest-healthy + index-degraded** → the loud `proposals waiting since <oldest> - run /sensei review` line. The miner ran (Digest present, ADR-0015 failure line does not fire), but the proposal artifact is untrustworthy, so the user is pointed at review. Never under-reminds.

## Invariants this decision relies on

- **Union-glob of `.md` + `.json`.** `compute_pending` treats any date with a `.md` *or* `.json` as a run-day. A healthy day carries a `.json` (an empty `{"proposals": []}` on quiet nights); a `.md` with a missing or malformed `.json` is **degraded** — the "never under-remind on a partial write" property. The return shape is unchanged, so the `run()` consumer needs no edits.
- **`.md` is written before `.json`.** Review reads the `.md` (`SKILL.md`); the index only points into it. Writing the `.md` first makes the forbidden state — a `.json` whose `.md` doesn't exist — impossible by construction. A crash between the two writes leaves `.md`-without-`.json` → degraded/loud, and review can still show the proposals.
- **The `- **Key:**` line stays in the `.md`.** It lost its *nudge* consumer (the regex) but keeps its *review* consumer: review records verdicts in `decisions.jsonl` by key and skips already-decided proposals by key. Step 5 mirrors these keys into the index; the line's byte-exact rigidity is no longer load-bearing (its remaining reader is an LLM, not a regex).

## Accepted blind spot

A **valid** index that silently under-lists proposals is undetectable by the Nudge — the count is simply low. This is accepted: review reads the full `.md`, so nothing is lost except the nudge line's count, and the risk is now **bounded to valid JSON** (strictly better than today's unbounded prose miscount). No cheap guard exists that doesn't resurrect the seam: the only structural cross-check — index-count vs `.md`-block-count — is `KEY_RE`/`split("---")` reborn.

## Considered and rejected

- **Status quo: LLM writes prose, `KEY_RE` reads it.** Rejected — the seam this ADR exists to close.
- **Restructure proposals into a JSON-first format with a rendered `.md` view.** Rejected (scope firewall): the `.md` stays the canonical human/review artifact; the index is strictly an *additive* index beside it.
- **`.json`-only glob (ignore `.md`-only days).** Rejected: a partial LLM failure that writes the `.md` but dies before the `.json` would go silent on the pending line — an under-remind the union-glob exists to prevent.

## Consequence

- The Nudge stops reading the `.md` entirely. `KEY_RE`, `text.split("---")`, the one-line placeholder check, and the `len(keys) < len(blocks)` degraded heuristic are all deleted from `nudge.py`.
- Quiet nights write only the index (`{"proposals": []}`); the one-line placeholder `.md` is retired (the Digest, not a placeholder, is the proof-of-patrol).
- ADR-0002 untouched: the index is state under `~/.claude/sensei/`, not a config file — the "nightly proposes, never edits config" bright line is unaffected.
- ADR-0014 not extended literally (see the distinction above); a back-pointer is added there. ADR-0015 untouched: missing Digest is still the run-failure signal.
- No in-code migration: the format is pre-release with a single user, so legacy `.md`-only days are cleaned up by hand once, not handled by a compatibility branch.
