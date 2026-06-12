from pathlib import Path
import json
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_framework_readiness.py"


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


if __name__ == "__main__":
    unittest.main()
