---
name: sensei
last_updated: 2026-07-21
---

# sensei Strategy

## Target problem

You hit the same friction with Claude Code over and over — the same corrections, the same
tool-use denials, the same interrupts — but the fixes live in your head, and turning them into
durable `CLAUDE.md` / skill rules is manual work you skip. The signal is buried in transcripts
nobody re-reads, so recurring friction never compounds into a better config, and you can't tell
which of the rules you *do* have are still earning their place.

## Our approach

Mine your own transcripts deterministically (zero-token, stdlib-only) for friction, let an LLM
cluster it and draft concrete config diffs, and change nothing until you accept it over coffee.
We win by being **trustworthy by construction**, not by asking for trust: the deterministic
miner is the only thing that reads raw transcripts, nightly only ever proposes, and review is
the sole surface that applies. That boundary is what lets an automated tool touch your config at
all.

## Who it's for

**Primary:** A developer running Claude Code daily who wants their setup to get better on its
own without babysitting it. They're hiring sensei to turn recurring friction into durable,
reviewed config rules — and to keep that config honest — without manual upkeep.

<!-- sensei is also built for distribution (ADR-0006), but the daily solo user drives the product decisions. -->

## Key metrics

- **Friction-reduction rate** — for an accepted rule, the drop in its matching events after
  acceptance vs. its stored `baseline`. The core outcome; the whole loop exists to move it.
  Lives in `decisions.jsonl` (baseline) joined against `events.json`. *Not yet computed — this
  is what the current track builds.*
- **Proposal acceptance rate** — accepted / (accepted + rejected) per review. The leading signal
  of whether proposals are well-shaped to this user. Lives in `decisions.jsonl`.
- **Config health** — net rule count over time and the retirement rate: is the config staying
  lean and are dead rules leaving, or does `CLAUDE.md` only ever grow? Lives in the target files
  + `decisions.jsonl`.
- **Review-ritual adherence** — fraction of days the review actually happens after a nudge is
  seen. Is the human loop sticking? Lives in the nudge state + decision dates.

## Tracks

### Prove and prune _(current focus)_

Close the effectiveness loop: measure whether an accepted rule actually reduced friction, then
act on the measurement — reaffirm what works, retire and quarantine what doesn't.

_Why it serves the approach:_ Trust-by-construction is hollow if sensei can't show its own
proposals earned their keep; this is the track that makes the whole pitch credible.

### Trustworthy edits

Make every config edit show its blast radius before it lands — a dry-run of the moments a rule
would fire, plus deterministic conflict and structural checks against the live config.

_Why it serves the approach:_ The one moment sensei mutates real config is currently backed only
by LLM diligence; mechanical verification is what keeps "review applies" safe as the config
grows.

### Two-sided signal

Learn from what went *well*, not only what hurt — a positive signal from clean and
skill-succeeded sessions that both vetoes over-broad rules and reinforces what already works.

_Why it serves the approach:_ A tool that only senses pain over-corrects; a two-sided signal is
the cheapest guard against sensei quietly making Claude worse.

### Compounding across people

Turn one person's accumulated, proven rules into a portable pack a colleague adopts through their
own review, and a starter pack that gives a brand-new install day-one value.

_Why it serves the approach:_ sensei's real product is the hard-won judgment a long-running
instance earns; distribution (ADR-0006) is only real once that judgment can cross between people
without breaking the review-applies boundary.

## Not working on

- **The scope firewall:** each version ships one track's sentence. A new idea — however good —
  is triaged into a *later* GitHub milestone, never pulled into the current one. Live sequence
  and status: the repo's GitHub Milestones.
- **Automating the apply step (auto-apply "safe" proposals).** Deferred until dry-run makes
  "safe" provable; it currently pushes on the review-applies boundary.
- **Retirement, dry-run, positive signal, and rule packs are all real tracks — but not this
  version.** They are gated behind the effectiveness loop being real and trusted first.
- **Anything cross-machine or non-macOS.** Out by ADR-0007; not revisited here.
