#!/usr/bin/env python3
"""Start the T0-managed TASKBOARD supervisor with practical defaults."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys
from typing import Optional

from taskboard_loop import default_event_log_file, default_state_file, format_text, run_loop, write_state_snapshot
from taskboard_t0 import default_target_dir


DEFAULT_AGENT_TEMPLATE = 'codex --prompt-file "{target_file}"'
STARTER_AUTO_BOUNDARY = (
    "T0 one-command auto mode: run the supervisor as the user-facing manager, "
    "launch or recover T1/T2/T3 when needed, and keep T0 out of worker tasks."
)


def annotate_starter_mode(results: list[dict[str, object]], auto_mode: bool) -> list[dict[str, object]]:
    mode = "auto" if auto_mode else "dry-check"
    boundary = STARTER_AUTO_BOUNDARY if auto_mode else "T0 starter dry-check mode: report orchestration without launching workers."
    for payload in results:
        payload["auto_mode"] = auto_mode
        payload["starter_mode"] = mode
        payload["starter_boundary"] = boundary
    return results


def option_was_provided(argv: Optional[list[str]], option: str) -> bool:
    args = argv if argv is not None else sys.argv[1:]
    return any(item == option or item.startswith(f"{option}=") for item in args)


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
        )
        results = annotate_starter_mode(results, args.auto)
        if state_file is not None and results:
            snapshot_goal = str(results[-1].get("goal") or args.goal or "")
            write_state_snapshot(state_file, root, snapshot_goal, results, not args.no_stop_on_complete)
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
