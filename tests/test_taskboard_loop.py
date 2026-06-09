from pathlib import Path
import json
import subprocess
import sys
import tempfile
import time
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

    def test_loop_stops_when_goal_complete_sentinel_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\n## Goal\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text("# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8")

            output = self.run_loop(root, "--goal", "Ship demo")

        self.assertEqual(output[0]["state"], "idle")
        self.assertEqual(output[0]["dispatch"]["state"], "complete")
        self.assertEqual(output[0]["dispatch"]["reason"], "goal-complete-sentinel")
        self.assertIn("summarize completion to the user", output[0]["actions"])

    def test_loop_stops_after_first_complete_iteration_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\n## Goal\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text("# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8")

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--iterations",
                "3",
                "--interval-seconds",
                "0",
            )

        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["dispatch"]["state"], "complete")

    def test_loop_can_continue_after_complete_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\n## Goal\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text("# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8")

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--iterations",
                "2",
                "--interval-seconds",
                "0",
                "--no-stop-on-complete",
            )

        self.assertEqual(len(output), 2)
        self.assertEqual(output[0]["dispatch"]["state"], "complete")
        self.assertEqual(output[1]["dispatch"]["state"], "complete")

    def test_iterations_runs_multiple_bounded_cycles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(root, "--goal", "Ship demo", "--iterations", "2", "--interval-seconds", "0")

        self.assertEqual(len(output), 2)

    def test_loop_writes_latest_t0_state_snapshot_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(root, "--goal", "Ship demo")
            state_file = root / ".taskboard" / "t0" / "latest.json"
            snapshot = json.loads(state_file.read_text(encoding="utf-8"))

        self.assertEqual(snapshot["kind"], "taskboard-t0-supervisor-state")
        self.assertEqual(snapshot["iteration_count"], 1)
        self.assertEqual(snapshot["latest"]["state"], output[0]["state"])
        self.assertEqual(snapshot["latest"]["dispatch"]["next_role"], output[0]["dispatch"]["next_role"])
        self.assertIn("T0 supervisor-only", snapshot["boundary"])
        self.assertIn("do not perform design", snapshot["boundary"])

    def test_loop_can_disable_t0_state_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_loop(root, "--goal", "Ship demo", "--no-state-file")

        self.assertFalse((root / ".taskboard" / "t0" / "latest.json").exists())

    def test_loop_writes_isolated_role_target_files_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-003.v1.{T2_CODE_REVIEW}-L2.md"
            (taskboard / task_name).write_text("# task\n\n**Wave**: 1\n", encoding="utf-8")

            output = self.run_loop(root, "--goal", "Ship demo")
            t1_target = root / ".taskboard" / "targets" / "taskboard-T1.md"
            t2_target = root / ".taskboard" / "targets" / "taskboard-T2.md"
            t3_target = root / ".taskboard" / "targets" / "taskboard-T3.md"
            target_files_exist = [t1_target.exists(), t2_target.exists(), t3_target.exists()]
            t2_text = t2_target.read_text(encoding="utf-8")
            t1_text = t1_target.read_text(encoding="utf-8")

        self.assertEqual(
            [item["role"] for item in output[0]["target_files"]],
            ["T1", "T2", "T3"],
        )
        self.assertEqual(target_files_exist, [True, True, True])
        self.assertIn("managed_by: T0", t2_text)
        self.assertIn(task_name, t2_text)
        self.assertIn(f"--assignment-id T2:{task_name}", t2_text)
        self.assertIn("managed-loop", t1_text)
        self.assertIn("T0 writes role targets only", t2_text)

    def test_loop_can_disable_role_target_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(root, "--goal", "Ship demo", "--no-target-files")

        self.assertEqual(output[0]["target_files"], [])
        self.assertFalse((root / ".taskboard" / "targets").exists())

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

    def test_assignment_lease_expiry_reissues_acknowledged_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-003.v1.{T2_CODE_REVIEW}-L2.md"
            (taskboard / task_name).write_text("# task\n\n**Wave**: 1\n", encoding="utf-8")

            session_dir = root / ".taskboard" / "sessions"
            session_dir.mkdir(parents=True)
            old_assignment_time = time.time() - 600
            for role in ("T1", "T2", "T3"):
                payload = {
                    "role": role,
                    "title": f"taskboard-{role}",
                    "status": "alive",
                    "pid": 123,
                    "last_seen": time.time(),
                }
                if role == "T2":
                    payload.update(
                        {
                            "status": "reviewing",
                            "last_seen": old_assignment_time,
                            "task": task_name,
                            "assignment_id": f"T2:{task_name}",
                        }
                    )
                (session_dir / f"taskboard-{role}.json").write_text(json.dumps(payload), encoding="utf-8")

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--stale-seconds",
                "999999999",
                "--assignment-lease-seconds",
                "300",
            )

        self.assertEqual(output[0]["assignment"]["state"], "lease-expired")
        self.assertGreaterEqual(output[0]["assignment"]["age_seconds"], 599)
        self.assertIn("lease expired", " ".join(output[0]["actions"]))


if __name__ == "__main__":
    unittest.main()
