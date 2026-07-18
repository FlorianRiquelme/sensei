#!/usr/bin/env python3
"""
sensei mine — scan ~/.claude/projects transcripts for friction: interrupts, tool-use
denials, and correction-language user messages. Deterministic, zero tokens, stdlib only.

Usage:
  python3 mine.py                # last 1 day
  python3 mine.py --days 7
  python3 mine.py --days 0       # all time
  python3 mine.py --out PATH     # default ~/.claude/sensei/events.json
"""
import json, os, re, glob, argparse, datetime as dt

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
MAX_PER_SESSION = 15
MAX_TOTAL = 400

# --- Correction lexicon -------------------------------------------------------
# Push-back words that flag a user message as a `correction`. Ships English + German.
# THIS IS THE ONE PLACE TO EDIT FOR YOUR LANGUAGE: add your language's negations and
# "no, do X instead" phrases as alternatives below. It only affects `correction` recall
# — `interrupt` and `denial` detection are language-independent (they match Claude Code's
# own English status strings), so sensei still works with an unedited lexicon. Over-capture
# is fine; the analyzer filters semantically (ADR-0004).
# ------------------------------------------------------------------------------
CORRECTION_RE = re.compile(
    r"\b(no+pe?|don'?t|stop|wrong|not (what|like) (i|that)|actually|instead|"
    r"i said|i meant|why did you|you should have|never|always use|"
    r"nein|nicht so|falsch|doch nicht)\b",
    re.IGNORECASE,
)

def parse_ts(s):
    if not s: return None
    try: return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception: return None

def as_blocks(content):
    return content if isinstance(content, list) else []

def block_text(content):
    """Flatten a string-or-block-array content field to plain text (text blocks only)."""
    if isinstance(content, str):
        return content
    parts = []
    for b in as_blocks(content):
        if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
            parts.append(b["text"])
    return "\n".join(parts)

def mine_session(fp, project, session, cutoff):
    events = []
    in_window = cutoff is None
    last_assistant_text = ""
    tool_uses = {}  # tool_use_id -> (name, input_str)

    try:
        lines = open(fp, errors="ignore").readlines()
    except OSError:
        return events, False

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("isSidechain") or r.get("isMeta"):
            continue

        ts = r.get("timestamp")
        rdt = parse_ts(ts)
        if cutoff and rdt and rdt >= cutoff:
            in_window = True

        rtype = r.get("type")
        msg = r.get("message", {}) or {}
        content = msg.get("content")

        if rtype == "assistant":
            for b in as_blocks(content):
                if not isinstance(b, dict): continue
                if b.get("type") == "text" and b.get("text"):
                    last_assistant_text = b["text"]
                elif b.get("type") == "tool_use":
                    tool_uses[b.get("id")] = (b.get("name", "?"), json.dumps(b.get("input", {}))[:200])
            continue

        if rtype != "user":
            continue
        if cutoff and (not rdt or rdt < cutoff):
            continue
        if len(events) >= MAX_PER_SESSION:
            continue

        # denial: tool_result whose content says the user rejected the tool use
        denied = False
        for b in as_blocks(content):
            if not isinstance(b, dict) or b.get("type") != "tool_result":
                continue
            result_text = block_text(b.get("content"))
            low = result_text.lower()
            if "doesn't want to proceed" in low or "user rejected" in low:
                tname, tinput = tool_uses.get(b.get("tool_use_id"), ("?", ""))
                events.append({
                    "ts": ts, "project": project, "session": session, "type": "denial",
                    "user_text": "", "assistant_context": last_assistant_text[:500],
                    "tool": tname, "tool_input": tinput,
                })
                denied = True
        if denied:
            continue

        # plain user text: interrupt or correction
        user_text = block_text(content)
        stripped = user_text.strip()
        if not stripped or stripped.startswith("<"):
            continue

        if stripped.startswith("[Request interrupted by user"):
            events.append({
                "ts": ts, "project": project, "session": session, "type": "interrupt",
                "user_text": stripped[:1000], "assistant_context": last_assistant_text[:500],
            })
            continue

        if len(stripped) > 2000:
            continue
        if CORRECTION_RE.search(user_text):
            events.append({
                "ts": ts, "project": project, "session": session, "type": "correction",
                "user_text": stripped[:1000], "assistant_context": last_assistant_text[:500],
            })

    return events, in_window

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1, help="window in days; 0 = all time")
    ap.add_argument("--out", default=os.path.expanduser("~/.claude/sensei/events.json"))
    ap.add_argument("--projects-dir", default=PROJECTS_DIR, help="dir to scan (default ~/.claude/projects)")
    args = ap.parse_args()

    cutoff = None
    if args.days > 0:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)

    # main sessions only: <project>/<uuid>.jsonl — this glob already excludes
    # anything nested under <project>/<uuid>/subagents/*.jsonl
    files = sorted(glob.glob(os.path.join(args.projects_dir, "*", "*.jsonl")))

    all_events = []
    sessions_scanned = 0
    for fp in files:
        project = os.path.basename(os.path.dirname(fp))
        session = os.path.splitext(os.path.basename(fp))[0]
        events, in_window = mine_session(fp, project, session, cutoff)
        if in_window:
            sessions_scanned += 1
            all_events.extend(events)

    all_events.sort(key=lambda e: e["ts"] or "", reverse=True)
    all_events = all_events[:MAX_TOTAL]

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "days": args.days,
        "sessions_scanned": sessions_scanned,
        "events": all_events,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"sensei-mine: scanned {sessions_scanned} sessions, {len(all_events)} events -> {args.out}")

if __name__ == "__main__":
    main()
