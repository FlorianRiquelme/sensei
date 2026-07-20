#!/bin/bash
# sensei installer — idempotent. Copies the skill + miner, creates state dirs, loads the launchd job.
# Ships no absolute paths: the miner is copied out of the repo (so the clone is disposable after
# install), and the plist template's __HOME__ placeholder is resolved to the installing user's $HOME.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$HOME/.claude/skills/sensei"
SENSEI_DIR="$HOME/.claude/sensei"
LABEL="sh.sensei"
PLIST_TEMPLATE="$REPO_DIR/sh.sensei.plist.template"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "sensei: installing skill + miner + nudge -> $SKILLS_DIR"
mkdir -p "$SKILLS_DIR"
cp "$REPO_DIR/skill/SKILL.md" "$SKILLS_DIR/SKILL.md"
cp "$REPO_DIR/mine.py" "$SKILLS_DIR/mine.py"
cp "$REPO_DIR/nudge.py" "$SKILLS_DIR/nudge.py"
cp "$REPO_DIR/settings_hook.py" "$SKILLS_DIR/settings_hook.py"

echo "sensei: ensuring state dirs -> $SENSEI_DIR/{proposals,digests,logs}"
mkdir -p "$SENSEI_DIR/proposals" "$SENSEI_DIR/digests" "$SENSEI_DIR/logs"

echo "sensei: seeding today's digest"
PYTHON3="$(command -v python3)"
"$PYTHON3" "$SKILLS_DIR/mine.py" --days 1

echo "sensei: registering SessionStart nudge hook -> $HOME/.claude/settings.json"
"$PYTHON3" "$SKILLS_DIR/settings_hook.py" add --command "$PYTHON3 $SKILLS_DIR/nudge.py"

echo "sensei: installing launchd job -> $PLIST_DST"
sed "s|__HOME__|$HOME|g" "$PLIST_TEMPLATE" > "$PLIST_DST"

if launchctl list | grep -q "$LABEL"; then
  echo "sensei: unloading existing job before reload"
  launchctl unload "$PLIST_DST"
fi
launchctl load "$PLIST_DST"

echo "sensei: installed. Runs daily 05:30 via launchd; logs -> $SENSEI_DIR/logs/nightly.log"
echo "sensei: session nudge active — one line at the start of your first session each day"
