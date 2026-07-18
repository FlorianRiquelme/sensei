import json, os, subprocess, sys, tempfile, unittest, datetime as dt

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


if __name__ == "__main__":
    unittest.main()
