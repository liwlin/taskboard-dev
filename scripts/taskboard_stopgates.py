#!/usr/bin/env python3
"""Aggregate T0-visible stop gates without doing worker tasks."""

from argparse import ArgumentParser
from pathlib import Path
import json
from typing import Optional

from taskboard_next import Task, discover_tasks


T0_STOP_GATE_BOUNDARY = (
    "T0 aggregates stop gates for the user; do not execute design, review, "
    "implementation, verification, or commit work."
)

STOP_GATE_MARKERS = (
    "T1-待决策",
    "T1-decision",
    "stop gate",
    "stop-gate",
    "decision needed",
    "**Gate**:",
    "Gate:",
)


def field_value(lines: list[str], field: str) -> str:
    markers = (f"**{field}**:", f"{field}:")
    for line in lines:
        stripped = line.strip()
        for marker in markers:
            if stripped.startswith(marker):
                return stripped[len(marker) :].strip()
    return ""


def list_after_field(lines: list[str], field: str) -> list[str]:
    markers = (f"**{field}**:", f"{field}:")
    options: list[str] = []
    collecting = False
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(marker) for marker in markers):
            collecting = True
            continue
        if collecting:
            if stripped.startswith("**") and stripped.endswith(":"):
                break
            if stripped.startswith("- "):
                options.append(stripped[2:].strip())
            elif stripped and not stripped.startswith("#"):
                break
    return options


def task_has_stop_gate(task: Task, text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in task.status.lower() or marker.lower() in lowered for marker in STOP_GATE_MARKERS)


def stop_gate_from_task(task: Task) -> Optional[dict[str, object]]:
    try:
        text = task.path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    if not task_has_stop_gate(task, text):
        return None

    lines = text.splitlines()
    gate = field_value(lines, "Gate") or "Decision needed"
    question = field_value(lines, "Question") or field_value(lines, "Decision Needed") or task.path.stem
    recommended = field_value(lines, "Recommended")
    options = list_after_field(lines, "Options")
    return {
        "task": task.path.name,
        "role": task.role,
        "status": task.status,
        "gate": gate,
        "question": question,
        "options": options,
        "recommended": recommended,
        "action": "Ask the user through T0 only; do not ask the user to manage T1/T2/T3.",
    }


def report_stop_gates(root: Path) -> dict[str, object]:
    gates = []
    for task in discover_tasks(root):
        gate = stop_gate_from_task(task)
        if gate is not None:
            gates.append(gate)
    gates.sort(key=lambda item: str(item["task"]))
    return {
        "kind": "taskboard-t0-stop-gates",
        "stop_gate_count": len(gates),
        "stop_gates": gates,
        "boundary": T0_STOP_GATE_BOUNDARY,
    }


def format_text(payload: dict[str, object]) -> str:
    lines = [
        f"stop_gate_count={payload['stop_gate_count']}",
        f"boundary={payload['boundary']}",
    ]
    for gate in payload["stop_gates"]:
        lines.append(
            f"- task={gate['task']} gate={gate['gate']} question={gate['question']} recommended={gate['recommended']}"
        )
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing docs/taskboard")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    payload = report_stop_gates(Path(args.root).resolve())
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
