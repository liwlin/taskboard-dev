from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_sessions.py"
TASKBOARD_CLI = ROOT / "scripts" / "taskboard.py"


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

    def run_taskboard(self, root: Path, *args: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(TASKBOARD_CLI), "--root", str(root), "--format", "json", *args],
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

    def test_heartbeat_records_current_task_assignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            heartbeat = self.run_sessions(
                root,
                "heartbeat",
                "--role",
                "T2",
                "--status",
                "reviewing",
                "--task",
                "TASK-003.v1.T2-review.md",
                "--assignment-id",
                "T2:TASK-003.v1.T2-review.md",
            )
            probe = self.run_sessions(root, "probe", "--expected", "T2", "--stale-seconds", "300")

        self.assertEqual(heartbeat["task"], "TASK-003.v1.T2-review.md")
        self.assertEqual(heartbeat["assignment_id"], "T2:TASK-003.v1.T2-review.md")
        self.assertEqual(probe["sessions"]["T2"]["task"], "TASK-003.v1.T2-review.md")
        self.assertEqual(probe["sessions"]["T2"]["assignment_id"], "T2:TASK-003.v1.T2-review.md")

    def test_probe_reports_missing_roles_with_recovery_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            probe = self.run_sessions(root, "probe", "--expected", "T1,T2,T3")

        self.assertEqual(probe["state"], "attention")
        self.assertEqual(probe["missing_roles"], ["T1", "T2", "T3"])
        self.assertEqual(probe["stale_roles"], [])
        self.assertIn("recover taskboard-T2", " ".join(probe["recovery_actions"]))
        self.assertIn("manager-only", " ".join(probe["recovery_actions"]))

    def test_probe_treats_fresh_alive_marker_as_role_alive_without_session_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            alive = self.run_taskboard(root, "alive", "T2")
            probe = self.run_sessions(root, "probe", "--expected", "T2", "--stale-seconds", "300")

        self.assertEqual(alive["role"], "T2")
        self.assertEqual(probe["state"], "healthy")
        self.assertEqual(probe["missing_roles"], [])
        self.assertEqual(probe["stale_roles"], [])
        self.assertEqual(probe["sessions"]["T2"]["state"], "alive")
        self.assertEqual(probe["sessions"]["T2"]["status"], "alive-marker")
        self.assertEqual(probe["sessions"]["T2"]["source"], ".taskboard/alive")

    def test_probe_treats_stale_alive_marker_as_stale_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alive_dir = root / ".taskboard" / "alive"
            alive_dir.mkdir(parents=True)
            marker = alive_dir / "T3"
            marker.touch()
            old_time = time.time() - 600
            os.utime(marker, (old_time, old_time))

            probe = self.run_sessions(root, "probe", "--expected", "T3", "--stale-seconds", "300")

        self.assertEqual(probe["state"], "attention")
        self.assertEqual(probe["missing_roles"], [])
        self.assertEqual(probe["stale_roles"], ["T3"])
        self.assertEqual(probe["sessions"]["T3"]["state"], "stale")
        self.assertEqual(probe["sessions"]["T3"]["status"], "alive-marker")

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

    def test_probe_recovery_command_can_reference_role_target_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            probe = self.run_sessions(
                root,
                "probe",
                "--expected",
                "T1",
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt-file "{target_file}"',
            )

        self.assertEqual(probe["missing_roles"], ["T1"])
        self.assertEqual(len(probe["recovery_commands"]), 1)
        self.assertIn("codex --prompt-file", probe["recovery_commands"][0])
        self.assertIn("taskboard-T1.md", probe["recovery_commands"][0])
        self.assertNotIn('prompt-file ""', probe["recovery_commands"][0])

    def test_probe_writes_recovery_target_file_for_prompt_file_launchers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            probe = self.run_sessions(
                root,
                "probe",
                "--expected",
                "T1",
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt-file "{target_file}"',
            )
            target_file = root / ".taskboard" / "targets" / "taskboard-T1.md"
            target_exists = target_file.exists()
            target_text = target_file.read_text(encoding="utf-8") if target_exists else ""
            target_file_text = str(target_file)

        self.assertEqual(probe["missing_roles"], ["T1"])
        self.assertTrue(target_exists)
        self.assertEqual(probe["target_files"][0]["role"], "T1")
        self.assertEqual(probe["target_files"][0]["path"], target_file_text)
        self.assertIn("managed_by: T0", target_text)
        self.assertIn("assigned_role: T1", target_text)
        self.assertIn("Ship demo", target_text)

    def test_probe_default_dry_check_does_not_write_target_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            probe = self.run_sessions(root, "probe", "--expected", "T1", "--goal", "Ship demo")
            target_dir_exists = (root / ".taskboard" / "targets").exists()

        self.assertEqual(probe["missing_roles"], ["T1"])
        self.assertEqual(probe["recovery_commands"], [])
        self.assertEqual(probe["target_files"], [])
        self.assertFalse(target_dir_exists)

    def test_probe_inline_recovery_command_does_not_write_target_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            probe = self.run_sessions(
                root,
                "probe",
                "--expected",
                "T1",
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt "{target}"',
            )
            target_dir_exists = (root / ".taskboard" / "targets").exists()

        self.assertEqual(probe["missing_roles"], ["T1"])
        self.assertEqual(len(probe["recovery_commands"]), 1)
        self.assertEqual(probe["target_files"], [])
        self.assertFalse(target_dir_exists)


if __name__ == "__main__":
    unittest.main()
