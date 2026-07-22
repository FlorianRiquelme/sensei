---
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
---

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
