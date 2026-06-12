from pathlib import Path
import hashlib
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


def text_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def role_prompt(role: str) -> str:
    return "\n".join(
        [
            f"You are taskboard-{role}",
            f"Read SKILL.md and references/role-{role.lower()}.md",
            "Use this embedded target as the T0-managed role inbox.",
            "Do not inherit T0 private reasoning",
            "Return progress only through TASKBOARD",
            "T0 input boundary:",
            "Startup skill gate:",
            "Worker loop contract:",
            "Idle recheck contract:",
        ]
    )


def write_real_native_subagent_evidence(root: Path) -> None:
    t0_dir = root / ".taskboard" / "t0"
    t0_dir.mkdir(parents=True, exist_ok=True)
    prompts = [{"role": role, "prompt": role_prompt(role)} for role in ("T1", "T2", "T3")]
    write_file(
        root,
        ".taskboard/t0/subagent-fallback.json",
        json.dumps(
            {
                "kind": "taskboard-subagent-fallback-packet",
                "subagent_prompt_count": 3,
                "subagent_prompt_roles": ["T1", "T2", "T3"],
                "subagent_fallback": {
                    "kind": "taskboard-subagent-fallback",
                    "subagent_prompts": prompts,
                },
            },
            sort_keys=True,
        ),
    )
    roles = {}
    for role in ("T1", "T2", "T3"):
        agent_id = f"019eb736-{role.lower()}-real-agent"
        prompt = role_prompt(role)
        summary = f"{role} completed through a real native subagent"
        roles[role] = {
            "role": role,
            "status": "completed",
            "agent_id": agent_id,
            "summary": summary,
            "completed_at": "2026-06-12T00:00:00Z",
            "spawn_receipt": {
                "role": role,
                "agent_id": agent_id,
                "spawn_tool": "multi_agent_v1.spawn_agent",
                "agent_nickname": f"{role} managed child",
                "prompt_hash": text_hash(prompt),
                "native_status": "spawned",
                "recorded_at": "2026-06-12T00:00:00Z",
            },
            "completion_receipt": {
                "role": role,
                "agent_id": agent_id,
                "native_status": "completed",
                "recorded_at": "2026-06-12T00:01:00Z",
            },
            "result_receipt": {
                "role": role,
                "agent_id": agent_id,
                "result_tool": "multi_agent_v1.wait_agent",
                "result_status": "completed",
                "native_status": "completed",
                "summary_hash": text_hash(summary),
                "recorded_at": "2026-06-12T00:01:00Z",
            },
            "attempts": [],
        }
    write_file(
        root,
        ".taskboard/t0/subagents.json",
        json.dumps(
            {
                "kind": "taskboard-subagent-dispatch-state",
                "version": 1,
                "roles": roles,
            },
            sort_keys=True,
        ),
    )


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
    write_real_native_subagent_evidence(root)
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
        native_state = checks["real-native-subagent-field-run"]["state"]
        self.assertIn(native_state, {"missing", "passed"})
        if native_state == "missing":
            self.assertIn("real native-subagent field run", payload["remaining_gaps"])
        else:
            self.assertNotIn("real native-subagent field run", payload["remaining_gaps"])
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
        if "check=real-native-subagent-field-run state=missing" in result.stdout:
            self.assertIn("gap=real native-subagent field run", result.stdout)
        else:
            self.assertIn("check=real-native-subagent-field-run state=passed", result.stdout)
            self.assertNotIn("gap=real native-subagent field run", result.stdout)

    def test_readiness_requires_real_native_subagent_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_ready_repo(root)
            (root / ".taskboard" / "t0" / "subagents.json").unlink()

            returncode, payload = self.run_readiness("--root", str(root))

        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["state"], "field-verification-required")
        self.assertIn("real native-subagent field run", payload["remaining_gaps"])
        checks = {item["id"]: item for item in payload["checks"]}
        self.assertEqual(checks["real-native-subagent-field-run"]["state"], "missing")

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
