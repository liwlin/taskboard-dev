#!/usr/bin/env python3
"""Report T0-managed TASKBOARD progress for the user."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys
from typing import Optional

from taskboard_loop import default_state_file
from taskboard_t0 import read_goal


T0_PROGRESS_BOUNDARY = (
    "T0 manager-only progress: summarize goal, queue, session, and assignment state for the user; "
    "do not perform design, review, implementation, verification, or commit work."
)


def read_latest_snapshot(root: Path) -> Optional[dict[str, object]]:
    path = default_state_file(root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def build_user_summary(
    state: str,
    goal: str,
    next_role: str,
    task: str,
    assignment_state: str,
    active_count: int,
    launch_failure_count: int = 0,
    suppressed_launch_count: int = 0,
) -> str:
    if launch_failure_count:
        return (
            f"T0 could not launch or recover {launch_failure_count} managed role command(s) "
            f"for goal '{goal}'. T0 should retry or switch launcher mode; this is not T1/T2/T3 user management."
        )
    if suppressed_launch_count:
        return (
            f"T0 is waiting for recent T0 launch attempt(s) to produce worker heartbeats for goal '{goal}'. "
            "It is not duplicating managed terminals while the launch lease is active."
        )
    if state == "needs-supervisor-run":
        return (
            f"T0 has the goal '{goal}' but no supervisor snapshot yet. "
            "Start or resume T0; this does not ask you to manage T1/T2/T3."
        )
    if state == "complete":
        return f"T0 sees the goal '{goal}' as complete and is ready to summarize completion to the user."
    if next_role and next_role != "T0":
        return (
            f"T0 is managing T1/T2/T3 for goal '{goal}'. "
            f"Next managed role: {next_role}; task: {task}; active tasks: {active_count}; "
            f"assignment: {assignment_state}."
        )
    return f"T0 is managing the goal '{goal}' and monitoring for the next role action."


def build_user_action(
    state: str,
    dispatch_state: str,
    actions: list[str],
    launch_failure_count: int = 0,
) -> str:
    if launch_failure_count:
        return "T0 launch/recovery failed; fix the T0 launcher configuration or rerun T0 with another launcher."
    if state == "needs-supervisor-run":
        return "Start or resume T0 with taskboard_start.py or taskboard_loop.py."
    if dispatch_state == "needs-goal":
        return "Provide one user goal to T0."
    if dispatch_state == "complete":
        return "Review T0's completion summary."
    if actions:
        return "No user action required; T0 is handling routine role recovery or dispatch."
    return "No user action required."


def report_progress(root: Path) -> dict[str, object]:
    snapshot = read_latest_snapshot(root)
    if snapshot is None:
        goal = read_goal(root, "")
        return {
            "kind": "taskboard-t0-progress",
            "state": "needs-supervisor-run",
            "goal": goal,
            "next_role": "T0",
            "task": "none",
            "assignment_state": "none",
            "active_count": 0,
            "missing_roles": [],
            "stale_roles": [],
            "launch_failures": [],
            "launch_failure_count": 0,
            "suppressed_launches": [],
            "suppressed_launch_count": 0,
            "user_summary": build_user_summary("needs-supervisor-run", goal, "T0", "none", "none", 0),
            "user_action": build_user_action("needs-supervisor-run", "needs-supervisor-run", []),
            "boundary": T0_PROGRESS_BOUNDARY,
        }

    latest = snapshot.get("latest", {})
    latest_payload = latest if isinstance(latest, dict) else {}
    dispatch = latest_payload.get("dispatch", {})
    dispatch_payload = dispatch if isinstance(dispatch, dict) else {}
    assignment = latest_payload.get("assignment", {})
    assignment_payload = assignment if isinstance(assignment, dict) else {}
    queue_health = latest_payload.get("queue_health", {})
    queue_payload = queue_health if isinstance(queue_health, dict) else {}
    session_probe = latest_payload.get("session_probe", {})
    session_payload = session_probe if isinstance(session_probe, dict) else {}
    actions = latest_payload.get("actions", [])
    action_list = [str(action) for action in actions] if isinstance(actions, list) else []
    suppressed_launches = latest_payload.get("suppressed_launches", [])
    suppressed_launch_list: list[dict[str, object]] = []
    if isinstance(suppressed_launches, list):
        for item in suppressed_launches:
            if not isinstance(item, dict):
                continue
            suppressed_launch_list.append(
                {
                    "role": str(item.get("role") or ""),
                    "reason": str(item.get("reason") or ""),
                    "remaining_seconds": item.get("remaining_seconds"),
                }
            )
    executed_commands = latest_payload.get("executed_commands", [])
    launch_failures: list[dict[str, object]] = []
    if isinstance(executed_commands, list):
        for item in executed_commands:
            if not isinstance(item, dict):
                continue
            try:
                returncode = int(item.get("returncode", 0))
            except (TypeError, ValueError):
                returncode = 0
            if returncode == 0:
                continue
            launch_failures.append(
                {
                    "command": str(item.get("command") or ""),
                    "returncode": returncode,
                    "output": str(item.get("output") or ""),
                }
            )

    goal = str(snapshot.get("goal") or latest_payload.get("goal") or read_goal(root, ""))
    state = str(latest_payload.get("state") or dispatch_payload.get("state") or "unknown")
    next_role = str(dispatch_payload.get("next_role") or "T0")
    task = str(dispatch_payload.get("task") or "none")
    assignment_state = str(assignment_payload.get("state") or "none")
    try:
        active_count = int(queue_payload.get("active_count") or 0)
    except (TypeError, ValueError):
        active_count = 0

    return {
        "kind": "taskboard-t0-progress",
        "state": state,
        "goal": goal,
        "next_role": next_role,
        "task": task,
        "assignment_state": assignment_state,
        "active_count": active_count,
        "missing_roles": list(session_payload.get("missing_roles", []))
        if isinstance(session_payload.get("missing_roles", []), list)
        else [],
        "stale_roles": list(session_payload.get("stale_roles", []))
        if isinstance(session_payload.get("stale_roles", []), list)
        else [],
        "launch_failures": launch_failures,
        "launch_failure_count": len(launch_failures),
        "suppressed_launches": suppressed_launch_list,
        "suppressed_launch_count": len(suppressed_launch_list),
        "user_summary": build_user_summary(
            state,
            goal,
            next_role,
            task,
            assignment_state,
            active_count,
            len(launch_failures),
            len(suppressed_launch_list),
        ),
        "user_action": build_user_action(
            state,
            str(dispatch_payload.get("state") or ""),
            action_list,
            len(launch_failures),
        ),
        "actions": action_list,
        "boundary": T0_PROGRESS_BOUNDARY,
    }


def format_text(payload: dict[str, object]) -> str:
    lines = [
        f"state={payload['state']}",
        f"goal={payload['goal']}",
        f"next_role={payload['next_role']}",
        f"task={payload['task']}",
        f"assignment_state={payload['assignment_state']}",
        f"user_action={payload['user_action']}",
        f"summary={payload['user_summary']}",
        f"boundary={payload['boundary']}",
    ]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing T0 runtime state")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    payload = report_progress(Path(args.root).resolve())
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
