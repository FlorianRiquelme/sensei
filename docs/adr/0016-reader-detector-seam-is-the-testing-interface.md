# The reader/detector seam is the testing interface for detection policy

Inside the miner, transcript-format knowledge and detection policy are separated by an
internal seam. A single **reader** owns all Claude Code transcript-format knowledge — JSONL
parsing, `isSidechain`/`isMeta` filtering, string-or-block content flattening,
`tool_use`/`tool_result` correlation, timestamp parsing, and the format-level
`parse_errors`/`unreadable` drop counts (#18) — and yields an ordered stream of normalized
records. The **detectors** — friction detection, per-session repeat-candidate collection, and
the cross-session non-ubiquity selection (ADR-0011) — are pure functions over those records.
The detector functions, not a subprocess over on-disk JSONL, are the sanctioned unit-test
surface for detection policy.

This **refines ADR-0001**, it does not compete with it. ADR-0001 fixes the *outer* boundary:
the miner is the single deterministic, zero-token component that reads raw transcripts; the LLM
only ever sees `events.json`. This ADR fixes the miner's *interior*. It changes **no invariant**
— 0001, 0004 (recall over precision), 0008 (stdlib-only), 0010 (stateless wide window), and 0011
(repeat structural thinning) all still hold — and **no external behavior**: `mine.py --days N
--out PATH → events.json` and the daily digest are unchanged, byte-for-byte, for identical input.

## Why record it

The transcript format is fixed externally by Claude Code; detection policy is ours and evolves.
When the two are fused — as the original `mine_session` fused them — the only way to test a
one-line lexicon change is to author a whole transcript on disk and shell out, and the fused
function invites accretion: its return grew to a five-tuple when the Recall Leak Counter (#18)
added a `meta` dict, because "just add one field" is the path of least resistance in a function
that already does everything. The seam exists precisely so a future contributor does not re-fuse
the two. The rule of thumb it encodes: a new piece of *format* knowledge belongs to the reader; a
new piece of *detection policy* belongs to a detector and gets an in-memory test.

## Consequences

- The cost is a normalized record type and one internal indirection, paid once.
- Detection-policy changes get fast, subprocess-free, in-memory tests; the existing
  subprocess/fixture suite stays as the integration guard *over* the seam.
- A change that genuinely must touch both the reader and a detector is a signal that the
  transcript format itself changed — worth noticing rather than absorbing silently.
