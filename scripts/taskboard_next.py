#!/usr/bin/env python3
"""Select the next TASKBOARD role/task from filename state."""

from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Optional


STATUS_RE = re.compile(r"^(TASK-\d+)\.v(\d+)\.(.+?)\.md$")

ROLE_PRIORITY = {
    "T0": [
        ("T1", "T1-待决策"),
        ("T2", "T2-待审核代码"),
        ("T2", "T2-待审核方案"),
        ("T3", "T3-需修复"),
        ("T3", "T3-待验证"),
        ("T3", "T3-待执行"),
        ("T1", "T1-方案需修改"),
    ],
    "T1": [
        ("T1", "T1-待决策"),
        ("T1", "T1-方案需修改"),
    ],
    "T2": [
        ("T2", "T2-待审核代码"),
        ("T2", "T2-待审核方案"),
    ],
    "T3": [
        ("T3", "T3-需修复"),
        ("T3", "T3-待验证"),
        ("T3", "T3-待执行"),
    ],
}


@dataclass(frozen=True)
class Task:
    path: Path
    task_id: str
    version: int
    status: str
    role: str
    wave: int


def status_matches(actual: str, expected: str) -> bool:
    if expected == "T2-待审核代码":
        return actual.startswith("T2-待审核代码")
    return actual == expected


def parse_wave(path: Path) -> int:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("**Wave**:"):
                raw = line.split(":", 1)[1].strip()
                return int(raw)
    except (OSError, UnicodeDecodeError, ValueError):
        pass
    return 9999


def parse_task(path: Path) -> Optional[Task]:
    match = STATUS_RE.match(path.name)
    if not match:
        return None
    task_id, version, status = match.groups()
    role = status.split("-", 1)[0]
    if role not in {"T1", "T2", "T3"}:
        return None
    return Task(
        path=path,
        task_id=task_id,
        version=int(version),
        status=status,
        role=role,
        wave=parse_wave(path),
    )


def discover_tasks(root: Path) -> list[Task]:
    taskboard = root / "docs" / "taskboard"
    if not taskboard.exists():
        return []
    tasks = []
    for path in taskboard.glob("TASK-*.T*.md"):
        task = parse_task(path)
        if task is not None:
            tasks.append(task)
    return tasks


def has_goal_context(root: Path) -> bool:
    for relative in ("docs/PROJECT.md", "docs/REQUIREMENTS.md"):
        path = root / relative
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return True
    return False


def select_task(role: str, root: Path) -> tuple[str, str, Optional[Task], str]:
    role = role.upper()
    if role not in ROLE_PRIORITY:
        raise ValueError(f"unknown role: {role}")

    tasks = discover_tasks(root)
    for target_role, target_status in ROLE_PRIORITY[role]:
        candidates = [
            task
            for task in tasks
            if task.role == target_role and status_matches(task.status, target_status)
        ]
        if candidates:
            selected = sorted(candidates, key=lambda item: (item.wave, item.path.stat().st_mtime, item.path.name))[0]
            return target_role, target_status, selected, "matched-active-task"

    if role == "T0" and has_goal_context(root):
        return "T1", "T1-create-or-revise", None, "no-active-tasks-goal-incomplete"

    return role, "complete" if role == "T0" else "idle", None, "empty-queue"


def format_selection(role: str, status: str, task: Optional[Task], reason: str) -> str:
    task_name = task.path.name if task is not None else "none"
    return f"role={role} status={status} task={task_name} reason={reason}"


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=sorted(ROLE_PRIORITY), required=True)
    parser.add_argument("--root", default=".", help="Project root containing docs/taskboard")
    args = parser.parse_args(argv)

    try:
        role, status, task, reason = select_task(args.role, Path(args.root).resolve())
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    print(format_selection(role, status, task, reason))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
