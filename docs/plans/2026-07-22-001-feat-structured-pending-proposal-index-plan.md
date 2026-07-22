---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
execution: code
---

<!-- Product Contract preservation: unchanged. ce-plan enriched this requirements-only
     artifact in place to implementation-ready (Planning Contract + Implementation Units +
     Verification + Definition of Done appended below); no R-IDs or product scope altered. -->

# Structured Pending-Proposal Index - Plan

## Goal Capsule

- **Objective:** Retire the Nudge's markdown regex. The Nightly LLM stage writes a small
  structured sidecar (`proposals/YYYY-MM-DD.json`) listing the proposal keys/kinds it just
  emitted; `nudge.py`'s `compute_pending` reads it via `load_json` instead of reverse-engineering
  pending state from the human-facing `.md`. This closes the one prose seam in an otherwise
  all-JSON pipeline.
- **Product authority:** The maintainer. This brainstorm frames *what* to build; the binding
  adopt/defer/reject decision and any ADR are the maintainer's, via `/grill-with-docs`.
- **Recommendation carried in:** **ADOPT.**
- **Open blockers:** None. Issue #22 is unblocked and labeled `ready-for-agent` (milestone
  v-next).

## Context

Source: GitHub issue #22 (milestone v-next: "Prove it works"). This is **architecture-hardening**,
not part of the milestone's core track sentence — sanctioned under the CLAUDE.md "feature-complete
is a hardening window" rule, which is why it lives in v-next.

Today `compute_pending` (nudge.py:56–92) re-derives pending state from prose the Nightly LLM
authored: `KEY_RE` scrapes `- **Key:**` lines, `text.split("---")` counts blocks, the one-line
placeholder file is detected structurally, and a "degraded" day is inferred when
`len(keys) < len(blocks)`. SKILL.md:119–120 pins the `- **Key:**` line as "a parse contract the
session nudge depends on." A fuzzy LLM writer and a rigid regex reader are forced to agree on
markdown; format drift silently mis-counts, mitigated only by "err toward reporting pending."

Every *other* inter-stage seam is already structured JSON read via `load_json`: `events.json`
(the miner→LLM contract), `decisions.jsonl` (nudge.py:157), `digests/*.json` (nudge.py:138).
This is the lone exception.

## Product Contract

### Recommendation and rationale (codebase-design vocabulary)

**ADOPT.** The Proposal-key format has **poor locality**: authored as LLM prose in SKILL.md,
consumed by a regex ~200 lines deep in nudge.py, bridged by a documented "parse contract" that
spans a fuzzy writer and a rigid reader. A sidecar defines the format **once, as a schema** — the
writer fills slots, the reader does `load_json`. It removes the **leaking seam** (the only prose
seam in an all-JSON pipeline) and replaces *"LLM writes prose + regex reads it"* with *"LLM fills
a rigid schema."*

**Correction to the issue's framing** (must reach `/grill-with-docs`): this does **not** literally
extend ADR-0014. ADR-0014's property is that *only the deterministic **miner** can guarantee the
artifact exists* — which is why the **Digest**, not proposals, is the "did nightly run" signal
(ADR-0014 consequence: the miner runs before the LLM stage and structurally cannot know
proposals). The sidecar is an **LLM-stage** artifact and inherits the same durability as the
`.md` it sits beside — no worse than today, but not the deterministic-presence guarantee. So:

- The **run-happened signal stays the miner's Digest** (ADR-0015 unchanged).
- The sidecar **only** refines pending-*proposal* counting.
- This extends the *structured-inter-stage-seam* pattern, **not** the *deterministic-presence*
  pattern.

### Scope — in

1. **New nightly artifact** `~/.claude/sensei/proposals/YYYY-MM-DD.json` (the **Proposal index**),
   written by the LLM stage, **every run**, including an empty `proposals` array on
   zero-qualifying nights.
2. **Collapsed `compute_pending`** that reads only the index. `KEY_RE`, `text.split("---")`,
   the one-line placeholder check, and the `len(keys) < len(blocks)` degraded heuristic are all
   **deleted**.
3. **SKILL nightly step 5** gains the index-write instruction, with two invariants:
   - **`.md` first, then `.json`.** The `.md` is written before the index, as the final action of
     the proposal step. Review reads the `.md`; the index only points into it, so the forbidden
     state (`.json` present, `.md` absent) must be impossible by construction. A crash between the
     two leaves `.md`-without-`.json` → degraded/loud, and review can still show the proposals.
   - **Zero-qualifying nights write only the index** (`{"proposals": []}`). The one-line
     placeholder `.md` is **retired** — the Digest, not a placeholder, is the proof-of-patrol, and
     under the union-glob a placeholder `.md` whose index write failed would false-alarm as
     degraded on a night with zero proposals.
   - The `- **Key:**` line **stays**, re-pointed: it lost its *nudge* consumer (the regex) but
     keeps its *review* consumer (review records verdicts by key). Its byte-exact rigidity is no
     longer load-bearing; step 5 mirrors these keys into the index.

### Scope — out (firewall)

- **No** restructuring proposals into a JSON-first format with a rendered `.md` view. The `.md`
  stays the canonical human/review artifact (review reads it, SKILL.md:164); the index is
  strictly an **additive** index.
- **No** in-code migration or backfill. The format is pre-release with a single user, so legacy
  `.md`-only days are cleaned up **by hand, once** (see Migration), not by a compatibility branch.

### Index schema (spike)

```json
{
  "proposals": [
    {"key": "~/.claude/CLAUDE.md::ddev-prefix-artisan", "kind": "prose"},
    {"key": "~/.claude/settings.json::block-bare-artisan", "kind": "hook"}
  ]
}
```

- `kind` ∈ `prose` | `habit-rule` | `hook` (mirrors SKILL.md's proposal-kind labels).
- **`date` dropped** (was in the earlier draft): it is 100% redundant with the filename —
  `compute_pending` derives the date from the basename, never from a field — and duplicating it is
  a pure drift hazard. Top-level shape is just `{"proposals": [...]}`.
- **`kind` kept** despite the Nudge only **counting** (it consumes `key` alone today). Unlike
  `date`, `kind` is a first-class attribute, not a derived duplicate; the index is rewritten every
  night and ages out in ~30 days, so it carries *zero* migration burden and can start being read
  (e.g. "1 **hook** proposal waiting — you install those yourself") with no backfill. Cheap,
  self-describing, defuses the usual YAGNI objection.

### Collapsed `compute_pending` (spike)

```python
def compute_pending(proposals_dir, decided_keys):
    # A run-day = any date with a .md OR .json in proposals/. The sidecar is
    # authoritative; a missing/malformed sidecar (legacy .md-only day, OR a broken
    # run) is degraded. An empty "proposals": [] => healthy, nothing pending.
    stems = sorted({os.path.splitext(os.path.basename(p))[0]
                    for p in glob.glob(os.path.join(proposals_dir, "*.md"))
                           + glob.glob(os.path.join(proposals_dir, "*.json"))})
    pending, degraded = [], []
    for date_str in stems:
        idx = load_json(os.path.join(proposals_dir, f"{date_str}.json"))
        if not isinstance(idx, dict) or not isinstance(idx.get("proposals"), list):
            degraded.append(date_str)
            continue
        for p in idx["proposals"]:
            key = p.get("key") if isinstance(p, dict) else None
            if key and key not in decided_keys:
                pending.append(date_str)
    if degraded:
        return {"degraded": True, "oldest": min(degraded + pending)}
    if pending:
        return {"degraded": False, "count": len(pending), "oldest": min(pending)}
    return None
```

The **union-glob of `.md` + `.json`** is load-bearing, and its justification survived the grill
once legacy migration was stripped away: with legacy days cleaned up by hand, the *only* remaining
`.md`-without-healthy-`.json` case going forward is a **partial LLM failure** — the night the LLM
writes the `.md` with real proposals but dies before the index. The union-glob catches exactly that
(→ degraded/loud), honoring "never under-remind," at zero cost. A healthy new day with an empty
array contributes nothing. The return shape is unchanged, so `run()`'s consumer (nudge.py:160–166)
needs no edits.

### "Degraded" mapping (AC criterion 3)

In the structured world, **degraded** = the index is **missing** for a day whose `.md` exists (a
partial LLM failure — `.md` written, index not, caught by the union-glob + `.md`-first ordering)
**or malformed** (not valid JSON / not `{"proposals": [...]}`). The old `len(keys) < len(blocks)`
partial-write case folds into "malformed or missing." (Pre-existing legacy `.md`-only days are not
a concern — they are cleaned up by hand once, pre-release; see Migration.)

- **Not detectable:** a *valid* sidecar that silently under-lists proposals. Accepted — review
  reads the full `.md` (SKILL.md:164), so nothing is lost except the nudge line's count. Same risk
  class as today's LLM miscount, now **bounded to valid JSON** (strictly better).
- **Chosen behavior for no-trustworthy-index:** loud, count-unknown —
  `"proposals waiting since <oldest> - run /sensei review"`. Never under-reminds.

### ADR impact

- **ADR-0002** (nightly proposes, never edits config): **untouched.** The sidecar is state under
  `~/.claude/sensei/`, not a config file. The issue's "not config, bright line untouched" holds.
- **ADR-0015** (Nudge is sole announcement surface; missing-Digest = failure): **untouched.** The
  failure line still fires on missing Digest. A **broken LLM run** now surfaces as Digest-healthy
  **+** proposals-degraded → the loud "run /sensei review" line — correct: the miner ran, the LLM
  stage may have broken, the user is pointed at review.
- **ADR-0014** (Digest is a *deterministic miner* artifact): **not extended literally** — see the
  correction above. **ADR-0016 written** (`/grill-with-docs`) to record the decision that *an
  LLM-stage structured Proposal index is acceptable for parsing pending state, while the
  run-happened signal stays the miner's Digest.* A back-pointer was added to ADR-0014 delimiting
  the two artifacts, and CONTEXT.md gained a **Proposal index** glossary term.

### Migration / compatibility

**No in-code migration.** The format is pre-release with a single user (the maintainer), so there
is nothing to migrate for future distribution users — they install into an empty `proposals/` dir
and never carry legacy `.md` files. The maintainer's ~14 existing legacy `.md` days (several with
real proposals, ~8 "nothing today" placeholders) are cleaned up **by hand, once**, as a build-time
step under `/goal` — *not* by a `compute_pending` compatibility branch.

Why no in-code path: a legacy `.md`-only day is structurally indistinguishable from a partial LLM
failure (both are `.md`-without-`.json`), and telling them apart would require reading the `.md`'s
keys — exactly the `KEY_RE` prose-parsing this feature deletes. So there is no clean in-code rule;
the earlier draft's claim that legacy days "self-heal via `decisions.jsonl`" was **wrong** (the
degraded branch never consults `decided_keys`, so those days would have false-alarmed loudly and
*permanently*, unclearable by review). Manual cleanup sidesteps the whole problem. The **ADR-0006
distribution concern is dropped** — it does not apply pre-release.

## Acceptance criteria (from #22)

- [x] Recommendation (adopt/defer/reject) with codebase-design rationale — **ADOPT** (above).
- [x] Prototype index schema drafted — above.
- [x] Confirm the Nudge can drop `KEY_RE`, the `---` split, and the placeholder/degraded logic —
  yes; degraded's structured mapping enumerated above.
- [x] Verify no conflict with ADR-0002 / 0014 / 0015; note whether a new ADR is warranted — done;
  0002 & 0015 untouched, 0014 not literally extended, **ADR-0016 written**.
- [x] Migration/compat note for old `.md`-only days — above (no in-code path; manual cleanup).

## Outstanding questions — resolved by `/grill-with-docs`

1. **Keep the `- **Key:**` line?** → **KEEP**, re-pointed. It lost its *nudge* consumer (the
   regex) but keeps its *review* consumer — review records verdicts in `decisions.jsonl` by key and
   skips already-decided proposals by key, reading the key from the `.md`. Dropping it would force
   review to correlate index entries back to `.md` blocks (the fuzzy matching we're deleting).
   Byte-exact rigidity relaxed; step 5 mirrors keys into the index. (Scope-in #3.)
2. **Write the new ADR?** → **YES, ADR-0016 written.** Clears all three `domain-modeling` bars
   (hard to reverse, surprising vs ADR-0014, real trade-off). Records the LLM-stage-index decision
   and that the run-happened signal stays the miner's Digest.
3. **Drop the placeholder `.md`?** → **DROP.** Quiet nights write only `{"proposals": []}`. The
   placeholder was vestigial (nothing read it; the Digest is the proof-of-patrol) and, under the
   union-glob, an active false-alarm risk if its index write failed. (Scope-in #3.)

### Also resolved in the grill (beyond the three)

- **Migration killed as a code concern** — pre-release/single-user → manual cleanup; the earlier
  "self-heal via `decisions.jsonl`" claim was factually wrong. (See Migration.)
- **Union-glob kept** — re-justified as partial-write insurance, not legacy handling.
- **`.md`-first-then-`.json` ordering** locked as an invariant. (Scope-in #3.)
- **Schema: `date` dropped, `kind` kept.** (Index schema.)

---

## Planning Contract (HOW)

*Enriched by `ce-plan` from the requirements above. The Product Contract is unchanged; this
section adds the implementation shape, sequencing, and verification. Plan depth: **Standard** —
well-bounded, zero surviving ambiguity (the grill locked every decision), touches the announcement
surface + tests.*

### Ship path (verify before assuming edits take effect)

`install.sh` copies **`nudge.py`** to `~/.claude/skills/sensei/nudge.py` (install.sh:18) and wires
the SessionStart hook to `$PYTHON3 $SKILLS_DIR/nudge.py` (install.sh:29). `skill/SKILL.md` and
`mine.py` ship the same way (ADR-0009). **Consequence:** editing `nudge.py` or `skill/SKILL.md` in
the repo is inert until `./install.sh` is re-run — a `/sensei nightly` test before re-install
exercises the stale installed copy. This is confirmed, not assumed: `nudge.py` is a first-class
install artifact, so the reader-side edit ships correctly once installed.

### Reader branch logic (the collapsed `compute_pending`)

Per-date decision the implementer and test author must both honor. `stem` = a date with a `.md`
**or** `.json` in `proposals/` (union-glob):

| `.json` index for the date | Result for that date |
|---|---|
| missing (only `.md` present) | **degraded** — partial LLM write or legacy `.md`-only day |
| present but not `{"proposals": [...]}` (malformed / bad JSON) | **degraded** |
| valid, `proposals` non-empty, ≥1 key not in `decided_keys` | **pending** (counts toward `count`) |
| valid, `proposals` empty **or** every key already decided | contributes nothing |

Aggregate: any degraded date ⇒ `{"degraded": True, "oldest": min(degraded + pending)}`; else any
pending ⇒ `{"degraded": False, "count": len(pending), "oldest": min(pending)}`; else `None`. Return
shape is **unchanged**, so `run()` (nudge.py:120–135) needs no edits. The spike in *Collapsed
`compute_pending`* above is the reference implementation.

### Implementation Units

#### U1. SKILL.md step 5 — LLM-stage index-write contract

- **Goal:** The nightly LLM stage writes `proposals/YYYY-MM-DD.json` every run, `.md` first then
  `.json`, and stops writing the placeholder `.md` on quiet nights. Re-point the `- **Key:**` note
  off the retired nudge-parse contract.
- **Requirements:** Scope-in #1, #3; Outstanding-questions #1, #3; ADR-0016 (invariants:
  `.md`-first-then-`.json`, `- **Key:**` line stays/re-pointed, quiet nights write only the index).
- **Dependencies:** none.
- **Files:** `skill/SKILL.md`.
- **Approach:**
  1. **Step 5 (skill/SKILL.md:153–156)** — after the existing "Write `…/YYYY-MM-DD.md`" instruction,
     add: write the index `~/.claude/sensei/proposals/YYYY-MM-DD.json` as
     `{"proposals": [{"key": "<key>", "kind": "prose|habit-rule|hook"}, …]}`, one entry per proposal
     just emitted, mirroring each proposal's `- **Key:**` and its kind label. **No `date` field**
     (redundant with the filename). State the ordering invariant explicitly: **the `.md` is written
     first (final action of drafting proposals), then the `.json`** — never the reverse; the index
     only points into the `.md`.
  2. **Retire the placeholder `.md`** — replace the "If zero patterns qualified, write a one-line
     file: `# … nothing today …`" instruction with: on a zero-qualifying night, write **only**
     `{"proposals": []}` and **no** `.md`. (The Digest is the proof-of-patrol; a placeholder `.md`
     whose index write failed would false-alarm as degraded under the union-glob.)
  3. **Re-point the `- **Key:**` note (skill/SKILL.md:117–119)** — replace "this literal format is a
     parse contract the session nudge depends on" with wording that the key is now a **review +
     human field, mirrored into the index** by step 5; its byte-exact rigidity is no longer
     load-bearing (its remaining reader is an LLM/review, not a regex). Keep the line itself and the
     "every proposal shape emits it" requirement.
- **Patterns to follow:** existing step-5 prose voice; the index shape in *Index schema (spike)*
  above; ADR-0016 "Invariants this decision relies on".
- **Test scenarios:** `Test expectation: none — SKILL.md is LLM-facing instruction prose, not
  executable code (ADR-0002: nightly proposes, the LLM authors the artifacts). Correctness of the
  writer is exercised indirectly by U3's reader tests over the shapes it produces.`
- **Verification:** step 5 names the `.json` index write, the `.md`-first ordering, and the
  no-placeholder quiet-night rule; the `- **Key:**` note no longer claims a nudge parse contract;
  no other step references `KEY_RE` or markdown parsing.

#### U2. Collapse `compute_pending` to read the index

- **Goal:** `nudge.py` reads pending state from the structured index only; all markdown-parsing
  logic is deleted; return shape and `run()` are unchanged.
- **Requirements:** Scope-in #2; "Degraded" mapping; ADR-0016 Consequence.
- **Dependencies:** none (pairs with U1 — U1 defines the artifact U2 reads, but no code dependency).
- **Files:** `nudge.py`.
- **Approach:**
  - Delete `KEY_RE` (nudge.py:12) and remove the now-orphaned **`re`** from the import line
    (nudge.py:8) — `re` has no other use in the file (verified). This is a required orphan cleanup,
    not a tangential edit.
  - Replace the `compute_pending` body (nudge.py:51–87) with the index-reading implementation from
    the *Collapsed `compute_pending` (spike)* above: union-glob of `*.md` + `*.json` → per-date
    `load_json` of `{date}.json` → missing/malformed ⇒ degraded, valid ⇒ count undecided keys.
    Reuse the existing module-level `load_json` (nudge.py:20). Update the docstring to describe the
    index-read behavior.
  - Delete `text.split("---")`, the one-line placeholder skip, and the `len(keys) < len(blocks)`
    heuristic — they have no counterpart in the new body.
  - **Do not touch** `run()`, `load_json`, `load_decided_keys`, `emit`, `expected_date`, or `main`.
- **Patterns to follow:** the reference spike; the existing `load_json`-based reads elsewhere in
  `nudge.py` (digest at :98, this stays the model for degraded/malformed → `None` handling).
- **Test scenarios:** covered by U3 (behavior lives in `compute_pending`; U3 drives it through the
  `run()` subprocess harness). This unit's own check is that the deleted symbols are gone and the
  module still imports.
- **Verification:** `grep -n 'KEY_RE\|split("---")\|len(keys)\|\bre\b' nudge.py` returns nothing;
  `python3 -c "import ast; ast.parse(open('nudge.py').read())"` succeeds; the function signature
  `compute_pending(proposals_dir, decided_keys)` and its return shape are unchanged.

#### U3. Migrate + extend the nudge tests

- **Goal:** Test coverage reflects the index contract. Existing tests that encode the retired
  `.md`-parse behavior are migrated to write a `.json` index; the six required scenarios are covered.
- **Requirements:** the requirements-doc test list (empty index, populated index, missing index →
  degraded, malformed index → degraded, union-glob `.md`-only → degraded, all-decided keys → None).
- **Dependencies:** U2.
- **Files:** `tests/test_nudge.py`.
- **Approach:**
  - Add a `write_index(sensei_dir, date_str, proposals)` helper (mirrors `write_digest` /
    `write_proposal`) that writes `proposals/{date_str}.json` = `{"proposals": proposals}`.
  - **Migrate the existing `.md`-only tests** — they will otherwise fail, because a `.md` with no
    `.json` is now *degraded*, not parsed:
    - `test_pending_line_reports_count_and_oldest` → write a 2-entry index; still expect
      `2 proposals waiting` + oldest date.
    - `test_pending_excludes_decided_keys` → write a 1-entry index whose key is in
      `decisions.jsonl`; still expect `0 proposals`.
    - `test_degrades_on_unparseable_key` → repurpose/rename to the **union-glob `.md`-only**
      scenario (a `.md` with no sibling `.json` ⇒ degraded, "proposals waiting since …"); this
      preserves the existing coverage under the new rule.
  - Keep `write_proposal` (`.md`) — still needed for the union-glob `.md`-only case.
  - Add the missing scenarios:
    - **Empty index** — `write_index(…, [])` + digest present ⇒ heartbeat "0 proposals", `nudge-state` written.
    - **Populated index** — 2 entries, none decided ⇒ "2 proposals waiting" + oldest.
    - **Missing index (degraded)** — `.md` present, no `.json` ⇒ degraded loud line (this is the
      union-glob `.md`-only case; one test can serve both if named clearly).
    - **Malformed index (degraded)** — write `{date}.json` = `"{not valid json"` (or a JSON list, or
      `{"proposals": 5}`) ⇒ degraded loud line, no crash.
    - **All-decided keys → None** — populated index, every key in `decisions.jsonl` ⇒ "0 proposals".
- **Patterns to follow:** existing `run_nudge` subprocess harness, `write_digest`/`write_proposal`
  helpers, `tempfile.TemporaryDirectory`, `--now` override; stdlib `unittest` only (no deps).
- **Test scenarios (this unit's deliverable):** happy path — empty index ⇒ heartbeat; populated
  index ⇒ count+oldest. Edge — union-glob `.md`-only ⇒ degraded; all-decided ⇒ None; a valid index
  mixing decided + undecided keys ⇒ counts only undecided. Error — malformed JSON and wrong-shape
  JSON (`{"proposals": 5}`, top-level list) ⇒ degraded, `returncode == 0` (never crashes session
  start). Integration — the full `run()` path via subprocess asserts the emitted `systemMessage`
  string for each.
- **Verification:** `python3 -m unittest discover tests` is green; no test still writes a `.md`
  expecting it to be *parsed* for keys.

#### U4. One-time manual cleanup of legacy `.md`-only days (build task, live state)

- **Goal:** After the reader switches to the index, no legacy `.md`-only day remains in the
  maintainer's `~/.claude/sensei/proposals/` to false-alarm as degraded. **No in-code migration** —
  this is the deliberate manual step ADR-0016 sanctions.
- **Requirements:** Migration / compatibility; ADR-0016 Consequence (no compatibility branch).
- **Dependencies:** U1, U2 (do this only once the new writer/reader are installed).
- **Files:** none in-repo. Operates on **live user state** — `~/.claude/sensei/proposals/*.md`
  (currently 14 files: `2026-07-09.md` … `2026-07-22.md`).
- **Approach:** This is an operational step performed under `/goal`, **not** committed code, and it
  is the **explicitly-authorized exception** to the CLAUDE.md guardrail "never delete proposals
  during development unless explicitly asked" (the plan asks). Manual judgment, not a scripted `rm`:
  1. Before deleting anything, ensure any *still-undecided real* proposals in those 14 files are
     captured — run `/sensei review` (or record verdicts) so nothing valuable is lost, since these
     `.md` files are the only record of those proposals (there is no index for them).
  2. Then remove the legacy `.md` files so no `.md`-only day survives. Do **not** backfill indexes
     (that would require the `KEY_RE` parsing this feature deletes).
  3. Confirm: `ls ~/.claude/sensei/proposals/*.md` shows only files that also have a sibling
     `.json` (i.e. produced by the new writer), or none.
  - Going forward the LLM stage writes the index every night; no `.md`-only day recurs except a
    genuine partial-write, which *should* be caught as degraded.
- **Test scenarios:** `Test expectation: none — one-time operational cleanup of live state, not
  code. Verified by inspection (step 3).`
- **Verification:** after cleanup, a real session start emits the heartbeat (or a correct pending
  line), not a spurious "proposals waiting since 2026-07-09".

### Sequencing

U1 and U2 are the two ends of one contract and can be implemented in parallel (different files, no
code dependency); land both before U3. U3 depends on U2. U4 is last — it touches live state and is
only meaningful once the new writer + reader are installed (`./install.sh`). Suggested landing
order: **U1 + U2 → U3 → (install) → U4.**

### Verification Contract

- **Automated:** `python3 -m unittest discover tests` passes (U3 green; `test_mine.py` /
  `test_settings_hook.py` unaffected).
- **Static:** `KEY_RE`, `split("---")`, `len(keys)`, and the `re` import are all absent from
  `nudge.py`; `compute_pending` signature and return shape unchanged; `run()` untouched.
- **Manual reader smoke (never against live state):** run `nudge.py` from the repo against a
  scratch fixture dir — `python3 nudge.py --sensei-dir <scratch> --now 2026-07-22T09:00:00` — seeded
  with a digest + hand-written index files covering empty / populated / missing / malformed, and
  confirm the emitted `systemMessage` matches the reader-branch table. Never point `--sensei-dir` at
  `~/.claude/sensei`.
- **Writer:** SKILL.md step 5 is inspected (U1 verification) — the writer is LLM prose, exercised
  end-to-end only by a real `/sensei nightly` after `./install.sh`.
- **ADR-0002 bright line:** unchanged — no config file is written or edited by any unit.

### Definition of Done

- [x] U1 — SKILL.md step 5 specifies the `.json` index write, `.md`-first ordering, and the
  no-placeholder quiet-night rule; the `- **Key:**` note is re-pointed to review/index.
- [x] U2 — `compute_pending` reads the index only; `KEY_RE`, `split("---")`, the placeholder skip,
  the `len(keys) < len(blocks)` heuristic, and the orphaned `re` import are deleted; union-glob and
  degraded mapping retained; return shape and `run()` unchanged.
- [x] U3 — existing `.md`-parse tests migrated to indexes; all six scenarios covered; full test
  suite green.
- [x] Verification Contract's automated + static + manual-smoke checks pass.
- [x] U4 — legacy `.md`-only days cleaned up by hand after install; no spurious degraded nudge.
- [x] (Already done in the grill — verify only, do not redo: ADR-0016 exists, ADR-0014 back-pointer
  present, CONTEXT.md "Proposal index" term present.)
