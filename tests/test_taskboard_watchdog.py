from pathlib import Path
import json
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))
from taskboard_watchdog import report_guardian, report_watchdog  # noqa: E402


class TaskboardWatchdogTest(unittest.TestCase):
    def write_snapshot(self, root: Path, updated_at: str) -> None:
        state_dir = root / ".taskboard" / "t0"
        state_dir.mkdir(parents=True)
        snapshot = {
            "kind": "taskboard-t0-supervisor-state",
            "goal": "Ship demo",
            "updated_at": updated_at,
            "latest": {
                "state": "active",
                "resume_config": {"interval_seconds": 60, "launcher": "none"},
                "dispatch": {
                    "state": "dispatch",
                    "next_role": "T1",
                    "task": "TASK-001.v1.T1-plan.md",
                },
                "assignment": {"state": "pending-ack", "role": "T1"},
                "queue_health": {"active_count": 1},
                "session_probe": {"missing_roles": [], "stale_roles": []},
            },
        }
        (state_dir / "latest.json").write_text(json.dumps(snapshot), encoding="utf-8")

    def test_watchdog_reports_fresh_t0_without_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_snapshot(root, "2999-01-01T00:00:00Z")

            report = report_watchdog(root, execute=False)

        self.assertEqual(report["kind"], "taskboard-t0-watchdog")
        self.assertEqual(report["state"], "fresh")
        self.assertFalse(report["should_resume"])
        self.assertEqual(report["executed_resume"], False)
        self.assertEqual(report["resume_command"], "")
        self.assertIn("No user action required", report["user_action"])

    def test_watchdog_reports_stale_t0_resume_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_snapshot(root, "2000-01-01T00:00:00Z")

            report = report_watchdog(root, execute=False)

        self.assertEqual(report["state"], "stale")
        self.assertTrue(report["should_resume"])
        self.assertFalse(report["executed_resume"])
        self.assertIn("python scripts/taskboard_start.py", report["resume_command"])
        self.assertIn("--launcher none", report["resume_command"])
        self.assertIn("Resume T0", report["user_action"])
        self.assertIn("do not manage T1/T2/T3", report["user_action"])

    def test_watchdog_execute_runs_only_t0_resume_command(self):
        calls = []

        def fake_runner(command: str):
            calls.append(command)
            return 7

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_snapshot(root, "2000-01-01T00:00:00Z")

            report = report_watchdog(root, execute=True, runner=fake_runner)

        self.assertEqual(calls, [report["resume_command"]])
        self.assertEqual(report["state"], "resumed")
        self.assertTrue(report["executed_resume"])
        self.assertEqual(report["resume_returncode"], 7)
        self.assertIn("taskboard_start.py", calls[0])
        self.assertNotIn("taskboard-T1", calls[0])
        self.assertNotIn("taskboard-T2", calls[0])
        self.assertNotIn("taskboard-T3", calls[0])

    def test_guardian_runs_bounded_watchdog_cycles_without_worker_management(self):
        calls = []
        sleeps = []

        def fake_runner(command: str):
            calls.append(command)
            return 0

        def fake_sleep(seconds: int):
            sleeps.append(seconds)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_snapshot(root, "2000-01-01T00:00:00Z")

            report = report_guardian(
                root,
                execute=True,
                iterations=2,
                interval_seconds=0,
                forever=False,
                runner=fake_runner,
                sleeper=fake_sleep,
            )

        self.assertEqual(report["kind"], "taskboard-t0-guardian")
        self.assertEqual(report["iterations"], 2)
        self.assertEqual(len(report["cycles"]), 2)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("taskboard_start.py" in command for command in calls))
        self.assertTrue(all("taskboard-T1" not in command for command in calls))
        self.assertEqual(sleeps, [0])
        self.assertIn("kept T0 under supervision", report["user_action"])
        self.assertIn("must not launch or manage T1/T2/T3 directly", report["boundary"])

    def test_guardian_defaults_to_forever_until_t0_reaches_terminal_state(self):
        cycles = [
            {
                "kind": "taskboard-t0-watchdog",
                "state": "resumed",
                "progress_state": "attention",
                "executed_resume": True,
                "should_resume": True,
                "resume_command": "python scripts/taskboard_start.py --root . --auto",
            },
            {
                "kind": "taskboard-t0-watchdog",
                "state": "complete",
                "progress_state": "complete",
                "executed_resume": False,
                "should_resume": False,
                "resume_command": "",
            },
        ]
        sleeps = []

        def fake_reporter(*args, **kwargs):
            return dict(cycles.pop(0))

        def fake_sleep(seconds: int):
            sleeps.append(seconds)

        with tempfile.TemporaryDirectory() as tmp:
            report = report_guardian(
                Path(tmp),
                execute=True,
                interval_seconds=0,
                reporter=fake_reporter,
                sleeper=fake_sleep,
            )

        self.assertEqual(report["kind"], "taskboard-t0-guardian")
        self.assertEqual(report["state"], "complete")
        self.assertTrue(report["forever"])
        self.assertEqual(report["iterations"], 2)
        self.assertEqual(report["stop_reason"], "terminal-state:complete")
        self.assertEqual(report["executed_resume_count"], 1)
        self.assertEqual(sleeps, [0])
        self.assertEqual(len(cycles), 0)


if __name__ == "__main__":
    unittest.main()
