#!/usr/bin/env python3
"""
sensei mine — scan ~/.claude/projects transcripts for friction (interrupts, tool-use
denials, correction-language user messages) and repeats (re-supplied directives with no
friction). Deterministic, zero tokens, stdlib only.

Usage:
  python3 mine.py                # last 14 days (friction); repeats always look back 30 days
  python3 mine.py --days 7
  python3 mine.py --days 0       # all time (disables both the friction and repeat cutoffs)
  python3 mine.py --out PATH     # default ~/.claude/sensei/events.json
"""
import json, os, re, glob, argparse, datetime as dt

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
MAX_PER_SESSION = 15
MAX_TOTAL = 400

# ADR-0010: the friction window and the repeat window are two cutoffs applied over one
# stateless read of each transcript (no cross-run ledger, no persisted state). Widening
# either window only widens what the deterministic stage *considers* — MAX_TOTAL and
# MAX_PER_SESSION still bound what reaches the LLM.
REPEAT_WINDOW_DAYS = 30

# --- Repeat thinning (ADR-0011 — a bounded, structural exception to ADR-0004) ---------
# Repeats are ubiquitous (unlike friction, which is rare), so the miner thins them
# structurally before emitting: a small glue blocklist, a length floor, and a
# non-ubiquity test (recurs across >= N sessions but is NOT present in nearly all of
# them). No directive allowlist, ever — friction detection stays greedy.
REPEAT_MIN_SESSIONS = 3
REPEAT_UBIQUITY_CEILING = 0.8
REPEAT_LENGTH_FLOOR = 12
REPEAT_TOP_K = 10
REPEAT_GLUE_BLOCKLIST = {
    "yes", "yep", "yeah", "yup", "ok", "okay", "k", "kk", "sure", "sure thing",
    "next", "continue", "go ahead", "go on", "sounds good", "looks good",
    "great", "perfect", "nice", "cool", "thanks", "thank you", "thx", "ty",
    "got it", "understood", "ack", "fine", "alright", "good", "done", "lgtm",
    "nein", "ja", "gut", "weiter", "passt", "genau", "danke",
}

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

def normalize_phrase(text):
    t = text.strip().lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def mine_session(fp, project, session, friction_cutoff, repeat_cutoff):
    """Read one transcript once. Returns (events, in_friction_window, in_repeat_window,
    repeat_phrases) — repeat_phrases is the set of this session's normalized candidate
    phrases within the repeat window; non-ubiquity is computed across sessions in main()."""
    events = []
    repeat_phrases = set()
    in_friction_window = friction_cutoff is None
    in_repeat_window = repeat_cutoff is None
    last_assistant_text = ""
    tool_uses = {}  # tool_use_id -> (name, input_str)
    pending_interrupt = None  # last-emitted interrupt event awaiting a followup_text (KTD-3)
    correction_n = 0
    interrupt_n = 0

    try:
        lines = open(fp, errors="ignore").readlines()
    except OSError:
        return events, in_friction_window, in_repeat_window, repeat_phrases

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
        if friction_cutoff and rdt and rdt >= friction_cutoff:
            in_friction_window = True
        if repeat_cutoff and rdt and rdt >= repeat_cutoff:
            in_repeat_window = True

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

        friction_ok = friction_cutoff is None or (rdt and rdt >= friction_cutoff)
        repeat_ok = repeat_cutoff is None or (rdt and rdt >= repeat_cutoff)
        if not friction_ok and not repeat_ok:
            continue

        # denial: tool_result whose content says the user rejected the tool use
        denied = False
        for b in as_blocks(content):
            if not isinstance(b, dict) or b.get("type") != "tool_result":
                continue
            result_text = block_text(b.get("content"))
            low = result_text.lower()
            if "doesn't want to proceed" in low or "user rejected" in low:
                if friction_ok and len(events) < MAX_PER_SESSION:
                    tname, tinput = tool_uses.get(b.get("tool_use_id"), ("?", ""))
                    events.append({
                        "ts": ts, "project": project, "session": session, "type": "denial",
                        "user_text": "", "assistant_context": last_assistant_text[:500],
                        "tool": tname, "tool_input": tinput,
                    })
                denied = True
        if denied:
            continue

        # plain user text: interrupt, correction, or repeat candidate
        user_text = block_text(content)
        stripped = user_text.strip()
        if not stripped or stripped.startswith("<"):
            continue

        is_slash_command = stripped.startswith("/")
        is_interrupt = stripped.startswith("[Request interrupted by user")
        is_correction = (not is_interrupt) and len(stripped) <= 2000 and bool(CORRECTION_RE.search(user_text))

        # backfill followup_text on the pending interrupt (KTD-3) — any qualifying plain
        # text closes it out; another interrupt or a slash command does not.
        if pending_interrupt is not None and not is_slash_command and not is_interrupt:
            pending_interrupt["followup_text"] = stripped[:1000]
            pending_interrupt = None

        if friction_ok and len(events) < MAX_PER_SESSION:
            if is_interrupt:
                interrupt_n += 1
                ev = {
                    "ts": ts, "project": project, "session": session, "type": "interrupt",
                    "user_text": stripped[:1000], "assistant_context": last_assistant_text[:500],
                    "nth_in_session": interrupt_n, "followup_text": "",
                }
                events.append(ev)
                pending_interrupt = ev
                continue
            if is_correction:
                correction_n += 1
                events.append({
                    "ts": ts, "project": project, "session": session, "type": "correction",
                    "user_text": stripped[:1000], "assistant_context": last_assistant_text[:500],
                    "nth_in_session": correction_n,
                })
                continue

        # repeat candidacy: plain directive text with no friction at all — excludes
        # interrupts, slash commands, and anything already flagged as a correction.
        if repeat_ok and not is_interrupt and not is_slash_command and not is_correction and len(stripped) <= 2000:
            norm = normalize_phrase(stripped)
            if len(norm) >= REPEAT_LENGTH_FLOOR and norm not in REPEAT_GLUE_BLOCKLIST:
                repeat_phrases.add(norm)

    return events, in_friction_window, in_repeat_window, repeat_phrases

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14, help="friction window in days; 0 = all time")
    ap.add_argument("--out", default=os.path.expanduser("~/.claude/sensei/events.json"))
    ap.add_argument("--projects-dir", default=PROJECTS_DIR, help="dir to scan (default ~/.claude/projects)")
    args = ap.parse_args()

    friction_cutoff = None
    repeat_cutoff = None
    if args.days > 0:
        now = dt.datetime.now(dt.timezone.utc)
        friction_cutoff = now - dt.timedelta(days=args.days)
        repeat_cutoff = now - dt.timedelta(days=REPEAT_WINDOW_DAYS)

    # main sessions only: <project>/<uuid>.jsonl — this glob already excludes
    # anything nested under <project>/<uuid>/subagents/*.jsonl
    files = sorted(glob.glob(os.path.join(args.projects_dir, "*", "*.jsonl")))

    all_events = []
    sessions_scanned = 0
    repeat_sessions_total = 0
    phrase_sessions = {}  # normalized phrase -> set of (project, session)

    for fp in files:
        project = os.path.basename(os.path.dirname(fp))
        session = os.path.splitext(os.path.basename(fp))[0]
        events, in_friction, in_repeat, phrases = mine_session(
            fp, project, session, friction_cutoff, repeat_cutoff
        )
        if in_friction or in_repeat:
            sessions_scanned += 1
        if in_friction:
            all_events.extend(events)
        if in_repeat:
            repeat_sessions_total += 1
            for phrase in phrases:
                phrase_sessions.setdefault(phrase, set()).add((project, session))

    # non-ubiquity test (ADR-0011): keep phrases that recur across >= N sessions but
    # are not present in nearly all of them; hard-capped top-K, like every other signal.
    if repeat_sessions_total > 0:
        candidates = []
        for phrase, sessions in phrase_sessions.items():
            count = len(sessions)
            if count >= REPEAT_MIN_SESSIONS and (count / repeat_sessions_total) < REPEAT_UBIQUITY_CEILING:
                candidates.append((phrase, count, sessions))
        candidates.sort(key=lambda c: c[1], reverse=True)
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        for phrase, count, sessions in candidates[:REPEAT_TOP_K]:
            all_events.append({
                "ts": now_iso, "type": "repeat", "user_text": phrase,
                "session_count": count, "projects": sorted({p for p, _ in sessions}),
            })

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
