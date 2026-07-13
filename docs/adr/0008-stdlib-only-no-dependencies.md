# stdlib-only Python, no dependencies, no venv

The miner (`mine.py`) uses only the Python 3 standard library — no third-party packages, no virtualenv, no lockfile. "Keep everything boring and stdlib."

## Why

For the open-source project (ADR-0006) this is a deliberate stance, not just prototype laziness: zero dependencies means anyone can audit the entire miner in a single read, and install it with nothing but a system Python 3. It reinforces the auditability goal of ADR-0001 — the one component that touches raw transcripts has no opaque dependencies hiding behind it.

## Consequence

Resist adding a dependency for convenience (a nicer arg parser, a JSON-lines library, a fuzzy-match package). The bar for a first dependency is high and should itself be recorded as an ADR if it's ever crossed.
