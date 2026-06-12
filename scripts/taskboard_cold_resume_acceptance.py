#!/usr/bin/env python3
"""Validate field evidence for next-day cold worker resume."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys
from typing import Optional

from taskboard_progress import report_progress


BOUNDARY = (
    "taskboard cold-resume acceptance is read-only; it audits T0 progress and TASKBOARD "
    "evidence for fresh worker recovery and must not launch workers, edit files, or create proof."
)


def is_smoke_starter_mode(starter_mode: str) -> bool:
    lowered = starter_mode.strip().lower()
    return any(token in lowered for token in ("demo", "smoke", "test"))


def has_t0_control_plane_evidence(progress: dict[str, object]) -> bool:
    event_count = safe_int(progress.get("event_count"), 0)
    t0_supervisor = progress.get("t0_supervisor", {})
    t0_supervisor_payload = t0_supervisor if isinstance(t0_supervisor, dict) else {}
    latest_state = str(t0_supervisor_payload.get("state") or "")
    return event_count > 0 or latest_state not in {"", "missing"}


def safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def collect_acceptance(root: Path) -> dict[str, object]:
    root = root.resolve()
    progress = report_progress(root)
    failures: list[str] = []
    evidence: list[str] = []

    if not has_t0_control_plane_evidence(progress):
        failures.append("missing T0 control-plane snapshot/event evidence")
    else:
        evidence.append("T0 control-plane evidence found")

    if not bool(progress.get("auto_mode")):
        failures.append("T0 auto_mode evidence missing")

    starter_mode = str(progress.get("starter_mode") or "")
    if starter_mode and is_smoke_starter_mode(starter_mode):
        failures.append(f"T0 starter_mode looks like smoke/test/demo evidence: {starter_mode}")
    elif starter_mode:
        evidence.append(f"T0 starter_mode recorded: {starter_mode}")

    if str(progress.get("checkout_owner_state") or "") == "conflict":
        failures.append("checkout owner conflict evidence present")

    next_role = str(progress.get("next_role") or "")
    task = str(progress.get("task") or "")
    if next_role not in {"T1", "T2", "T3"} or not task or task == "none":
        failures.append("no selected worker TASK for cold resume")

    cold_resume = progress.get("cold_resume_readiness", {})
    cold_resume_payload = cold_resume if isinstance(cold_resume, dict) else {}
    cold_state = str(cold_resume_payload.get("state") or "")
    if cold_state != "ready":
        failures.append(f"cold_resume_readiness not ready: {cold_state or '<missing>'}")
    else:
        evidence.append("cold-resume readiness accepted")

    missing_evidence = cold_resume_payload.get("missing_evidence", [])
    missing_evidence_list = missing_evidence if isinstance(missing_evidence, list) else []
    failures.extend(f"cold resume missing evidence: {item}" for item in missing_evidence_list)

    if str(cold_resume_payload.get("scoped_git_status_state") or "") != "available":
        failures.append("scoped git status unavailable for selected TASK Files")

    if not str(cold_resume_payload.get("source_of_truth") or ""):
        failures.append("cold resume source_of_truth explanation missing")

    state = "passed" if not failures else "failed"
    return {
        "kind": "taskboard-cold-resume-acceptance",
        "state": state,
        "root": str(root),
        "failure_count": len(failures),
        "failures": failures,
        "evidence": evidence,
        "progress": {
            "state": progress.get("state"),
            "goal": progress.get("goal"),
            "next_role": next_role,
            "task": task,
            "assignment_state": progress.get("assignment_state"),
            "assignment_role": progress.get("assignment_role"),
            "auto_mode": progress.get("auto_mode"),
            "starter_mode": starter_mode,
            "checkout_owner_state": progress.get("checkout_owner_state"),
            "user_action": progress.get("user_action"),
        },
        "cold_resume": cold_resume_payload,
        "boundary": BOUNDARY,
    }


def format_text(payload: dict[str, object]) -> str:
    progress = payload.get("progress", {})
    progress_payload = progress if isinstance(progress, dict) else {}
    cold_resume = payload.get("cold_resume", {})
    cold_payload = cold_resume if isinstance(cold_resume, dict) else {}
    lines = [
        f"state={payload['state']}",
        f"root={payload['root']}",
        f"failure_count={payload['failure_count']}",
        f"progress_next_role={progress_payload.get('next_role', '')}",
        f"progress_task={progress_payload.get('task', '')}",
        f"cold_resume_state={cold_payload.get('state', '')}",
        f"cold_resume_task={cold_payload.get('task', '')}",
        f"boundary={payload['boundary']}",
    ]
    for failure in payload["failures"]:
        lines.append(f"failure={failure}")
    for item in payload["evidence"]:
        lines.append(f"evidence={item}")
    return "\n".join(lines)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing docs/ and .taskboard/")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = collect_acceptance(Path(args.root))
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(payload))
    return 0 if payload["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
