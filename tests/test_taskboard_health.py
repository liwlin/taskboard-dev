from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_health.py"
sys.path.insert(0, str(ROOT / "scripts"))
from taskboard_next import ROLE_PRIORITY  # noqa: E402


T2_CODE_REVIEW = ROLE_PRIORITY["T0"][1][1]
T3_EXECUTE = ROLE_PRIORITY["T0"][5][1]


class TaskboardHealthTest(unittest.TestCase):
    def run_health(self, root: Path, *args: str) -> dict:
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

    def write_task(self, taskboard: Path, name: str, age_minutes: int = 0) -> Path:
        path = taskboard / name
        path.write_text("# task\n\n**Wave**: 1\n", encoding="utf-8")
        if age_minutes:
            old_time = time.time() - age_minutes * 60
            os.utime(path, (old_time, old_time))
        return path

    def test_reports_queue_counts_next_role_and_wake_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            code_review_status = f"{T2_CODE_REVIEW}-L2"
            self.write_task(taskboard, f"TASK-001.v1.{code_review_status}.md")
            self.write_task(taskboard, f"TASK-002.v1.{T3_EXECUTE}.md")

            output = self.run_health(root)

        self.assertEqual(output["state"], "active")
        self.assertEqual(output["active_count"], 2)
        self.assertEqual(output["next"]["role"], "T2")
        self.assertEqual(output["next"]["task"], f"TASK-001.v1.{code_review_status}.md")
        self.assertEqual(output["queues"]["T2"][code_review_status]["count"], 1)
        self.assertEqual(output["queues"]["T3"][T3_EXECUTE]["count"], 1)
        self.assertIn("wake taskboard-T2", output["actions"][0])
        self.assertIn("T0 manager-only", output["boundary"])

    def test_marks_old_tasks_as_stalled_without_executing_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            self.write_task(taskboard, f"TASK-010.v1.{T3_EXECUTE}.md", age_minutes=45)

            output = self.run_health(root, "--stale-minutes", "30")

        self.assertEqual(output["state"], "attention")
        self.assertEqual(len(output["stalled_tasks"]), 1)
        stalled = output["stalled_tasks"][0]
        self.assertEqual(stalled["role"], "T3")
        self.assertGreaterEqual(stalled["age_minutes"], 44)
        self.assertIn("reissue target to taskboard-T3", stalled["action"])
        self.assertIn("do not execute", stalled["action"])

    def test_empty_goal_context_requests_t1_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\nShip demo\n", encoding="utf-8")

            output = self.run_health(root)

        self.assertEqual(output["state"], "ready-for-next-task")
        self.assertEqual(output["active_count"], 0)
        self.assertEqual(output["next"]["role"], "T1")
        self.assertIn("wake taskboard-T1", " ".join(output["actions"]))

    def test_explicit_goal_requests_t1_before_project_context_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_health(root, "--goal", "Ship demo")

        self.assertEqual(output["state"], "ready-for-next-task")
        self.assertEqual(output["next"]["role"], "T1")
        self.assertEqual(output["next"]["reason"], "explicit-goal-no-active-tasks")

    def test_goal_complete_sentinel_reports_complete_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\n## Goal\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text("# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8")

            output = self.run_health(root, "--goal", "Ship demo")

        self.assertEqual(output["state"], "complete")
        self.assertEqual(output["next"]["role"], "T0")
        self.assertEqual(output["next"]["reason"], "goal-complete-sentinel")


if __name__ == "__main__":
    unittest.main()
