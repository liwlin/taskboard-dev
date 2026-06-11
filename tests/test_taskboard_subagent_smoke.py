from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_subagent_smoke.py"


class TaskboardSubagentSmokeTest(unittest.TestCase):
    def run_smoke(self, *args: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--format", "json", *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return json.loads(result.stdout)

    def test_smoke_proves_subagent_ack_done_retry_control_plane(self):
        payload = self.run_smoke()

        self.assertEqual(payload["kind"], "taskboard-subagent-smoke")
        self.assertEqual(payload["state"], "passed")
        self.assertEqual(payload["plan"]["mode"], "subagent")
        self.assertEqual(payload["plan"]["launch_command_count"], 0)
        self.assertEqual(payload["plan"]["subagent_prompt_roles"], ["T1", "T2", "T3"])
        self.assertEqual(payload["initial"]["pending_roles"], ["T1", "T2", "T3"])
        self.assertEqual(payload["dispatches"]["T1"]["done"]["status"], "completed")
        self.assertEqual(payload["dispatches"]["T2"]["failure"]["status"], "failed")
        self.assertEqual(payload["dispatches"]["T2"]["retry"]["status"], "retry-pending")
        self.assertEqual(payload["dispatches"]["T2"]["retry"]["attempt_count"], 1)
        self.assertEqual(payload["dispatches"]["T2"]["retry_next_role"], "T2")
        self.assertEqual(payload["dispatches"]["T2"]["done"]["status"], "completed")
        self.assertEqual(payload["dispatches"]["T3"]["done"]["status"], "completed")
        self.assertEqual(payload["final"]["pending_roles"], [])
        self.assertEqual(payload["final"]["failed_roles"], [])
        self.assertEqual(payload["final"]["completed_roles"], ["T1", "T2", "T3"])
        self.assertEqual(payload["final"]["next_state"], "complete")
        self.assertIn("T0 subagent fail/retry preserved the failed T2 attempt and requeued T2", payload["evidence"])

    def test_smoke_refuses_existing_docs_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "PROJECT.md").write_text("# Existing\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root), "--format", "json"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stdout)
        self.assertIn("--force", result.stdout)


if __name__ == "__main__":
    unittest.main()
