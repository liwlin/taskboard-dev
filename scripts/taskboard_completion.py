#!/usr/bin/env python3
"""Audit whether T0 has enough evidence to summarize goal completion."""

from argparse import ArgumentParser
from pathlib import Path
import json
from typing import Optional

from taskboard_next import Task, discover_tasks, has_goal_complete_sentinel


T0_COMPLETION_BOUNDARY = (
    "T0 completion audit is read-only; T0 may summarize completion evidence for the user "
    "but must not execute T1/T2/T3 work, archive tasks, edit code, verify, commit, or release."
)


def archived_task_files(root: Path) -> list[Path]:
    archive = root / "docs" / "taskboard" / "archive"
    if not archive.exists():
        return []
    return sorted(path for path in archive.glob("TASK-*.md") if path.is_file())


def dev_log_has_completion_entries(root: Path) -> bool:
    path = root / "docs" / "dev-log.md"
    if not path.exists():
        return False
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()]
    except (OSError, UnicodeDecodeError):
        return False
    meaningful = [
        line
        for line in lines
        if line and not line.startswith("#") and "no completed" not in line.lower()
    ]
    return bool(meaningful)


def active_task_summary(tasks: list[Task]) -> list[dict[str, str]]:
    return [
        {
            "task": task.path.name,
            "role": task.role,
            "status": task.status,
        }
        for task in sorted(tasks, key=lambda item: (item.wave, item.path.name))
    ]


def missing_evidence(
    active_count: int,
    goal_complete: bool,
    archived_count: int,
    has_dev_log_entries: bool,
) -> list[str]:
    missing = []
    if active_count:
        missing.append("active TASK files remain")
    if not goal_complete:
        missing.append("no goal completion sentinel")
    if archived_count == 0:
        missing.append("no archived TASK evidence")
    if not has_dev_log_entries:
        missing.append("dev-log has no completion entries")
    return missing


def build_user_action(
    completion_ready: bool,
    missing: list[str],
    active_tasks: list[dict[str, str]],
) -> str:
    if completion_ready:
        return "T0 may summarize completion to the user with archived task and dev-log evidence."
    if active_tasks:
        first = active_tasks[0]
        return (
            f"Do not summarize completion yet; wake taskboard-{first['role']} "
            f"for active {first['task']}."
        )
    if "no goal completion sentinel" in missing:
        return "Do not summarize completion yet; wake T1 to record or revise the goal completion evidence."
    return "Do not summarize completion yet; collect the missing completion evidence through T1/T2/T3."


def report_completion(root: Path) -> dict[str, object]:
    tasks = discover_tasks(root)
    active_tasks = active_task_summary(tasks)
    archives = archived_task_files(root)
    goal_complete = has_goal_complete_sentinel(root)
    has_dev_log_entries = dev_log_has_completion_entries(root)
    missing = missing_evidence(len(tasks), goal_complete, len(archives), has_dev_log_entries)
    completion_ready = not missing
    return {
        "kind": "taskboard-t0-completion-audit",
        "state": "complete-ready" if completion_ready else "incomplete",
        "completion_ready": completion_ready,
        "active_count": len(tasks),
        "active_tasks": active_tasks,
        "archived_count": len(archives),
        "archived_tasks": [path.name for path in archives],
        "goal_complete_sentinel": goal_complete,
        "dev_log_has_completion_entries": has_dev_log_entries,
        "missing_evidence": missing,
        "user_action": build_user_action(completion_ready, missing, active_tasks),
        "boundary": T0_COMPLETION_BOUNDARY,
    }


def format_text(payload: dict[str, object]) -> str:
    lines = [
        f"state={payload['state']}",
        f"completion_ready={payload['completion_ready']}",
        f"active_count={payload['active_count']}",
        f"archived_count={payload['archived_count']}",
        f"goal_complete_sentinel={payload['goal_complete_sentinel']}",
        f"dev_log_has_completion_entries={payload['dev_log_has_completion_entries']}",
        f"user_action={payload['user_action']}",
        f"boundary={payload['boundary']}",
    ]
    missing = payload["missing_evidence"]
    if missing:
        lines.append("missing_evidence:")
        for item in missing:
            lines.append(f"- {item}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing docs/taskboard")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    payload = report_completion(Path(args.root).resolve())
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
