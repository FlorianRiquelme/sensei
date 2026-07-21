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
import json, os, re, glob, argparse, fnmatch, math, datetime as dt

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

# --- Effectiveness ledger (ADR-0016; PD4/PD5/D5) --------------------------------
# A "trigger" (carried on an accepted decisions.jsonl row) anchors a before/after
# comparison: friction in the SLICE_DAYS window before acceptance vs. the same-length
# window right now, once GRACE_DAYS have passed. Never a bare "working" on thin data
# (R12) — MIN_OPPORTUNITIES/MIN_BASELINE gate that; MAX_LEDGER_LOOKBACK_DAYS bounds
# how far back the walk needs to read for even the oldest anchor's baseline slice.
GRACE_DAYS = 14
SLICE_DAYS = 14
MIN_OPPORTUNITIES = 3
MIN_BASELINE = 2
WORKING_DROP = 0.5
MAX_LEDGER_LOOKBACK_DAYS = 60

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

def match_clause(clause, *, tool_name, tool_input, user_text):
    """One AND-clause of a trigger: {"kind": "tool"|"keyword"|"glob", "value": ...}.
    Malformed/unknown clauses fail closed (False), never raise."""
    if not isinstance(clause, dict):
        return False
    kind = clause.get("kind")
    value = clause.get("value")
    if not kind or not value:
        return False
    try:
        if kind == "tool":
            return tool_name == value
        if kind == "glob":
            if not tool_input:
                return False
            for tok in re.split(r"[\s'\"]+", tool_input):
                if tok and fnmatch.fnmatch(tok, value):
                    return True
            return False
        if kind == "keyword":
            haystack = f"{tool_input or ''}\n{user_text or ''}".lower()
            return value.lower() in haystack
    except Exception:
        return False
    return False

def is_opportunity(trigger, *, tool_name, tool_input, user_text):
    """A trigger (AND-list of clauses) matches this record. PD3 surface routing: a
    compound trigger (any tool/glob clause) tests its keyword clauses against
    tool_input only; a pure-keyword trigger tests against user_text only — assistant
    text is never a valid surface. Empty/malformed trigger never matches."""
    if not trigger:
        return False
    is_compound = any(isinstance(c, dict) and c.get("kind") in ("tool", "glob") for c in trigger)
    eff_tool_input = tool_input if is_compound else ""
    eff_user_text = "" if is_compound else user_text
    for clause in trigger:
        if not match_clause(clause, tool_name=tool_name, tool_input=eff_tool_input, user_text=eff_user_text):
            return False
    return True

def anchor_slice(rdt, anchor):
    """Which of an anchor's two slices (if any) a record's timestamp falls into."""
    if rdt is None:
        return None
    ps, pe = anchor["pre_accept_slice"]
    if ps <= rdt <= pe:
        return "pre_accept"
    cs, ce = anchor["current_slice"]
    if cs <= rdt <= ce:
        return "current"
    return None

def load_ledger_anchors(decisions_path, *, now):
    """Read decisions.jsonl and derive one anchor per key: the earliest accepted,
    triggered, non-hook-tier decision under that key (PD6). Returns (anchors,
    lookback_days) where lookback_days is the bounded read-back window covering every
    anchor's pre-accept slice, floored at REPEAT_WINDOW_DAYS."""
    anchors_by_key = {}
    try:
        with open(decisions_path, errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("verdict") != "accepted":
            continue
        trigger = d.get("trigger")
        if not trigger:
            continue
        if d.get("tier") == "hook":
            continue
        key = d.get("key")
        if not key:
            continue
        ds = d.get("date")
        try:
            accept_date = dt.datetime.strptime(ds, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue
        existing = anchors_by_key.get(key)
        if existing is None or accept_date < existing["accept_date"]:
            anchors_by_key[key] = {"key": key, "trigger": trigger, "accept_date": accept_date, "baseline": d.get("baseline")}

    anchors = []
    max_lookback_needed = 0
    for key, a in anchors_by_key.items():
        accept_date = a["accept_date"]
        pre_start = accept_date - dt.timedelta(days=SLICE_DAYS)
        anchors.append({
            "key": key,
            "trigger": a["trigger"],
            "accept_date": accept_date,
            "baseline": a["baseline"],
            "pre_accept_slice": (pre_start, accept_date),
            "current_slice": (now - dt.timedelta(days=SLICE_DAYS), now),
            "days_since_accept": (now - accept_date).days,
        })
        # round up: pre_start is at midnight while `now` carries a time-of-day, so an
        # integer-day floor would leave ledger_cutoff a few hours short of the slice start
        # and spuriously age it out. ceil guarantees the walk reaches the whole slice.
        needed = math.ceil((now - pre_start).total_seconds() / 86400)
        if needed > max_lookback_needed:
            max_lookback_needed = needed

    if anchors:
        lookback_days = max(min(MAX_LEDGER_LOOKBACK_DAYS, max_lookback_needed), REPEAT_WINDOW_DAYS)
    else:
        lookback_days = REPEAT_WINDOW_DAYS

    return anchors, lookback_days

def load_untriggered_keys(decisions_path):
    """Accepted, non-hook decision keys that carry NO trigger and have no triggered
    sibling under the same key. These render as `not_measurable_yet` (R11/AE4) — the one
    honest thing the ledger can say about a rule it cannot measure. Keys with any triggered
    accepted decision are excluded (they anchor and are measured instead, PD6)."""
    triggered, untriggered = set(), set()
    try:
        with open(decisions_path, errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("verdict") != "accepted" or d.get("tier") == "hook":
            continue
        key = d.get("key")
        if not key:
            continue
        (triggered if d.get("trigger") else untriggered).add(key)
    return sorted(untriggered - triggered)

def mine_session(fp, project, session, friction_cutoff, repeat_cutoff, anchors=None, ledger_cutoff=None):
    """Read one transcript once. Returns (events, in_friction_window, in_repeat_window,
    repeat_phrases, earliest_ts) — repeat_phrases is the set of this session's normalized
    candidate phrases within the repeat window; non-ubiquity is computed across sessions
    in main(). `anchors` (optional, mutated in place) are effectiveness-ledger anchors
    (ADR-0016) accumulating opportunity/friction counts per slice as this same walk reads
    each record — no second pass over the transcript."""
    events = []
    repeat_phrases = set()
    in_friction_window = friction_cutoff is None
    in_repeat_window = repeat_cutoff is None
    last_assistant_text = ""
    tool_uses = {}  # tool_use_id -> (name, input_str, {anchor_idx: slice_name})
    pending_matched = {}  # compound-anchor idx -> the tool_use's slice, awaiting the human's next reply (PD3)
    pending_interrupt = None  # last-emitted interrupt event awaiting a followup_text (KTD-3)
    correction_n = 0
    interrupt_n = 0
    anchors = anchors or []
    earliest_ts = None

    try:
        with open(fp, errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return events, in_friction_window, in_repeat_window, repeat_phrases, earliest_ts

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
        if rdt is not None and (earliest_ts is None or rdt < earliest_ts):
            earliest_ts = rdt
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
                    name = b.get("name", "?")
                    input_str = json.dumps(b.get("input", {}))[:200]
                    matched = {}  # anchor idx -> this tool_use's slice; friction is credited there
                    for idx, anchor in enumerate(anchors):
                        if not anchor.get("is_compound"):
                            continue
                        if not is_opportunity(anchor["trigger"], tool_name=name, tool_input=input_str, user_text=""):
                            continue
                        sl = anchor_slice(rdt, anchor)
                        if sl is None:
                            continue  # only a tool_use inside a slice is an opportunity — keeps friction ⊆ opportunities (PD3)
                        if sl == "current":
                            anchor["current_opportunities"] += 1
                        matched[idx] = sl
                    tool_uses[b.get("id")] = (name, input_str, matched)
                    pending_matched.update(matched)
            continue

        if rtype != "user":
            continue

        friction_ok = friction_cutoff is None or (rdt and rdt >= friction_cutoff)
        repeat_ok = repeat_cutoff is None or (rdt and rdt >= repeat_cutoff)
        # ledger_ok widens this single walk back over each anchor's pre-accept slice (up to
        # MAX_LEDGER_LOOKBACK_DAYS) so its baseline is counted with the same instrument as the
        # current slice. Event/repeat emission below stays gated on friction_ok/repeat_ok — a
        # ledger-only record contributes to anchor counts but is never emitted as an event.
        # Without this the baseline truncates at the 30-day repeat window (ADR-0016/D3).
        ledger_ok = ledger_cutoff is None or (rdt and rdt >= ledger_cutoff)
        if not friction_ok and not repeat_ok and not ledger_ok:
            continue

        # denial: tool_result whose content says the user rejected the tool use
        denied = False
        for b in as_blocks(content):
            if not isinstance(b, dict) or b.get("type") != "tool_result":
                continue
            result_text = block_text(b.get("content"))
            low = result_text.lower()
            if "doesn't want to proceed" in low or "user rejected" in low:
                tname, tinput, matched = tool_uses.get(b.get("tool_use_id"), ("?", "", {}))
                if friction_ok and len(events) < MAX_PER_SESSION:
                    events.append({
                        "ts": ts, "project": project, "session": session, "type": "denial",
                        "user_text": "", "assistant_context": last_assistant_text[:500],
                        "tool": tname, "tool_input": tinput,
                    })
                for idx, slice_name in matched.items():
                    anchor = anchors[idx]
                    if slice_name == "current":
                        anchor["current_friction"] += 1
                    elif slice_name == "pre_accept":
                        anchor["pre_accept_friction"] += 1
                # already credited via the tool_use_id link above — don't let a
                # follow-up correction ("no, use X instead") double-count it below.
                for idx in matched:
                    pending_matched.pop(idx, None)
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
        # ledger friction excludes slash commands: a custom command whose text happens to
        # hit the correction lexicon ("/use-ddev-instead") is structural, not real friction.
        # Scoped to the ledger only — the `correction` event stream is left unchanged.
        is_ledger_friction = (is_interrupt or is_correction) and not is_slash_command

        # ledger: a compound trigger's opportunity is a tool_use block (PD3), which the
        # transcript never links directly to a later correction/interrupt (unlike a
        # denial, tied via tool_use_id) — so the human's next reply after a matching
        # tool call is the deterministic, structural proxy for whether it caused
        # friction. Consumed once per reply so a later, unrelated correction can't be
        # misattributed to a stale match.
        if pending_matched:
            if is_ledger_friction:
                for idx, slice_name in pending_matched.items():
                    anchor = anchors[idx]
                    if slice_name == "current":
                        anchor["current_friction"] += 1
                    elif slice_name == "pre_accept":
                        anchor["pre_accept_friction"] += 1
            pending_matched = {}

        # ledger: pure-keyword triggers (no tool/glob clause) are tested against user
        # text only (PD3) — opportunity here, friction if this same record is already
        # classified as an interrupt or correction below.
        for anchor in anchors:
            if anchor.get("is_compound"):
                continue
            if not is_opportunity(anchor["trigger"], tool_name=None, tool_input="", user_text=stripped):
                continue
            slice_name = anchor_slice(rdt, anchor)
            if slice_name == "current":
                anchor["current_opportunities"] += 1
                if is_ledger_friction:
                    anchor["current_friction"] += 1
            elif slice_name == "pre_accept":
                if is_ledger_friction:
                    anchor["pre_accept_friction"] += 1

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

    return events, in_friction_window, in_repeat_window, repeat_phrases, earliest_ts

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14, help="friction window in days; 0 = all time")
    ap.add_argument("--out", default=os.path.expanduser("~/.claude/sensei/events.json"))
    ap.add_argument("--projects-dir", default=PROJECTS_DIR, help="dir to scan (default ~/.claude/projects)")
    ap.add_argument("--decisions", default=None, help="path to decisions.jsonl (default <dirname of --out>/decisions.jsonl)")
    args = ap.parse_args()
    if args.decisions is None:
        args.decisions = os.path.join(os.path.dirname(args.out), "decisions.jsonl")

    now = dt.datetime.now(dt.timezone.utc)
    friction_cutoff = None
    repeat_cutoff = None
    if args.days > 0:
        friction_cutoff = now - dt.timedelta(days=args.days)
        repeat_cutoff = now - dt.timedelta(days=REPEAT_WINDOW_DAYS)

    # effectiveness ledger (ADR-0016): anchors are derived once up front, then
    # accumulated in the same per-file walk below — no second pass over transcripts.
    # ledger_cutoff widens that walk back over the oldest anchor's pre-accept slice
    # (bounded by MAX_LEDGER_LOOKBACK_DAYS, floored at the repeat window). None under
    # --days 0 (all-time), matching the friction/repeat cutoffs.
    anchors, lookback_days = load_ledger_anchors(args.decisions, now=now)
    ledger_cutoff = now - dt.timedelta(days=lookback_days) if args.days > 0 else None
    for a in anchors:
        a["is_compound"] = any(isinstance(c, dict) and c.get("kind") in ("tool", "glob") for c in a["trigger"])
        a["pre_accept_friction"] = 0
        a["current_friction"] = 0
        a["current_opportunities"] = 0

    # main sessions only: <project>/<uuid>.jsonl — this glob already excludes
    # anything nested under <project>/<uuid>/subagents/*.jsonl
    files = sorted(glob.glob(os.path.join(args.projects_dir, "*", "*.jsonl")))

    all_events = []
    sessions_scanned = 0
    repeat_sessions_total = 0
    phrase_sessions = {}  # normalized phrase -> set of (project, session)
    earliest_ts_overall = None

    for fp in files:
        project = os.path.basename(os.path.dirname(fp))
        session = os.path.splitext(os.path.basename(fp))[0]
        events, in_friction, in_repeat, phrases, earliest_ts = mine_session(
            fp, project, session, friction_cutoff, repeat_cutoff, anchors, ledger_cutoff=ledger_cutoff
        )
        if earliest_ts is not None and (earliest_ts_overall is None or earliest_ts < earliest_ts_overall):
            earliest_ts_overall = earliest_ts
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

    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    out = {
        "generated_at": generated_at,
        "days": args.days,
        "sessions_scanned": sessions_scanned,
        "events": all_events,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)

    # Effectiveness ledger (ADR-0016): one row per anchor, recomputed from scratch each
    # run (no cross-run accumulation) — written even with zero anchors so /sensei status
    # can distinguish "ledger empty" from "ledger missing".
    # The aged-out fallback (PD4 step 3) keys on how far back the walk actually reached:
    # the later of the ledger cutoff and the earliest record on disk. A pre-accept slice
    # starting before that floor could not be measured with the same instrument, so it
    # falls back to the stored baseline rather than reporting a truncated count as fact.
    read_floor = earliest_ts_overall
    if ledger_cutoff is not None:
        read_floor = ledger_cutoff if read_floor is None else max(ledger_cutoff, read_floor)

    ledger_rows = []
    for a in anchors:
        fallback = False
        baseline_seed = None
        if a["days_since_accept"] < GRACE_DAYS:
            standing = "not_measurable_yet"
        elif read_floor is not None and a["pre_accept_slice"][0] < read_floor:
            standing = "inconclusive"
            fallback = True
            baseline_seed = a["baseline"]
        elif a["current_opportunities"] < MIN_OPPORTUNITIES:
            standing = "inconclusive"
        elif a["pre_accept_friction"] < MIN_BASELINE:
            standing = "inconclusive"
        elif a["current_friction"] <= math.floor(WORKING_DROP * a["pre_accept_friction"]):
            standing = "working"
        else:
            standing = "not_working"
        ledger_rows.append({
            "key": a["key"], "standing": standing, "trigger_present": True,
            "pre_accept_friction": a["pre_accept_friction"],
            "current_friction": a["current_friction"],
            "current_opportunities": a["current_opportunities"],
            "days_since_accept": a["days_since_accept"],
            "fallback": fallback, "baseline_seed": baseline_seed,
        })
    # Accepted rules with no inferable trigger can't be measured, but they still get an
    # honest line (R11/AE4): rendered `not_measurable_yet`, distinct from the measured rows.
    anchor_keys = {a["key"] for a in anchors}
    for key in load_untriggered_keys(args.decisions):
        if key in anchor_keys:
            continue
        ledger_rows.append({
            "key": key, "standing": "not_measurable_yet", "trigger_present": False,
            "pre_accept_friction": 0, "current_friction": 0, "current_opportunities": 0,
            "days_since_accept": None, "fallback": False, "baseline_seed": None,
        })
    ledger_out = {"generated_at": generated_at, "rows": ledger_rows}
    with open(os.path.join(os.path.dirname(args.out), "ledger.json"), "w") as f:
        json.dump(ledger_out, f, indent=2)

    # Digest: a per-day, human-facing artifact whose mere presence proves the
    # nightly patrol ran (ADR-0014). Written here, not by the LLM stage, so it
    # survives a broken chain. `date` is local — never derived from the UTC
    # `generated_at` above — to match the Nudge's local-time failure check.
    by_type = {}
    by_project = {}
    for e in all_events:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        # friction events carry a single `project`; `repeat` events span several and
        # carry `projects` (ADR-0011) — count the repeat under each of its projects.
        projects = e.get("projects") or [e.get("project")]
        for p in projects:
            if p:
                by_project[p] = by_project.get(p, 0) + 1
    local_date = dt.datetime.now().date().isoformat()
    digest = {
        "date": local_date,
        "generated_at": generated_at,
        "sessions_scanned": sessions_scanned,
        "events_total": len(all_events),
        "by_type": by_type,
        "by_project": by_project,
    }
    digest_dir = os.path.join(os.path.dirname(args.out), "digests")
    os.makedirs(digest_dir, exist_ok=True)
    with open(os.path.join(digest_dir, f"{local_date}.json"), "w") as f:
        json.dump(digest, f, indent=2)

    print(f"sensei-mine: scanned {sessions_scanned} sessions, {len(all_events)} events -> {args.out}")

if __name__ == "__main__":
    main()
