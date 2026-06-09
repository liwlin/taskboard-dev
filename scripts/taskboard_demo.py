#!/usr/bin/env python3
"""Create a deterministic TASKBOARD dry-run demo for T0 supervision."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys
from typing import Optional

from taskboard_next import ROLE_PRIORITY
from taskboard_sessions import write_heartbeat


GOAL = "Ship a demo feature through the T0-managed TASKBOARD pipeline."


def task_status(role: str, index: int) -> str:
    return ROLE_PRIORITY[role][index][1]


def write_file(path: Path, text: str, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass --force or choose an empty demo root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def task_file(task_id: str, title: str, status: str, wave: int, instruction: str) -> str:
    return f"""# {task_id}: {title}

**Spec**: docs/superpowers/specs/demo-design.md
**Plan**: docs/superpowers/plans/demo-plan.md
**Version**: v1
**Reqs**: REQ-DEMO-001
**Depends**: none
**Wave**: {wave}
**Review**: L2

## Current Instruction

{instruction}

## Acceptance (T2 verifies against these)

- [ ] T0 can identify the owning role from the filename status.
- [ ] The task contains enough context for the owning role to continue.

## Verify (T3 runs these before handoff)

- [ ] `python scripts/taskboard_next.py --role T0 --root <demo-root>`

## Files

| Action | File |
|--------|------|
| Modify | demo/no-op.txt |

## Pending

- [ ] Dry-run the role handoff without editing application code.
"""


def create_demo(root: Path, force: bool, with_heartbeats: bool) -> dict[str, object]:
    docs = root / "docs"
    if docs.exists() and any(docs.iterdir()) and not force:
        raise FileExistsError(f"{docs} is not empty; pass --force or choose an empty demo root")

    taskboard = docs / "taskboard"
    for directory in (
        taskboard,
        taskboard / "archive",
        taskboard / "history",
        docs / "reviews",
        docs / "superpowers" / "specs",
        docs / "superpowers" / "plans",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    write_file(
        docs / "PROJECT.md",
        f"""# PROJECT

## Goal
{GOAL}

## Non-Goals
- Do not modify product source code in this dry-run demo.

## Tech Stack
- Demo-only TASKBOARD files.

## Constraints
- T0 is manager-only and must not execute worker tasks.

## Success Criteria
- T0 loop reports managed sessions, queue health, and next dispatch role.
""",
        force,
    )
    write_file(
        docs / "MAP.md",
        """# MAP

## Directory Responsibilities
| Directory | Purpose |
|-----------|---------|
| docs/taskboard/ | Demo TASKBOARD state machine |

## Build & Test Commands
- `python scripts/taskboard_loop.py --root <demo-root> --goal "demo" --iterations 1`
""",
        force,
    )
    write_file(
        docs / "REQUIREMENTS.md",
        """# Requirements

- REQ-DEMO-001 [P1] Demonstrate T0-managed role scheduling without user-managed T1/T2/T3 terminals.
""",
        force,
    )
    write_file(
        docs / "STATE.md",
        """# STATE

## Decisions
- Demo board only; no product decision required.

## Blockers
- none
""",
        force,
    )
    write_file(docs / "dev-log.md", "# Development Log\n\nNo completed demo tasks yet.\n", force)

    design_status = task_status("T0", 2)
    execute_status = task_status("T0", 5)
    code_review_status = f"{task_status('T0', 1)}-L2"
    tasks = [
        (
            f"TASK-001.v1.{design_status}.md",
            task_file("TASK-001", "Review demo design", design_status, 1, "T2 reviews the dry-run demo design."),
        ),
        (
            f"TASK-002.v1.{execute_status}.md",
            task_file("TASK-002", "Execute demo no-op", execute_status, 2, "T3 performs a no-op implementation dry run."),
        ),
        (
            f"TASK-003.v1.{code_review_status}.md",
            task_file("TASK-003", "Review demo code handoff", code_review_status, 1, "T2 reviews a simulated code handoff."),
        ),
    ]
    written_tasks = []
    for name, content in tasks:
        path = taskboard / name
        write_file(path, content, force)
        written_tasks.append(name)

    heartbeats = []
    if with_heartbeats:
        for role in ("T1", "T2", "T3"):
            heartbeat = write_heartbeat(root, role, f"taskboard-{role}", "demo-alive", None)
            heartbeats.append(heartbeat["role"])

    return {
        "root": str(root),
        "goal": GOAL,
        "tasks": written_tasks,
        "heartbeats": heartbeats,
        "next_check": f"python scripts/taskboard_loop.py --root {root} --goal \"{GOAL}\" --iterations 1",
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Empty directory where the demo TASKBOARD will be created")
    parser.add_argument("--force", action="store_true", help="Overwrite existing demo files under --root/docs")
    parser.add_argument("--with-heartbeats", action="store_true", help="Write alive T1/T2/T3 demo heartbeats")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        payload = create_demo(Path(args.root).resolve(), args.force, args.with_heartbeats)
    except FileExistsError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"created demo root: {payload['root']}")
        print(f"goal: {payload['goal']}")
        print("tasks:")
        for task in payload["tasks"]:
            print(f"- {task}")
        print(f"next_check: {payload['next_check']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
