#!/usr/bin/env python3
"""Start the T0-managed TASKBOARD supervisor with practical defaults."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys
from typing import Optional

from taskboard_loop import default_state_file, format_text, run_loop
from taskboard_t0 import default_target_dir


DEFAULT_AGENT_TEMPLATE = 'codex --prompt-file "{target_file}"'


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
    parser.add_argument("--stale-minutes", type=int, default=30)
    parser.add_argument("--stale-seconds", type=int, default=300)
    parser.add_argument("--assignment-lease-seconds", type=int, default=300)
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
        "--state-file",
        help="Path for the latest T0 supervisor runtime snapshot. Defaults to .taskboard/t0/latest.json.",
    )
    parser.add_argument(
        "--no-state-file",
        action="store_true",
        help="Disable writing the latest T0 supervisor runtime snapshot.",
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
    target_dir = None if args.no_target_files else Path(args.target_dir).resolve() if args.target_dir else default_target_dir(root)

    try:
        results = run_loop(
            root,
            args.goal,
            args.stale_minutes,
            args.stale_seconds,
            args.launcher,
            args.agent_template,
            args.execute_launches,
            None if args.forever else args.iterations,
            args.interval_seconds,
            args.assignment_lease_seconds,
            not args.no_stop_on_complete,
            state_file,
            target_dir,
        )
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
