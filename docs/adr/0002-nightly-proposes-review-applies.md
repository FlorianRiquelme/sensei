# Nightly proposes; only interactive review applies — a permanent bright line

sensei's headless **nightly** mode may only write proposals; it must never edit `CLAUDE.md`, a skill, or any config file. Config changes are applied exclusively during interactive **review**, with a human accepting each one. This is a permanent invariant, not a "for now" stance — the skill states it as absolute "even if a fix looks trivial or obvious."

## Why

Config edits are high-blast-radius (they silently change Claude's behavior in *every* future session) and the nightly run is unsupervised at 05:30 (a bad autonomous edit would compound before anyone saw it). A human gate on every change is what makes sensei safe to run unattended and keeps the human in the loop on what their config becomes.

## Considered and rejected

Auto-applying "high-confidence, low-risk" edits (e.g. a typo fix) during nightly. Rejected permanently: any self-editing capability turns sensei into something you must audit like a coworker rather than skim like a proposal list. A confidence threshold is a moving line you'd forever second-guess; "never edit in nightly" is a bright line that costs nothing to reason about.
