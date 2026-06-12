from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_framework_readiness.py"


def write_file(root: Path, relative: str, text: str = "") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_minimal_ready_repo(root: Path) -> None:
    write_file(root, "scripts/taskboard_start.py")
    write_file(root, "README.md", "taskboard_start.py --goal\nlaunch_probe_recommended_backend\nCross-day cold resume\n")
    write_file(root, "tests/test_taskboard_start.py", "test_starter_auto_mode_runs_until_completion_by_default\n")
    write_file(root, "references/role-t0.md", "T0 is manager\n")
    write_file(root, "scripts/taskboard_t0_boundary_smoke.py")
    write_file(root, "tests/test_taskboard_t0_boundary_smoke.py", "test_smoke_fails_when_t0_creates_worker_owned_context\n")
    write_file(root, "scripts/taskboard_loop.py")
    write_file(root, "scripts/taskboard_sessions.py")
    write_file(root, "scripts/taskboard_watchdog.py")
    write_file(root, "scripts/taskboard_progress.py", "No user action required\ncold_resume_readiness\n")
    write_file(root, "tests/test_taskboard_progress.py", "test_progress_surfaces_assignment_recovery_without_user_role_management\n")
    write_file(root, "scripts/taskboard.py", "taskboard-launch-probe\n")
    write_file(root, "scripts/taskboard_subagents.py")
    write_file(root, "scripts/taskboard_subagent_smoke.py")
    write_file(root, "scripts/taskboard_subagent_acceptance.py")
    write_file(root, "scripts/taskboard_live_milestone_acceptance.py")
    write_file(root, "scripts/taskboard_cold_resume_smoke.py")
    write_file(root, "scripts/taskboard_cold_resume_acceptance.py")
    write_file(root, "scripts/taskboard_overnight_field_run.py")
    write_file(
        root,
        "tests/test_taskboard_cold_resume_acceptance.py",
        "test_acceptance_passes_with_real_t0_progress_and_cold_resume_evidence\n",
    )
    write_file(
        root,
        "tests/test_taskboard_live_milestone_acceptance.py",
        "test_acceptance_rejects_smoke_placeholders_and_checkout_conflict\n",
    )
    write_file(root, "scripts/package.sh", "taskboard_cold_resume_acceptance.py\ntaskboard_overnight_field_run.py\n")
    write_file(root, "scripts/sync-local-skill.ps1")
    write_file(root, "scripts/verify_release_consistency.py")
    write_file(root, "scripts/verify_t0_contract.py")
    write_file(
        root,
        ".taskboard/t0/overnight-field-run.json",
        json.dumps(
            {
                "kind": "taskboard-overnight-field-run",
                "state": "passed",
                "resume": {
                    "elapsed_seconds": 28800,
                    "min_elapsed_seconds": 28800,
                    "cold_resume_acceptance_state": "passed",
                },
                "verification": {
                    "live_milestone_acceptance_state": "passed",
                    "elapsed_seconds": 28800,
                },
            },
            sort_keys=True,
        ),
    )


class TaskboardFrameworkReadinessTest(unittest.TestCase):
    def run_readiness(self, *args: str) -> tuple[int, dict[str, object]]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(ROOT), "--format", "json", *args],
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

    def test_readiness_maps_user_goal_to_evidence_and_remaining_field_gap(self):
        returncode, payload = self.run_readiness()

        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["kind"], "taskboard-framework-readiness")
        self.assertEqual(payload["state"], "field-verification-required")
        self.assertFalse(payload["goal_complete"])
        self.assertIn("real overnight field run", payload["remaining_gaps"])

        checks = {item["id"]: item for item in payload["checks"]}
        for check_id in (
            "one-command-t0-entry",
            "t0-manager-only-boundary",
            "automatic-worker-management",
            "backend-selection-and-fallback",
            "cross-day-cold-resume",
            "field-acceptance-gates",
            "release-and-installation-consistency",
        ):
            self.assertEqual(checks[check_id]["state"], "passed", check_id)

        self.assertEqual(checks["real-overnight-field-run"]["state"], "missing")
        self.assertIn("taskboard_start.py --goal", checks["one-command-t0-entry"]["evidence"])
        self.assertIn("taskboard_cold_resume_acceptance.py", checks["cross-day-cold-resume"]["evidence"])
        self.assertIn("taskboard_live_milestone_acceptance.py", checks["field-acceptance-gates"]["evidence"])
        self.assertIn("T0 manager-only", payload["boundary"])

    def test_readiness_text_output_names_missing_field_run(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(ROOT)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("state=field-verification-required", result.stdout)
        self.assertIn("gap=real overnight field run", result.stdout)

    def test_readiness_accepts_verified_overnight_field_run_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_ready_repo(root)

            returncode, payload = self.run_readiness("--root", str(root))

        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["state"], "ready")
        self.assertTrue(payload["goal_complete"])
        checks = {item["id"]: item for item in payload["checks"]}
        self.assertEqual(checks["real-overnight-field-run"]["state"], "passed")
        self.assertIn("taskboard_overnight_field_run.py", checks["real-overnight-field-run"]["evidence"])


if __name__ == "__main__":
    unittest.main()
