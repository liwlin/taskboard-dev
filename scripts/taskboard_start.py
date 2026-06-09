#!/usr/bin/env python3
"""Start the T0-managed TASKBOARD supervisor with practical defaults."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys
from typing import Optional

from taskboard_loop import (
    build_resume_config,
    default_event_log_file,
    default_state_file,
    format_text,
    run_loop,
    write_state_snapshot,
)
from taskboard_progress import build_resume_command
from taskboard_t0 import default_target_dir, read_goal


DEFAULT_AGENT_TEMPLATE = 'codex --prompt-file "{target_file}"'
STARTER_AUTO_BOUNDARY = (
    "T0 one-command auto mode: run the supervisor as the user-facing manager, "
    "launch or recover T1/T2/T3 when needed, and keep T0 out of worker tasks."
)


def annotate_starter_mode(results: list[dict[str, object]], auto_mode: bool) -> list[dict[str, object]]:
    metadata = starter_metadata(auto_mode)
    for payload in results:
        payload.update(metadata)
    return results


def starter_metadata(auto_mode: bool) -> dict[str, object]:
    mode = "auto" if auto_mode else "dry-check"
    boundary = STARTER_AUTO_BOUNDARY if auto_mode else "T0 starter dry-check mode: report orchestration without launching workers."
    return {
        "auto_mode": auto_mode,
        "starter_mode": mode,
        "starter_boundary": boundary,
    }


def option_was_provided(argv: Optional[list[str]], option: str) -> bool:
    args = argv if argv is not None else sys.argv[1:]
    return any(item == option or item.startswith(f"{option}=") for item in args)


def build_interruption_payload(
    root: Path,
    goal: str,
    launcher: str,
    agent_template: str,
    stale_minutes: int,
    stale_seconds: int,
    interval_seconds: int,
    assignment_lease_seconds: int,
    launch_lease_seconds: int,
    target_dir: Optional[Path],
    auto_mode: bool,
) -> dict[str, object]:
    resume_config = build_resume_config(
        launcher,
        agent_template,
        stale_minutes,
        stale_seconds,
        interval_seconds,
        assignment_lease_seconds,
        launch_lease_seconds,
        target_dir,
    )
    metadata = starter_metadata(auto_mode)
    return {
        "kind": "taskboard-t0-interruption",
        "state": "interrupted",
        "goal": goal,
        "boundary": (
            "T0 interruption report: user-facing resume guidance only; "
            "T0 does not ask the user to manage T1/T2/T3."
        ),
        "resume_config": resume_config,
        "resume_command": build_resume_command(root, goal, "interrupted", 0, False, resume_config),
        "user_action": "Resume T0 with resume_command; do not manage T1/T2/T3 directly.",
        **metadata,
    }


def format_interruption_text(payload: dict[str, object]) -> str:
    lines = [
        f"state={payload['state']}",
        f"goal={payload['goal']}",
        f"boundary={payload['boundary']}",
        f"user_action={payload['user_action']}",
    ]
    resume_command = payload.get("resume_command")
    if resume_command:
        lines.append(f"resume_command={resume_command}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing TASKBOARD files")
    parser.add_argument("--goal", help="User goal for T0")
    parser.add_argument(
        "--launcher",
        choices=("windows-terminal", "powershell", "tmux", "none"),
        default="windows-terminal",
        help="Managed role launcher. Defaults to Windows Terminal for one-terminal T0 startup.",
    )
    parser.add_argument(
        "--agent-template",
        default=DEFAULT_AGENT_TEMPLATE,
        help="Agent command template for worker terminals. Supports {role}, {title}, {command}, {target}, {target_file}.",
    )
    parser.add_argument(
        "--execute-launches",
        action="store_true",
        help="Actually launch/recover T1/T2/T3 role terminals. Without this, start runs as a dry orchestration check.",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="One-command T0 automation mode: execute managed-role launches and run until completion unless --iterations is set.",
    )
    parser.add_argument("--stale-minutes", type=int, default=30)
    parser.add_argument("--stale-seconds", type=int, default=300)
    parser.add_argument("--assignment-lease-seconds", type=int, default=300)
    parser.add_argument("--launch-lease-seconds", type=int, default=300)
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--forever",
        action="store_true",
        help="Run until completion or interruption instead of stopping after --iterations.",
    )
    parser.add_argument(
        "--no-stop-on-complete",
        action="store_true",
        help="Keep looping after completion sentinel for monitoring/debugging.",
    )
    parser.add_argument(
        "--no-stop-on-stop-gate",
        action="store_true",
        help="Keep looping after a user stop gate for monitoring/debugging.",
    )
    parser.add_argument(
        "--state-file",
        help="Path for the latest T0 supervisor runtime snapshot. Defaults to .taskboard/t0/latest.json.",
    )
    parser.add_argument(
        "--no-state-file",
        action="store_true",
        help="Disable writing the latest T0 supervisor runtime snapshot.",
    )
    parser.add_argument(
        "--event-log-file",
        help="Path for the append-only T0 supervisor event log. Defaults to .taskboard/t0/events.jsonl.",
    )
    parser.add_argument(
        "--no-event-log",
        action="store_true",
        help="Disable writing the append-only T0 supervisor event log.",
    )
    parser.add_argument(
        "--target-dir",
        help="Directory for per-role T1/T2/T3 target files. Defaults to .taskboard/targets.",
    )
    parser.add_argument(
        "--no-target-files",
        action="store_true",
        help="Disable writing per-role target files for dry checks.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    state_file = None if args.no_state_file else Path(args.state_file).resolve() if args.state_file else default_state_file(root)
    event_log_file = (
        None
        if args.no_event_log
        else Path(args.event_log_file).resolve()
        if args.event_log_file
        else default_event_log_file(root)
    )
    target_dir = None if args.no_target_files else Path(args.target_dir).resolve() if args.target_dir else default_target_dir(root)
    execute_launches = args.execute_launches or args.auto
    iterations = args.iterations
    if args.auto and not option_was_provided(argv, "--iterations") and not args.forever:
        iterations = None

    try:
        results = run_loop(
            root,
            args.goal,
            args.stale_minutes,
            args.stale_seconds,
            args.launcher,
            args.agent_template,
            execute_launches,
            None if args.forever else iterations,
            args.interval_seconds,
            args.assignment_lease_seconds,
            not args.no_stop_on_complete,
            state_file,
            target_dir,
            args.launch_lease_seconds,
            event_log_file,
            not args.no_stop_on_stop_gate,
            starter_metadata(args.auto),
        )
        results = annotate_starter_mode(results, args.auto)
        if state_file is not None and results:
            snapshot_goal = str(results[-1].get("goal") or args.goal or "")
            write_state_snapshot(state_file, root, snapshot_goal, results, not args.no_stop_on_complete)
    except KeyboardInterrupt:
        effective_goal = read_goal(root, args.goal)
        payload = build_interruption_payload(
            root,
            effective_goal,
            args.launcher,
            args.agent_template,
            args.stale_minutes,
            args.stale_seconds,
            args.interval_seconds,
            args.assignment_lease_seconds,
            args.launch_lease_seconds,
            target_dir,
            args.auto,
        )
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(format_interruption_text(payload))
        return 130
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
