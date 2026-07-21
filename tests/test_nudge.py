import json, os, subprocess, sys, tempfile, unittest, datetime as dt

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUDGE_PY = os.path.join(REPO_ROOT, "nudge.py")

def run_nudge(sensei_dir, now, env_extra=None):
    env = dict(os.environ)
    env.pop("SENSEI_NIGHTLY", None)
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [sys.executable, NUDGE_PY, "--sensei-dir", sensei_dir, "--now", now.isoformat()],
        capture_output=True, text=True, env=env,
    )
    return result

def write_digest(sensei_dir, date_str, sessions_scanned=0, events_total=0, by_type=None, by_project=None, meta=None):
    digests_dir = os.path.join(sensei_dir, "digests")
    os.makedirs(digests_dir, exist_ok=True)
    digest = {
        "date": date_str,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sessions_scanned": sessions_scanned,
        "events_total": events_total,
        "by_type": by_type or {},
        "by_project": by_project or {},
    }
    if meta is not None:
        digest["_meta"] = meta
    with open(os.path.join(digests_dir, f"{date_str}.json"), "w") as f:
        json.dump(digest, f)

def write_proposal(sensei_dir, date_str, content):
    proposals_dir = os.path.join(sensei_dir, "proposals")
    os.makedirs(proposals_dir, exist_ok=True)
    with open(os.path.join(proposals_dir, f"{date_str}.md"), "w") as f:
        f.write(content)

def write_decisions(sensei_dir, records):
    with open(os.path.join(sensei_dir, "decisions.jsonl"), "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


class TestNudge(unittest.TestCase):
    def test_env_guard_no_output_no_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)
            write_digest(tmp, "2026-07-19")
            result = run_nudge(tmp, now, env_extra={"SENSEI_NIGHTLY": "1"})
            self.assertEqual(result.stdout.strip(), "")
            self.assertFalse(os.path.exists(os.path.join(tmp, "nudge-state")))

    def test_failure_line_when_digest_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)
            result = run_nudge(tmp, now)
            payload = json.loads(result.stdout)
            self.assertIn("did NOT happen", payload["systemMessage"])
            self.assertIn("nightly.log", payload["hookSpecificOutput"]["additionalContext"])
            self.assertFalse(os.path.exists(os.path.join(tmp, "nudge-state")))

    def test_failure_repeats_no_latch(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)
            r1 = run_nudge(tmp, now)
            r2 = run_nudge(tmp, now)
            self.assertIn("did NOT happen", json.loads(r1.stdout)["systemMessage"])
            self.assertIn("did NOT happen", json.loads(r2.stdout)["systemMessage"])

    def test_heartbeat_when_digest_present_zero_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)
            write_digest(tmp, "2026-07-19", sessions_scanned=6, events_total=14)
            result = run_nudge(tmp, now)
            payload = json.loads(result.stdout)
            self.assertIn("scanned 6 sessions", payload["systemMessage"])
            self.assertIn("14 events", payload["systemMessage"])
            self.assertIn("0 proposals", payload["systemMessage"])
            with open(os.path.join(tmp, "nudge-state")) as f:
                self.assertEqual(f.read().strip(), "2026-07-19")

    def test_leak_warning_over_threshold_heartbeat_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)
            write_digest(tmp, "2026-07-19", sessions_scanned=6, events_total=14, meta={
                "parse_errors": 0, "capped_sessions": 0, "total_capped": 5, "unreadable_files": 0,
            })
            result = run_nudge(tmp, now)
            payload = json.loads(result.stdout)
            self.assertIn("scanned 6 sessions", payload["systemMessage"])
            self.assertIn("missing signal", payload["systemMessage"])

    def test_leak_warning_over_threshold_pending_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)
            write_digest(tmp, "2026-07-19", meta={
                "parse_errors": 0, "capped_sessions": 1, "total_capped": 0, "unreadable_files": 0,
            })
            write_proposal(tmp, "2026-07-14", (
                "## Proposal one\n"
                "- **Key:** ~/.claude/CLAUDE.md::foo-rule\n"
            ))
            result = run_nudge(tmp, now)
            payload = json.loads(result.stdout)
            self.assertIn("proposal waiting", payload["systemMessage"])
            self.assertIn("/sensei review", payload["systemMessage"])
            self.assertIn("missing signal", payload["systemMessage"])

    def test_leak_warning_under_threshold_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)
            write_digest(tmp, "2026-07-19", sessions_scanned=6, events_total=14, meta={
                "parse_errors": 3, "capped_sessions": 0, "total_capped": 0, "unreadable_files": 0,
            })
            result = run_nudge(tmp, now)
            payload = json.loads(result.stdout)
            self.assertNotIn("missing signal", payload["systemMessage"])

    def test_leak_warning_absent_meta_no_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)
            write_digest(tmp, "2026-07-19", sessions_scanned=6, events_total=14)
            result = run_nudge(tmp, now)
            payload = json.loads(result.stdout)
            self.assertNotIn("missing signal", payload["systemMessage"])
            self.assertIn("scanned 6 sessions", payload["systemMessage"])

    def test_leak_warning_corrupt_meta_no_crash(self):
        # a hand-edited/corrupted digest with non-numeric _meta values must not crash the
        # nudge (which runs on every session start) nor suppress the base line.
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)
            write_digest(tmp, "2026-07-19", sessions_scanned=6, events_total=14, meta={
                "parse_errors": "x", "capped_sessions": None, "total_capped": "lots", "unreadable_files": [],
            })
            result = run_nudge(tmp, now)
            payload = json.loads(result.stdout)
            self.assertNotIn("missing signal", payload["systemMessage"])
            self.assertIn("scanned 6 sessions", payload["systemMessage"])

    def test_pending_line_reports_count_and_oldest(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)  # Friday
            write_digest(tmp, "2026-07-19")
            write_proposal(tmp, "2026-07-14", (  # Tuesday
                "## Proposal one\n"
                "- **Key:** ~/.claude/CLAUDE.md::foo-rule\n"
                "- **Supporting events:** 5\n"
                "---\n"
                "## Proposal two\n"
                "- **Key:** ~/.claude/CLAUDE.md::bar-rule\n"
                "- **Supporting events:** 3\n"
            ))
            result = run_nudge(tmp, now)
            payload = json.loads(result.stdout)
            self.assertIn("2 proposals waiting", payload["systemMessage"])
            self.assertIn("2026-07-14", payload["systemMessage"])
            self.assertIn("/sensei review", payload["systemMessage"])

    def test_pending_excludes_decided_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)
            write_digest(tmp, "2026-07-19")
            write_proposal(tmp, "2026-07-14", (
                "## Proposal one\n"
                "- **Key:** ~/.claude/CLAUDE.md::foo-rule\n"
            ))
            write_decisions(tmp, [
                {"date": "2026-07-15", "title": "x", "key": "~/.claude/CLAUDE.md::foo-rule", "verdict": "accepted"},
            ])
            result = run_nudge(tmp, now)
            payload = json.loads(result.stdout)
            self.assertIn("0 proposals", payload["systemMessage"])

    def test_degrades_on_unparseable_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)
            write_digest(tmp, "2026-07-19")
            write_proposal(tmp, "2026-07-10", "## Legacy proposal\nSome text, no Key line at all.\n")
            result = run_nudge(tmp, now)
            payload = json.loads(result.stdout)
            self.assertIn("proposals waiting since 2026-07-10", payload["systemMessage"])
            self.assertIn("/sensei review", payload["systemMessage"])

    def test_second_invocation_same_day_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)
            write_digest(tmp, "2026-07-19", sessions_scanned=1, events_total=1)
            r1 = run_nudge(tmp, now)
            self.assertNotEqual(r1.stdout.strip(), "")
            r2 = run_nudge(tmp, now)
            self.assertEqual(r2.stdout.strip(), "")

    def test_local_time_boundary_before_0530_uses_yesterday(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_digest(tmp, "2026-07-18", sessions_scanned=2, events_total=2)
            now = dt.datetime(2026, 7, 19, 5, 29, 0)
            result = run_nudge(tmp, now)
            payload = json.loads(result.stdout)
            self.assertIn("scanned 2 sessions", payload["systemMessage"])

    def test_local_time_boundary_after_0530_uses_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_digest(tmp, "2026-07-19", sessions_scanned=3, events_total=3)
            now = dt.datetime(2026, 7, 19, 5, 31, 0)
            result = run_nudge(tmp, now)
            payload = json.loads(result.stdout)
            self.assertIn("scanned 3 sessions", payload["systemMessage"])

    def test_malformed_decisions_and_digest_do_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 7, 19, 9, 0, 0)
            digests_dir = os.path.join(tmp, "digests")
            os.makedirs(digests_dir)
            with open(os.path.join(digests_dir, "2026-07-19.json"), "w") as f:
                f.write("{not valid json")
            with open(os.path.join(tmp, "decisions.jsonl"), "w") as f:
                f.write("{not valid json\n")
            result = run_nudge(tmp, now)
            self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
