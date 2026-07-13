# sensei targets macOS only

sensei is macOS-only, by choice — even though it is open-sourced (ADR-0006). The scheduler is a launchd plist and the notification is `osascript -e 'display notification'`; both are macOS-native and have no cross-platform fallback. The author works only on macOS and scopes the project to it.

## Consequence

- launchd and `osascript` are legitimate hard dependencies, not shortcuts to abstract away. Do **not** build a cross-OS scheduler/notifier abstraction (cron/systemd-timer, notify-send, etc.) — that reach was considered and declined.
- "Portable install" in ADR-0006 means portable **across macOS users and machines** (no hardcoded username/path), not cross-OS.
- The README/docs should state the macOS requirement plainly so Linux/Windows users aren't surprised by a silent no-op.
