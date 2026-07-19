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
The headless skill mode, run by launchd — reads mined events, clusters them, and writes proposals. Never edits config. (The miner runs in the launchd shell just before, so nightly itself only reads `events.json`.)

**Review**:
The interactive morning mode — walks proposals one at a time and applies the ones you accept.

**Decision**:
An append-only record of a past verdict on a proposal (`accepted` | `rejected`) in `decisions.jsonl`, carrying the proposal's Proposal key. sensei's memory: an accepted proposal is already applied; a rejected one is suppressed for a Cooldown, not forever.
_Avoid_: verdict (except as the field name), outcome

**Cooldown**:
The finite window (default 30 days) a rejected Proposal stays suppressed before its pattern becomes eligible again. sensei's rejection memory is a cooldown, not permanent silence.
_Avoid_: permanent suppression, ban, blacklist

**Proposal key**:
A Proposal's stable identity — target file plus a normalized rule signature — independent of its LLM-generated title. The thing a Decision is matched on, so re-worded duplicates of the same rule collapse to one identity.
_Avoid_: title (as a dedup key)

**Digest**:
The dated proof-of-patrol artifact the Miner writes every night before the LLM stage runs — sessions scanned and event counts by type and by project. Miner-owned and deterministic: it carries only what the Miner knows, never proposals (which the LLM stage writes later). Its absence for a night is the failure signal; pending-proposal state is read live by the Nudge, not stored here.
_Avoid_: report, summary, log

**Nudge**:
The SessionStart line that carries the Digest's payload into the session: a heartbeat on quiet nights, a pending-proposal pointer, or a loud "nightly did not run". The sole discovery surface. Fires once per calendar day in the healthy state (Digest present); the failure line is exempt and repeats every session until the Digest appears or the day turns over — a broken patrol stays loud.
_Avoid_: notification, banner

**Baseline**:
The pattern's pre-acceptance event count, stored on a Decision at accept time. The seed for future friction receipts; nothing reads it yet.
_Avoid_: receipt (the receipt is the future report computed from a Baseline)
