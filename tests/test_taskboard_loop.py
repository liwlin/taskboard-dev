from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_loop.py"
sys.path.insert(0, str(ROOT / "scripts"))
from taskboard_next import ROLE_PRIORITY  # noqa: E402


T2_CODE_REVIEW = ROLE_PRIORITY["T0"][1][1]


class TaskboardLoopTest(unittest.TestCase):
    def run_loop(self, root: Path, *args: str) -> list[dict]:
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

    def test_once_combines_session_probe_health_and_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(root, "--goal", "Ship demo")

        self.assertEqual(len(output), 1)
        payload = output[0]
        self.assertEqual(payload["state"], "attention")
        self.assertEqual(payload["session_probe"]["missing_roles"], ["T1", "T2", "T3"])
        self.assertEqual(payload["queue_health"]["next"]["role"], "T1")
        self.assertEqual(payload["dispatch"]["next_role"], "T1")
        self.assertIn("T0 supervisor-only", payload["boundary"])
        self.assertIn("recover taskboard-T1", " ".join(payload["actions"]))

    def test_loop_generates_recovery_commands_without_executing_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt "{target}"',
            )

        payload = output[0]
        self.assertEqual(len(payload["launch_commands"]), 3)
        self.assertEqual(payload["executed_commands"], [])
        self.assertIn("taskboard-T2", payload["launch_commands"][1])
        self.assertIn("codex --prompt", payload["launch_commands"][1])

    def test_loop_reports_needs_goal_without_goal_or_project_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(root)

        self.assertEqual(output[0]["state"], "needs-goal")
        self.assertEqual(output[0]["dispatch"]["state"], "needs-goal")
        self.assertIn("ask user for one T0 goal", output[0]["actions"])

    def test_iterations_runs_multiple_bounded_cycles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(root, "--goal", "Ship demo", "--iterations", "2", "--interval-seconds", "0")

        self.assertEqual(len(output), 2)

    def test_assignment_moves_from_pending_to_acknowledged_by_worker_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-003.v1.{T2_CODE_REVIEW}-L2.md"
            (taskboard / task_name).write_text("# task\n\n**Wave**: 1\n", encoding="utf-8")

            session_dir = root / ".taskboard" / "sessions"
            session_dir.mkdir(parents=True)
            base_session = {
                "role": "T2",
                "title": "taskboard-T2",
                "status": "alive",
                "pid": 123,
                "last_seen": 4102444800,
            }
            (session_dir / "taskboard-T1.json").write_text(
                json.dumps({**base_session, "role": "T1", "title": "taskboard-T1"}),
                encoding="utf-8",
            )
            (session_dir / "taskboard-T2.json").write_text(json.dumps(base_session), encoding="utf-8")
            (session_dir / "taskboard-T3.json").write_text(
                json.dumps({**base_session, "role": "T3", "title": "taskboard-T3"}),
                encoding="utf-8",
            )

            pending = self.run_loop(root, "--goal", "Ship demo", "--stale-seconds", "999999999")
            (session_dir / "taskboard-T2.json").write_text(
                json.dumps({**base_session, "task": task_name, "assignment_id": f"T2:{task_name}"}),
                encoding="utf-8",
            )
            acknowledged = self.run_loop(root, "--goal", "Ship demo", "--stale-seconds", "999999999")

        self.assertEqual(pending[0]["assignment"]["state"], "pending-ack")
        self.assertIn("reissue target to taskboard-T2", " ".join(pending[0]["actions"]))
        self.assertEqual(acknowledged[0]["assignment"]["state"], "acknowledged")
        self.assertEqual(acknowledged[0]["assignment"]["assignment_id"], f"T2:{task_name}")


if __name__ == "__main__":
    unittest.main()
