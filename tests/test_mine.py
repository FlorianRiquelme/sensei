import importlib.util, json, os, subprocess, sys, tempfile, unittest, datetime as dt

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(REPO_ROOT, "tests", "fixtures", "projects")
MINE_PY = os.path.join(REPO_ROOT, "mine.py")

def run_mine(projects_dir, out_path, days=0, decisions_path=None):
    cmd = [sys.executable, MINE_PY, "--days", str(days), "--projects-dir", projects_dir, "--out", out_path]
    if decisions_path is not None:
        cmd += ["--decisions", decisions_path]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    with open(out_path) as f:
        return json.load(f)


def ledger_path_for(out_path):
    return os.path.join(os.path.dirname(out_path), "ledger.json")


def write_decisions(path, decisions):
    with open(path, "w") as f:
        for d in decisions:
            f.write(json.dumps(d) + "\n")

def digest_path_for(out_path):
    return os.path.join(os.path.dirname(out_path), "digests", f"{dt.datetime.now().date().isoformat()}.json")


class TestMineFixtures(unittest.TestCase):
    def test_fixtures_all_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(FIXTURES, out_path, days=0)

        self.assertEqual(data["sessions_scanned"], 2)
        events = data["events"]
        by_type = {}
        for e in events:
            by_type.setdefault(e["type"], []).append(e)

        self.assertEqual(len(by_type.get("correction", [])), 1)
        self.assertEqual(len(by_type.get("denial", [])), 1)
        self.assertEqual(len(by_type.get("interrupt", [])), 1)
        self.assertEqual(len(events), 3)

        corr = by_type["correction"][0]
        self.assertEqual(corr["project"], "project-a")
        self.assertEqual(corr["session"], "11111111-1111-1111-1111-111111111111")

        denial = by_type["denial"][0]
        self.assertEqual(denial["project"], "project-b")
        self.assertEqual(denial["tool"], "Bash")

        interrupt = by_type["interrupt"][0]
        self.assertEqual(interrupt["project"], "project-b")


def load_mine_module():
    spec = importlib.util.spec_from_file_location("mine_mod", MINE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_session(proj_dir, name, records):
    fp = os.path.join(proj_dir, name)
    with open(fp, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return fp


class TestMineDynamic(unittest.TestCase):
    def test_length_guard_skips_long_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            long_text = "never " * 500  # > 2000 chars, contains lexicon word
            record = {
                "type": "user", "timestamp": "2020-01-01T00:00:00Z",
                "message": {"role": "user", "content": long_text},
            }
            fp = os.path.join(proj_dir, "sess.jsonl")
            with open(fp, "w") as f:
                f.write(json.dumps(record) + "\n")

            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=0)

        self.assertEqual(len(data["events"]), 0)

    def test_time_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            now = dt.datetime.now(dt.timezone.utc)
            recent_ts = now.isoformat().replace("+00:00", "Z")
            old_ts = (now - dt.timedelta(days=5)).isoformat().replace("+00:00", "Z")
            records = [
                {"type": "user", "timestamp": recent_ts, "message": {"role": "user", "content": "No, actually use the other one."}},
                {"type": "user", "timestamp": old_ts, "message": {"role": "user", "content": "No, actually use the other one."}},
            ]
            fp = os.path.join(proj_dir, "sess.jsonl")
            with open(fp, "w") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")

            projects_dir = os.path.join(tmp, "projects")
            out_recent = os.path.join(tmp, "recent.json")
            out_all = os.path.join(tmp, "all.json")
            data_recent = run_mine(projects_dir, out_recent, days=1)
            data_all = run_mine(projects_dir, out_all, days=0)

        self.assertEqual(len(data_recent["events"]), 1)
        self.assertEqual(len(data_all["events"]), 2)

    # --- U1: interrupt followup_text + nth_in_session ---------------------------------

    def test_interrupt_followup_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            write_session(proj_dir, "sess.jsonl", [
                {"type": "user", "timestamp": "2020-01-01T00:00:00Z",
                 "message": {"role": "user", "content": "[Request interrupted by user for tool use]"}},
                {"type": "user", "timestamp": "2020-01-01T00:00:01Z",
                 "message": {"role": "user", "content": "actually use the helper function"}},
            ])
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=0)

        interrupts = [e for e in data["events"] if e["type"] == "interrupt"]
        self.assertEqual(len(interrupts), 1)
        self.assertEqual(interrupts[0]["followup_text"], "actually use the helper function")

    def test_interrupt_followup_skips_tool_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            write_session(proj_dir, "sess.jsonl", [
                {"type": "user", "timestamp": "2020-01-01T00:00:00Z",
                 "message": {"role": "user", "content": "[Request interrupted by user for tool use]"}},
                {"type": "user", "timestamp": "2020-01-01T00:00:01Z",
                 "message": {"role": "user", "content": [
                     {"type": "tool_result", "tool_use_id": "toolu_x", "content": "some result"},
                 ]}},
                {"type": "user", "timestamp": "2020-01-01T00:00:02Z",
                 "message": {"role": "user", "content": "use the other one instead"}},
            ])
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=0)

        interrupts = [e for e in data["events"] if e["type"] == "interrupt"]
        self.assertEqual(len(interrupts), 1)
        self.assertEqual(interrupts[0]["followup_text"], "use the other one instead")

    def test_interrupt_with_no_followup(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            write_session(proj_dir, "sess.jsonl", [
                {"type": "user", "timestamp": "2020-01-01T00:00:00Z",
                 "message": {"role": "user", "content": "[Request interrupted by user for tool use]"}},
            ])
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=0)

        interrupts = [e for e in data["events"] if e["type"] == "interrupt"]
        self.assertEqual(len(interrupts), 1)
        self.assertFalse(interrupts[0]["followup_text"])

    def test_two_corrections_get_ordinals(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            write_session(proj_dir, "sess.jsonl", [
                {"type": "user", "timestamp": "2020-01-01T00:00:00Z",
                 "message": {"role": "user", "content": "no, stop, that's wrong"}},
                {"type": "user", "timestamp": "2020-01-01T00:00:01Z",
                 "message": {"role": "user", "content": "actually never do that again"}},
            ])
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=0)

        corrections = sorted(
            (e for e in data["events"] if e["type"] == "correction"),
            key=lambda e: e["ts"],
        )
        self.assertEqual(len(corrections), 2)
        self.assertEqual([c["nth_in_session"] for c in corrections], [1, 2])

    # --- U2: widened friction window (ADR-0010) ---------------------------------------

    def test_days_14_window_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            now = dt.datetime.now(dt.timezone.utc)
            ts_10d = (now - dt.timedelta(days=10)).isoformat().replace("+00:00", "Z")
            ts_20d = (now - dt.timedelta(days=20)).isoformat().replace("+00:00", "Z")
            write_session(proj_dir, "sess.jsonl", [
                {"type": "user", "timestamp": ts_10d, "message": {"role": "user", "content": "no, stop, that's wrong"}},
                {"type": "user", "timestamp": ts_20d, "message": {"role": "user", "content": "no, stop, that's wrong"}},
            ])
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=14)

        self.assertEqual(len(data["events"]), 1)

    def test_max_per_session_caps_regardless_of_window(self):
        mine_mod = load_mine_module()
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            now = dt.datetime.now(dt.timezone.utc)
            records = []
            for i in range(20):
                ts = (now - dt.timedelta(hours=i)).isoformat().replace("+00:00", "Z")
                records.append({
                    "type": "user", "timestamp": ts,
                    "message": {"role": "user", "content": f"no, stop, that's wrong number {i}"},
                })
            write_session(proj_dir, "sess.jsonl", records)
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=14)

        self.assertLessEqual(len(data["events"]), mine_mod.MAX_PER_SESSION)

    # --- U3: `repeat` event type with structural thinning (ADR-0011) ------------------

    def test_repeat_emitted_for_phrase_across_three_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            # 3 of 5 sessions carry the phrase (60% < the 80% ubiquity ceiling) so it
            # qualifies as a repeat rather than reading as conversational ubiquity.
            for i in range(3):
                write_session(proj_dir, f"sess{i}.jsonl", [
                    {"type": "user", "timestamp": f"2020-01-0{i+1}T00:00:00Z",
                     "message": {"role": "user", "content": "run the tests before committing"}},
                ])
            for i in range(3, 5):
                write_session(proj_dir, f"sess{i}.jsonl", [
                    {"type": "user", "timestamp": f"2020-01-0{i+1}T00:00:00Z",
                     "message": {"role": "user", "content": "looks good, ship it"}},
                ])
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=0)

        repeats = [e for e in data["events"] if e["type"] == "repeat"]
        self.assertEqual(len(repeats), 1)
        self.assertEqual(repeats[0]["session_count"], 3)
        self.assertEqual(repeats[0]["user_text"], "run the tests before committing")

    def test_repeat_glue_token_not_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            for i in range(3):
                write_session(proj_dir, f"sess{i}.jsonl", [
                    {"type": "user", "timestamp": f"2020-01-0{i+1}T00:00:00Z",
                     "message": {"role": "user", "content": "continue"}},
                ])
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=0)

        self.assertEqual(len([e for e in data["events"] if e["type"] == "repeat"]), 0)

    def test_repeat_short_phrase_below_length_floor_not_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            for i in range(3):
                write_session(proj_dir, f"sess{i}.jsonl", [
                    {"type": "user", "timestamp": f"2020-01-0{i+1}T00:00:00Z",
                     "message": {"role": "user", "content": "np thx"}},
                ])
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=0)

        self.assertEqual(len([e for e in data["events"] if e["type"] == "repeat"]), 0)

    def test_repeat_ubiquitous_phrase_not_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            # 5 sessions, phrase present in all 5 (>= ubiquity ceiling) -> should NOT qualify
            for i in range(5):
                write_session(proj_dir, f"sess{i}.jsonl", [
                    {"type": "user", "timestamp": f"2020-01-0{i+1}T00:00:00Z",
                     "message": {"role": "user", "content": "please review this carefully"}},
                ])
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=0)

        self.assertEqual(len([e for e in data["events"] if e["type"] == "repeat"]), 0)

    def test_repeat_respects_top_k_cap(self):
        mine_mod = load_mine_module()

        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            n_phrases = mine_mod.REPEAT_TOP_K + 5
            n_sessions = mine_mod.REPEAT_MIN_SESSIONS + 1
            for s in range(n_sessions):
                records = [
                    {"type": "user", "timestamp": f"2020-01-{s+1:02d}T00:00:00Z",
                     "message": {"role": "user", "content": f"use the dedicated helper number {p} please"}}
                    for p in range(n_phrases)
                ]
                write_session(proj_dir, f"sess{s}.jsonl", records)
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=0)

        repeats = [e for e in data["events"] if e["type"] == "repeat"]
        self.assertLessEqual(len(repeats), mine_mod.REPEAT_TOP_K)


class TestMineDigest(unittest.TestCase):
    def test_digest_fields_and_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(FIXTURES, out_path, days=0)
            with open(digest_path_for(out_path)) as f:
                digest = json.load(f)

        for field in ("date", "generated_at", "sessions_scanned", "events_total", "by_type", "by_project"):
            self.assertIn(field, digest)

        self.assertEqual(digest["events_total"], len(data["events"]))
        self.assertEqual(digest["sessions_scanned"], data["sessions_scanned"])
        self.assertEqual(sum(digest["by_type"].values()), digest["events_total"])
        self.assertEqual(sum(digest["by_project"].values()), digest["events_total"])
        self.assertEqual(digest["by_type"].get("correction"), 1)
        self.assertEqual(digest["by_type"].get("denial"), 1)
        self.assertEqual(digest["by_type"].get("interrupt"), 1)
        self.assertEqual(digest["by_project"].get("project-a"), 1)
        self.assertEqual(digest["by_project"].get("project-b"), 2)
        self.assertEqual(digest["date"], dt.datetime.now().date().isoformat())

    def test_digest_local_date_not_derived_from_utc_generated_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "events.json")
            run_mine(FIXTURES, out_path, days=0)
            with open(digest_path_for(out_path)) as f:
                digest = json.load(f)

        self.assertEqual(digest["date"], dt.datetime.now().date().isoformat())
        self.assertNotEqual(digest["date"], digest["generated_at"])

    def test_digest_durable_across_same_day_reruns(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "events.json")
            run_mine(FIXTURES, out_path, days=0)
            run_mine(FIXTURES, out_path, days=0)
            with open(digest_path_for(out_path)) as f:
                digest = json.load(f)

        self.assertEqual(digest["events_total"], 3)

    def test_digest_zero_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects")
            os.makedirs(proj_dir)
            out_path = os.path.join(tmp, "events.json")
            run_mine(proj_dir, out_path, days=0)
            with open(digest_path_for(out_path)) as f:
                digest = json.load(f)

        self.assertEqual(digest["events_total"], 0)
        self.assertEqual(digest["by_type"], {})
        self.assertEqual(digest["by_project"], {})


# --- U2: trigger-matching primitives (PD1/PD3) -------------------------------------

class TestTriggerMatching(unittest.TestCase):
    def setUp(self):
        self.m = load_mine_module()

    def test_compound_trigger_matches_bash_with_keyword(self):
        trigger = [{"kind": "tool", "value": "Bash"}, {"kind": "keyword", "value": "artisan"}]
        self.assertTrue(self.m.is_opportunity(
            trigger, tool_name="Bash", tool_input="ddev artisan migrate", user_text=""))

    def test_compound_trigger_rejects_bash_without_keyword(self):
        trigger = [{"kind": "tool", "value": "Bash"}, {"kind": "keyword", "value": "artisan"}]
        self.assertFalse(self.m.is_opportunity(
            trigger, tool_name="Bash", tool_input="ddev composer install", user_text=""))

    def test_compound_trigger_rejects_keyword_on_other_tool(self):
        trigger = [{"kind": "tool", "value": "Bash"}, {"kind": "keyword", "value": "artisan"}]
        self.assertFalse(self.m.is_opportunity(
            trigger, tool_name="Read", tool_input="run artisan migrate", user_text=""))

    def test_tool_clause_is_exact_not_prefix(self):
        trigger = [{"kind": "tool", "value": "Bash"}]
        self.assertFalse(self.m.is_opportunity(
            trigger, tool_name="BashOutput", tool_input="", user_text=""))

    def test_glob_clause_matches_nested_path(self):
        trigger = [{"kind": "glob", "value": "app/**/*.php"}]
        self.assertTrue(self.m.is_opportunity(
            trigger, tool_name="Edit", tool_input='{"file_path": "app/Models/User.php"}', user_text=""))

    def test_glob_clause_rejects_other_path(self):
        trigger = [{"kind": "glob", "value": "app/**/*.php"}]
        self.assertFalse(self.m.is_opportunity(
            trigger, tool_name="Edit", tool_input='{"file_path": "resources/x.php"}', user_text=""))

    def test_pure_keyword_trigger_matches_user_text(self):
        trigger = [{"kind": "keyword", "value": "ddev"}]
        self.assertTrue(self.m.is_opportunity(
            trigger, tool_name=None, tool_input="", user_text="please use ddev for this"))

    def test_pure_keyword_trigger_ignores_tool_input(self):
        # "ddev" only appears on the tool_input surface; a pure-keyword trigger must
        # never read that surface (assistant/tool text is not a valid opportunity
        # surface for a pure-keyword trigger).
        trigger = [{"kind": "keyword", "value": "ddev"}]
        self.assertFalse(self.m.is_opportunity(
            trigger, tool_name="Bash", tool_input="ddev artisan migrate", user_text="looks fine"))

    def test_empty_trigger_never_matches(self):
        self.assertFalse(self.m.is_opportunity(
            [], tool_name="Bash", tool_input="ddev artisan migrate", user_text="ddev"))

    def test_malformed_clause_no_crash(self):
        trigger = [{"value": "artisan"}]  # missing "kind"
        self.assertFalse(self.m.is_opportunity(
            trigger, tool_name="Bash", tool_input="ddev artisan migrate", user_text=""))


# --- U3: decisions loader / anchor + slice derivation (PD4/PD6) --------------------

class TestLedgerAnchors(unittest.TestCase):
    def setUp(self):
        self.m = load_mine_module()
        self.now = dt.datetime.now(dt.timezone.utc)

    def _date(self, days_ago):
        return (self.now - dt.timedelta(days=days_ago)).strftime("%Y-%m-%d")

    def test_single_anchor_slice_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(path, [{
                "date": self._date(40), "title": "t", "key": "k1", "verdict": "accepted",
                "target": "x", "reason": "r", "reason_kind": "friction", "tier": "user",
                "baseline": 3, "trigger": [{"kind": "keyword", "value": "artisan"}],
            }])
            anchors, lookback = self.m.load_ledger_anchors(path, now=self.now)

        self.assertEqual(len(anchors), 1)
        a = anchors[0]
        expected_accept = dt.datetime.strptime(self._date(40), "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        self.assertEqual(a["accept_date"], expected_accept)
        self.assertEqual(a["pre_accept_slice"], (expected_accept - dt.timedelta(days=self.m.SLICE_DAYS), expected_accept))
        self.assertGreaterEqual(a["days_since_accept"], 39)

    def test_earliest_decision_wins_for_same_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(path, [
                {"date": self._date(20), "title": "t", "key": "k1", "verdict": "accepted",
                 "target": "x", "reason": "r", "reason_kind": "friction", "tier": "user",
                 "baseline": 3, "trigger": [{"kind": "keyword", "value": "artisan"}]},
                {"date": self._date(40), "title": "t", "key": "k1", "verdict": "accepted",
                 "target": "x", "reason": "r", "reason_kind": "friction", "tier": "user",
                 "baseline": 3, "trigger": [{"kind": "keyword", "value": "artisan"}]},
            ])
            anchors, _ = self.m.load_ledger_anchors(path, now=self.now)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0]["accept_date"].strftime("%Y-%m-%d"), self._date(40))

    def test_hook_tier_or_missing_trigger_never_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(path, [
                {"date": self._date(40), "key": "hook-key", "verdict": "accepted",
                 "tier": "hook", "trigger": [{"kind": "keyword", "value": "x"}]},
                {"date": self._date(40), "key": "no-trigger-key", "verdict": "accepted", "tier": "user"},
            ])
            anchors, _ = self.m.load_ledger_anchors(path, now=self.now)

        self.assertEqual(anchors, [])

    def test_rejected_variants_never_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(path, [
                {"date": self._date(40), "key": "k1", "verdict": "rejected", "tier": "user",
                 "trigger": [{"kind": "keyword", "value": "x"}]},
                {"date": self._date(40), "key": "k2", "verdict": "reject-retry-narrower", "tier": "user",
                 "trigger": [{"kind": "keyword", "value": "x"}]},
                {"date": self._date(40), "key": "k3", "verdict": "reject-not-wanted", "tier": "user",
                 "trigger": [{"kind": "keyword", "value": "x"}]},
            ])
            anchors, _ = self.m.load_ledger_anchors(path, now=self.now)

        self.assertEqual(anchors, [])

    def test_lookback_bounded_and_floored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(path, [{
                "date": self._date(300), "key": "old-key", "verdict": "accepted", "tier": "user",
                "baseline": 1, "trigger": [{"kind": "keyword", "value": "x"}],
            }])
            anchors, lookback = self.m.load_ledger_anchors(path, now=self.now)

        self.assertEqual(lookback, self.m.MAX_LEDGER_LOOKBACK_DAYS)
        self.assertGreaterEqual(lookback, self.m.REPEAT_WINDOW_DAYS)

    def test_missing_decisions_file_no_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "decisions.jsonl")  # never written
            anchors, lookback = self.m.load_ledger_anchors(path, now=self.now)

        self.assertEqual(anchors, [])
        self.assertEqual(lookback, self.m.REPEAT_WINDOW_DAYS)


# --- U4: single-walk ledger accumulation + ledger.json emission (PD2/PD4) ----------

def iso(d):
    return d.isoformat().replace("+00:00", "Z")


class TestLedgerIntegration(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime.now(dt.timezone.utc)

    def _decision(self, key, days_ago_accepted, baseline=3):
        return {
            "date": (self.now - dt.timedelta(days=days_ago_accepted)).strftime("%Y-%m-%d"),
            "title": "t", "key": key, "verdict": "accepted", "target": "x",
            "reason": "r", "reason_kind": "friction", "tier": "user",
            "baseline": baseline, "trigger": [{"kind": "keyword", "value": "artisan"}],
        }

    def _row(self, ledger, key):
        rows = [r for r in ledger["rows"] if r["key"] == key]
        self.assertEqual(len(rows), 1, f"expected exactly one row for {key}")
        return rows[0]

    def _filler(self, days_ago=60):
        # a harmless record older than any anchor's pre_accept_slice start, so the
        # earliest-record-read fallback (AE5) isn't spuriously triggered by tests that
        # aren't exercising it.
        return {"type": "user", "timestamp": iso(self.now - dt.timedelta(days=days_ago)),
                "message": {"role": "user", "content": "hello"}}

    def test_ae1_working(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            records = [self._filler()]
            for d in (45, 44, 43, 42, 41):
                records.append({"type": "user", "timestamp": iso(self.now - dt.timedelta(days=d)),
                                 "message": {"role": "user", "content": "no, don't run artisan like that"}})
            for d in (5, 4, 3):
                records.append({"type": "user", "timestamp": iso(self.now - dt.timedelta(days=d)),
                                 "message": {"role": "user", "content": "please run artisan migrate"}})
            write_session(proj_dir, "sess.jsonl", records)

            decisions_path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(decisions_path, [self._decision("ae1", 40)])

            out_path = os.path.join(tmp, "events.json")
            run_mine(os.path.join(tmp, "projects"), out_path, days=0, decisions_path=decisions_path)
            with open(ledger_path_for(out_path)) as f:
                ledger = json.load(f)

        row = self._row(ledger, "ae1")
        self.assertEqual(row["pre_accept_friction"], 5)
        self.assertEqual(row["current_friction"], 0)
        self.assertEqual(row["current_opportunities"], 3)
        self.assertEqual(row["standing"], "working")
        self.assertFalse(row["fallback"])

    def test_ae1_working_compound_trigger_correction_friction(self):
        # AE1's own narrative is a tool+keyword trigger ("ddev-prefix") measured via
        # *corrections*, not denials. A compound opportunity is a tool_use block (PD3),
        # which the transcript never links directly to a later correction — the human's
        # next reply after the matching tool call is the deterministic proxy (mirrors
        # how a denial is tied back via tool_use_id).
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            records = [self._filler()]
            for d in (50, 49, 48, 47, 46):
                records.append({"type": "assistant", "timestamp": iso(self.now - dt.timedelta(days=d)),
                                 "message": {"role": "assistant", "content": [
                                     {"type": "tool_use", "id": f"toolu_pre_{d}", "name": "Bash",
                                      "input": {"command": "php artisan migrate"}},
                                 ]}})
                records.append({"type": "user", "timestamp": iso(self.now - dt.timedelta(days=d)),
                                 "message": {"role": "user", "content": "no, use ddev artisan instead"}})
            for d in (5, 4, 3):
                records.append({"type": "assistant", "timestamp": iso(self.now - dt.timedelta(days=d)),
                                 "message": {"role": "assistant", "content": [
                                     {"type": "tool_use", "id": f"toolu_cur_{d}", "name": "Bash",
                                      "input": {"command": "ddev artisan migrate"}},
                                 ]}})
            write_session(proj_dir, "sess.jsonl", records)

            decisions_path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(decisions_path, [{
                "date": (self.now - dt.timedelta(days=40)).strftime("%Y-%m-%d"),
                "title": "t", "key": "ae1-compound", "verdict": "accepted", "target": "x",
                "baseline": 5,
                "trigger": [{"kind": "tool", "value": "Bash"}, {"kind": "keyword", "value": "artisan"}],
            }])

            out_path = os.path.join(tmp, "events.json")
            run_mine(os.path.join(tmp, "projects"), out_path, days=0, decisions_path=decisions_path)
            with open(ledger_path_for(out_path)) as f:
                ledger = json.load(f)

        row = self._row(ledger, "ae1-compound")
        self.assertEqual(row["pre_accept_friction"], 5)
        self.assertEqual(row["current_friction"], 0)
        self.assertEqual(row["current_opportunities"], 3)
        self.assertEqual(row["standing"], "working")

    def test_compound_trigger_denial_not_double_counted_by_followup_correction(self):
        # A denied tool_use already earns friction credit via the tool_use_id link
        # (existing denial handling) — a correction immediately following the deny
        # ("no, use ddev instead") must not ALSO earn credit via the pending-reply proxy.
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            d = 5
            ts = iso(self.now - dt.timedelta(days=d))
            records = [
                self._filler(),
                {"type": "assistant", "timestamp": ts, "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "toolu_x", "name": "Bash", "input": {"command": "php artisan migrate"}},
                ]}},
                {"type": "user", "timestamp": ts, "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_x", "content": "The user doesn't want to proceed."},
                ]}},
                {"type": "user", "timestamp": ts, "message": {"role": "user", "content": "no, use ddev instead"}},
            ]
            write_session(proj_dir, "sess.jsonl", records)

            decisions_path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(decisions_path, [{
                "date": (self.now - dt.timedelta(days=40)).strftime("%Y-%m-%d"),
                "title": "t", "key": "no-double-count", "verdict": "accepted", "target": "x",
                "baseline": 5,
                "trigger": [{"kind": "tool", "value": "Bash"}, {"kind": "keyword", "value": "artisan"}],
            }])

            out_path = os.path.join(tmp, "events.json")
            run_mine(os.path.join(tmp, "projects"), out_path, days=0, decisions_path=decisions_path)
            with open(ledger_path_for(out_path)) as f:
                ledger = json.load(f)

        row = self._row(ledger, "no-double-count")
        self.assertEqual(row["current_friction"], 1)

    def test_ae2_not_working(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            records = [self._filler()]
            for d in (45, 44, 43, 42):
                records.append({"type": "user", "timestamp": iso(self.now - dt.timedelta(days=d)),
                                 "message": {"role": "user", "content": "no, don't run artisan like that"}})
            for d in (10, 8, 6, 4):
                records.append({"type": "user", "timestamp": iso(self.now - dt.timedelta(days=d)),
                                 "message": {"role": "user", "content": "no, don't run artisan like that"}})
            write_session(proj_dir, "sess.jsonl", records)

            decisions_path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(decisions_path, [self._decision("ae2", 40)])

            out_path = os.path.join(tmp, "events.json")
            run_mine(os.path.join(tmp, "projects"), out_path, days=0, decisions_path=decisions_path)
            with open(ledger_path_for(out_path)) as f:
                ledger = json.load(f)

        row = self._row(ledger, "ae2")
        self.assertEqual(row["pre_accept_friction"], 4)
        self.assertEqual(row["current_friction"], 4)
        self.assertEqual(row["standing"], "not_working")

    def test_ae3_inconclusive_zero_opportunities_never_reads_working(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            records = [self._filler()]
            for d in (45, 44, 43, 42, 41):
                records.append({"type": "user", "timestamp": iso(self.now - dt.timedelta(days=d)),
                                 "message": {"role": "user", "content": "no, don't run artisan like that"}})
            # current slice: no mention of the trigger keyword at all
            records.append({"type": "user", "timestamp": iso(self.now - dt.timedelta(days=5)),
                             "message": {"role": "user", "content": "looks good, ship it"}})
            write_session(proj_dir, "sess.jsonl", records)

            decisions_path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(decisions_path, [self._decision("ae3", 40)])

            out_path = os.path.join(tmp, "events.json")
            run_mine(os.path.join(tmp, "projects"), out_path, days=0, decisions_path=decisions_path)
            with open(ledger_path_for(out_path)) as f:
                ledger = json.load(f)

        row = self._row(ledger, "ae3")
        self.assertEqual(row["current_opportunities"], 0)
        self.assertEqual(row["current_friction"], 0)
        self.assertEqual(row["standing"], "inconclusive")

    def test_ae4a_within_grace_period_not_measurable_yet(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            write_session(proj_dir, "sess.jsonl", [])

            decisions_path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(decisions_path, [self._decision("ae4a", 5)])  # < GRACE_DAYS

            out_path = os.path.join(tmp, "events.json")
            run_mine(os.path.join(tmp, "projects"), out_path, days=0, decisions_path=decisions_path)
            with open(ledger_path_for(out_path)) as f:
                ledger = json.load(f)

        row = self._row(ledger, "ae4a")
        self.assertEqual(row["standing"], "not_measurable_yet")

    def test_ae4b_key_without_trigger_produces_no_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            write_session(proj_dir, "sess.jsonl", [])

            decisions_path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(decisions_path, [{
                "date": (self.now - dt.timedelta(days=40)).strftime("%Y-%m-%d"),
                "key": "ae4b", "verdict": "accepted", "tier": "user",
            }])  # no "trigger" field

            out_path = os.path.join(tmp, "events.json")
            run_mine(os.path.join(tmp, "projects"), out_path, days=0, decisions_path=decisions_path)
            with open(ledger_path_for(out_path)) as f:
                ledger = json.load(f)

        self.assertEqual([r for r in ledger["rows"] if r["key"] == "ae4b"], [])

    def test_ae5_fallback_when_pre_accept_slice_predates_available_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            # only record on disk is recent; the anchor's pre-accept slice (~100+14
            # days ago) predates it entirely.
            write_session(proj_dir, "sess.jsonl", [
                {"type": "user", "timestamp": iso(self.now - dt.timedelta(days=5)),
                 "message": {"role": "user", "content": "please run artisan migrate"}},
            ])

            decisions_path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(decisions_path, [self._decision("ae5", 100, baseline=7)])

            out_path = os.path.join(tmp, "events.json")
            run_mine(os.path.join(tmp, "projects"), out_path, days=0, decisions_path=decisions_path)
            with open(ledger_path_for(out_path)) as f:
                ledger = json.load(f)

        row = self._row(ledger, "ae5")
        self.assertEqual(row["standing"], "inconclusive")
        self.assertTrue(row["fallback"])
        self.assertEqual(row["baseline_seed"], 7)

    def test_small_n_current_opportunities_below_minimum(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            records = [self._filler()]
            for d in (45, 44, 43, 42, 41):
                records.append({"type": "user", "timestamp": iso(self.now - dt.timedelta(days=d)),
                                 "message": {"role": "user", "content": "no, don't run artisan like that"}})
            for d in (5, 3):  # only 2 current opportunities, below MIN_OPPORTUNITIES
                records.append({"type": "user", "timestamp": iso(self.now - dt.timedelta(days=d)),
                                 "message": {"role": "user", "content": "please run artisan migrate"}})
            write_session(proj_dir, "sess.jsonl", records)

            decisions_path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(decisions_path, [self._decision("small-n-opp", 40)])

            out_path = os.path.join(tmp, "events.json")
            run_mine(os.path.join(tmp, "projects"), out_path, days=0, decisions_path=decisions_path)
            with open(ledger_path_for(out_path)) as f:
                ledger = json.load(f)

        row = self._row(ledger, "small-n-opp")
        self.assertEqual(row["current_opportunities"], 2)
        self.assertEqual(row["standing"], "inconclusive")

    def test_small_n_pre_accept_friction_below_minimum(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            records = [self._filler(), {"type": "user", "timestamp": iso(self.now - dt.timedelta(days=45)),
                        "message": {"role": "user", "content": "no, don't run artisan like that"}}]
            for d in (5, 4, 3):
                records.append({"type": "user", "timestamp": iso(self.now - dt.timedelta(days=d)),
                                 "message": {"role": "user", "content": "please run artisan migrate"}})
            write_session(proj_dir, "sess.jsonl", records)

            decisions_path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(decisions_path, [self._decision("small-n-baseline", 40)])

            out_path = os.path.join(tmp, "events.json")
            run_mine(os.path.join(tmp, "projects"), out_path, days=0, decisions_path=decisions_path)
            with open(ledger_path_for(out_path)) as f:
                ledger = json.load(f)

        row = self._row(ledger, "small-n-baseline")
        self.assertEqual(row["pre_accept_friction"], 1)
        self.assertEqual(row["current_opportunities"], 3)
        self.assertEqual(row["standing"], "inconclusive")

    def test_ledger_written_with_empty_rows_when_no_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            out_path = os.path.join(tmp, "events.json")
            run_mine(os.path.join(tmp, "projects"), out_path, days=0)  # no --decisions override
            with open(ledger_path_for(out_path)) as f:
                ledger = json.load(f)

        self.assertIn("generated_at", ledger)
        self.assertEqual(ledger["rows"], [])

    def test_regression_fixtures_unchanged_with_anchors_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            decisions_path = os.path.join(tmp, "decisions.jsonl")
            write_decisions(decisions_path, [self._decision("regression-key", 40)])
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(FIXTURES, out_path, days=0, decisions_path=decisions_path)

        self.assertEqual(data["sessions_scanned"], 2)
        by_type = {}
        for e in data["events"]:
            by_type.setdefault(e["type"], []).append(e)
        self.assertEqual(len(by_type.get("correction", [])), 1)
        self.assertEqual(len(by_type.get("denial", [])), 1)
        self.assertEqual(len(by_type.get("interrupt", [])), 1)
        self.assertEqual(len(data["events"]), 3)


if __name__ == "__main__":
    unittest.main()
