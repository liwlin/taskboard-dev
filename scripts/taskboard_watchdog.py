#!/usr/bin/env python3
"""Watch and resume the T0 supervisor without asking the user to manage workers."""

from argparse import ArgumentParser
from pathlib import Path
import json
import subprocess
from typing import Callable, Optional

from taskboard_progress import report_progress


Runner = Callable[[str], int]


def run_resume_command(command: str) -> int:
    result = subprocess.run(command, shell=True, check=False)
    return int(result.returncode)


def report_watchdog(root: Path, execute: bool = False, runner: Optional[Runner] = None) -> dict[str, object]:
    progress = report_progress(root)
    t0_supervisor_state = str(progress.get("t0_supervisor_state") or "")
    resume_command = str(progress.get("resume_command") or "")
    should_resume = bool(resume_command) and t0_supervisor_state in {"missing", "stale"}
    executed_resume = False
    resume_returncode: Optional[int] = None
    state = t0_supervisor_state or "unknown"

    if should_resume and execute:
        command_runner = runner or run_resume_command
        resume_returncode = command_runner(resume_command)
        executed_resume = True
        state = "resumed"

    if not should_resume:
        user_action = "No user action required; T0 supervisor is fresh or no resume is currently safe."
        resume_command = ""
    elif execute:
        user_action = "T0 watchdog resumed T0 with resume_command; do not manage T1/T2/T3 directly."
    else:
        user_action = "Resume T0 with resume_command; do not manage T1/T2/T3 directly."

    return {
        "kind": "taskboard-t0-watchdog",
        "state": state,
        "goal": str(progress.get("goal") or ""),
        "should_resume": should_resume,
        "executed_resume": executed_resume,
        "resume_returncode": resume_returncode,
        "resume_command": resume_command,
        "t0_supervisor_state": t0_supervisor_state,
        "t0_supervisor_age_seconds": progress.get("t0_supervisor_age_seconds"),
        "t0_supervisor_stale_after_seconds": progress.get("t0_supervisor_stale_after_seconds"),
        "user_action": user_action,
        "boundary": (
            "T0 watchdog only checks and resumes the T0 supervisor; "
            "it must not launch or manage T1/T2/T3 directly."
        ),
    }


def format_text(payload: dict[str, object]) -> str:
    lines = [
        f"kind={payload['kind']}",
        f"state={payload['state']}",
        f"goal={payload['goal']}",
        f"should_resume={payload['should_resume']}",
        f"executed_resume={payload['executed_resume']}",
        f"t0_supervisor_state={payload['t0_supervisor_state']}",
        f"t0_supervisor_age_seconds={payload['t0_supervisor_age_seconds']}",
        f"t0_supervisor_stale_after_seconds={payload['t0_supervisor_stale_after_seconds']}",
        f"user_action={payload['user_action']}",
        f"boundary={payload['boundary']}",
    ]
    if payload.get("resume_returncode") is not None:
        lines.append(f"resume_returncode={payload['resume_returncode']}")
    if payload.get("resume_command"):
        lines.append(f"resume_command={payload['resume_command']}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing TASKBOARD files")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the T0 resume command when the T0 supervisor is stale or missing.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    payload = report_watchdog(Path(args.root).resolve(), args.execute)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
