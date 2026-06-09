from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_next.py"


class TaskboardNextTest(unittest.TestCase):
    def run_next(self, role: str, root: Path) -> str:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--role", role, "--root", str(root)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout.strip()

    def write_task(self, taskboard: Path, name: str) -> None:
        path = taskboard / name
        path.write_text("# task\n\n**Wave**: 1\n", encoding="utf-8")

    def test_t0_selects_highest_priority_across_all_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            self.write_task(taskboard, "TASK-003.v1.T3-待执行.md")
            self.write_task(taskboard, "TASK-002.v1.T2-待审核方案.md")
            self.write_task(taskboard, "TASK-001.v1.T2-待审核代码-L2.md")

            output = self.run_next("T0", root)

        self.assertIn("role=T2", output)
        self.assertIn("status=T2-待审核代码", output)
        self.assertIn("TASK-001.v1.T2-待审核代码-L2.md", output)

    def test_role_specific_selection_keeps_t3_priority_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            self.write_task(taskboard, "TASK-010.v1.T3-待执行.md")
            self.write_task(taskboard, "TASK-011.v1.T3-待验证.md")
            self.write_task(taskboard, "TASK-012.v1.T3-需修复.md")

            output = self.run_next("T3", root)

        self.assertIn("role=T3", output)
        self.assertIn("status=T3-需修复", output)
        self.assertIn("TASK-012.v1.T3-需修复.md", output)

    def test_t0_requests_t1_when_goal_exists_but_no_active_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            (root / "docs" / "PROJECT.md").write_text(
                "# PROJECT\n\n## Goal\nShip demo\n", encoding="utf-8"
            )

            output = self.run_next("T0", root)

        self.assertIn("role=T1", output)
        self.assertIn("reason=no-active-tasks-goal-incomplete", output)

    def test_t0_reports_complete_when_no_active_tasks_and_no_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_next("T0", root)

        self.assertIn("role=T0", output)
        self.assertIn("status=complete", output)


if __name__ == "__main__":
    unittest.main()
