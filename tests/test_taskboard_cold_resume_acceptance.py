from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_cold_resume_acceptance.py"
T3_EXECUTE = "T3-待执行"


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_event(root: Path, payload: dict[str, object]) -> None:
    path = root / ".taskboard" / "t0" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def init_git_with_dirty_file(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("def login():\n    return 'old-token'\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    subprocess.run(
        ["git", "config", "user.email", "taskboard@example.invalid"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Taskboard Cold Resume"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    subprocess.run(["git", "add", relative], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    path.write_text("def login():\n    return 'token-refresh-in-progress'\n", encoding="utf-8")


def write_active_t3_task(root: Path, with_current_instruction: bool = True) -> str:
    taskboard = root / "docs" / "taskboard"
    taskboard.mkdir(parents=True, exist_ok=True)
    task_name = f"TASK-017.v2.{T3_EXECUTE}.md"
    lines = [
        "# TASK-017 Login resume",
        "",
        "**Wave**: 1",
        "**Files**:",
        "- src/login.py",
        "",
        "## Pending",
        "- [x] Inspect partial login change",
        "- [ ] Finish token refresh branch",
        "",
    ]
    if with_current_instruction:
        lines.extend(
            [
                "## Current Instruction",
                "Continue from token refresh branch; preserve the scoped diff.",
                "",
            ]
        )
    lines.extend(
        [
            "## History",
            "- 2026-06-11 T3: paused after local edit.",
            "",
        ]
    )
    (taskboard / task_name).write_text("\n".join(lines), encoding="utf-8")
    return task_name


def write_t0_runtime(root: Path, task_name: str, starter_mode: str = "auto") -> None:
    write_json(
        root / ".taskboard" / "t0" / "latest.json",
        {
            "kind": "taskboard-t0-supervisor-state",
            "goal": "Continue login",
            "updated_at": "2999-01-01T00:00:00Z",
            "latest": {
                "state": "attention",
                "auto_mode": True,
                "starter_mode": starter_mode,
                "dispatch": {"state": "dispatch", "next_role": "T3", "task": task_name},
                "assignment": {
                    "state": "unassigned",
                    "role": "T3",
                    "task": task_name,
                    "reason": "taskboard-T3 is missing",
                },
                "queue_health": {"active_count": 1},
                "session_probe": {"missing_roles": ["T3"], "stale_roles": []},
                "resume_config": {"launcher": "none", "interval_seconds": 60},
            },
        },
    )
    append_event(
        root,
        {
            "kind": "taskboard-t0-supervisor-event",
            "state": "attention",
            "auto_mode": True,
            "starter_mode": starter_mode,
            "next_role": "T3",
            "task": task_name,
            "assignment_state": "unassigned",
            "assignment_role": "T3",
            "assignment_task": task_name,
        },
    )


class TaskboardColdResumeAcceptanceTest(unittest.TestCase):
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

    def test_acceptance_passes_with_real_t0_progress_and_cold_resume_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_with_dirty_file(root, "src/login.py")
            task_name = write_active_t3_task(root)
            write_t0_runtime(root, task_name)

            returncode, payload = self.run_acceptance(root)

        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["kind"], "taskboard-cold-resume-acceptance")
        self.assertEqual(payload["state"], "passed")
        self.assertEqual(payload["failure_count"], 0)
        self.assertEqual(payload["progress"]["next_role"], "T3")
        self.assertEqual(payload["cold_resume"]["state"], "ready")
        self.assertEqual(payload["cold_resume"]["task"], task_name)
        self.assertIn("M src/login.py", payload["cold_resume"]["scoped_git_status"])
        self.assertTrue(any("T0 control-plane evidence found" in item for item in payload["evidence"]))
        self.assertTrue(any("cold-resume readiness accepted" in item for item in payload["evidence"]))

    def test_acceptance_fails_for_smoke_mode_and_missing_current_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_with_dirty_file(root, "src/login.py")
            task_name = write_active_t3_task(root, with_current_instruction=False)
            write_t0_runtime(root, task_name, starter_mode="cold-resume-smoke")

            returncode, payload = self.run_acceptance(root)

        self.assertEqual(returncode, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertTrue(any("starter_mode looks like smoke/test/demo" in item for item in payload["failures"]), payload)
        self.assertTrue(any("Current Instruction" in item for item in payload["failures"]), payload)
        self.assertEqual(payload["cold_resume"]["state"], "attention")


if __name__ == "__main__":
    unittest.main()
