#!/usr/bin/env python3
"""
sensei settings_hook — idempotently register/deregister sensei's SessionStart hook in
~/.claude/settings.json, without disturbing any foreign hooks already registered there.

Usage:
  python3 settings_hook.py add --command "<abs-python3> <abs-nudge.py>" [--settings PATH]
  python3 settings_hook.py remove [--settings PATH]
"""
import argparse, json, os, sys

DEFAULT_SETTINGS = os.path.expanduser("~/.claude/settings.json")
MARKER = "_sensei"

def load_settings(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        text = f.read()
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"sensei settings_hook: {path} is not valid JSON ({e}); refusing to modify", file=sys.stderr)
        sys.exit(1)

def save_settings(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

def is_sensei_group(group):
    for hook in group.get("hooks", []):
        if hook.get(MARKER) or "nudge.py" in hook.get("command", ""):
            return True
    return False

def add(settings, command):
    hooks = settings.setdefault("hooks", {})
    session_start = hooks.setdefault("SessionStart", [])
    sensei_group = {
        "matcher": "*",
        "hooks": [{"type": "command", "command": command, MARKER: True}],
    }
    for i, group in enumerate(session_start):
        if is_sensei_group(group):
            session_start[i] = sensei_group
            return settings
    session_start.append(sensei_group)
    return settings

def remove(settings):
    hooks = settings.get("hooks", {})
    session_start = hooks.get("SessionStart")
    if not session_start:
        return settings
    hooks["SessionStart"] = [g for g in session_start if not is_sensei_group(g)]
    if not hooks["SessionStart"]:
        del hooks["SessionStart"]
    return settings

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["add", "remove"])
    ap.add_argument("--command", help="fully-resolved '<abs-python3> <abs-nudge.py>' command (required for add)")
    ap.add_argument("--settings", default=DEFAULT_SETTINGS)
    args = ap.parse_args()

    if args.action == "add" and not args.command:
        ap.error("--command is required for add")

    settings = load_settings(args.settings)
    if args.action == "add":
        settings = add(settings, args.command)
    else:
        settings = remove(settings)
    save_settings(args.settings, settings)

if __name__ == "__main__":
    main()
