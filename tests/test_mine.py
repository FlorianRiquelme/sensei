import importlib.util, json, os, subprocess, sys, tempfile, unittest, datetime as dt

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(REPO_ROOT, "tests", "fixtures", "projects")
MINE_PY = os.path.join(REPO_ROOT, "mine.py")

def run_mine(projects_dir, out_path, days=0):
    subprocess.run(
        [sys.executable, MINE_PY, "--days", str(days), "--projects-dir", projects_dir, "--out", out_path],
        check=True, capture_output=True, text=True,
    )
    with open(out_path) as f:
        return json.load(f)

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

    def test_meta_present_and_zero_for_clean_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(FIXTURES, out_path, days=0)

        meta = data["_meta"]
        for key in ("parse_errors", "capped_sessions", "total_capped", "unreadable_files"):
            self.assertIn(key, meta)
            self.assertEqual(meta[key], 0)


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

    # --- GitHub #18: recall leak counter (`_meta`) -------------------------------------

    def test_meta_parse_errors_counts_malformed_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            fp = os.path.join(proj_dir, "sess.jsonl")
            with open(fp, "w") as f:
                f.write(json.dumps({
                    "type": "user", "timestamp": "2020-01-01T00:00:00Z",
                    "message": {"role": "user", "content": "no, stop, that's wrong"},
                }) + "\n")
                f.write("not valid json\n")
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=0)

        self.assertEqual(data["_meta"]["parse_errors"], 1)
        corrections = [e for e in data["events"] if e["type"] == "correction"]
        self.assertEqual(len(corrections), 1)

    def test_meta_capped_sessions_counts_session_over_max_per_session(self):
        mine_mod = load_mine_module()
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            now = dt.datetime.now(dt.timezone.utc)
            records = []
            n = mine_mod.MAX_PER_SESSION + 3
            for i in range(n):
                ts = (now - dt.timedelta(hours=n - i)).isoformat().replace("+00:00", "Z")
                records.append({
                    "type": "user", "timestamp": ts,
                    "message": {"role": "user", "content": f"no, stop, that's wrong number {i}"},
                })
            write_session(proj_dir, "sess.jsonl", records)
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=14)

        self.assertEqual(data["_meta"]["capped_sessions"], 1)
        corrections = [e for e in data["events"] if e["type"] == "correction"]
        self.assertEqual(len(corrections), mine_mod.MAX_PER_SESSION)

    def test_capped_interrupt_does_not_leak_backfill(self):
        mine_mod = load_mine_module()
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            now = dt.datetime.now(dt.timezone.utc)
            records = []
            for i in range(mine_mod.MAX_PER_SESSION):
                ts = (now - dt.timedelta(hours=20 - i)).isoformat().replace("+00:00", "Z")
                records.append({
                    "type": "user", "timestamp": ts,
                    "message": {"role": "user", "content": f"no, stop, that's wrong number {i}"},
                })
            # this interrupt would be the MAX_PER_SESSION+1th qualifying event -> dropped
            ts_interrupt = (now - dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z")
            records.append({
                "type": "user", "timestamp": ts_interrupt,
                "message": {"role": "user", "content": "[Request interrupted by user for tool use]"},
            })
            ts_followup = now.isoformat().replace("+00:00", "Z")
            records.append({
                "type": "user", "timestamp": ts_followup,
                "message": {"role": "user", "content": "use the helper function instead"},
            })
            write_session(proj_dir, "sess.jsonl", records)
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=14)

        self.assertEqual(data["_meta"]["capped_sessions"], 1)
        interrupts = [e for e in data["events"] if e["type"] == "interrupt"]
        self.assertEqual(len(interrupts), 0)
        corrections = [e for e in data["events"] if e["type"] == "correction"]
        self.assertEqual(len(corrections), mine_mod.MAX_PER_SESSION)
        for c in corrections:
            self.assertNotIn("followup_text", c)

    def test_meta_unreadable_file_counts_and_emits_no_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            # a directory named *.jsonl matches the glob but raises IsADirectoryError
            # (an OSError subclass) on open() — portable and root-safe.
            os.makedirs(os.path.join(proj_dir, "sess.jsonl"))
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=0)

        self.assertEqual(data["_meta"]["unreadable_files"], 1)
        self.assertEqual(len(data["events"]), 0)

    def test_meta_total_capped_counts_events_over_max_total(self):
        mine_mod = load_mine_module()
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "projects", "proj")
            os.makedirs(proj_dir)
            now = dt.datetime.now(dt.timezone.utc)
            n_sessions = (mine_mod.MAX_TOTAL // mine_mod.MAX_PER_SESSION) + 3
            for s in range(n_sessions):
                records = []
                for i in range(mine_mod.MAX_PER_SESSION):
                    ts = (now - dt.timedelta(hours=i, minutes=s)).isoformat().replace("+00:00", "Z")
                    records.append({
                        "type": "user", "timestamp": ts,
                        "message": {"role": "user", "content": f"no, stop, that's wrong number {i}"},
                    })
                write_session(proj_dir, f"sess{s}.jsonl", records)
            out_path = os.path.join(tmp, "events.json")
            data = run_mine(os.path.join(tmp, "projects"), out_path, days=14)

        produced = n_sessions * mine_mod.MAX_PER_SESSION
        self.assertEqual(len(data["events"]), mine_mod.MAX_TOTAL)
        self.assertEqual(data["_meta"]["total_capped"], produced - mine_mod.MAX_TOTAL)

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

        for field in ("date", "generated_at", "sessions_scanned", "events_total", "by_type", "by_project", "_meta"):
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
        self.assertEqual(digest["_meta"], data["_meta"])

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
        for key in ("parse_errors", "capped_sessions", "total_capped", "unreadable_files"):
            self.assertEqual(digest["_meta"][key], 0)


if __name__ == "__main__":
    unittest.main()
