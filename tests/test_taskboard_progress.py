from pathlib import Path
import json
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


class TaskboardProgressTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
