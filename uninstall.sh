#!/bin/bash
# sensei uninstaller — removes the hook, launchd job, and skills dir. Preserves
# ~/.claude/sensei/ state (decisions.jsonl, proposals/, digests/, events.json,
# nudge-state, logs/) — run this from the clone, like install.sh.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$HOME/.claude/skills/sensei"
LABEL="sh.sensei"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "sensei: removing SessionStart nudge hook -> $HOME/.claude/settings.json"
python3 "$REPO_DIR/settings_hook.py" remove

if launchctl list | grep -q "$LABEL"; then
  echo "sensei: unloading launchd job"
  launchctl unload "$PLIST_DST"
fi
if [ -f "$PLIST_DST" ]; then
  echo "sensei: removing launchd job -> $PLIST_DST"
  rm -f "$PLIST_DST"
fi

if [ -d "$SKILLS_DIR" ]; then
  echo "sensei: removing skill + scripts -> $SKILLS_DIR"
  rm -rf "$SKILLS_DIR"
fi

echo "sensei: uninstalled. State preserved -> $HOME/.claude/sensei/ (decisions, proposals, digests, logs)"
