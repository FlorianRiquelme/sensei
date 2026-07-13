# sensei is built for distribution, not just personal use

sensei will be open-sourced and used by other people. This is the governing constraint for the project going forward, and it is not visible in the prototype — which reads as a single-user tool: it hardcodes one user's absolute repo path, username, personal launchd label (`com.florian.sensei`), and an EN+DE-only correction lexicon.

## Consequence — everything user-specific is prototype-only

The following are shortcuts of the personal prototype and must be parameterized or resolved at install time before release, not treated as design:

- The absolute miner path (`/Users/florianriquelme/Repos/.../mine.py`) hardcoded in the plist and skill body.
- The personal launchd label `com.florian.sensei` and all `/Users/florianriquelme/...` paths in the plist (`WorkingDirectory`, log paths, the `Write` allowlist scope).
- The install-by-copy of the skill (fine mechanically, but the whole install flow needs a portable shape).
- The EN+DE lexicon baked into `mine.py` (ADR-0004) — for distribution this should be configurable/localizable, or at minimum documented as the one place a user edits.

The installer is responsible for making sensei portable: resolve the repo path at install time and template it into the plist and skill, derive the label/paths from the running user, and never ship one person's absolute paths. Tracked as a GitHub issue.
