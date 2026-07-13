# Headless run uses a scoped `--allowedTools` allowlist, never `--dangerously-skip-permissions`

The launchd job runs `claude -p` with a tight `--allowedTools` allowlist: `osascript`, `Read`, and `Write` scoped to `~/.claude/sensei/**`. The obvious lazy path for automation — `--dangerously-skip-permissions` — is rejected.

The miner is deliberately **not** in the allowlist: the launchd job runs it in plain zsh, before Claude, so Claude only ever reads `events.json` and never invokes the miner (see ADR-0001 and ADR-0009). This also removes the one place where a `~`-vs-absolute path mismatch between the skill and the allowlist could have hung the headless run on an unanswerable prompt.

## Why — hard enforcement of the nightly boundary

This is the enforcement layer under ADR-0002. Nightly is *instructed* not to edit config; the allowlist makes it *unable* to. Because `Write` is filesystem-scoped to `~/.claude/sensei/**`, a misbehaving — or prompt-injected — nightly run physically cannot write to `CLAUDE.md` or any skill. The policy in ADR-0002 is a soft instruction; this scope is the hard boundary that backs it.

This matters because the corpus is untrusted: transcripts contain arbitrary text that flows into the model's context, so prompt injection during an unsupervised 05:30 run is a real threat model, not a hypothetical.

## Consequence

If a future nightly run breaks on a permission prompt, the fix is to widen the allowlist *within* `~/.claude/sensei/**` — never to reach for `--dangerously-skip-permissions`. Weakening this to a broad Write scope or skip-permissions would silently dissolve ADR-0002's guarantee.
