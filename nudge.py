#!/usr/bin/env python3
"""
sensei nudge — SessionStart hook. Prints at most one sensei line via the top-level
systemMessage field: a heartbeat, a pending-proposals reminder, or a loud "nightly
did not run" warning. Lean and stdlib-only — this runs synchronously and blocks the
prompt on every session start.
"""
import argparse, glob, json, os, re, sys, datetime as dt

NIGHTLY_HOUR, NIGHTLY_MINUTE = 5, 30  # mirrors sh.sensei.plist.template's StartCalendarInterval

# GitHub #18: cap hits and unreadable files are rare and each means real lost signal, so
# flag on first occurrence; a handful of malformed lines is normal transcript noise, so
# gate parse_errors behind a small floor. Tune here if real-world digests show it's off.
PARSE_ERRORS_FLOOR = 10

KEY_RE = re.compile(r"^- \*\*Key:\*\*\s*(.+)$", re.MULTILINE)

def expected_date(now):
    boundary = now.replace(hour=NIGHTLY_HOUR, minute=NIGHTLY_MINUTE, second=0, microsecond=0)
    if now >= boundary:
        return now.date()
    return (now - dt.timedelta(days=1)).date()

def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

def load_decided_keys(decisions_path):
    keys = set()
    if not os.path.exists(decisions_path):
        return keys
    try:
        with open(decisions_path) as f:
            lines = f.readlines()
    except OSError:
        return keys
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = rec.get("key")
        if key:
            keys.add(key)
    return keys

def compute_pending(proposals_dir, decided_keys):
    """Returns None (nothing pending), or a dict:
    {"degraded": False, "count": N, "oldest": "YYYY-MM-DD"} or
    {"degraded": True, "oldest": "YYYY-MM-DD"}.
    Any parse miss errs toward reporting pending (over-remind, never under-remind)."""
    files = sorted(glob.glob(os.path.join(proposals_dir, "*.md")))
    pending_keys = []  # (date_str, key)
    degraded_dates = []

    for fp in files:
        date_str = os.path.splitext(os.path.basename(fp))[0]
        try:
            text = open(fp).read()
        except OSError:
            continue
        stripped = text.strip()
        if stripped.startswith("# ") and "\n" not in stripped:
            continue  # zero-proposal one-line placeholder file

        keys = [k.strip() for k in KEY_RE.findall(text)]
        blocks = [b for b in text.split("---") if b.strip()]
        if not keys:
            degraded_dates.append(date_str)
            continue
        if len(keys) < len(blocks):
            degraded_dates.append(date_str)
        for key in keys:
            if key not in decided_keys:
                pending_keys.append((date_str, key))

    if degraded_dates:
        oldest = min(degraded_dates + [d for d, _ in pending_keys])
        return {"degraded": True, "oldest": oldest}
    if pending_keys:
        oldest = min(d for d, _ in pending_keys)
        return {"degraded": False, "count": len(pending_keys), "oldest": oldest}
    return None

def leak_warning(meta):
    """Compact summary of the miner's own silent drops (GitHub #18), or None below
    threshold. `meta` is a digest's `_meta` block (may be missing/partial — read
    defensively so a pre-existing digest without `_meta` yields no warning, never
    an error)."""
    total_capped = meta.get("total_capped", 0)
    capped_sessions = meta.get("capped_sessions", 0)
    unreadable_files = meta.get("unreadable_files", 0)
    parse_errors = meta.get("parse_errors", 0)

    if not (total_capped > 0 or capped_sessions > 0 or unreadable_files > 0 or parse_errors >= PARSE_ERRORS_FLOOR):
        return None

    parts = []
    if capped_sessions > 0:
        parts.append(f"{capped_sessions} session(s) hit the per-session cap")
    if total_capped > 0:
        parts.append(f"{total_capped} events dropped past the global cap")
    if unreadable_files > 0:
        parts.append(f"{unreadable_files} unreadable file(s)")
    if parse_errors >= PARSE_ERRORS_FLOOR:
        parts.append(f"{parse_errors} parse errors")
    return ", ".join(parts)

def emit(system_message, additional_context=None):
    payload = {"systemMessage": system_message}
    if additional_context:
        payload["hookSpecificOutput"] = {"additionalContext": additional_context}
    print(json.dumps(payload))

def run(sensei_dir, now):
    exp_date = expected_date(now)
    digest_path = os.path.join(sensei_dir, "digests", f"{exp_date.isoformat()}.json")
    digest = load_json(digest_path)

    if digest is None:
        emit(
            "sensei: the nightly run did NOT happen last night - check ~/.claude/sensei/logs/nightly.log",
            additional_context="sensei nightly did not run; see ~/.claude/sensei/logs/nightly.log for details.",
        )
        return

    state_path = os.path.join(sensei_dir, "nudge-state")
    today_str = now.date().isoformat()
    if os.path.exists(state_path):
        try:
            with open(state_path) as f:
                if f.read().strip() == today_str:
                    return  # already nudged today
        except OSError:
            pass

    decided = load_decided_keys(os.path.join(sensei_dir, "decisions.jsonl"))
    pending = compute_pending(os.path.join(sensei_dir, "proposals"), decided)

    if pending:
        if pending["degraded"]:
            line = f"sensei: proposals waiting since {pending['oldest']} - run /sensei review"
        else:
            n = pending["count"]
            noun = "proposal" if n == 1 else "proposals"
            line = f"sensei: {n} {noun} waiting (oldest {pending['oldest']}) - run /sensei review"
    else:
        line = (
            f"sensei: last night scanned {digest.get('sessions_scanned', 0)} sessions, "
            f"{digest.get('events_total', 0)} events, 0 proposals"
        )

    warning = leak_warning(digest.get("_meta") or {})
    if warning:
        line = f"{line} | sensei may be missing signal: {warning}"

    emit(line)
    with open(state_path, "w") as f:
        f.write(today_str)

def main():
    if os.environ.get("SENSEI_NIGHTLY"):
        return  # the nightly's own `claude -p` invocation; not a real user session

    ap = argparse.ArgumentParser()
    ap.add_argument("--sensei-dir", default=os.path.expanduser("~/.claude/sensei"))
    ap.add_argument("--now", default=None, help="ISO local datetime override, for tests")
    args = ap.parse_args()

    try:
        now = dt.datetime.fromisoformat(args.now) if args.now else dt.datetime.now()
        run(args.sensei_dir, now)
    except Exception:
        return  # never disrupt session start over a hook bug

if __name__ == "__main__":
    main()
