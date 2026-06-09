from pathlib import Path
import json
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_sessions.py"


class TaskboardSessionsTest(unittest.TestCase):
    def run_sessions(self, root: Path, *args: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), "--format", "json", *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return json.loads(result.stdout)

    def test_heartbeat_then_probe_reports_role_alive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            heartbeat = self.run_sessions(root, "heartbeat", "--role", "T1", "--status", "looping")
            probe = self.run_sessions(root, "probe", "--expected", "T1", "--stale-seconds", "300")

        self.assertEqual(heartbeat["role"], "T1")
        self.assertEqual(probe["state"], "healthy")
        self.assertEqual(probe["sessions"]["T1"]["state"], "alive")
        self.assertEqual(probe["sessions"]["T1"]["status"], "looping")
        self.assertIn("T0 manager-only", probe["boundary"])

    def test_probe_reports_missing_roles_with_recovery_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            probe = self.run_sessions(root, "probe", "--expected", "T1,T2,T3")

        self.assertEqual(probe["state"], "attention")
        self.assertEqual(probe["missing_roles"], ["T1", "T2", "T3"])
        self.assertEqual(probe["stale_roles"], [])
        self.assertIn("recover taskboard-T2", " ".join(probe["recovery_actions"]))
        self.assertIn("manager-only", " ".join(probe["recovery_actions"]))

    def test_probe_reports_stale_role_and_launcher_recovery_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / ".taskboard" / "sessions"
            session_dir.mkdir(parents=True)
            old_time = time.time() - 600
            (session_dir / "taskboard-T3.json").write_text(
                json.dumps(
                    {
                        "role": "T3",
                        "title": "taskboard-T3",
                        "status": "looping",
                        "pid": 123,
                        "last_seen": old_time,
                    }
                ),
                encoding="utf-8",
            )

            probe = self.run_sessions(
                root,
                "probe",
                "--expected",
                "T3",
                "--stale-seconds",
                "300",
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt "{target}"',
            )

        self.assertEqual(probe["state"], "attention")
        self.assertEqual(probe["missing_roles"], [])
        self.assertEqual(probe["stale_roles"], ["T3"])
        self.assertEqual(probe["sessions"]["T3"]["state"], "stale")
        self.assertEqual(len(probe["recovery_commands"]), 1)
        self.assertIn("taskboard-T3", probe["recovery_commands"][0])
        self.assertIn("codex --prompt", probe["recovery_commands"][0])


if __name__ == "__main__":
    unittest.main()
