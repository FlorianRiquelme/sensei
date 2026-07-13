# sensei

A self-improving Claude Code setup: it mines your own session transcripts for friction, clusters recurring patterns, and proposes concrete edits to your Claude config — which you review before anything changes.

## Language

**Friction**:
An observable moment where the human had to correct, stop, or reject Claude — the raw signal sensei learns from. Concretely: a correction, a denial, or an interrupt.
_Avoid_: feedback, mistake, error

**Correction**:
A user text message that pushes back on what Claude did or said, detected by the correction lexicon.
_Avoid_: complaint, comment

**Denial**:
A tool-use the user rejected (Claude asked to run a tool; the user declined).
_Avoid_: rejection, block

**Interrupt**:
A session record where the user cut Claude off mid-action (`[Request interrupted by user`).
_Avoid_: cancel, abort

**Event**:
One extracted unit of friction (correction | denial | interrupt) in `events.json`, carrying its surrounding context. The miner's output unit.

**Miner**:
The deterministic, zero-token Python tool (`mine.py`) that scans transcripts and emits events. The only component that reads raw transcripts.
_Avoid_: scanner, parser, extractor

**Proposal**:
A candidate config change sensei drafts from a qualifying pattern — title, evidence, root cause, target file, and exact text to paste. Never applied automatically.
_Avoid_: suggestion, fix, recommendation

**Pattern**:
A cluster of events sharing one root cause. Only a *qualifying* pattern (≥2 independent sessions, or one high-severity event) becomes a proposal.

**Nightly**:
The headless mode, run by launchd — mines and writes proposals. Never edits config.

**Review**:
The interactive morning mode — walks proposals one at a time and applies the ones you accept.

**Decision**:
An append-only record of a past verdict on a proposal (`accepted` | `rejected`) in `decisions.jsonl`. sensei's memory: a rejected proposal is never re-proposed.
_Avoid_: verdict (except as the field name), outcome
