---
name: spike
description: >
  Spike-first investigation for internal-approach questions. Builds a throwaway
  spike to get real evidence, posts an adopt/defer/reject recommendation on the
  issue, discards the spike code, then hands the decision to the CE pipeline to
  implement fresh. Use for issues shaped like "Investigate / should we adopt
  approach X" where the deliverable is a recommendation (not a feature) and the
  approach can only be judged by building a bit — e.g. an internal seam,
  refactor shape, or data-model change. NOT for a verdict on an external
  technology/library/platform (use /ce-pov), and NOT for open product framing
  where the options aren't yet known (use /ce-brainstorm).
argument-hint: "<issue-number-or-url>"
---

# spike

A spike earns a **decision, not a merge**. The whole point is to buy evidence cheaply, record what it taught, and throw the code away so spike-quality work never becomes the implementation by default. The real build happens fresh through the normal CE pipeline (`## Workflow` in `CLAUDE.md`).

## Route first

- **External candidate** (a named library/tool/platform, judged from its docs) → this is a verdict, use `/ce-pov`.
- **Open product framing** (what should we even build, options unknown) → use `/ce-brainstorm`.
- **Internal approach you can only judge by building** (a seam, a refactor shape, a data-model or perf change) → spike. Continue below.

## Workflow

### 1. Ground

Read the issue (`gh issue view <n> --comments`) and the code it touches. Name the **one question** the spike must answer, and — before writing any spike code — the **hard, verifiable success criteria** that will decide it. Criteria must be checkable, not vibes: "`events.json` byte-for-byte identical + all tests green", "p95 under 200ms", "the detector is callable without a subprocess". Capture a baseline now if the criterion is a before/after comparison.

### 2. Spike in isolation

Work in a dedicated worktree (`EnterWorktree`, per `CLAUDE.local.md`) on a `spike/<topic>` branch. Build the smallest thing that tests the question — throwaway quality is fine, but it must be **honest**: real enough that passing the criteria is real evidence. Run the criteria and record the result.

### 3. Recommend on the issue

Post a comment: **adopt / defer / reject**, with the spike as proof — the criteria results, what surprised you, and any risk the spike surfaced. This comment is the durable deliverable; it outlives the code.

### 4. Discard the spike code

The load-bearing step. Drop the spike so it can't be mistaken for the implementation. The repo's git guardrails block `reset --hard` and `push --force`, so use the allowed forms:

```bash
git checkout -B <branch> origin/main          # drop the spike commit locally (reset --hard is blocked)
git push origin --delete <branch>             # remove the pushed spike branch (push --force is blocked)
```

If deferring or rejecting, stop here — the recommendation is the whole output.

### 5. Capture and hand off

If adopting, write a **requirements-only plan doc** capturing what the spike learned — the chosen approach, the shape (e.g. a data/record shape), the invariants to preserve, and the verifiable criteria as acceptance examples. Path and contract follow `/ce-brainstorm`'s output: `docs/plans/YYYY-MM-DD-NNN-<type>-<topic>-plan.md`, `artifact_contract: ce-unified-plan/v1`, `artifact_readiness: requirements-only`. Commit it as the feature branch's first commit.

Then hand off to the pipeline per the `### Stage handoffs` convention in `CLAUDE.md`: `pbcopy` a `/grill-with-docs` kickoff prompt naming the plan doc, the branch, and instructing the next session to **implement fresh** (do not reconstruct the spike).

## Worked example

Issue #23 (reader/detector seam inside the Miner): spiked the split in a worktree, held it to "`events.json` byte-for-byte unchanged + all 50 tests pass", posted an *adopt* recommendation, discarded the spike branch, wrote `docs/plans/2026-07-22-001-refactor-miner-reader-detector-seam-plan.md`, and handed off to `/grill-with-docs`.
