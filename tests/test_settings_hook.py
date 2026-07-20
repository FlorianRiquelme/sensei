import json, os, subprocess, sys, tempfile, unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_HOOK_PY = os.path.join(REPO_ROOT, "settings_hook.py")
COMMAND = "/usr/bin/python3 /abs/path/nudge.py"

FOREIGN_SESSION_START = [
    {"hooks": [{"type": "command", "command": 'bash "/Users/x/.vibe-ads/ensure-statusline.sh"'}]}
]

def run_hook(args, check=True):
    return subprocess.run(
        [sys.executable, SETTINGS_HOOK_PY] + args,
        capture_output=True, text=True, check=check,
    )

def write_settings(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def read_settings(path):
    with open(path) as f:
        return json.load(f)

def sensei_groups(settings):
    return [
        g for g in settings.get("hooks", {}).get("SessionStart", [])
        if any(h.get("_sensei") or "nudge.py" in h.get("command", "") for h in g.get("hooks", []))
    ]


class TestSettingsHook(unittest.TestCase):
    def test_add_creates_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            run_hook(["add", "--command", COMMAND, "--settings", path])
            settings = read_settings(path)

        groups = sensei_groups(settings)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["hooks"][0]["command"], COMMAND)
        self.assertIn(groups[0].get("matcher"), ("*", None))

    def test_add_preserves_foreign_session_start_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            write_settings(path, {"hooks": {"SessionStart": [dict(FOREIGN_SESSION_START[0])]}})
            run_hook(["add", "--command", COMMAND, "--settings", path])
            settings = read_settings(path)

        session_start = settings["hooks"]["SessionStart"]
        self.assertEqual(len(session_start), 2)
        self.assertIn(FOREIGN_SESSION_START[0], session_start)
        self.assertEqual(len(sensei_groups(settings)), 1)

    def test_add_twice_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            write_settings(path, {"hooks": {"SessionStart": [dict(FOREIGN_SESSION_START[0])]}})
            run_hook(["add", "--command", COMMAND, "--settings", path])
            run_hook(["add", "--command", COMMAND, "--settings", path])
            settings = read_settings(path)

        self.assertEqual(len(sensei_groups(settings)), 1)
        self.assertEqual(len(settings["hooks"]["SessionStart"]), 2)

    def test_add_preserves_unrelated_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            write_settings(path, {
                "model": "sonnet",
                "permissions": {"allow": ["Bash(ls:*)"]},
                "hooks": {
                    "SessionStart": [dict(FOREIGN_SESSION_START[0])],
                    "Stop": [{"hooks": [{"type": "command", "command": "echo stop"}]}],
                },
            })
            run_hook(["add", "--command", COMMAND, "--settings", path])
            settings = read_settings(path)

        self.assertEqual(settings["model"], "sonnet")
        self.assertEqual(settings["permissions"], {"allow": ["Bash(ls:*)"]})
        self.assertEqual(settings["hooks"]["Stop"][0]["hooks"][0]["command"], "echo stop")

    def test_remove_deletes_only_sensei_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            write_settings(path, {"hooks": {"SessionStart": [dict(FOREIGN_SESSION_START[0])]}})
            run_hook(["add", "--command", COMMAND, "--settings", path])
            run_hook(["remove", "--settings", path])
            settings = read_settings(path)

        session_start = settings["hooks"]["SessionStart"]
        self.assertEqual(len(session_start), 1)
        self.assertEqual(session_start[0], FOREIGN_SESSION_START[0])

    def test_remove_noop_when_no_sensei_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            original = {"hooks": {"SessionStart": [dict(FOREIGN_SESSION_START[0])]}}
            write_settings(path, original)
            result = run_hook(["remove", "--settings", path])
            settings = read_settings(path)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(settings, original)

    def test_add_then_remove_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            original = {"hooks": {"SessionStart": [dict(FOREIGN_SESSION_START[0])]}}
            write_settings(path, original)
            run_hook(["add", "--command", COMMAND, "--settings", path])
            run_hook(["remove", "--settings", path])
            settings = read_settings(path)

        self.assertEqual(settings, original)

    def test_malformed_json_fails_loudly_without_clobbering(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            with open(path, "w") as f:
                f.write("{not valid json")
            result = run_hook(["add", "--command", COMMAND, "--settings", path], check=False)
            with open(path) as f:
                contents_after = f.read()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(contents_after, "{not valid json")


if __name__ == "__main__":
    unittest.main()
