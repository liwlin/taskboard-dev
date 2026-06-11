#!/usr/bin/env python3
"""Smoke-test the T0-to-worker acknowledgement path in a temporary TASKBOARD."""

from argparse import ArgumentParser
from pathlib import Path
import json
import shutil
import sys
import tempfile
from typing import Optional

from taskboard import cycle_payload, status_payload
from taskboard_demo import GOAL as DEMO_GOAL, create_demo
from taskboard_loop import default_event_log_file, default_state_file, run_loop
from taskboard_progress import report_progress
from taskboard_sessions import write_heartbeat
from taskboard_t0 import default_target_dir


DEFAULT_AGENT_TEMPLATE = 'claude "{target}"'


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
        runtime_metadata={"auto_mode": True, "starter_mode": "e2e-smoke"},
        fallback_launchers=[],
        agent_preflight_enabled=True,
        agent_preflight_command=None,
    )
    if not results:
        raise RuntimeError("T0 supervisor returned no payloads")
    return results[-1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_smoke(root: Path, goal: str, force: bool) -> dict[str, object]:
    root = root.resolve()
    demo = create_demo(root, force=force, with_heartbeats=False)
    first = supervisor_once(root, goal)

    first_dispatch = first.get("dispatch", {})
    require(isinstance(first_dispatch, dict), "first T0 dispatch is missing")
    role = str(first_dispatch.get("next_role") or "")
    task = str(first_dispatch.get("task") or "")
    require(role in {"T1", "T2", "T3"}, f"expected worker role, got {role!r}")
    require(task != "none", "expected a concrete TASKBOARD task")
    target_files = first.get("target_files", [])
    require(isinstance(target_files, list) and target_files, "T0 did not write worker target files")

    worker_cycle = cycle_payload(root, role, sleep_seconds=0)
    worker_next = worker_cycle.get("next", {})
    require(isinstance(worker_next, dict), "worker cycle did not return a next payload")
    require(worker_next.get("task") == task, "worker cycle did not select T0's assigned task")
    assignment_id = f"{role}:{task}"
    heartbeat = write_heartbeat(
        root,
        role,
        f"taskboard-{role}",
        "acknowledged-task",
        None,
        task=task,
        assignment_id=assignment_id,
    )

    acknowledged = supervisor_once(root, goal)
    assignment = acknowledged.get("assignment", {})
    require(isinstance(assignment, dict), "second T0 assignment is missing")
    require(assignment.get("state") == "acknowledged", "T0 did not observe worker acknowledgement")
    require(assignment.get("expected_assignment_id") == assignment_id, "acknowledged assignment id mismatch")

    progress = report_progress(root)
    status = status_payload(root, stale_minutes=30, goal=goal)
    return {
        "kind": "taskboard-e2e-smoke",
        "state": "passed",
        "root": str(root),
        "goal": goal,
        "demo": demo,
        "first_dispatch": {
            "role": role,
            "task": task,
            "assignment_state": str(first.get("assignment", {}).get("state")),
            "target_file_count": len(target_files),
        },
        "worker_cycle": {
            "role": role,
            "action": worker_cycle.get("action"),
            "task": worker_next.get("task"),
            "should_exit": worker_cycle.get("should_exit"),
        },
        "worker_heartbeat": {
            "role": heartbeat.get("role"),
            "task": heartbeat.get("task"),
            "assignment_id": heartbeat.get("assignment_id"),
            "status": heartbeat.get("status"),
        },
        "acknowledged_assignment": {
            "state": assignment.get("state"),
            "role": assignment.get("role"),
            "task": assignment.get("task"),
            "expected_assignment_id": assignment.get("expected_assignment_id"),
            "reason": assignment.get("reason"),
        },
        "progress": {
            "state": progress.get("state"),
            "next_role": progress.get("next_role"),
            "assignment_state": progress.get("assignment_state"),
            "assignment_role": progress.get("assignment_role"),
            "assignment_task": progress.get("assignment_task"),
            "user_action": progress.get("user_action"),
        },
        "status": {
            "active_count": status.get("queue_health", {}).get("active_count"),
            "next": status.get("next"),
            "completion_ready": status.get("completion", {}).get("completion_ready"),
        },
        "evidence": [
            "T0 accepted one goal and selected a managed worker role",
            "T0 wrote isolated role target files",
            "Worker cycle selected the same task and refreshed liveness",
            "Worker heartbeat acknowledged the T0 assignment",
            "T0 progress reports the assignment as acknowledged",
        ],
    }


def format_text(payload: dict[str, object]) -> str:
    first = payload["first_dispatch"]
    ack = payload["acknowledged_assignment"]
    progress = payload["progress"]
    lines = [
        f"state={payload['state']}",
        f"root={payload['root']}",
        f"goal={payload['goal']}",
        f"first_dispatch={first['role']} {first['task']} target_files={first['target_file_count']}",
        f"worker_cycle_action={payload['worker_cycle']['action']}",
        f"acknowledged_assignment={ack['state']} {ack['role']} {ack['task']}",
        f"progress_state={progress['state']}",
        f"progress_assignment_state={progress['assignment_state']}",
        f"user_action={progress['user_action']}",
        "evidence:",
    ]
    lines.extend(f"- {item}" for item in payload["evidence"])
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Optional root for the smoke TASKBOARD. Defaults to a temporary directory.")
    parser.add_argument("--goal", default=DEMO_GOAL)
    parser.add_argument("--force", action="store_true", help="Overwrite existing demo files under --root/docs")
    parser.add_argument("--keep", action="store_true", help="Keep an automatically-created temporary root for inspection")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    temp_root: Optional[str] = None
    if args.root:
        root = Path(args.root)
    else:
        temp_root = tempfile.mkdtemp(prefix="taskboard-e2e-smoke-")
        root = Path(temp_root)

    try:
        payload = run_smoke(root, args.goal, args.force)
    except (OSError, RuntimeError, FileExistsError, ValueError) as exc:
        if temp_root and not args.keep:
            shutil.rmtree(temp_root, ignore_errors=True)
        print(f"taskboard e2e smoke failed: {exc}", file=sys.stderr)
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
