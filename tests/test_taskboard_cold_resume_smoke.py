from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_cold_resume_smoke.py"


class TaskboardColdResumeSmokeTest(unittest.TestCase):
    def run_smoke(self, root: Path, *args: str) -> dict:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(root),
                "--format",
                "json",
                *args,
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return json.loads(result.stdout)

    def test_smoke_proves_fresh_worker_recovers_active_task_from_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.run_smoke(Path(tmp))

        self.assertEqual(payload["kind"], "taskboard-cold-resume-smoke")
        self.assertEqual(payload["state"], "passed")
        self.assertEqual(payload["dispatch"]["role"], "T3")
        self.assertEqual(payload["dispatch"]["task"], "TASK-017.v2.T3-待执行.md")
        self.assertEqual(payload["assignment"]["state"], "unassigned")
        self.assertEqual(payload["session_probe"]["state"], "attention")
        self.assertEqual(payload["progress"]["next_role"], "T3")
        self.assertEqual(payload["target_file"]["role"], "T3")
        self.assertTrue(payload["target_file"]["contains_cold_resume_contract"])
        self.assertTrue(payload["target_file"]["contains_current_instruction_contract"])
        self.assertIn("src/login.py", payload["scoped_git_status"])
        self.assertIn("Current Instruction", payload["task_evidence"])
        self.assertIn("unchecked Pending", payload["evidence"])
        self.assertIn("T0 selected T3 from active TASKBOARD state", payload["evidence"])
        self.assertIn("No user-managed worker terminal is required", payload["evidence"])

    def test_smoke_refuses_existing_docs_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "PROJECT.md").write_text("# Existing\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("not empty", result.stdout)


if __name__ == "__main__":
    unittest.main()
