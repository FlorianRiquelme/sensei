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
A session record where the user cut Claude off mid-action (`[Request interrupted by user`). Carries a `followup_text` — the next plain user text after the interrupt, if any — so the LLM can see whether the user immediately clarified.
_Avoid_: cancel, abort

**Repeat**:
A directive the user re-supplies across sessions with **no friction at all** (e.g. "use ddev", "branch off develop"). Unlike the three friction types, the miner thins repeats *structurally* before emitting them — a glue blocklist, a length floor, and a non-ubiquity test (recurs across ≥N sessions but isn't present in nearly all of them) — never lexically (ADR-0011, a bounded exception to ADR-0004). Turns sensei from "learn from my pain" into "learn from my habits."
_Avoid_: habit (as the event type name), pattern (that's the cluster, not the event)

**Event**:
One extracted unit — friction (correction | denial | interrupt) or a repeat — in `events.json`, carrying its surrounding context and a `nth_in_session` ordinal (correction/interrupt) for the LLM to judge recurrence. The miner's output unit; friction events read a ~14-day window, repeats read a wider ~30-day window (ADR-0010).

**Miner**:
The deterministic, zero-token Python tool (`mine.py`) that scans transcripts and emits events. The only component that reads raw transcripts.
_Avoid_: scanner, parser, extractor

**Proposal**:
A candidate config change sensei drafts from a qualifying pattern — title, evidence, root cause, target file, and exact text to paste. Never applied automatically. Three kinds: a **prose proposal** (from a friction pattern), a **habit-rule proposal** (from a repeat pattern), or a **hook proposal** (escalation of a non-sticking accepted rule — a ready hook script + settings snippet + placement + test note, presented but never installed by sensei).
_Avoid_: suggestion, fix, recommendation

**Pattern**:
A cluster of events sharing one root cause. A friction pattern qualifies at ≥2 independent sessions, or one high-severity event; a repeat pattern qualifies simply by the miner having emitted it (already cross-session by construction — no re-applied friction gate).

**Nightly**:
The headless skill mode, run by launchd — reads mined events, clusters them, and writes proposals. Never edits config, including the hook proposal kind (a ready artifact, not an edit). (The miner runs in the launchd shell just before, so nightly itself only reads `events.json`.)

**Review**:
The interactive morning mode — walks proposals one at a time, runs a mini-grill on reject, and applies the prose/habit-rule proposals you accept. A hook proposal is presented and recorded but never applied — the human installs it.

**Decision**:
An append-only record of a past verdict on a proposal (`accepted` | `reject-retry-narrower` | `reject-not-wanted`, or the legacy bare `rejected`) in `decisions.jsonl`, carrying the proposal's Proposal key. sensei's memory: an accepted proposal is already applied — unless it later fails to stick, in which case it's escalated to a hook proposal past a grace period; a rejected one is suppressed for a Cooldown, not forever.
_Avoid_: verdict (except as the field name), outcome

**Cooldown**:
The finite window a rejected Proposal stays suppressed before its pattern becomes eligible again — normal (default 30 days) for `reject-retry-narrower` and legacy bare `rejected`; extended but still finite (default 90 days), plus cluster deprioritization, for `reject-not-wanted`. sensei's rejection memory is a cooldown, not permanent silence.
_Avoid_: permanent suppression, ban, blacklist

**Mini-grill**:
Review's short "why?" probe run on every reject, before recording a verdict — makes "I don't want this at all" the expensive path instead of a lazy menu pick. Classifies the reason into a structured verdict and routes it: a *steering* reason is stored in `decisions.jsonl` for sensei's own future runs; a *config-truth* reason is promoted into a live CLAUDE.md/skill proposal applied right there in review.

**Proposal key**:
A Proposal's stable identity — target file plus a normalized rule signature — independent of its LLM-generated title. The thing a Decision is matched on, so re-worded duplicates of the same rule collapse to one identity.
_Avoid_: title (as a dedup key)
