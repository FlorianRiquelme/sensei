---
title: Miner Reader/Detector Seam - Plan
type: refactor
date: 2026-07-22
topic: miner-reader-detector-seam
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
---

# Miner Reader/Detector Seam - Plan

## Goal Capsule

- **Objective:** Split the Miner internally into one transcript **reader** and pure **detectors**, so detection policy has its own interface seam and is testable without a subprocess or on-disk fixture.
- **Product authority:** The solo developer maintaining sensei (STRATEGY.md primary persona). This is sanctioned boy-scout cleanup inside the current milestone, not a new track.
- **Open blockers:** None. Investigated under issue #23; approach validated by a throwaway spike.

---

## Product Contract

### Summary

Introduce an internal reader/detector seam in `mine.py`. One reader owns the Claude Code transcript format and yields normalized records; pure detector functions turn those records into events. The Miner stays the single deterministic transcript reader and its external interface is unchanged — the depth is entirely internal.

### Problem Frame

`mine_session` interleaves two things that vary for unrelated reasons: knowledge of the external transcript format (JSONL parse, record-type dispatch, `tool_use`/`tool_result` correlation, the `[Request interrupted by user` sentinel, string-or-array content), and detection policy (correction lexicon, interrupt/denial/repeat rules, followup backfill). The format is fixed by Claude Code; the policy is ours and evolves.

Because the two are fused, the only test surface is `tests/test_mine.py` shelling out via `subprocess.run` over JSONL fixtures written to a temp projects dir — testing a one-line lexicon change means authoring a whole transcript on disk. Repeat detection is smeared across two places (`mine_session` collects candidate phrases; `main` runs the cross-session non-ubiquity test). And the function's return has grown to a five-tuple `(events, in_friction_window, in_repeat_window, repeat_phrases, meta)` — evidence the single function keeps accreting responsibilities (the `meta` dict arrived with the Recall Leak Counter, #18).

### Key Decisions

- **Adopt the seam.** Two things genuinely vary independently (fixed external format, evolving detection policy), so the seam is real rather than speculative abstraction. Depth is a property of the interface, not the implementation.
- **The reader owns format knowledge and format-level drop counts.** Parsing, block flattening, `tool_use` extraction, `isSidechain`/`isMeta` skipping, and the `parse_errors`/`unreadable` counts (#18) all belong to the reader — they are facts about reading the file, not about detecting friction.
- **Detectors are pure functions over normalized records.** No I/O; callable against an in-memory record list. The `capped` signal (a qualifying friction event dropped at `MAX_PER_SESSION`) is a detection statistic and rides with the friction detector, not the reader.
- **Repeat detection becomes local.** Two named functions replace the smear: per-session candidate collection, and the cross-session non-ubiquity selection (ADR-0011).
- **Normalized record shape.** Detectors need, per surviving line in order: the raw timestamp (for output) and a parsed timestamp (for window filtering); a role (assistant / user / other); role-normalized flattened text (see below); the message's `tool_use`s (id, name, input) and `tool_result`s (tool-use id, result text). `other` records carry only timestamps so window membership stays a property of the record stream. Exact representation (namedtuple / dataclass / dict) and the concrete function names are a **planning choice**; issue #23 proposes a `namedtuple` and the names `read_transcript` / `detect_friction` / `collect_repeat_candidates` / `select_repeats`, carried forward here as a planning *input*, not a requirement.
- **`text` is role-normalized by the reader, not uniformly flattened.** Today the miner extracts text differently by role, and both rules are byte-for-byte-critical: a `user` record's text is `block_text(content)` (all `text` blocks joined, or the raw string), while an `assistant` record's text is the *last non-empty* `text` block only, and an assistant turn carrying no `text` block (e.g. tool-use-only) must **not** overwrite the standing assistant context that the next correction/interrupt/denial attaches to. The reader emits role-appropriate text; the detector preserves the non-overwrite rule.

```mermaid
flowchart TB
  T[transcript .jsonl] --> RD[reader: owns format + parse/unreadable counts]
  RD --> REC[normalized records + read_meta]
  REC --> DF[detect friction pure]
  REC --> RC[collect repeat candidates pure, per-session]
  RC --> SR[select repeats pure, cross-session non-ubiquity]
  DF --> EV[events.json unchanged]
  SR --> EV
```

### Requirements

**Seam structure**

- R1. `mine.py` exposes one reader that owns all transcript-format knowledge and yields an **ordered stream of one normalized record per surviving transcript line**, plus the format-level drop counts (`parse_errors`, `unreadable`). A line that fails JSON parse is counted in `parse_errors` and **not** yielded; `isSidechain`/`isMeta` lines are dropped entirely; **every other line is yielded** — `assistant`, `user`, and any other type as `role="other"` — each carrying its parsed timestamp (`None` if missing/unparseable). Window membership, and therefore `sessions_scanned`, must be derivable from the record stream alone: today an in-window *assistant*-only session still counts as scanned, so the reader may not drop "uninteresting" line types. The reader also emits role-normalized text per record (user = joined `block_text`; assistant = last non-empty text block; other = empty).
- R2. Friction detection (denial, interrupt, correction, followup backfill) is a pure function over normalized records; it also reports whether the session was capped at `MAX_PER_SESSION`. It reproduces today's `assistant_context` exactly — including that an assistant turn with **no** text block does not overwrite the standing assistant context.
- R3. Repeat detection is split into a pure per-session candidate collector and a pure cross-session non-ubiquity selector.
- R4. The five-tuple return of `mine_session` is dissolved: window membership is derived from the record stream, and the per-stage statistics travel with the stage that produces them.

**Behavior preservation**

- R5. The external interface is unchanged: `mine.py --days N --out PATH` → `events.json`, plus the `--projects-dir` flag and the digest artifact.
- R6. For identical input, the **fully serialized** `events.json` and daily digest are identical before and after the refactor — a whole-object comparison of every event and every field in order, not a spot-check of selected keys — once the run-varying timestamps are masked. The masked fields are exactly: top-level `generated_at`, each `repeat` event's `ts` (set to `now()` at emit time), and the digest's `generated_at` and local `date`. Verification is a **one-time migration gate**: run the refactored miner and the pre-refactor `mine.py` (the branch-point commit) over `tests/fixtures/projects`, mask those fields, and assert equality. No golden snapshot is committed — the existing fixture suite (R9) and the new in-memory detector tests (R8) are the permanent guards; the byte-equality claim is a migration claim, true against one prior commit, not a forever test that would fight every future intentional detection change.
- R7. The Miner remains deterministic, zero-token, stdlib-only, and the single component that reads raw transcripts.

**Testability**

- R8. At least one detector is unit-tested against an in-memory list of normalized records — no subprocess, no temp dir, no on-disk fixture.
- R9. The existing subprocess/fixture tests continue to pass unchanged, serving as the integration guard over the seam.

**Consistency**

- R10. The change preserves ADR-0001 (deterministic miner is the only transcript reader), ADR-0004 (favors recall; the repeat structural-thinning exception in ADR-0011 stays scoped to repeats), and ADR-0008 (stdlib-only).

### Acceptance Examples

- AE1. **Covers R6, R9.** Running the refactored miner and the branch-point `mine.py` over `tests/fixtures/projects` yields serialized outputs (both `events.json` and the digest) that are identical after masking `generated_at`, each `repeat.ts`, and the digest `date` — a whole-object diff, not a selected-key check. The full existing test suite (50 tests) passes unchanged.
- AE2. **Covers R8.** A test constructs a short list of records (e.g. an assistant message, a user interrupt, a plain follow-up) and calls the friction detector directly, asserting the emitted event without touching the filesystem.
- AE3. **Covers R1.** A session whose only in-window record is an `assistant` message (no friction, no repeat candidate) still counts toward `sessions_scanned` — proving the reader yields non-user lines and window membership is derived from the full stream, not from emitted events.

### Scope Boundaries

- Detection policy does not change: no new event types, no lexicon edits, no recall/precision tuning. This is a structural move only.
- Behavior is preserved to the byte, **including behaviors that may read as bugs** — e.g. a lexicon-bearing interrupt follow-up ("actually use the helper") emitting **both** an `interrupt` (with that text backfilled as `followup_text`) and a `correction`. Any such fix is a separate, out-of-scope change with its own detection-policy decision; the refactor changes nothing here.
- The external CLI, `events.json` schema, and digest output do not change.
- No cross-run state, ledger, or persistence is introduced (ADR-0010 stands).

### Dependencies / Assumptions

- Stdlib-only; no new dependencies (ADR-0008).
- Transcripts are appended in chronological order. The seam relies on this only at one micro-edge (interrupt-followup backfill across the repeat-but-not-friction window), which is unreachable under chronological ordering because the repeat window contains the friction window; output is unaffected.

### Outstanding Questions

**Resolved (grill-with-docs)**

- Record the seam in a short ADR? **Yes — ADR-0016**, "the reader/detector seam is the testing interface for detection policy." Framed as a refinement of ADR-0001's interior; changes no invariant, so it documents structure rather than deciding new behavior.

**Deferred to Planning**

- Exact representation of the normalized record (namedtuple vs dataclass vs dict) and precise function names/signatures. Issue #23's `namedtuple` + names are a planning input, not a requirement.

### Sources / Research

- Investigation and validated spike: issue #23 (recommendation comment records the seam, the dissolved tuple, and byte-for-byte confirmation). The spike code itself was discarded; implementation proceeds fresh here.
- Current implementation: `mine.py` (`mine_session`, `main`), tests in `tests/test_mine.py`.
- Governing ADRs: `docs/adr/0001-deterministic-miner-llm-only-sees-events.md`, `docs/adr/0004-miner-favors-recall-precision-is-the-llms-job.md`, `docs/adr/0008-stdlib-only-no-dependencies.md`, `docs/adr/0010-miner-stateless-wide-window-over-ledger.md`, `docs/adr/0011-repeat-events-structural-thinning.md`.
- New decision from this stage: `docs/adr/0016-reader-detector-seam-is-the-testing-interface.md`.
