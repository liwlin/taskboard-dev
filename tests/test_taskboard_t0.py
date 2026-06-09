from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_t0.py"


class TaskboardT0Test(unittest.TestCase):
    def run_t0(self, root: Path, *args: str) -> dict:
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

    def write_task(self, taskboard: Path, name: str) -> None:
        (taskboard / name).write_text("# task\n\n**Wave**: 1\n", encoding="utf-8")

    def test_dispatches_highest_priority_active_task_with_role_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            self.write_task(taskboard, "TASK-003.v1.T3-待执行.md")
            self.write_task(taskboard, "TASK-001.v1.T2-待审核代码-L2.md")

            output = self.run_t0(root, "--goal", "完成登录功能")

        self.assertEqual(output["state"], "dispatch")
        self.assertEqual(output["mode"], "terminal")
        self.assertEqual(output["next_role"], "T2")
        self.assertEqual(output["command"], "start managed terminals: /taskboard-dev T1, /taskboard-dev T2, /taskboard-dev T3")
        self.assertEqual(output["task"], "TASK-001.v1.T2-待审核代码-L2.md")
        self.assertIn("完成登录功能", output["target"])
        self.assertIn("T2", output["target"])
        self.assertEqual(
            [session["role"] for session in output["managed_sessions"]],
            ["T1", "T2", "T3"],
        )
        self.assertEqual(
            [session["title"] for session in output["managed_sessions"]],
            ["taskboard-T1", "taskboard-T2", "taskboard-T3"],
        )

    def test_goal_without_active_tasks_dispatches_t1_to_create_board_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_t0(root, "--goal", "完成支付模块")

        self.assertEqual(output["state"], "dispatch")
        self.assertEqual(output["next_role"], "T1")
        self.assertEqual(output["status"], "T1-create-or-revise")
        self.assertEqual(len(output["managed_sessions"]), 3)
        self.assertEqual(output["managed_sessions"][0]["command"], "/taskboard-dev T1")
        self.assertIn("创建或修订", output["target"])

    def test_empty_board_without_goal_requests_t0_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_t0(root)

        self.assertEqual(output["state"], "needs-goal")
        self.assertEqual(output["next_role"], "T0")
        self.assertEqual(output["command"], "/taskboard-dev T0")
        self.assertEqual(output["task"], "none")
        self.assertIn("用户目标", output["target"])
        self.assertEqual(output["managed_sessions"], [])


if __name__ == "__main__":
    unittest.main()
