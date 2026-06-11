#!/usr/bin/env python3
"""Single TASKBOARD control-plane CLI.

This v4.5 facade keeps the existing v4.4 scripts working while giving T0 and
workers one compact command surface for deterministic board operations.
"""

from argparse import ArgumentParser
from pathlib import Path
import json
import os
import sys
import time
from typing import Optional

from taskboard_completion import report_completion
from taskboard_decide import record_decision
from taskboard_health import report_health
from taskboard_next import ROLE_PRIORITY, STATUS_RE, has_goal_complete_sentinel, select_task
from taskboard_stopgates import report_stop_gates
from taskboard_subagents import (
    subagent_ack_payload,
    subagent_next_payload,
    subagent_result_payload,
    subagent_retry_payload,
    subagent_status_payload,
)


VALID_ROLES = {"T0", "T1", "T2", "T3"}
VALID_STATUSES = {
    status
    for priorities in ROLE_PRIORITY.values()
    for _, status in priorities
}
VALID_STATUSES.update(
    {
        "T2-待审核代码-L1",
        "T2-待审核代码-L2",
        "T2-待审核代码-L3",
        "archive-完成",
        "archive-中止",
    }
)


def taskboard_dir(root: Path) -> Path:
    return root / "docs" / "taskboard"


def format_output(payload: dict[str, object], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return "\n".join(f"{key}={value}" for key, value in payload.items())


def next_payload(root: Path, role: str) -> dict[str, object]:
    selected_role, status, task, reason = select_task(role, root)
    return {
        "kind": "taskboard-next",
        "role": selected_role,
        "status": status,
        "task": task.path.name if task is not None else "none",
        "reason": reason,
    }


def status_payload(root: Path, stale_minutes: int, goal: Optional[str]) -> dict[str, object]:
    queue_health = report_health(root, stale_minutes, goal)
    return {
        "kind": "taskboard-status",
        "queue_health": queue_health,
        "stop_gates": report_stop_gates(root),
        "completion": report_completion(root),
        "next": queue_health.get("next", next_payload(root, "T0")),
    }


def stall_payload(root: Path, minutes: int, goal: Optional[str]) -> dict[str, object]:
    health = report_health(root, minutes, goal)
    stalled = health.get("stalled_tasks", [])
    stalled_list = stalled if isinstance(stalled, list) else []
    return {
        "kind": "taskboard-stall",
        "minutes": minutes,
        "stalled_count": len(stalled_list),
        "stalled_tasks": stalled_list,
        "actions": health.get("actions", []),
        "boundary": "taskboard stall is read-only; it does not execute worker tasks.",
    }


def alive_payload(root: Path, role: str) -> dict[str, object]:
    normalized_role = role.upper()
    if normalized_role not in VALID_ROLES:
        raise ValueError(f"invalid role: {role}")
    path = root / ".taskboard" / "alive" / normalized_role
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return {
        "kind": "taskboard-alive",
        "role": normalized_role,
        "path": str(path),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def cycle_payload(root: Path, role: str, sleep_seconds: int) -> dict[str, object]:
    normalized_role = role.upper()
    if normalized_role not in {"T1", "T2", "T3"}:
        raise ValueError(f"invalid worker role: {role}")
    liveness = alive_payload(root, normalized_role)
    next_item = next_payload(root, normalized_role)
    if has_goal_complete_sentinel(root) and next_item.get("task") == "none":
        action = "exit-goal-complete"
        should_exit = True
    elif next_item.get("status") == "idle" and next_item.get("task") == "none":
        action = "idle-recheck"
        should_exit = False
    else:
        action = "work"
        should_exit = False
    return {
        "kind": "taskboard-worker-cycle",
        "role": normalized_role,
        "liveness": liveness,
        "next": next_item,
        "action": action,
        "should_exit": should_exit,
        "recheck_after_seconds": max(0, sleep_seconds),
        "next_cycle_command": (
            f"python scripts/taskboard.py --root . cycle {normalized_role} "
            f"--sleep-seconds {max(0, sleep_seconds)}"
        ),
        "boundary": (
            "worker cycle is role-local; empty queue is not completion unless "
            "the goal-complete sentinel is present."
        ),
    }


def parse_task_name(task_name: str) -> tuple[str, str, str]:
    match = STATUS_RE.match(task_name)
    if not match:
        raise ValueError(f"invalid TASKBOARD task name: {task_name}")
    task_id, version, status = match.groups()
    return task_id, version, status


def validate_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")


def move_target_name(task_name: str, new_status: str) -> str:
    task_id, version, _ = parse_task_name(task_name)
    return f"{task_id}.v{version}.{new_status}.md"


def append_history(root: Path, task_id: str, old_name: str, new_name: str, note: str) -> Path:
    history_dir = taskboard_dir(root) / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    history = history_dir / f"{task_id}.history.md"
    entry = [
        "",
        f"## {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} taskboard move",
        "",
        f"- From: `{old_name}`",
        f"- To: `{new_name}`",
    ]
    if note.strip():
        entry.append(f"- Note: {note.strip()}")
    entry.append("")
    existing = history.read_text(encoding="utf-8") if history.exists() else f"# {task_id} history\n"
    history.write_text(existing.rstrip() + "\n".join(entry), encoding="utf-8")
    return history


def move_payload(root: Path, task_name: str, new_status: str, note: str = "") -> dict[str, object]:
    validate_status(new_status)
    task_id, _, old_status = parse_task_name(task_name)
    source = taskboard_dir(root) / task_name
    if not source.exists():
        raise ValueError(f"task not found: {task_name}")
    target_name = move_target_name(task_name, new_status)
    target = source.with_name(target_name)
    if target.exists():
        raise ValueError(f"move target already exists: {target_name}")

    source.rename(target)
    now = time.time()
    os.utime(target, (now, now))
    history = append_history(root, task_id, task_name, target_name, note)
    return {
        "kind": "taskboard-move",
        "task_id": task_id,
        "from": task_name,
        "from_status": old_status,
        "to": target_name,
        "to_status": new_status,
        "history": str(history),
        "boundary": "taskboard move validates status, renames the task, appends history, and touches mtime.",
    }


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing docs/taskboard")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    subparsers = parser.add_subparsers(dest="command", required=True)

    next_parser = subparsers.add_parser("next", help="Select the next task for a role")
    next_parser.add_argument("role", choices=sorted(ROLE_PRIORITY))

    status_parser = subparsers.add_parser("status", help="Show T0 board status")
    status_parser.add_argument("--stale-minutes", type=int, default=30)
    status_parser.add_argument("--goal")

    stall_parser = subparsers.add_parser("stall", help="Report stalled tasks")
    stall_parser.add_argument("--minutes", type=int, default=30)
    stall_parser.add_argument("--goal")

    alive_parser = subparsers.add_parser("alive", help="Touch a role liveness marker")
    alive_parser.add_argument("role")

    cycle_parser = subparsers.add_parser("cycle", help="Touch liveness and choose the worker's next loop action")
    cycle_parser.add_argument("role", choices=("T1", "T2", "T3"))
    cycle_parser.add_argument("--sleep-seconds", type=int, default=120)

    decide_parser = subparsers.add_parser("decide", help="Record a T0 stop-gate decision")
    decide_parser.add_argument("task")
    decide_parser.add_argument("--answer", required=True)
    decide_parser.add_argument("--resume-status", default="T1-方案需修改")

    move_parser = subparsers.add_parser("move", help="Validate and move a task to a new status")
    move_parser.add_argument("task")
    move_parser.add_argument("status")
    move_parser.add_argument("--note", default="")

    subagent_parser = subparsers.add_parser("subagent", help="Manage T0 native-subagent dispatch records")
    subagent_subparsers = subagent_parser.add_subparsers(dest="subagent_command", required=True)
    subagent_subparsers.add_parser("status", help="Show native-subagent dispatch status")
    subagent_subparsers.add_parser("next", help="Return the next pending native-subagent prompt")
    subagent_ack = subagent_subparsers.add_parser("ack", help="Record a native-subagent dispatch")
    subagent_ack.add_argument("--role", required=True)
    subagent_ack.add_argument("--agent-id", required=True)
    subagent_ack.add_argument("--note", default="")
    subagent_done = subagent_subparsers.add_parser("done", help="Record a completed native subagent")
    subagent_done.add_argument("--role", required=True)
    subagent_done.add_argument("--summary", default="")
    subagent_fail = subagent_subparsers.add_parser("fail", help="Record a failed native subagent")
    subagent_fail.add_argument("--role", required=True)
    subagent_fail.add_argument("--summary", default="")
    subagent_retry = subagent_subparsers.add_parser("retry", help="Return a failed native subagent role to pending")
    subagent_retry.add_argument("--role", required=True)
    subagent_retry.add_argument("--note", default="")
    return parser


def run(args) -> dict[str, object]:
    root = Path(args.root).resolve()
    if args.command == "next":
        return next_payload(root, args.role)
    if args.command == "status":
        return status_payload(root, args.stale_minutes, args.goal)
    if args.command == "stall":
        return stall_payload(root, args.minutes, args.goal)
    if args.command == "alive":
        return alive_payload(root, args.role)
    if args.command == "cycle":
        return cycle_payload(root, args.role, args.sleep_seconds)
    if args.command == "decide":
        return record_decision(root, args.answer, args.task, args.resume_status)
    if args.command == "move":
        return move_payload(root, args.task, args.status, args.note)
    if args.command == "subagent":
        if args.subagent_command == "status":
            return subagent_status_payload(root)
        if args.subagent_command == "next":
            return subagent_next_payload(root)
        if args.subagent_command == "ack":
            return subagent_ack_payload(root, args.role, args.agent_id, args.note)
        if args.subagent_command == "done":
            return subagent_result_payload(root, args.role, "completed", args.summary)
        if args.subagent_command == "fail":
            return subagent_result_payload(root, args.role, "failed", args.summary)
        if args.subagent_command == "retry":
            return subagent_retry_payload(root, args.role, args.note)
    raise ValueError(f"unknown command: {args.command}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = run(args)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(format_output(payload, args.format))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
