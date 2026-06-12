from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from tests.test_taskboard_cold_resume_acceptance import (
    init_git_with_dirty_file,
    write_active_t3_task,
    write_t0_runtime,
)
from tests.test_taskboard_live_milestone_acceptance import make_complete_live_milestone


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_overnight_field_run.py"


def remove_active_tasks(root: Path) -> None:
    taskboard = root / "docs" / "taskboard"
    if not taskboard.exists():
        return
    for path in taskboard.glob("TASK-*.md"):
        path.unlink()


def prepare_cold_resume_root(root: Path) -> str:
    init_git_with_dirty_file(root, "src/login.py")
    task_name = write_active_t3_task(root)
    write_t0_runtime(root, task_name)
    return task_name


class TaskboardOvernightFieldRunTest(unittest.TestCase):
    def run_overnight(self, root: Path, *args: str) -> tuple[int, dict[str, object]]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), "--format", "json", *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(result.stdout) from exc
        return result.returncode, payload

    def test_start_resume_and_verify_records_real_overnight_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_name = prepare_cold_resume_root(root)

            start_code, start_payload = self.run_overnight(
                root,
                "start",
                "--run-id",
                "field-2026-06-12",
                "--now-epoch",
                "1000",
            )
            resume_code, resume_payload = self.run_overnight(
                root,
                "resume",
                "--now-epoch",
                "3700",
                "--min-elapsed-seconds",
                "1800",
            )

            remove_active_tasks(root)
            make_complete_live_milestone(root)
            verify_code, verify_payload = self.run_overnight(
                root,
                "verify",
                "--min-elapsed-seconds",
                "1800",
            )

            marker = json.loads((root / ".taskboard" / "t0" / "overnight-field-run.json").read_text(encoding="utf-8"))

        self.assertEqual(start_code, 0, start_payload)
        self.assertEqual(start_payload["state"], "started")
        self.assertEqual(start_payload["run_id"], "field-2026-06-12")
        self.assertEqual(start_payload["cold_resume_acceptance"]["progress"]["task"], task_name)
        self.assertIn("must not launch workers", start_payload["boundary"])

        self.assertEqual(resume_code, 0, resume_payload)
        self.assertEqual(resume_payload["state"], "resume-verified")
        self.assertGreaterEqual(resume_payload["elapsed_seconds"], 1800)
        self.assertEqual(resume_payload["cold_resume_acceptance"]["state"], "passed")

        self.assertEqual(verify_code, 0, verify_payload)
        self.assertEqual(verify_payload["state"], "passed")
        self.assertEqual(verify_payload["live_milestone_acceptance"]["state"], "passed")
        self.assertTrue(any("live milestone acceptance passed" in item for item in verify_payload["evidence"]))
        self.assertEqual(marker["state"], "passed")
        self.assertEqual(marker["resume"]["cold_resume_acceptance_state"], "passed")
        self.assertEqual(marker["verification"]["live_milestone_acceptance_state"], "passed")

    def test_resume_rejects_too_short_elapsed_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_cold_resume_root(root)

            start_code, _ = self.run_overnight(
                root,
                "start",
                "--run-id",
                "field-short",
                "--now-epoch",
                "1000",
            )
            resume_code, resume_payload = self.run_overnight(
                root,
                "resume",
                "--now-epoch",
                "1010",
                "--min-elapsed-seconds",
                "300",
            )

        self.assertEqual(start_code, 0)
        self.assertEqual(resume_code, 1)
        self.assertEqual(resume_payload["state"], "failed")
        self.assertTrue(any("elapsed_seconds below required minimum" in item for item in resume_payload["failures"]), resume_payload)


if __name__ == "__main__":
    unittest.main()
