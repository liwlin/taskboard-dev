#!/usr/bin/env python3
"""Record a T0 user decision for a stop gate and resume T1."""

from argparse import ArgumentParser
from pathlib import Path
import json
import time
from typing import Optional

from taskboard_stopgates import report_stop_gates


T0_DECISION_BOUNDARY = (
    "T0 records user decisions only: append the user's stop-gate answer, "
    "resume T1 for plan/task revision, and do not perform design, review, implementation, verification, or commit work."
)


def resumed_task_name(task_name: str, resume_status: str) -> str:
    parts = task_name.split(".")
    if len(parts) < 4:
        raise ValueError(f"invalid TASKBOARD task name: {task_name}")
    parts[-2] = resume_status
    return ".".join(parts)


def choose_stop_gate(root: Path, task_name: Optional[str]) -> dict[str, object]:
    report = report_stop_gates(root)
    stop_gates = report.get("stop_gates", [])
    gates = stop_gates if isinstance(stop_gates, list) else []
    if task_name:
        for gate in gates:
            if isinstance(gate, dict) and gate.get("task") == task_name:
                return gate
        raise ValueError(f"stop gate task not found: {task_name}")
    if not gates:
        raise ValueError("no T0 stop gate task found")
    first_gate = gates[0]
    if not isinstance(first_gate, dict):
        raise ValueError("invalid stop gate report")
    return first_gate


def append_decision_to_task(path: Path, decision: str, gate: dict[str, object]) -> None:
    text = path.read_text(encoding="utf-8-sig")
    block = (
        "\n\n## T0 User Decision\n\n"
        "kind: taskboard-t0-user-decision\n"
        f"recorded_at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
        f"gate: {gate.get('gate') or ''}\n"
        f"question: {gate.get('question') or ''}\n"
        f"decision: {decision}\n"
        f"boundary: {T0_DECISION_BOUNDARY}\n"
    )
    path.write_text(text.rstrip() + block + "\n", encoding="utf-8")


def append_decision_to_state(root: Path, decision: str, gate: dict[str, object], resumed_name: str) -> None:
    state = root / "docs" / "STATE.md"
    existing = state.read_text(encoding="utf-8-sig") if state.exists() else "# STATE\n"
    entry = (
        "\n\n## T0 Stop-Gate Decision\n\n"
        f"- Task: {gate.get('task') or ''}\n"
        f"- Gate: {gate.get('gate') or ''}\n"
        f"- Question: {gate.get('question') or ''}\n"
        f"- Decision: {decision}\n"
        f"- Resumed as: {resumed_name}\n"
        "- Boundary: T0 recorded the user's answer and resumed T1; T0 did not perform worker tasks.\n"
    )
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(existing.rstrip() + entry + "\n", encoding="utf-8")


def record_decision(root: Path, decision: str, task_name: Optional[str] = None, resume_status: str = "T1-方案需修改") -> dict[str, object]:
    if not decision.strip():
        raise ValueError("--decision must not be empty")
    gate = choose_stop_gate(root, task_name)
    original_name = str(gate.get("task") or "")
    original = root / "docs" / "taskboard" / original_name
    if not original.exists():
        raise ValueError(f"stop gate task file not found: {original_name}")
    resumed_name = resumed_task_name(original_name, resume_status)
    resumed = original.with_name(resumed_name)
    if resumed.exists():
        raise ValueError(f"resume target already exists: {resumed_name}")

    normalized_decision = decision.strip()
    append_decision_to_task(original, normalized_decision, gate)
    original.rename(resumed)
    append_decision_to_state(root, normalized_decision, gate, resumed_name)

    return {
        "kind": "taskboard-t0-decision",
        "version": 1,
        "recorded": True,
        "task": original_name,
        "resumed_task": resumed_name,
        "next_role": "T1",
        "decision": normalized_decision,
        "boundary": T0_DECISION_BOUNDARY,
    }


def format_text(payload: dict[str, object]) -> str:
    return "\n".join(
        [
            f"recorded={payload['recorded']}",
            f"task={payload['task']}",
            f"resumed_task={payload['resumed_task']}",
            f"next_role={payload['next_role']}",
            f"boundary={payload['boundary']}",
        ]
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing docs/taskboard")
    parser.add_argument("--task", help="Specific stop-gate task filename. Defaults to the first stop gate.")
    parser.add_argument("--decision", required=True, help="User decision captured by T0.")
    parser.add_argument("--resume-status", default="T1-方案需修改", help="Status to rename the task to after recording.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        payload = record_decision(Path(args.root).resolve(), args.decision, args.task, args.resume_status)
    except ValueError as exc:
        print(exc)
        return 2

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
