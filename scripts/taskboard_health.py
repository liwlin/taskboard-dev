#!/usr/bin/env python3
"""Report T0-visible TASKBOARD queue health without doing worker tasks."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys
import time
from typing import Optional

from taskboard_next import Task, discover_tasks, has_goal_context, select_task


ROLES = ("T1", "T2", "T3")
T0_BOUNDARY = (
    "T0 manager-only: observe queues, wake or recover T1/T2/T3, and surface stop gates; "
    "do not execute development, design, review, implementation, verification, or commit tasks in T0."
)


def task_sort_key(task: Task) -> tuple[int, float, str]:
    return (task.wave, task.path.stat().st_mtime, task.path.name)


def task_age_minutes(task: Task, now: float) -> int:
    age_seconds = max(0, now - task.path.stat().st_mtime)
    return int(age_seconds // 60)


def build_queues(tasks: list[Task]) -> dict[str, dict[str, dict[str, object]]]:
    queues: dict[str, dict[str, dict[str, object]]] = {role: {} for role in ROLES}
    for task in sorted(tasks, key=task_sort_key):
        role_queues = queues.setdefault(task.role, {})
        entry = role_queues.setdefault(task.status, {"count": 0, "tasks": []})
        entry["count"] = int(entry["count"]) + 1
        entry["tasks"].append(task.path.name)
    return queues


def build_next(root: Path, explicit_goal: Optional[str]) -> dict[str, str]:
    role, status, task, reason = select_task("T0", root)
    if role == "T0" and status == "complete" and explicit_goal and explicit_goal.strip() and reason != "goal-complete-sentinel":
        role = "T1"
        status = "T1-create-or-revise"
        reason = "explicit-goal-no-active-tasks"
    return {
        "role": role,
        "status": status,
        "task": task.path.name if task is not None else "none",
        "reason": reason,
    }


def build_stalled_tasks(tasks: list[Task], stale_minutes: int, now: float) -> list[dict[str, object]]:
    if stale_minutes < 0:
        raise ValueError("--stale-minutes must be >= 0")

    stalled = []
    for task in sorted(tasks, key=task_sort_key):
        age = task_age_minutes(task, now)
        if age >= stale_minutes:
            stalled.append(
                {
                    "task": task.path.name,
                    "role": task.role,
                    "status": task.status,
                    "age_minutes": age,
                    "action": (
                        f"reissue target to taskboard-{task.role}; "
                        "do not execute the development task in T0"
                    ),
                }
            )
    return stalled


def build_actions(next_item: dict[str, str], stalled_tasks: list[dict[str, object]]) -> list[str]:
    if stalled_tasks:
        return [
            f"wake taskboard-{item['role']} for stalled {item['task']}"
            for item in stalled_tasks
        ]

    role = next_item["role"]
    status = next_item["status"]
    task = next_item["task"]
    if role in ROLES and task != "none":
        return [f"wake taskboard-{role} for {task}"]
    if role == "T1" and status == "T1-create-or-revise":
        return ["wake taskboard-T1 to create or revise TASK files from the user goal"]
    if role == "T0" and status == "complete":
        return ["summarize completion to the user; do not run worker tasks in T0"]
    return [f"inspect {role} state and keep T0 manager-only"]


def build_state(active_count: int, next_item: dict[str, str], stalled_tasks: list[dict[str, object]], root: Path) -> str:
    if stalled_tasks:
        return "attention"
    if active_count:
        return "active"
    if next_item["role"] == "T0" and next_item["status"] == "complete":
        return "complete"
    if next_item["role"] == "T1" and next_item["status"] == "T1-create-or-revise":
        return "ready-for-next-task"
    if has_goal_context(root):
        return "ready-for-next-task"
    return "empty"


def report_health(root: Path, stale_minutes: int, explicit_goal: Optional[str] = None) -> dict[str, object]:
    tasks = discover_tasks(root)
    now = time.time()
    next_item = build_next(root, explicit_goal)
    stalled_tasks = build_stalled_tasks(tasks, stale_minutes, now)
    active_count = len(tasks)
    return {
        "state": build_state(active_count, next_item, stalled_tasks, root),
        "active_count": active_count,
        "queues": build_queues(tasks),
        "stalled_tasks": stalled_tasks,
        "next": next_item,
        "actions": build_actions(next_item, stalled_tasks),
        "boundary": T0_BOUNDARY,
    }


def format_text(payload: dict[str, object]) -> str:
    lines = [
        f"state={payload['state']}",
        f"active_count={payload['active_count']}",
        f"boundary={payload['boundary']}",
        "next:",
        json.dumps(payload["next"], ensure_ascii=False, sort_keys=True),
        "actions:",
    ]
    for action in payload["actions"]:
        lines.append(f"- {action}")
    stalled_tasks = payload["stalled_tasks"]
    if stalled_tasks:
        lines.append("stalled_tasks:")
        for item in stalled_tasks:
            lines.append(
                f"- {item['task']} role={item['role']} age_minutes={item['age_minutes']} action={item['action']}"
            )
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing docs/taskboard")
    parser.add_argument(
        "--stale-minutes",
        type=int,
        default=30,
        help="Mark active TASK files older than this threshold as stalled",
    )
    parser.add_argument("--goal", help="Current user goal when it has not yet been written to PROJECT.md")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        payload = report_health(Path(args.root).resolve(), args.stale_minutes, args.goal)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
