#!/usr/bin/env python3
"""Record and verify a real overnight T0-managed worker recovery field run."""

from argparse import ArgumentParser, Namespace, SUPPRESS
from pathlib import Path
import json
import time
from typing import Optional

from taskboard_cold_resume_acceptance import collect_acceptance as collect_cold_resume_acceptance
from taskboard_live_milestone_acceptance import collect_acceptance as collect_live_milestone_acceptance
from taskboard_t0 import read_runtime_goal


MARKER_RELATIVE = ".taskboard/t0/overnight-field-run.json"
DEFAULT_MIN_ELAPSED_SECONDS = 8 * 60 * 60
BOUNDARY = (
    "taskboard overnight field-run recorder is T0 control-plane only: record start/resume/verify "
    "evidence, but must not launch workers, edit TASKBOARD task files, implement code, review code, "
    "or create proof for T1/T2/T3."
)


def now_epoch() -> float:
    return time.time()


def iso_from_epoch(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def marker_path(root: Path) -> Path:
    return root / MARKER_RELATIVE


def read_marker(root: Path) -> dict[str, object]:
    path = marker_path(root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_marker(root: Path, payload: dict[str, object]) -> None:
    path = marker_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def summarize_cold_acceptance(payload: dict[str, object]) -> dict[str, object]:
    progress = payload.get("progress", {})
    progress_payload = progress if isinstance(progress, dict) else {}
    cold_resume = payload.get("cold_resume", {})
    cold_payload = cold_resume if isinstance(cold_resume, dict) else {}
    return {
        "state": payload.get("state"),
        "failure_count": payload.get("failure_count"),
        "failures": payload.get("failures", []),
        "progress": {
            "next_role": progress_payload.get("next_role"),
            "task": progress_payload.get("task"),
            "assignment_state": progress_payload.get("assignment_state"),
            "auto_mode": progress_payload.get("auto_mode"),
            "starter_mode": progress_payload.get("starter_mode"),
        },
        "cold_resume": {
            "state": cold_payload.get("state"),
            "task": cold_payload.get("task"),
            "source_of_truth": cold_payload.get("source_of_truth"),
            "scoped_git_status_state": cold_payload.get("scoped_git_status_state"),
        },
    }


def summarize_live_acceptance(payload: dict[str, object]) -> dict[str, object]:
    return {
        "state": payload.get("state"),
        "failure_count": payload.get("failure_count"),
        "failures": payload.get("failures", []),
        "required_roles": payload.get("required_roles", []),
        "t0_control_plane": payload.get("t0_control_plane", {}),
        "completion": payload.get("completion", {}),
    }


def failure_payload(root: Path, command: str, failures: list[str], marker: Optional[dict[str, object]] = None) -> dict[str, object]:
    return {
        "kind": "taskboard-overnight-field-run",
        "command": command,
        "state": "failed",
        "root": str(root.resolve()),
        "marker_file": str(marker_path(root).resolve()),
        "failure_count": len(failures),
        "failures": failures,
        "evidence": [],
        "marker": marker or {},
        "boundary": BOUNDARY,
    }


def next_command(root: Path, stage: str) -> str:
    root_text = str(root.resolve())
    if stage == "start":
        return f'python scripts/taskboard_overnight_field_run.py --root "{root_text}" start'
    if stage == "resume":
        return f'python scripts/taskboard_overnight_field_run.py --root "{root_text}" resume'
    if stage == "verify":
        return f'python scripts/taskboard_overnight_field_run.py --root "{root_text}" verify'
    return ""


def quote_cli_value(value: object) -> str:
    text = str(value)
    return '"' + text.replace('"', '\\"') + '"'


def t0_prepare_command(root: Path, goal_override: Optional[str] = None) -> str:
    goal = read_runtime_goal(root) or goal_override or "<user goal>"
    return (
        "python scripts/taskboard_start.py "
        f"--root {quote_cli_value(root.resolve())} "
        f"--goal {quote_cli_value(goal)}"
    )


def with_prepare_guidance(root: Path, payload: dict[str, object], goal_override: Optional[str] = None) -> dict[str, object]:
    if payload.get("next_ready") is not False:
        return {
            **payload,
            "prepare_state": "not-needed",
            "prepare_command": "",
            "prepare_reason": "",
        }
    next_gate = str(payload.get("next_gate") or "next gate")
    return {
        **payload,
        "prepare_state": "needed",
        "prepare_command": t0_prepare_command(root, goal_override),
        "prepare_reason": (
            f"Run or resume T0 until {next_gate} is ready; do not manage T1/T2/T3 directly."
        ),
    }


def next_gate_status(
    root: Path,
    stage: str,
    elapsed_seconds: Optional[int] = None,
    min_elapsed_seconds: int = DEFAULT_MIN_ELAPSED_SECONDS,
) -> dict[str, object]:
    if stage == "none":
        return {"next_gate": "none", "next_ready": True, "next_blockers": []}

    blockers: list[str] = []
    if stage in {"start", "resume"}:
        if stage == "resume" and elapsed_seconds is not None and elapsed_seconds < min_elapsed_seconds:
            blockers.append(f"elapsed_seconds below required minimum: {elapsed_seconds} < {min_elapsed_seconds}")
        cold_acceptance = collect_cold_resume_acceptance(root)
        blockers.extend(str(item) for item in cold_acceptance.get("failures", []))
        return {
            "next_gate": "cold-resume-acceptance",
            "next_ready": not blockers and cold_acceptance.get("state") == "passed",
            "next_blockers": blockers,
            "next_gate_state": cold_acceptance.get("state"),
        }

    if stage == "verify":
        live_acceptance = collect_live_milestone_acceptance(root, ["T1", "T2", "T3"])
        blockers.extend(str(item) for item in live_acceptance.get("failures", []))
        return {
            "next_gate": "live-milestone-acceptance",
            "next_ready": not blockers and live_acceptance.get("state") == "passed",
            "next_blockers": blockers,
            "next_gate_state": live_acceptance.get("state"),
        }

    return {"next_gate": "unknown", "next_ready": False, "next_blockers": [f"unknown next stage: {stage}"]}


def command_status(root: Path, args: Namespace) -> dict[str, object]:
    marker = read_marker(root)
    current_time = float(args.now_epoch) if args.now_epoch is not None else now_epoch()
    base = {
        "kind": "taskboard-overnight-field-run",
        "command": "status",
        "root": str(root.resolve()),
        "marker_file": str(marker_path(root).resolve()),
        "failure_count": 0,
        "failures": [],
        "evidence": [],
        "boundary": BOUNDARY,
    }
    if not marker:
        return with_prepare_guidance(root, {
            **base,
            "state": "not-started",
            "next_stage": "start",
            "next_command": next_command(root, "start"),
            **next_gate_status(root, "start", min_elapsed_seconds=args.min_elapsed_seconds),
            "marker": {},
        }, args.goal)

    marker_state = str(marker.get("state") or "")
    run_id = str(marker.get("run_id") or "<field-run-id>")
    started_at = marker.get("started_at_epoch")
    try:
        started_epoch = float(started_at)
    except (TypeError, ValueError):
        started_epoch = current_time
    elapsed_seconds = max(0, int(current_time - started_epoch))

    if marker_state == "passed":
        return with_prepare_guidance(root, {
            **base,
            "state": "passed",
            "run_id": run_id,
            "elapsed_seconds": elapsed_seconds,
            "next_stage": "none",
            "next_command": "",
            **next_gate_status(root, "none"),
            "marker": marker,
        }, args.goal)

    if marker.get("resume"):
        return with_prepare_guidance(root, {
            **base,
            "state": "ready-to-verify",
            "run_id": run_id,
            "elapsed_seconds": elapsed_seconds,
            "next_stage": "verify",
            "next_command": next_command(root, "verify"),
            **next_gate_status(root, "verify"),
            "marker": marker,
        }, args.goal)

    state = "ready-to-resume" if elapsed_seconds >= args.min_elapsed_seconds else "waiting-overnight"
    return with_prepare_guidance(root, {
        **base,
        "state": state,
        "run_id": run_id,
        "elapsed_seconds": elapsed_seconds,
        "min_elapsed_seconds": args.min_elapsed_seconds,
        "next_stage": "resume",
        "next_command": next_command(root, "resume"),
        **next_gate_status(root, "resume", elapsed_seconds, args.min_elapsed_seconds),
        "marker": marker,
    }, args.goal)


def command_start(root: Path, args: Namespace) -> dict[str, object]:
    existing = read_marker(root)
    if existing and not args.force:
        return failure_payload(root, "start", ["overnight field-run marker already exists; use --force to replace it"], existing)

    cold_acceptance = collect_cold_resume_acceptance(root)
    if cold_acceptance.get("state") != "passed":
        return failure_payload(
            root,
            "start",
            [f"cold resume acceptance did not pass: {item}" for item in cold_acceptance.get("failures", [])],
        ) | {"cold_resume_acceptance": summarize_cold_acceptance(cold_acceptance)}

    current_time = float(args.now_epoch) if args.now_epoch is not None else now_epoch()
    run_id = args.run_id or f"overnight-{int(current_time)}"
    summary = summarize_cold_acceptance(cold_acceptance)
    marker = {
        "kind": "taskboard-overnight-field-run",
        "state": "started",
        "run_id": run_id,
        "started_at_epoch": current_time,
        "started_at": iso_from_epoch(current_time),
        "start": {
            "cold_resume_acceptance_state": cold_acceptance.get("state"),
            "progress_next_role": summary["progress"]["next_role"],
            "progress_task": summary["progress"]["task"],
            "cold_resume_state": summary["cold_resume"]["state"],
        },
        "boundary": BOUNDARY,
    }
    write_marker(root, marker)
    return {
        **marker,
        "command": "start",
        "root": str(root.resolve()),
        "marker_file": str(marker_path(root).resolve()),
        "cold_resume_acceptance": summary,
        "failure_count": 0,
        "failures": [],
        "evidence": [
            "cold resume acceptance passed at overnight start",
            "T0 control-plane overnight marker written",
        ],
    }


def command_resume(root: Path, args: Namespace) -> dict[str, object]:
    marker = read_marker(root)
    if not marker:
        return failure_payload(root, "resume", ["overnight field-run marker missing; run start first"])

    started_at = marker.get("started_at_epoch")
    try:
        started_epoch = float(started_at)
    except (TypeError, ValueError):
        return failure_payload(root, "resume", ["overnight field-run marker missing started_at_epoch"], marker)

    current_time = float(args.now_epoch) if args.now_epoch is not None else now_epoch()
    elapsed_seconds = max(0, int(current_time - started_epoch))
    failures: list[str] = []
    if elapsed_seconds < args.min_elapsed_seconds:
        failures.append(
            f"elapsed_seconds below required minimum: {elapsed_seconds} < {args.min_elapsed_seconds}"
        )

    cold_acceptance = collect_cold_resume_acceptance(root)
    if cold_acceptance.get("state") != "passed":
        failures.extend(f"cold resume acceptance did not pass: {item}" for item in cold_acceptance.get("failures", []))

    summary = summarize_cold_acceptance(cold_acceptance)
    if failures:
        payload = failure_payload(root, "resume", failures, marker)
        payload["elapsed_seconds"] = elapsed_seconds
        payload["min_elapsed_seconds"] = args.min_elapsed_seconds
        payload["cold_resume_acceptance"] = summary
        return payload

    marker["state"] = "resume-verified"
    marker["resume"] = {
        "resumed_at_epoch": current_time,
        "resumed_at": iso_from_epoch(current_time),
        "elapsed_seconds": elapsed_seconds,
        "min_elapsed_seconds": args.min_elapsed_seconds,
        "cold_resume_acceptance_state": cold_acceptance.get("state"),
        "progress_next_role": summary["progress"]["next_role"],
        "progress_task": summary["progress"]["task"],
        "cold_resume_state": summary["cold_resume"]["state"],
    }
    write_marker(root, marker)
    return {
        **marker,
        "command": "resume",
        "root": str(root.resolve()),
        "marker_file": str(marker_path(root).resolve()),
        "elapsed_seconds": elapsed_seconds,
        "min_elapsed_seconds": args.min_elapsed_seconds,
        "cold_resume_acceptance": summary,
        "failure_count": 0,
        "failures": [],
        "evidence": [
            "elapsed threshold accepted",
            "cold resume acceptance passed after worker terminals were reopened",
        ],
    }


def command_verify(root: Path, args: Namespace) -> dict[str, object]:
    marker = read_marker(root)
    if not marker:
        return failure_payload(root, "verify", ["overnight field-run marker missing; run start and resume first"])

    resume = marker.get("resume", {})
    resume_payload = resume if isinstance(resume, dict) else {}
    failures: list[str] = []
    if resume_payload.get("cold_resume_acceptance_state") != "passed":
        failures.append("resume cold resume acceptance was not passed")
    elapsed_seconds = int(resume_payload.get("elapsed_seconds") or 0)
    if elapsed_seconds < args.min_elapsed_seconds:
        failures.append(
            f"recorded elapsed_seconds below required minimum: {elapsed_seconds} < {args.min_elapsed_seconds}"
        )

    live_acceptance = collect_live_milestone_acceptance(root, ["T1", "T2", "T3"])
    if live_acceptance.get("state") != "passed":
        failures.extend(f"live milestone acceptance did not pass: {item}" for item in live_acceptance.get("failures", []))

    live_summary = summarize_live_acceptance(live_acceptance)
    if failures:
        payload = failure_payload(root, "verify", failures, marker)
        payload["elapsed_seconds"] = elapsed_seconds
        payload["min_elapsed_seconds"] = args.min_elapsed_seconds
        payload["live_milestone_acceptance"] = live_summary
        return payload

    marker["state"] = "passed"
    marker["verification"] = {
        "verified_at_epoch": now_epoch(),
        "verified_at": iso_from_epoch(now_epoch()),
        "elapsed_seconds": elapsed_seconds,
        "min_elapsed_seconds": args.min_elapsed_seconds,
        "live_milestone_acceptance_state": live_acceptance.get("state"),
    }
    write_marker(root, marker)
    return {
        **marker,
        "command": "verify",
        "root": str(root.resolve()),
        "marker_file": str(marker_path(root).resolve()),
        "elapsed_seconds": elapsed_seconds,
        "min_elapsed_seconds": args.min_elapsed_seconds,
        "live_milestone_acceptance": live_summary,
        "failure_count": 0,
        "failures": [],
        "evidence": [
            "overnight resume marker accepted",
            "live milestone acceptance passed",
        ],
    }


def format_text(payload: dict[str, object]) -> str:
    lines = [
        f"state={payload.get('state')}",
        f"command={payload.get('command')}",
        f"root={payload.get('root', '')}",
        f"marker_file={payload.get('marker_file', '')}",
        f"failure_count={payload.get('failure_count', 0)}",
        f"boundary={payload.get('boundary', BOUNDARY)}",
    ]
    if "run_id" in payload:
        lines.append(f"run_id={payload['run_id']}")
    if "elapsed_seconds" in payload:
        lines.append(f"elapsed_seconds={payload['elapsed_seconds']}")
    if "next_stage" in payload:
        lines.append(f"next_stage={payload['next_stage']}")
    if "next_command" in payload:
        lines.append(f"next_command={payload['next_command']}")
    if "next_gate" in payload:
        lines.append(f"next_gate={payload['next_gate']}")
    if "next_ready" in payload:
        lines.append(f"next_ready={str(payload['next_ready']).lower()}")
    for blocker in payload.get("next_blockers", []):
        lines.append(f"next_blocker={blocker}")
    if "prepare_state" in payload:
        lines.append(f"prepare_state={payload['prepare_state']}")
    if "prepare_command" in payload:
        lines.append(f"prepare_command={payload['prepare_command']}")
    if "prepare_reason" in payload:
        lines.append(f"prepare_reason={payload['prepare_reason']}")
    for failure in payload.get("failures", []):
        lines.append(f"failure={failure}")
    for item in payload.get("evidence", []):
        lines.append(f"evidence={item}")
    return "\n".join(lines)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing docs/ and .taskboard/")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Report current overnight field-run stage and next command")
    status.add_argument("--format", choices=("text", "json"), default=SUPPRESS, help="Output format")
    status.add_argument("--now-epoch", type=float, default=None, help="Override current epoch for deterministic tests")
    status.add_argument("--min-elapsed-seconds", type=int, default=DEFAULT_MIN_ELAPSED_SECONDS)
    status.add_argument("--goal", default="", help="T0 goal to use in prepare_command when no saved goal exists")

    start = subparsers.add_parser("start", help="Record the pre-close overnight field-run baseline")
    start.add_argument("--format", choices=("text", "json"), default=SUPPRESS, help="Output format")
    start.add_argument("--run-id", default="", help="Stable field-run id to store in the marker")
    start.add_argument("--now-epoch", type=float, default=None, help="Override current epoch for deterministic tests")
    start.add_argument("--force", action="store_true", help="Replace an existing marker")

    resume = subparsers.add_parser("resume", help="Record next-day worker-terminal reopen evidence")
    resume.add_argument("--format", choices=("text", "json"), default=SUPPRESS, help="Output format")
    resume.add_argument("--now-epoch", type=float, default=None, help="Override current epoch for deterministic tests")
    resume.add_argument("--min-elapsed-seconds", type=int, default=DEFAULT_MIN_ELAPSED_SECONDS)

    verify = subparsers.add_parser("verify", help="Verify overnight resume plus live milestone acceptance")
    verify.add_argument("--format", choices=("text", "json"), default=SUPPRESS, help="Output format")
    verify.add_argument("--min-elapsed-seconds", type=int, default=DEFAULT_MIN_ELAPSED_SECONDS)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    if args.command == "status":
        payload = command_status(root, args)
    elif args.command == "start":
        payload = command_start(root, args)
    elif args.command == "resume":
        payload = command_resume(root, args)
    elif args.command == "verify":
        payload = command_verify(root, args)
    else:
        parser.error(f"unknown command: {args.command}")

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(payload))
    success_states = {
        "not-started",
        "waiting-overnight",
        "ready-to-resume",
        "ready-to-verify",
        "started",
        "resume-verified",
        "passed",
    }
    return 0 if payload.get("state") in success_states else 1


if __name__ == "__main__":
    raise SystemExit(main())
