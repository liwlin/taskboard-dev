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

    def test_status_reports_next_action_across_overnight_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_cold_resume_root(root)

            initial_code, initial = self.run_overnight(root, "status", "--now-epoch", "1000")
            self.run_overnight(root, "start", "--run-id", "field-status", "--now-epoch", "1000")
            started_code, started = self.run_overnight(
                root,
                "status",
                "--now-epoch",
                "1100",
                "--min-elapsed-seconds",
                "300",
            )
            ready_code, ready = self.run_overnight(
                root,
                "status",
                "--now-epoch",
                "1400",
                "--min-elapsed-seconds",
                "300",
            )
            self.run_overnight(root, "resume", "--now-epoch", "1400", "--min-elapsed-seconds", "300")
            resumed_code, resumed = self.run_overnight(root, "status", "--now-epoch", "1500")
            remove_active_tasks(root)
            make_complete_live_milestone(root)
            self.run_overnight(root, "verify", "--min-elapsed-seconds", "300")
            passed_code, passed = self.run_overnight(root, "status")

        self.assertEqual(initial_code, 0, initial)
        self.assertEqual(initial["state"], "not-started")
        self.assertEqual(initial["next_stage"], "start")
        self.assertTrue(initial["next_command"].endswith(" start"), initial["next_command"])
        self.assertNotIn("<field-run-id>", initial["next_command"])

        self.assertEqual(started_code, 0, started)
        self.assertEqual(started["state"], "waiting-overnight")
        self.assertEqual(started["next_stage"], "resume")
        self.assertEqual(started["elapsed_seconds"], 100)
        self.assertIn("resume", started["next_command"])

        self.assertEqual(ready_code, 0, ready)
        self.assertEqual(ready["state"], "ready-to-resume")
        self.assertEqual(ready["next_stage"], "resume")
        self.assertEqual(ready["elapsed_seconds"], 400)

        self.assertEqual(resumed_code, 0, resumed)
        self.assertEqual(resumed["state"], "ready-to-verify")
        self.assertEqual(resumed["next_stage"], "verify")
        self.assertIn("verify", resumed["next_command"])

        self.assertEqual(passed_code, 0, passed)
        self.assertEqual(passed["state"], "passed")
        self.assertEqual(passed["next_stage"], "none")
        self.assertEqual(passed["next_command"], "")

    def test_status_reports_start_gate_readiness_and_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty_root = Path(tmp) / "empty"
            empty_root.mkdir()
            blocked_code, blocked = self.run_overnight(empty_root, "status")

            ready_root = Path(tmp) / "ready"
            ready_root.mkdir()
            prepare_cold_resume_root(ready_root)
            ready_code, ready = self.run_overnight(ready_root, "status")

        self.assertEqual(blocked_code, 0, blocked)
        self.assertEqual(blocked["next_stage"], "start")
        self.assertFalse(blocked["next_ready"])
        self.assertIn("no selected worker TASK for cold resume", blocked["next_blockers"])
        self.assertEqual(blocked["next_gate"], "cold-resume-acceptance")

        self.assertEqual(ready_code, 0, ready)
        self.assertEqual(ready["next_stage"], "start")
        self.assertTrue(ready["next_ready"])
        self.assertEqual(ready["next_blockers"], [])
        self.assertEqual(ready["next_gate"], "cold-resume-acceptance")

    def test_status_guides_blocked_field_run_back_to_t0_preparation(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty_root = Path(tmp) / "empty"
            empty_root.mkdir()
            blocked_code, blocked = self.run_overnight(empty_root, "status")

            ready_root = Path(tmp) / "ready"
            ready_root.mkdir()
            prepare_cold_resume_root(ready_root)
            ready_code, ready = self.run_overnight(ready_root, "status")

        self.assertEqual(blocked_code, 0, blocked)
        self.assertEqual(blocked["prepare_state"], "needed")
        self.assertIn("taskboard_start.py", blocked["prepare_command"])
        self.assertIn("--goal", blocked["prepare_command"])
        self.assertIn("<user goal>", blocked["prepare_command"])
        self.assertIn("T0", blocked["prepare_reason"])
        self.assertNotIn("taskboard-T1", blocked["prepare_command"])
        self.assertNotIn("taskboard-T2", blocked["prepare_command"])
        self.assertNotIn("taskboard-T3", blocked["prepare_command"])

        self.assertEqual(ready_code, 0, ready)
        self.assertEqual(ready["prepare_state"], "not-needed")
        self.assertEqual(ready["prepare_command"], "")

    def test_status_prepare_command_uses_saved_t0_goal_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".taskboard" / "t0"
            state_dir.mkdir(parents=True)
            (state_dir / "goal.json").write_text(
                json.dumps({"kind": "taskboard-t0-goal", "goal": "Ship demo"}),
                encoding="utf-8",
            )

            code, payload = self.run_overnight(root, "status")

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["prepare_state"], "needed")
        self.assertIn('--goal "Ship demo"', payload["prepare_command"])
        self.assertNotIn("<user goal>", payload["prepare_command"])

    def test_status_prepare_command_accepts_goal_argument_without_saved_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            code, payload = self.run_overnight(root, "status", "--goal", "Ship demo")

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["prepare_state"], "needed")
        self.assertIn('--goal "Ship demo"', payload["prepare_command"])
        self.assertNotIn("<user goal>", payload["prepare_command"])
        self.assertFalse((root / ".taskboard" / "t0" / "goal.json").exists())

    def test_status_accepts_format_after_subcommand_for_recovery_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_cold_resume_root(root)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root), "status", "--format", "json"],
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

        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["state"], "not-started")
        self.assertEqual(payload["next_stage"], "start")


if __name__ == "__main__":
    unittest.main()
