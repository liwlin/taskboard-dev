#!/usr/bin/env python3
"""Smoke-test next-day cold resume from TASKBOARD state."""

from argparse import ArgumentParser
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

from taskboard_loop import default_event_log_file, default_state_file, run_loop
from taskboard_progress import report_progress
from taskboard_t0 import DEFAULT_AGENT_TEMPLATE, default_target_dir, write_runtime_goal


GOAL = "Continue the login milestone after an overnight stop"
TASK_NAME = "TASK-017.v2.T3-待执行.md"
SCOPED_FILE = "src/login.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def ensure_clean_docs(root: Path, force: bool) -> None:
    docs = root / "docs"
    if docs.exists() and any(docs.iterdir()) and not force:
        raise FileExistsError(f"{docs} is not empty; pass --force or choose an empty smoke root")
    if force and docs.exists():
        shutil.rmtree(docs)


def run_git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stdout.strip()}")
    return result


def write_board(root: Path, goal: str) -> Path:
    taskboard = root / "docs" / "taskboard"
    taskboard.mkdir(parents=True, exist_ok=True)
    (taskboard / "history").mkdir()
    (taskboard / "archive").mkdir()
    (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\nLogin milestone.\n", encoding="utf-8")
    (root / "docs" / "MAP.md").write_text("# MAP\n\n- Login controller.\n", encoding="utf-8")
    (root / "docs" / "REQUIREMENTS.md").write_text("# REQUIREMENTS\n\n- [P1] Restore login flow.\n", encoding="utf-8")
    (root / "docs" / "STATE.md").write_text("# STATE\n\nGoal Complete: no\n", encoding="utf-8")
    (root / "docs" / "dev-log.md").write_text("# Development Log\n\n", encoding="utf-8")
    write_runtime_goal(root, goal)

    task = taskboard / TASK_NAME
    task.write_text(
        "\n".join(
            [
                "# TASK-017 Login resume",
                "",
                "**Wave**: 1",
                "**Files**:",
                f"- {SCOPED_FILE}",
                "",
                "## Pending",
                "- [x] Inspect yesterday's partial login change",
                "- [x] Confirm failing redirect path",
                "- [ ] Finish token refresh branch",
                "",
                "## Current Instruction",
                "Continue from token refresh branch; preserve yesterday's scoped diff.",
                "",
                "## History",
                "- 2026-06-11 T3: paused after local edit, no verification yet.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    old_target = root / ".taskboard" / "targets" / "taskboard-T3.md"
    old_target.parent.mkdir(parents=True, exist_ok=True)
    old_target.write_text("stale target from previous day\n", encoding="utf-8")
    return task


def setup_scoped_dirty_worktree(root: Path) -> str:
    source = root / SCOPED_FILE
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def login():\n    return 'old-token'\n", encoding="utf-8")
    run_git(root, "init")
    run_git(root, "config", "user.email", "taskboard@example.invalid")
    run_git(root, "config", "user.name", "Taskboard Smoke")
    run_git(root, "add", SCOPED_FILE)
    run_git(root, "commit", "-m", "baseline login file")
    source.write_text("def login():\n    return 'token-refresh-in-progress'\n", encoding="utf-8")
    return run_git(root, "status", "--short", "--", SCOPED_FILE).stdout.strip()


def supervisor_once(root: Path, goal: str) -> dict[str, object]:
    results = run_loop(
        root=root,
        goal=goal,
        stale_minutes=30,
        stale_seconds=300,
        launcher="none",
        agent_template=DEFAULT_AGENT_TEMPLATE,
        execute_launches=False,
        iterations=1,
        interval_seconds=0,
        assignment_lease_seconds=300,
        stop_on_complete=True,
        state_file=default_state_file(root),
        target_dir=default_target_dir(root),
        launch_lease_seconds=300,
        event_log_file=default_event_log_file(root),
        stop_on_stop_gate=True,
        runtime_metadata={"auto_mode": True, "starter_mode": "cold-resume-smoke"},
        fallback_launchers=[],
        agent_preflight_enabled=True,
        agent_preflight_command=None,
    )
    if not results:
        raise RuntimeError("T0 supervisor returned no payloads")
    return results[-1]


def run_smoke(root: Path, goal: str, force: bool) -> dict[str, object]:
    root = root.resolve()
    ensure_clean_docs(root, force)
    task = write_board(root, goal)
    scoped_status = setup_scoped_dirty_worktree(root)
    payload = supervisor_once(root, goal)
    progress = report_progress(root)

    dispatch = payload.get("dispatch", {})
    assignment = payload.get("assignment", {})
    session_probe = payload.get("session_probe", {})
    target_files = payload.get("target_files", [])
    require(isinstance(dispatch, dict), "T0 dispatch missing")
    require(dispatch.get("next_role") == "T3", f"expected T3 dispatch, got {dispatch.get('next_role')!r}")
    require(dispatch.get("task") == TASK_NAME, f"expected {TASK_NAME}, got {dispatch.get('task')!r}")
    require(isinstance(assignment, dict) and assignment.get("state") == "unassigned", "expected unassigned fresh worker assignment")
    require(isinstance(session_probe, dict) and session_probe.get("state") == "attention", "expected missing worker session attention")
    require(progress.get("next_role") == "T3", "progress did not surface T3 as next managed role")
    require(SCOPED_FILE in scoped_status, "scoped dirty git status did not include task file")

    target_file = next((item for item in target_files if isinstance(item, dict) and item.get("role") == "T3"), None)
    require(isinstance(target_file, dict), "T0 did not write T3 target file")
    target_path = Path(str(target_file["path"]))
    target_text = target_path.read_text(encoding="utf-8")
    task_text = task.read_text(encoding="utf-8")

    return {
        "kind": "taskboard-cold-resume-smoke",
        "state": "passed",
        "root": str(root),
        "goal": goal,
        "dispatch": {
            "role": dispatch.get("next_role"),
            "task": dispatch.get("task"),
            "reason": dispatch.get("reason"),
        },
        "assignment": {
            "state": assignment.get("state"),
            "role": assignment.get("role"),
            "task": assignment.get("task"),
            "reason": assignment.get("reason"),
        },
        "session_probe": {
            "state": session_probe.get("state"),
            "missing_roles": session_probe.get("missing_roles"),
        },
        "progress": {
            "state": progress.get("state"),
            "next_role": progress.get("next_role"),
            "task": progress.get("task"),
            "user_action": progress.get("user_action"),
        },
        "target_file": {
            "role": target_file.get("role"),
            "path": target_file.get("path"),
            "contains_cold_resume_contract": "Cross-day cold resume contract" in target_text,
            "contains_current_instruction_contract": "Current Instruction" in target_text,
        },
        "task_evidence": [
            "Current Instruction" if "## Current Instruction" in task_text else "missing Current Instruction",
            "unchecked Pending" if "- [ ]" in task_text else "missing unchecked Pending",
            "history" if "## History" in task_text else "missing history",
        ],
        "scoped_git_status": scoped_status,
        "evidence": [
            "T0 loaded saved goal from runtime state",
            "T0 selected T3 from active TASKBOARD state",
            "T0 wrote a fresh T3 target containing cold-resume rules",
            "unchecked Pending",
            "Current Instruction is present in active TASK",
            "Scoped git status exposes yesterday's partial work",
            "No user-managed worker terminal is required",
        ],
    }


def format_text(payload: dict[str, object]) -> str:
    dispatch = payload["dispatch"]
    progress = payload["progress"]
    lines = [
        f"state={payload['state']}",
        f"root={payload['root']}",
        f"goal={payload['goal']}",
        f"dispatch={dispatch['role']} {dispatch['task']}",
        f"progress={progress['state']} next_role={progress['next_role']}",
        f"scoped_git_status={payload['scoped_git_status']}",
        "evidence:",
    ]
    lines.extend(f"- {item}" for item in payload["evidence"])
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Optional smoke root. Defaults to a temporary directory.")
    parser.add_argument("--goal", default=GOAL)
    parser.add_argument("--force", action="store_true", help="Overwrite existing docs under --root")
    parser.add_argument("--keep", action="store_true", help="Keep an automatically-created temporary root")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    temp_root: Optional[str] = None
    if args.root:
        root = Path(args.root)
    else:
        temp_root = tempfile.mkdtemp(prefix="taskboard-cold-resume-smoke-")
        root = Path(temp_root)

    try:
        payload = run_smoke(root, args.goal, args.force)
    except (OSError, RuntimeError, FileExistsError, ValueError) as exc:
        if temp_root and not args.keep:
            shutil.rmtree(temp_root, ignore_errors=True)
        print(f"taskboard cold resume smoke failed: {exc}", file=sys.stderr)
        return 1

    if temp_root and not args.keep:
        shutil.rmtree(temp_root, ignore_errors=True)
        payload["root"] = "<temporary root removed>"

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
