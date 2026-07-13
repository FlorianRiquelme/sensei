#!/bin/bash
# sensei installer — idempotent. Copies the skill, creates state dirs, loads the launchd job.
# Repo (mine.py, this script) stays put; only the skill + plist get installed elsewhere.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$HOME/.claude/skills/sensei"
SENSEI_DIR="$HOME/.claude/sensei"
PLIST_NAME="com.florian.sensei.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"
LABEL="com.florian.sensei"

echo "sensei: installing skill -> $SKILLS_DIR"
mkdir -p "$SKILLS_DIR"
cp "$REPO_DIR/skill/SKILL.md" "$SKILLS_DIR/SKILL.md"

echo "sensei: ensuring state dirs -> $SENSEI_DIR/{proposals,logs}"
mkdir -p "$SENSEI_DIR/proposals" "$SENSEI_DIR/logs"

echo "sensei: installing launchd job -> $PLIST_DST"
cp "$REPO_DIR/$PLIST_NAME" "$PLIST_DST"

if launchctl list | grep -q "$LABEL"; then
  echo "sensei: unloading existing job before reload"
  launchctl unload "$PLIST_DST"
fi
launchctl load "$PLIST_DST"

echo "sensei: installed. Runs daily 05:30 via launchd; logs -> $SENSEI_DIR/logs/nightly.log"
