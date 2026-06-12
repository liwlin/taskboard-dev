from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_t0_boundary_smoke.py"
sys.path.insert(0, str(ROOT / "scripts"))
import taskboard_t0_boundary_smoke as smoke  # noqa: E402


class TaskboardT0BoundarySmokeTest(unittest.TestCase):
    def run_smoke(self, *args: str) -> tuple[int, Any]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--format", "json", *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        try:
            payload: Any = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = result.stdout
        return result.returncode, payload

    def test_smoke_passes_when_t0_startup_only_writes_control_plane_files(self):
        returncode, payload = self.run_smoke()

        self.assertEqual(returncode, 0, payload)
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["kind"], "taskboard-t0-boundary-smoke")
        self.assertEqual(payload["state"], "passed")
        self.assertEqual(payload["failure_count"], 0)
        self.assertEqual(
            payload["created_files"],
            [
                ".taskboard/t0/events.jsonl",
                ".taskboard/t0/goal.json",
                ".taskboard/t0/latest.json",
                ".taskboard/targets/taskboard-T1.launch.ps1",
                ".taskboard/targets/taskboard-T1.md",
                ".taskboard/targets/taskboard-T2.launch.ps1",
                ".taskboard/targets/taskboard-T2.md",
                ".taskboard/targets/taskboard-T3.launch.ps1",
                ".taskboard/targets/taskboard-T3.md",
            ],
        )
        self.assertIn("T0 did not create PROJECT/MAP/REQUIREMENTS/STATE/dev-log/HANDOFF", payload["evidence"])

    def test_smoke_refuses_non_empty_root_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "existing.txt").write_text("keep\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root), "--format", "json"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not empty", result.stdout)
        self.assertIn("--force", result.stdout)

    def test_smoke_fails_when_t0_creates_worker_owned_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake_run_start(run_root: Path, goal: str):
                (run_root / "docs" / "REQUIREMENTS.md").write_text("# T0 should not write this\n", encoding="utf-8")
                return [{"starter_mode": "dry-check", "executed_commands": []}], "fake"

            with patch("taskboard_t0_boundary_smoke.run_start", fake_run_start):
                payload = smoke.run_smoke(root, "Ship demo", force=True)

        self.assertEqual(payload["state"], "failed")
        self.assertTrue(any("worker-owned context" in item for item in payload["failures"]), payload)


if __name__ == "__main__":
    unittest.main()
