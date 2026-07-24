---
title: LLM Full-Mode Mining - Plan
type: feat
date: 2026-07-24
topic: llm-full-mode-mining
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
---

# LLM Full-Mode Mining - Plan

## Goal Capsule

- **Objective:** Add an on-demand, user-run "full mode" that uses an LLM to read a sampled slice of transcripts semantically, surface signal-types the deterministic miner misses, and promote each promotable one into a user-local detector the cheap nightly tier runs for free thereafter. The active scope is the single-user discover-and-promote loop; sharing detectors across people is not active scope.
- **Product authority:** Issue #30 (the requirement) and this Product Contract. The nightly deterministic tier, the review-applies boundary, and the effectiveness ledger are pre-existing and unchanged except where a Requirement below names the change.
- **Open blockers:**
  - The miner's reader/detector seam — detectors as pure functions over normalized records — is designed but **not implemented**. The `feat/miner-reader-detector-seam` branch holds only a plan and an ADR, and `mine.py` still fuses reading and detection in one function. Full mode needs a detector-loading seam, so landing (or building) it is a prerequisite (R10).
  - The guardrail for running user-local detector code inside the deterministic miner (the ADR-0001 softening) is unresolved and is the headline `/grill-with-docs` question.
  - graph-bro is *not* a blocker: its slice-1 engine already executes Topologies (built and end-to-end smoke-tested on `origin/main`, including a fan-out read-only + dedup-join example). The only step is updating the stale local checkout.

## Product Contract

### Summary

Full mode is an on-demand, cost-bounded, LLM-driven audit that complements — never replaces — the nightly deterministic miner. It runs as a graph-bro Topology authored in this repo: read-only agent nodes fan out over a sample of transcripts, read them semantically to find recurring signal-types `mine.py`'s lexicon misses, and author each promotable one as a **tested detector**. You review and accept detectors through the existing `/sensei review`; accepted detectors land in your **user-local** detector store, so the free tier catches that signal-type from the next mine run onward.

### Problem Frame

`mine.py` is deterministic, zero-token, and lexicon-based — fast, free, high precision, but with a hard recall ceiling. A 2026-07-24 design session found a real, recurring signal class it never surfaces: `/grill-with-docs` overrides. Across 23 real grill runs ~15% of proposals were overridden, but the miner missed most because several overrides were phrased as *questions* ("what if we used the X API?"), which `CORRECTION_RE` does not match. Only an LLM reading semantically caught them.

The gap is not that a regex *cannot* catch these — it is that no one authored the right matcher, and hand-authoring matchers for signal-types you have not yet noticed is work that never happens. The recall ceiling is really an authorship ceiling. Full mode spends LLM effort once to notice the signal-type and author the detector, so the free tier pays it forward on every run after.

### Key Decisions

- **Full mode runs on graph-bro, not as a standalone skill** (session-settled: user-directed — chosen over a standalone LLM skill: graph-bro is the user's workflow engine and sensei is its first dogfood, so running the full scan on it validates both products in tandem). The fan-out, read-only reader nodes, join/dedup, and sample selection are expressed as a graph-bro Topology.
- **A promoted detector is LLM-authored code, not matcher-data** (session-settled: user-directed — chosen over declarative matcher-data and over a tiered data+code split: code unlocks structural signal-types like "denial then rephrase within N turns" that a keyword/glob/regex vocabulary cannot express). The LLM authors the detector at promotion time; the detector then runs deterministically at mine time.
- **Detectors live in user-local state, never merged into the repo** (session-settled: user-directed — chosen over merging into shipped `mine.py`: detectors are personalized to one user's workflow, and `mine.py` ships to everyone, so a repo merge would force one user's detector on all installs). The shared miner gains one generic capability — loading user-local detectors at mine time; the detectors themselves are user data. This is also the seam the deferred commons will reuse.
- **Promotion flows through `/sensei review`; a detector is never auto-applied** (session-settled: user-approved — the review-applies boundary of ADR-0002 was surfaced and kept). Full mode proposes; the human accepts. Because a detector is user-local state loaded at runtime, acceptance needs no repo edit and no `install.sh` re-run — it is live on the next mine run.
- **v1 is discover-and-promote; proving a promoted detector reduced friction is deferred** (session-settled: user-directed — chosen over a discover-only slice and over a full discover-promote-measure slice). Measurement rides the existing effectiveness ledger once a detector is live and is out of v1 scope.
- **Review stays the human apply surface because graph-bro's `human` node kind is deferred** (session-settled: user-approved). The Topology is read-only discovery that emits proposals; the human checkpoint lives outside the graph, in `/sensei review`, matching ADR-0002.

### Requirements

**The full-mode run**

- R1. Full mode is invoked on demand by the user, never on the nightly launchd schedule. It complements the deterministic nightly tier and never replaces or blocks it.
- R2. The run is cost-bounded and operates on a sample of the corpus, not the whole corpus (the corpus is ~750MB / 700+ sessions per 60 days).
- R3. The run executes as a graph-bro Topology whose reader nodes are read-only: they read transcripts and propose, and mutate no live sensei state during the run.
- R4. Reader nodes read transcripts *semantically* and surface recurring **signal-types** the deterministic miner misses — the personalized "what is worth mining for this user," not only individual facts.
- R5. The full-mode reader stage is the only new component permitted to read raw transcripts with an LLM; the deterministic `mine.py` remains the only *deterministic* transcript reader, and neither the nightly path nor a promoted detector ever calls a model at mine time.

**Detector authoring and promotion**

- R6. For each promotable signal-type, the run authors a **detector**: a deterministic code unit plus a unit test that proves it fires on the real transcript cases the run discovered. The test is the recall evidence and is written into the existing stdlib `tests/`.
- R7. A promoted detector must be deterministic and stdlib-only, and must make no network or model calls at mine time. Acceptance is gated on this holding (see Outstanding Questions for the enforcement mechanism).
- R8. Detector proposals are presented in `/sensei review` one at a time alongside today's proposal kinds; the user inspects the detector and its test and accepts, rejects, or edits. Reject runs the existing mini-grill and cooldown.
- R9. On accept, the detector is written to a user-local detector store under `~/.claude/sensei/`; it is live on the next mine run with no repo edit and no `install.sh` re-run.
- R10. `mine.py` loads user-local detectors at mine time through the reader/detector seam (detectors as pure functions over normalized records) and runs them in the same pass as the built-in detectors.

**Determinism and measurement stay intact**

- R11. A promoted detector emits events in the same shape as the built-in detectors, so its output flows unchanged into the existing nightly clustering, review, status, and effectiveness-ledger machinery.
- R12. The LLM drives discovery and proposal only. Effectiveness-ledger keys, cooldown, and dedup continue to be derived deterministically exactly as today; non-deterministic extraction never feeds those.

**The mining-graph deliverable and the boundary**

- R13. The mining-graph Topology and its semantics are a sensei deliverable that lives in this repo and is handed to graph-bro at runtime by file path. graph-bro contains nothing that names sensei or its domain (graph-bro's boundary invariant R1).
- R14. The detector-vs-fact split is explicit in the run's output. A **detector** is a generalizable, PII-free technique promoted into the user-local detector store. A **fact** is a user-specific config truth (e.g. mac-only, zod-everywhere) that stays local and flows through the existing prose/habit-rule proposal path to `CLAUDE.md`/skills — never into the detector store.

### Key Flows

- F1. On-demand full-mode discovery run
  - **Trigger:** The user invokes full mode (a new interactive mode; exact command deferred to planning).
  - **Steps:** A cost-bounded sample of sessions is selected; graph-bro executes the Topology — read-only reader nodes fan out (`for_each`) over transcript batches and each returns candidate missed-signal observations; a join with a `dedup`/`merge` reducer consolidates candidates across batches; an authoring node clusters candidates into signal-types, classifies each as detector or fact, and for each promotable detector writes a detector proposal (code + test + evidence); proposals are written to the user-local proposals area.
  - **Outcome:** Dated detector and fact proposals await review. No live state changed.
- F2. Detector promotion through review
  - **Trigger:** The user runs `/sensei review` with pending detector proposals.
  - **Steps:** Review presents each detector proposal — the detector code, its unit test, and the discovered evidence — one at a time; the user inspects, accepts, rejects (mini-grill + cooldown), or edits; on accept the detector is written to the user-local detector store.
  - **Outcome:** The accepted detector is live; the next mine run loads it and emits events in the normal shape.

### Visualizations

The discover-promote loop and where it touches the existing tiers:

```mermaid
flowchart TB
  U[User invokes full mode] --> S[Select cost-bounded sample]
  S --> G[graph-bro executes Topology]
  subgraph G2[Topology: read-only]
    R1n[Reader nodes fan out for_each] --> J[Join + dedup]
    J --> A[Authoring node: cluster into signal-types, classify detector vs fact, write detector code + test]
  end
  G --> P[Detector + fact proposals in user-local proposals area]
  P --> RV[/sensei review — human accepts]
  RV -->|detector| DS[User-local detector store]
  RV -->|fact| CM[CLAUDE.md / skills via existing proposal path]
  DS --> M[mine.py loads user-local detectors at mine time]
  M --> EV[events.json in normal shape]
  EV --> NL[Existing nightly / review / status / ledger]
```

### Acceptance Examples

- AE1. Grill-override phrased as a question (the motivating case)
  - **Covers R4, R6, R10.**
  - **Given** sessions where the user overrode a grill recommendation by asking "what if we used the X API?" rather than issuing a lexical correction.
  - **When** full mode reads the sample and the deterministic miner had emitted nothing for those turns.
  - **Then** the run surfaces an interrogative-override signal-type and authors a detector (with a passing test over those real cases); after the user accepts it, a later mine run emits an event on that phrasing that `CORRECTION_RE` would have missed.
- AE2. Determinism guard on a proposed detector
  - **Covers R7.**
  - **Given** a proposed detector whose code would call a model or import a network library at mine time.
  - **When** it reaches the acceptance gate.
  - **Then** it fails the gate and is not promotable, because a promoted detector must run deterministically with no model calls.
- AE3. A user-specific fact is not promoted as a detector
  - **Covers R14.**
  - **Given** the run discovers a user-specific config truth (e.g. "this user is mac-only") rather than a generalizable technique.
  - **When** the authoring node classifies the finding.
  - **Then** it is emitted as a fact through the existing prose-proposal path to `CLAUDE.md`, not written to the detector store.

### Scope Boundaries

**Deferred for later**

- The detector **commons / sharing** — pulling community detectors, contributing generalized and human-reviewed detectors, opt-in per detector. Deferred until the single-user loop is proven; the user-local detector store is designed as the seam it will later plug into, but the commons is not built now.
- **Effectiveness measurement** of a promoted detector — proving the new signal-type actually reduced friction. Rides the existing ledger once a detector is live; out of v1.
- **Auto-applying** a detector without human review — rejected; it would put unreviewed LLM code into the deterministic instrument and break ADR-0002.

**Unchanged, not in scope to modify**

- The nightly deterministic tier, its launchd schedule, and the headless allowlist (ADR-0005) remain as they are. Full mode is a separate interactive invocation.

### Dependencies / Assumptions

- **graph-bro slice-1 engine (ready).** Requires a Topology (serializable nodes+edges, authored in the consumer repo, handed over by file path), read-only `agent` nodes, `for_each` fan-out, and a join with a `dedup` reducer. All of these are implemented and end-to-end tested on graph-bro's `origin/main`; a shipped `examples/fanout-read-join/topology.json` exercises the read-only-fan-out-then-dedup-join shape this plan needs. The local graph-bro checkout is ~20 commits stale and must be updated to match `origin/main`.
- **The reader/detector seam (prerequisite, not yet built).** R10 needs detectors to be pure functions over normalized records loaded at mine time. That seam does not exist yet: `mine.py` still fuses reading and detection, and the `feat/miner-reader-detector-seam` branch contains only a plan and an ADR, no refactor. Landing that seam — or building the detector-loading mechanism as part of this work — is a prerequisite for R9/R10.
- **User-local state location.** Assumes `~/.claude/sensei/` can hold a detector store that `mine.py` discovers and loads at mine time, alongside the existing `events.json`, `decisions.jsonl`, and `proposals/`.

### Outstanding Questions

**Resolve Before Planning** (own these in `/grill-with-docs`)

- **The ADR-0001 softening.** With detectors as user-local code loaded by `mine.py`, the deterministic miner now executes arbitrary user-local Python, so ADR-0001's guarantee moves from *structurally* deterministic to *review-plus-test-enforced* deterministic. Decide the guardrail depth: a static check that a detector imports no network/model libraries; a constrained detector API; or interpreting a matcher-DSL instead of `exec`-ing raw code. This choice may amend or add an ADR.
- **Reader/detector seam sequencing.** The seam R9/R10 depend on does not exist yet. Decide whether to land the planned `feat/miner-reader-detector-seam` refactor first (its ADR is numbered 0016, which now collides with main's ledger ADR-0016 and needs renumbering), or to build the detector-loading mechanism directly as part of this work.

**Deferred to Planning**

- Cadence and sample-selection strategy: how the sample is chosen (recency, stratification, random), how large, and how the cost bound is enforced.
- The full-mode invocation surface (a new `/sensei` mode name and its arguments).
- The concrete detector store format and its versioning scheme.
- The Topology's concrete node/edge specification and the exact file-path/CLI handoff to graph-bro.
- The PII-scrubbing / generalization step that keeps a detector free of user-specific data (needed now for the detector/fact split; load-bearing later for the commons).

### Sources / Research

- Issue #30 — the requirement (`gh issue view 30`).
- ADRs in `docs/adr/`: 0001 (deterministic miner is the sole transcript reader), 0002 (nightly proposes, review applies), 0004 (miner favors recall, precision is the LLM's job), 0005 (headless allowlist), 0008 (stdlib-only), 0009 (miner installed by copy), 0011 (repeat structural thinning), 0016 (ledger measures via LLM-authored triggers).
- `CONTEXT.md` — sensei domain glossary (Friction, Detector, Trigger, Proposal, Effectiveness ledger).
- `STRATEGY.md` — sensei tracks and the scope firewall (this is future-milestone work, not the current "Prove and prune" track).
- The reader/detector seam plan under `docs/plans/` and branch `feat/miner-reader-detector-seam` — a plan and ADR only; the refactor is unimplemented and the branch is stale relative to main's ADR-0016/0017 work.
- The graph-bro repo (`FlorianRiquelme/graph-bro`), `origin/main` (not the stale local checkout): its `CONTEXT.md` (Topology, read-only node, fan-out/join/reducer, boundary invariant), the implemented engine + CLI, the `examples/fanout-read-join/topology.json` smoke test that matches the mining shape, its engine slice-1 plan (`docs/plans/2026-07-24-001-feat-engine-slice-1-plan.md`), and issue #1 (sensei as its first consumer / dogfood).
