# The miner is installed by copy, not run from the repo

ADR-0006 anticipated that the installer would resolve the cloned repo's path and template it into the plist and skill. We chose differently: `install.sh` copies `mine.py` into `~/.claude/skills/sensei/mine.py` (alongside the skill it already copies there), and every reference uses that derived, `$HOME`-relative path.

## Why

- The install is self-contained — it survives the clone being moved or deleted, which a templated repo path does not.
- "Ship no absolute paths" becomes fully true: the miner path is derived from `$HOME`, not a machine-specific clone location baked into the installed artifacts.
- It is consistent with the skill, which was already installed by copy.

## Consequence

- The repo is disposable after install; it is not a runtime dependency.
- Updating the miner means re-running `install.sh` to re-copy — the same requirement the skill already had.
- This refines ADR-0006: the repo path is no longer a variable anyone templates. The only value resolved into the installed plist is `__HOME__` (the installing user's home).
