from pathlib import Path
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_start.py"
sys.path.insert(0, str(ROOT / "scripts"))
import taskboard_start as start_module  # noqa: E402


class TaskboardStartTest(unittest.TestCase):
    def run_start(self, root: Path, *args: str) -> list[dict]:
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

    def test_starter_uses_file_backed_t0_defaults_without_executing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_start(root, "--goal", "Ship demo", "--iterations", "1")
            goal_file = root / ".taskboard" / "t0" / "goal.json"
            saved_goal = json.loads(goal_file.read_text(encoding="utf-8"))
            t1_target = root / ".taskboard" / "targets" / "taskboard-T1.md"
            t1_exists = t1_target.exists()
            event_log = root / ".taskboard" / "t0" / "events.jsonl"
            events = [
                json.loads(line)
                for line in event_log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        payload = output[0]
        self.assertEqual(saved_goal["kind"], "taskboard-t0-goal")
        self.assertEqual(saved_goal["goal"], "Ship demo")
        self.assertEqual(payload["dispatch"]["launcher"], "windows-terminal")
        self.assertEqual(len(payload["launch_commands"]), 3)
        self.assertEqual(payload["executed_commands"], [])
        self.assertIn("codex --prompt-file", payload["launch_commands"][0])
        self.assertIn("taskboard-T1.md", payload["launch_commands"][0])
        self.assertTrue(t1_exists)
        self.assertEqual(events[0]["kind"], "taskboard-t0-supervisor-event")
        self.assertEqual(events[0]["goal"], "Ship demo")

    def test_starter_resumes_saved_goal_without_retyping_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_start(root, "--goal", "Ship demo", "--iterations", "1")
            resumed = self.run_start(root, "--iterations", "1")

        self.assertEqual(resumed[0]["goal"], "Ship demo")
        self.assertEqual(resumed[0]["dispatch"]["state"], "dispatch")
        self.assertIn("Ship demo", resumed[0]["dispatch"]["target"])

    def test_starter_can_use_tmux_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_start(root, "--goal", "Ship demo", "--iterations", "1", "--launcher", "tmux")

        self.assertEqual(output[0]["dispatch"]["launcher"], "tmux")
        self.assertIn("tmux new-session", output[0]["launch_commands"][0])

    def test_starter_can_disable_event_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_start(root, "--goal", "Ship demo", "--iterations", "1", "--no-event-log")

        self.assertFalse((root / ".taskboard" / "t0" / "events.jsonl").exists())

    def test_starter_auto_mode_marks_one_command_automation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_start(
                root,
                "--goal",
                "Ship demo",
                "--auto",
                "--iterations",
                "1",
                "--launcher",
                "none",
            )

        self.assertTrue(output[0]["auto_mode"])
        self.assertEqual(output[0]["starter_mode"], "auto")
        self.assertIn("T0 one-command auto mode", output[0]["starter_boundary"])

    def test_starter_auto_mode_stops_when_goal_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_start(root, "--auto", "--launcher", "none")

        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["state"], "needs-goal")
        self.assertEqual(output[0]["dispatch"]["state"], "needs-goal")
        self.assertIn("ask user for one T0 goal", output[0]["actions"])

    def test_starter_auto_mode_persists_in_latest_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_start(
                root,
                "--goal",
                "Ship demo",
                "--auto",
                "--iterations",
                "1",
                "--launcher",
                "tmux",
                "--stale-minutes",
                "12",
                "--stale-seconds",
                "34",
                "--assignment-lease-seconds",
                "56",
                "--launch-lease-seconds",
                "78",
            )
            snapshot = json.loads((root / ".taskboard" / "t0" / "latest.json").read_text(encoding="utf-8"))

        self.assertTrue(snapshot["latest"]["auto_mode"])
        self.assertEqual(snapshot["latest"]["starter_mode"], "auto")
        self.assertIn("T0 one-command auto mode", snapshot["latest"]["starter_boundary"])
        self.assertEqual(snapshot["latest"]["resume_config"]["launcher"], "tmux")
        self.assertEqual(snapshot["latest"]["resume_config"]["stale_minutes"], 12)
        self.assertEqual(snapshot["latest"]["resume_config"]["stale_seconds"], 34)
        self.assertEqual(snapshot["latest"]["resume_config"]["assignment_lease_seconds"], 56)
        self.assertEqual(snapshot["latest"]["resume_config"]["launch_lease_seconds"], 78)

    def test_starter_auto_mode_persists_in_event_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_start(
                root,
                "--goal",
                "Ship demo",
                "--auto",
                "--iterations",
                "1",
                "--launcher",
                "none",
            )
            event_log = root / ".taskboard" / "t0" / "events.jsonl"
            events = [
                json.loads(line)
                for line in event_log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertTrue(events[0]["auto_mode"])
        self.assertEqual(events[0]["starter_mode"], "auto")

    def test_starter_auto_mode_runs_until_completion_by_default(self):
        captured = {}

        def fake_run_loop(*args):
            captured["execute_launches"] = args[6]
            captured["iterations"] = args[7]
            return [{"state": "active"}]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            with patch("taskboard_start.run_loop", fake_run_loop):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = start_module.main(
                        [
                            "--root",
                            str(root),
                            "--goal",
                            "Ship demo",
                            "--auto",
                            "--launcher",
                            "none",
                            "--format",
                            "json",
                        ]
                    )

        self.assertEqual(code, 0)
        self.assertTrue(captured["execute_launches"])
        self.assertIsNone(captured["iterations"])

    def test_starter_auto_mode_respects_equals_style_iterations(self):
        captured = {}

        def fake_run_loop(*args):
            captured["iterations"] = args[7]
            return [{"state": "active"}]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            with patch("taskboard_start.run_loop", fake_run_loop):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = start_module.main(
                        [
                            "--root",
                            str(root),
                            "--goal",
                            "Ship demo",
                            "--auto",
                            "--iterations=1",
                            "--launcher",
                            "none",
                            "--format",
                            "json",
                        ]
                    )

        self.assertEqual(code, 0)
        self.assertEqual(captured["iterations"], 1)

    def test_starter_can_disable_stop_gate_stop_for_monitoring(self):
        captured = {}

        def fake_run_loop(*args):
            captured["stop_on_stop_gate"] = args[15]
            return [{"state": "stop-gate"}]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            with patch("taskboard_start.run_loop", fake_run_loop):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = start_module.main(
                        [
                            "--root",
                            str(root),
                            "--goal",
                            "Ship demo",
                            "--iterations",
                            "1",
                            "--no-stop-on-stop-gate",
                            "--format",
                            "json",
                        ]
                    )

        self.assertEqual(code, 0)
        self.assertFalse(captured["stop_on_stop_gate"])


if __name__ == "__main__":
    unittest.main()
