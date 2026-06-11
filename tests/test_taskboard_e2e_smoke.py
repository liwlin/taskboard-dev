from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = ROOT / "scripts" / "taskboard_e2e_smoke.py"


class TaskboardE2ESmokeTest(unittest.TestCase):
    def run_smoke(self, root: Path, *args: str) -> dict:
        result = subprocess.run(
            [
                sys.executable,
                str(SMOKE_SCRIPT),
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

    def test_smoke_proves_t0_to_worker_acknowledgement(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.run_smoke(Path(tmp))

        self.assertEqual(payload["state"], "passed")
        self.assertEqual(payload["kind"], "taskboard-e2e-smoke")
        self.assertIn(payload["first_dispatch"]["role"], {"T1", "T2", "T3"})
        self.assertNotEqual(payload["first_dispatch"]["task"], "none")
        self.assertGreaterEqual(payload["first_dispatch"]["target_file_count"], 1)
        self.assertEqual(payload["worker_cycle"]["action"], "work")
        self.assertEqual(payload["worker_cycle"]["task"], payload["first_dispatch"]["task"])
        self.assertEqual(payload["worker_heartbeat"]["assignment_id"], payload["acknowledged_assignment"]["expected_assignment_id"])
        self.assertEqual(payload["acknowledged_assignment"]["state"], "acknowledged")
        self.assertEqual(payload["completion"]["state"], "complete-ready")
        self.assertTrue(payload["completion"]["completion_ready"])
        self.assertGreaterEqual(payload["completion"]["archived_count"], 1)
        self.assertEqual(payload["completion"]["missing_evidence"], [])
        self.assertEqual(payload["final_dispatch"]["state"], "complete")
        self.assertEqual(payload["progress"]["state"], "complete")
        self.assertIn("T0 progress reports the assignment as acknowledged", payload["evidence"])
        self.assertIn("Completion audit reached complete-ready", payload["evidence"])
        self.assertIn("T0 progress reports the goal as complete", payload["evidence"])

    def test_smoke_refuses_existing_docs_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "PROJECT.md").write_text("# Existing\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SMOKE_SCRIPT), "--root", str(root)],
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
