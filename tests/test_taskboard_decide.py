from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_decide.py"
LOOP_SCRIPT = ROOT / "scripts" / "taskboard_loop.py"


class TaskboardDecideTest(unittest.TestCase):
    def run_decide(self, root: Path, *args: str) -> dict:
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

    def test_records_user_decision_and_resumes_t1_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = "TASK-009.v2.T1-待决策.md"
            task = taskboard / task_name
            task.write_text(
                "\n".join(
                    [
                        "# Decide rollout",
                        "",
                        "**Wave**: 2",
                        "**Gate**: Product decision",
                        "**Question**: Enable the beta banner?",
                        "**Options**:",
                        "- A: everyone",
                        "- B: admins only",
                        "**Recommended**: B",
                    ]
                ),
                encoding="utf-8",
            )

            payload = self.run_decide(
                root,
                "--decision",
                "Choose B: admins only",
            )
            resumed = taskboard / "TASK-009.v2.T1-方案需修改.md"
            state = root / "docs" / "STATE.md"
            resumed_exists = resumed.exists()
            original_exists = task.exists()
            resumed_text = resumed.read_text(encoding="utf-8")
            state_text = state.read_text(encoding="utf-8")
            loop_result = subprocess.run(
                [
                    sys.executable,
                    str(LOOP_SCRIPT),
                    "--root",
                    str(root),
                    "--goal",
                    "Ship beta banner",
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            loop_output = json.loads(loop_result.stdout)

        self.assertEqual(payload["kind"], "taskboard-t0-decision")
        self.assertEqual(payload["task"], task_name)
        self.assertEqual(payload["resumed_task"], "TASK-009.v2.T1-方案需修改.md")
        self.assertEqual(payload["next_role"], "T1")
        self.assertTrue(payload["recorded"])
        self.assertFalse(original_exists)
        self.assertTrue(resumed_exists)
        self.assertIn("## T0 User Decision", resumed_text)
        self.assertIn("Choose B: admins only", resumed_text)
        self.assertIn("T0 records user decisions only", resumed_text)
        self.assertIn("Choose B: admins only", state_text)
        self.assertEqual(loop_result.returncode, 0, loop_result.stdout)
        self.assertEqual(loop_output[0]["dispatch"]["next_role"], "T1")
        self.assertNotEqual(loop_output[0]["state"], "stop-gate")


if __name__ == "__main__":
    unittest.main()
