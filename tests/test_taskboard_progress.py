from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LOOP_SCRIPT = ROOT / "scripts" / "taskboard_loop.py"
PROGRESS_SCRIPT = ROOT / "scripts" / "taskboard_progress.py"
START_SCRIPT = ROOT / "scripts" / "taskboard_start.py"
sys.path.insert(0, str(ROOT / "scripts"))
from taskboard_next import ROLE_PRIORITY  # noqa: E402


T2_CODE_REVIEW = ROLE_PRIORITY["T0"][1][1]
T3_EXECUTE = ROLE_PRIORITY["T0"][5][1]
T1_REVISE = ROLE_PRIORITY["T0"][6][1]


class TaskboardProgressTest(unittest.TestCase):
    def run_text(self, script: Path, root: Path, *args: str) -> str:
        result = subprocess.run(
            [sys.executable, str(script), "--root", str(root), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout

    def run_json(self, script: Path, root: Path, *args: str):
        result = subprocess.run(
            [sys.executable, str(script), "--root", str(root), "--format", "json", *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return json.loads(result.stdout)

    def test_progress_summarizes_latest_t0_snapshot_for_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-003.v1.{T2_CODE_REVIEW}-L2.md"
            (taskboard / task_name).write_text("# task\n\n**Wave**: 1\n", encoding="utf-8")

            self.run_json(LOOP_SCRIPT, root, "--goal", "Ship demo")
            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["kind"], "taskboard-t0-progress")
        self.assertEqual(progress["goal"], "Ship demo")
        self.assertEqual(progress["state"], "attention")
        self.assertEqual(progress["next_role"], "T2")
        self.assertEqual(progress["task"], task_name)
        self.assertEqual(progress["assignment_state"], "unassigned")
        self.assertIn("T0 is managing T1/T2/T3", progress["user_summary"])
        self.assertIn("No user action required", progress["user_action"])
        self.assertIn("manager-only", progress["boundary"])

    def test_progress_uses_saved_goal_when_no_snapshot_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_json(START_SCRIPT, root, "--goal", "Ship demo", "--iterations", "1", "--no-state-file")
            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["goal"], "Ship demo")
        self.assertEqual(progress["state"], "needs-supervisor-run")
        self.assertIn("Start or resume T0", progress["user_action"])
        self.assertIn("not ask you to manage T1/T2/T3", progress["user_summary"])

    def test_progress_surfaces_one_command_auto_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_json(
                START_SCRIPT,
                root,
                "--goal",
                "Ship demo",
                "--auto",
                "--iterations",
                "1",
                "--launcher",
                "none",
            )
            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertTrue(progress["auto_mode"])
        self.assertEqual(progress["starter_mode"], "auto")
        self.assertIn("one-command", progress["starter_boundary"])

    def test_progress_surfaces_failed_t0_launch_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".taskboard" / "t0"
            state_dir.mkdir(parents=True)
            snapshot = {
                "kind": "taskboard-t0-supervisor-state",
                "goal": "Ship demo",
                "latest": {
                    "state": "attention",
                    "actions": ["launch/recover managed role sessions with generated commands"],
                    "dispatch": {
                        "state": "dispatch",
                        "next_role": "T1",
                        "task": "none",
                    },
                    "assignment": {"state": "none"},
                    "queue_health": {"active_count": 0},
                    "session_probe": {"missing_roles": ["T1"], "stale_roles": []},
                    "executed_commands": [
                        {
                            "command": "wt -w taskboard new-tab --title taskboard-T1",
                            "returncode": 1,
                            "output": "wt was not found",
                        }
                    ],
                },
            }
            (state_dir / "latest.json").write_text(json.dumps(snapshot), encoding="utf-8")

            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["launch_failure_count"], 1)
        self.assertIn("wt was not found", progress["launch_failures"][0]["output"])
        self.assertIn("T0 launch/recovery failed", progress["user_action"])
        self.assertIn("T0 could not launch or recover", progress["user_summary"])

    def test_progress_reads_bom_encoded_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".taskboard" / "t0"
            state_dir.mkdir(parents=True)
            snapshot = {
                "kind": "taskboard-t0-supervisor-state",
                "goal": "Ship demo",
                "latest": {
                    "state": "attention",
                    "dispatch": {"state": "dispatch", "next_role": "T1", "task": "none"},
                    "assignment": {"state": "none"},
                    "queue_health": {"active_count": 0},
                    "session_probe": {"missing_roles": ["T1"], "stale_roles": []},
                },
            }
            (state_dir / "latest.json").write_bytes(
                json.dumps(snapshot).encode("utf-8-sig")
            )

            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["goal"], "Ship demo")
        self.assertEqual(progress["state"], "attention")

    def test_progress_summarizes_suppressed_launches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".taskboard" / "t0"
            state_dir.mkdir(parents=True)
            snapshot = {
                "kind": "taskboard-t0-supervisor-state",
                "goal": "Ship demo",
                "latest": {
                    "state": "attention",
                    "actions": ["wait for T1 launch lease active; do not duplicate managed terminals"],
                    "dispatch": {"state": "dispatch", "next_role": "T1", "task": "none"},
                    "assignment": {"state": "none"},
                    "queue_health": {"active_count": 0},
                    "session_probe": {"missing_roles": ["T1"], "stale_roles": []},
                    "suppressed_launches": [
                        {
                            "role": "T1",
                            "reason": "launch-lease-active",
                            "remaining_seconds": 240,
                        }
                    ],
                },
            }
            (state_dir / "latest.json").write_text(json.dumps(snapshot), encoding="utf-8")

            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["suppressed_launch_count"], 1)
        self.assertIn("T1", progress["suppressed_launches"][0]["role"])
        self.assertIn("waiting for recent T0 launch", progress["user_summary"])
        self.assertIn("No user action required", progress["user_action"])

    def test_progress_surfaces_t0_stop_gate_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            (taskboard / "TASK-009.v2.T1-decision.md").write_text(
                """# Decide release behavior

**Wave**: 2
**Gate**: Product decision
**Question**: Should the beta banner be visible to all users?
**Options**:
- A: Show to everyone
- B: Show only to admins
**Recommended**: B
""",
                encoding="utf-8",
            )
            self.run_json(LOOP_SCRIPT, root, "--goal", "Ship demo")

            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["stop_gate_count"], 1)
        self.assertIn("Product decision", progress["stop_gates"][0]["gate"])
        self.assertIn("T0 stop gate requires user decision", progress["user_action"])
        self.assertIn("beta banner", progress["user_summary"])
        self.assertIn("taskboard_decide.py", progress["decision_command"])
        self.assertIn("--task TASK-009.v2.T1-decision.md", progress["decision_command"])
        self.assertIn('--decision "<user answer>"', progress["decision_command"])

    def test_progress_surfaces_completion_audit_when_t0_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "docs" / "taskboard" / "archive"
            archive.mkdir(parents=True)
            (archive / "TASK-001.v1.done.md").write_text("# done\n", encoding="utf-8")
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text(
                "# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8"
            )
            (root / "docs" / "dev-log.md").write_text(
                "# Development Log\n\n- TASK-001 completed and verified.\n",
                encoding="utf-8",
            )
            self.run_json(LOOP_SCRIPT, root, "--goal", "Ship demo")

            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertTrue(progress["completion_ready"])
        self.assertEqual(progress["completion_missing_evidence"], [])
        self.assertEqual(progress["completion_audit"]["state"], "complete-ready")
        self.assertIn("Review T0's completion summary", progress["user_action"])

    def test_progress_surfaces_t0_event_log_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            self.run_json(
                LOOP_SCRIPT,
                root,
                "--goal",
                "Ship demo",
                "--iterations",
                "2",
                "--interval-seconds",
                "0",
            )

            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["event_count"], 2)
        self.assertEqual(progress["latest_event"]["kind"], "taskboard-t0-supervisor-event")
        self.assertEqual(progress["latest_event"]["iteration"], 2)
        self.assertIn("append-only", progress["event_log_boundary"])

    def test_progress_surfaces_queue_metrics_for_user_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            (taskboard / f"TASK-001.v1.{T1_REVISE}.md").write_text(
                "# revise\n\n**Wave**: 3\n", encoding="utf-8"
            )
            (taskboard / f"TASK-002.v1.{T2_CODE_REVIEW}.md").write_text(
                "# review\n\n**Wave**: 1\n", encoding="utf-8"
            )
            stale_task = taskboard / f"TASK-003.v1.{T3_EXECUTE}.md"
            stale_task.write_text("# execute\n\n**Wave**: 2\n", encoding="utf-8")
            old_time = stale_task.stat().st_mtime - (45 * 60)
            os.utime(stale_task, (old_time, old_time))

            self.run_json(
                LOOP_SCRIPT,
                root,
                "--goal",
                "Ship dashboard",
                "--stale-minutes",
                "30",
            )
            progress = self.run_json(PROGRESS_SCRIPT, root)

        metrics = progress["queue_metrics"]
        self.assertEqual(metrics["active_count"], 3)
        self.assertEqual(metrics["stalled_count"], 1)
        self.assertEqual(metrics["role_counts"], {"T1": 1, "T2": 1, "T3": 1})
        self.assertEqual(metrics["next_role"], "T2")
        self.assertFalse(metrics["user_action_required"])
        self.assertIn("queue metrics", metrics["boundary"])
        self.assertIn("queue_metrics", progress["user_summary"])

    def test_progress_text_prints_queue_metrics_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            (taskboard / f"TASK-001.v1.{T1_REVISE}.md").write_text(
                "# revise\n\n**Wave**: 3\n", encoding="utf-8"
            )
            (taskboard / f"TASK-002.v1.{T2_CODE_REVIEW}.md").write_text(
                "# review\n\n**Wave**: 1\n", encoding="utf-8"
            )
            stale_task = taskboard / f"TASK-003.v1.{T3_EXECUTE}.md"
            stale_task.write_text("# execute\n\n**Wave**: 2\n", encoding="utf-8")
            old_time = stale_task.stat().st_mtime - (45 * 60)
            os.utime(stale_task, (old_time, old_time))

            self.run_json(
                LOOP_SCRIPT,
                root,
                "--goal",
                "Ship dashboard",
                "--stale-minutes",
                "30",
            )
            text = self.run_text(PROGRESS_SCRIPT, root)

        self.assertIn("queue_metrics_active_count=3", text)
        self.assertIn("queue_metrics_stalled_count=1", text)
        self.assertIn("queue_metrics_role_counts=T1:1,T2:1,T3:1", text)
        self.assertIn("queue_metrics_next_role=T2", text)


if __name__ == "__main__":
    unittest.main()
