from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_live_milestone_acceptance.py"


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_event(root: Path, payload: dict[str, object]) -> None:
    path = root / ".taskboard" / "t0" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def make_complete_live_milestone(root: Path) -> None:
    archive = root / "docs" / "taskboard" / "archive"
    archive.mkdir(parents=True)
    (archive / "TASK-001.v1.done.md").write_text(
        "# TASK-001\n\nImplemented by T3 and approved by T2.\n",
        encoding="utf-8",
    )
    (root / "docs" / "STATE.md").write_text(
        "# STATE\n\n**Goal Complete**: yes\n\n- T0-managed milestone accepted.\n",
        encoding="utf-8",
    )
    (root / "docs" / "dev-log.md").write_text(
        "# Development Log\n\n- TASK-001 completed by T3 and reviewed by T2 under T0.\n",
        encoding="utf-8",
    )
    write_json(root / ".taskboard" / "t0" / "latest.json", {
        "kind": "taskboard-t0-supervisor",
        "state": "complete",
        "auto_mode": True,
        "starter_mode": "auto",
        "goal": "Ship live milestone",
        "completion_ready": True,
        "completion_audit": {"state": "complete-ready", "completion_ready": True},
        "checkout_owner": {"state": "owned", "owner_id": "t0-live-owner"},
    })
    for role in ("T1", "T2", "T3"):
        write_json(root / ".taskboard" / "sessions" / f"taskboard-{role}.json", {
            "kind": "taskboard-session-heartbeat",
            "role": role,
            "agent_id": f"live-agent-{role.lower()}-a7f4",
            "status": "completed",
            "task": "TASK-001.v1.done.md",
            "assignment_id": f"{role}:TASK-001.v1.done.md",
            "summary": f"{role} finished its T0-managed responsibility",
            "updated_at": "2026-06-11T12:00:00Z",
        })
        (root / ".taskboard" / "alive").mkdir(parents=True, exist_ok=True)
        (root / ".taskboard" / "alive" / role).write_text("alive\n", encoding="utf-8")
    append_event(root, {
        "kind": "taskboard-t0-supervisor-event",
        "state": "dispatch",
        "auto_mode": True,
        "starter_mode": "auto",
        "assignment_role": "T1",
        "assignment_task": "TASK-001.v1.T1-plan.md",
        "executed_command_count": 3,
        "launch_probe_recommended_backend": "terminal",
    })
    append_event(root, {
        "kind": "taskboard-t0-supervisor-event",
        "state": "complete",
        "auto_mode": True,
        "starter_mode": "auto",
        "completion_ready": True,
        "completion_audit_state": "complete-ready",
        "assignment_role": "T3",
        "assignment_task": "TASK-001.v1.T3-implement.md",
    })


class TaskboardLiveMilestoneAcceptanceTest(unittest.TestCase):
    def run_acceptance(self, root: Path, *args: str) -> tuple[int, dict[str, object]]:
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

    def test_acceptance_passes_when_live_t0_managed_milestone_has_all_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_complete_live_milestone(root)

            returncode, payload = self.run_acceptance(root)

        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["kind"], "taskboard-live-milestone-acceptance")
        self.assertEqual(payload["state"], "passed")
        self.assertEqual(payload["required_roles"], ["T1", "T2", "T3"])
        self.assertEqual(payload["failure_count"], 0)
        self.assertEqual(payload["completion"]["state"], "complete-ready")
        self.assertTrue(payload["t0_control_plane"]["auto_mode"])
        self.assertEqual(payload["roles"]["T1"]["state"], "accepted")
        self.assertTrue(any("archived TASK evidence" in item for item in payload["evidence"]))

    def test_acceptance_fails_when_completion_and_role_evidence_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            (root / "docs" / "dev-log.md").write_text("# Development Log\n", encoding="utf-8")
            append_event(root, {
                "kind": "taskboard-t0-supervisor-event",
                "state": "dispatch",
                "auto_mode": True,
                "starter_mode": "e2e-smoke",
                "assignment_role": "T1",
            })

            returncode, payload = self.run_acceptance(root)

        self.assertEqual(returncode, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertTrue(any("no archived TASK evidence" in item for item in payload["failures"]), payload)
        self.assertTrue(any("T2: missing live worker evidence" in item for item in payload["failures"]), payload)
        self.assertTrue(any("no goal completion sentinel" in item for item in payload["failures"]), payload)
        self.assertTrue(any("starter_mode looks like smoke" in item for item in payload["failures"]), payload)
        self.assertTrue(any("T0 completion observation missing" in item for item in payload["failures"]), payload)

    def test_acceptance_rejects_smoke_placeholders_and_checkout_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_complete_live_milestone(root)
            session = root / ".taskboard" / "sessions" / "taskboard-T3.json"
            payload = json.loads(session.read_text(encoding="utf-8"))
            payload["agent_id"] = "smoke-agent-t3"
            session.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            append_event(root, {
                "kind": "taskboard-t0-supervisor-event",
                "state": "conflict",
                "checkout_owner_state": "conflict",
                "checkout_owner_id": "other-agent",
            })

            returncode, result = self.run_acceptance(root)

        self.assertEqual(returncode, 1)
        self.assertEqual(result["state"], "failed")
        self.assertTrue(any("placeholder evidence" in item for item in result["failures"]), result)
        self.assertTrue(any("checkout owner conflict" in item for item in result["failures"]), result)


if __name__ == "__main__":
    unittest.main()
