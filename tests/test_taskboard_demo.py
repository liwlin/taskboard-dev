from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEMO_SCRIPT = ROOT / "scripts" / "taskboard_demo.py"
LOOP_SCRIPT = ROOT / "scripts" / "taskboard_loop.py"


class TaskboardDemoTest(unittest.TestCase):
    def run_demo(self, root: Path, *args: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(DEMO_SCRIPT), "--root", str(root), "--format", "json", *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return json.loads(result.stdout)

    def run_loop(self, root: Path) -> list[dict]:
        result = subprocess.run(
            [
                sys.executable,
                str(LOOP_SCRIPT),
                "--root",
                str(root),
                "--goal",
                "Ship demo",
                "--iterations",
                "1",
                "--format",
                "json",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return json.loads(result.stdout)

    def test_demo_board_drives_t0_loop_to_code_review_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            demo = self.run_demo(root, "--with-heartbeats")
            loop = self.run_loop(root)

        self.assertEqual(len(demo["tasks"]), 3)
        payload = loop[0]
        self.assertEqual(payload["session_probe"]["state"], "healthy")
        self.assertEqual(payload["dispatch"]["next_role"], "T2")
        self.assertIn("TASK-003", payload["dispatch"]["task"])
        self.assertEqual(payload["queue_health"]["active_count"], 3)
        self.assertEqual(payload["state"], "active")

    def test_demo_refuses_to_overwrite_existing_docs_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "PROJECT.md").write_text("# Existing\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(DEMO_SCRIPT), "--root", str(root)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("not empty", result.stdout)


if __name__ == "__main__":
    unittest.main()
