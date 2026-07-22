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

1. **New nightly artifact** `~/.claude/sensei/proposals/YYYY-MM-DD.json`, written by the LLM
   stage, **every run**, including an empty `proposals` array on zero-qualifying nights.
2. **Collapsed `compute_pending`** that reads only the sidecar. `KEY_RE`, `text.split("---")`,
   the one-line placeholder check, and the `len(keys) < len(blocks)` degraded heuristic are all
   **deleted**.
3. **SKILL nightly step 5** gains the sidecar-write instruction. The `- **Key:**` line loses its
   "parse contract" status.

### Scope — out (firewall)

- **No** restructuring proposals into a JSON-first format with a rendered `.md` view. The `.md`
  stays the canonical human/review artifact (review reads it, SKILL.md:164); the sidecar is
  strictly an **additive index**.
- **No** backfill/migration tool. Legacy `.md`-only days self-heal (see Migration).

### Index schema (spike)

```json
{
  "date": "2026-07-22",
  "proposals": [
    {"key": "~/.claude/CLAUDE.md::ddev-prefix-artisan", "kind": "prose"},
    {"key": "~/.claude/settings.json::block-bare-artisan", "kind": "hook"}
  ]
}
```

- `kind` ∈ `prose` | `habit-rule` | `hook` (mirrors SKILL.md's proposal-kind labels).
- The current Nudge only **counts**, so it consumes `key` alone. `kind` and `date` are carried
  because the AC asks for them and they are the natural structured record of what the `.md`
  already labels — **not** because the Nudge needs them today (flagged YAGNI tension; low
  carrying cost, AC-mandated).

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

The **union-glob of `.md` + `.json`** is load-bearing: it keeps legacy `.md`-only days
visible-and-loud (they hit the missing-sidecar branch) while a healthy new day with an empty
array contributes nothing. The return shape is unchanged, so `run()`'s consumer (nudge.py:160–166)
needs no edits.

### "Degraded" mapping (AC criterion 3)

In the structured world, **degraded** = the sidecar is **missing** (legacy `.md`-only day, or the
LLM broke before writing it) **or malformed** (not valid JSON / not `{"proposals": [...]}`). The
old `len(keys) < len(blocks)` partial-write case folds into "malformed or missing."

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
  correction above. **A small new ADR is likely warranted** to record the decision that *an
  LLM-stage structured sidecar is acceptable for parsing pending state, while the run-happened
  signal stays the miner's Digest.* Writing it is `/grill-with-docs`'s call.

### Migration / compatibility

Legacy `proposals/*.md` files with no sidecar fall into the **missing-index → degraded** branch:
the Nudge shows the loud count-unknown reminder for them until they drop out of the pending set
via `decisions.jsonl`. Safe (never under-reminds), no migration tool, self-clearing. Matters for
distribution too (ADR-0006): installed users carry old `.md` days.

## Acceptance criteria (from #22)

- [x] Recommendation (adopt/defer/reject) with codebase-design rationale — **ADOPT** (above).
- [x] Prototype index schema drafted — above.
- [x] Confirm the Nudge can drop `KEY_RE`, the `---` split, and the placeholder/degraded logic —
  yes; degraded's structured mapping enumerated above.
- [x] Verify no conflict with ADR-0002 / 0014 / 0015; note whether a new ADR is warranted — done;
  0002 & 0015 untouched, 0014 not literally extended, **new ADR recommended**.
- [x] Migration/compat note for old `.md`-only days — above.

## Outstanding questions (for `/grill-with-docs`)

1. **Keep or drop the human-readable `- **Key:**` line in the `.md`** now that it is no longer a
   parse contract? Leaning **keep** (zero cost, aids human skimming), but a genuine fork.
2. **Write the new ADR?** Recommended yes (records the LLM-stage-sidecar decision and that the
   presence-signal stays the miner's). Grill's call.
3. **Zero-proposal day: also drop the one-line placeholder `.md`?** With the sidecar as the run
   marker, the placeholder is redundant with the Digest. Minor; can be decided at plan/build time.
