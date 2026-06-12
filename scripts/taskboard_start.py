#!/usr/bin/env python3
"""Start the T0-managed TASKBOARD supervisor with practical defaults."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys
from typing import Optional

from taskboard_loop import (
    append_event_log,
    build_launch_probe,
    build_resume_config,
    default_event_log_file,
    default_state_file,
    format_text,
    run_loop,
    write_state_snapshot,
)
from taskboard_progress import build_resume_command
from taskboard_t0 import DEFAULT_AGENT_TEMPLATE, default_target_dir, read_goal, write_runtime_goal


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
    fallback_launchers: Optional[list[str]] = None,
    agent_preflight_enabled: bool = True,
    agent_preflight_command: Optional[str] = None,
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
        fallback_launchers,
        agent_preflight_enabled,
        agent_preflight_command,
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
        "resume_command": build_resume_command(root, goal, "interrupted", 0, False, resume_config, auto_mode),
        "user_action": "Resume T0 with resume_command; do not manage T1/T2/T3 directly.",
        "dispatch": {"state": "interrupted", "next_role": "T0", "task": "none"},
        "assignment": {
            "state": "none",
            "role": "T0",
            "task": "none",
            "assignment_id": "",
            "reason": "t0-interrupted",
        },
        "queue_health": {"state": "unknown", "active_count": 0},
        "session_probe": {"state": "unknown", "missing_roles": [], "stale_roles": []},
        "stop_gate_report": {"stop_gate_count": 0, "stop_gates": []},
        "actions": ["resume T0 from the persisted interruption command"],
        "target_files": [],
        "planned_launch_commands": [],
        "requested_launch_commands": [],
        "launch_commands": [],
        "suppressed_launches": [],
        "executed_commands": [],
        **metadata,
    }


def build_config_error_payload(
    root: Path,
    goal: str,
    error: str,
    launcher: str,
    agent_template: str,
    stale_minutes: int,
    stale_seconds: int,
    interval_seconds: int,
    assignment_lease_seconds: int,
    launch_lease_seconds: int,
    target_dir: Optional[Path],
    auto_mode: bool,
    fallback_launchers: Optional[list[str]] = None,
    agent_preflight_enabled: bool = True,
    agent_preflight_command: Optional[str] = None,
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
        fallback_launchers,
        agent_preflight_enabled,
        agent_preflight_command,
    )
    metadata = starter_metadata(auto_mode)
    launch_probe = build_launch_probe(
        launcher,
        {
            "enabled": agent_preflight_enabled,
            "state": "config-error",
            "reason": "agent-preflight-config-error",
            "command": agent_preflight_command or agent_template or "",
            "error": error,
        },
    )
    return {
        "kind": "taskboard-t0-config-error",
        "state": "config-error",
        "goal": goal,
        "error": error,
        "boundary": (
            "T0 configuration error report: fix the T0 launcher/template configuration; "
            "do not ask the user to manage T1/T2/T3 directly."
        ),
        "resume_config": resume_config,
        "resume_command": "",
        "user_action": "T0 configuration failed; fix T0 launcher configuration before resuming.",
        "dispatch": {"state": "config-error", "next_role": "T0", "task": "none"},
        "assignment": {
            "state": "none",
            "role": "T0",
            "task": "none",
            "assignment_id": "",
            "reason": "t0-config-error",
        },
        "queue_health": {"state": "unknown", "active_count": 0},
        "session_probe": {"state": "unknown", "missing_roles": [], "stale_roles": []},
        "stop_gate_report": {"stop_gate_count": 0, "stop_gates": []},
        "actions": ["fix T0 launcher configuration"],
        "target_files": [],
        "planned_launch_commands": [],
        "requested_launch_commands": [],
        "launch_commands": [],
        "suppressed_launches": [],
        "executed_commands": [],
        "launch_probe": launch_probe,
        **metadata,
    }


def persist_interruption_payload(
    state_file: Optional[Path],
    event_log_file: Optional[Path],
    root: Path,
    goal: str,
    payload: dict[str, object],
    stop_on_complete: bool,
) -> None:
    if state_file is not None:
        write_state_snapshot(state_file, root, goal, [payload], stop_on_complete)
    if event_log_file is not None:
        append_event_log(event_log_file, root, goal, 1, payload)


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
        "--fallback-launcher",
        action="append",
        choices=("windows-terminal", "powershell", "tmux"),
        default=[],
        help="Fallback launcher to try after the primary launcher fails. Repeat to set priority order.",
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
        "--no-agent-preflight",
        action="store_true",
        help="Disable the worker agent command preflight before executing launcher commands.",
    )
    parser.add_argument(
        "--agent-preflight-command",
        help="Optional command T0 runs once before worker launches to verify agent CLI readiness.",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="One-command T0 automation mode. This is now the default unless --dry-run is set.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report T0 orchestration without executing managed-role launches or running indefinitely.",
    )
    parser.add_argument("--stale-minutes", type=int, default=30)
    parser.add_argument("--stale-seconds", type=int, default=300)
    parser.add_argument("--assignment-lease-seconds", type=int, default=300)
    parser.add_argument("--launch-lease-seconds", type=int, default=300)
    parser.add_argument("--checkout-owner-lease-seconds", type=int, default=1800)
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
    parser.add_argument(
        "--checkout-owner-id",
        help="Optional stable top-level checkout owner id for launcher execution guard.",
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
    auto_mode = args.auto or not args.dry_run
    execute_launches = args.execute_launches or auto_mode
    iterations = args.iterations
    if auto_mode and not option_was_provided(argv, "--iterations") and not args.forever:
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
            starter_metadata(auto_mode),
            args.fallback_launcher,
            not args.no_agent_preflight,
            args.agent_preflight_command,
            args.checkout_owner_id,
            args.checkout_owner_lease_seconds,
        )
        results = annotate_starter_mode(results, auto_mode)
        if state_file is not None and results:
            snapshot_goal = str(results[-1].get("goal") or args.goal or "")
            write_state_snapshot(state_file, root, snapshot_goal, results, not args.no_stop_on_complete)
    except KeyboardInterrupt:
        effective_goal = read_goal(root, args.goal)
        write_runtime_goal(root, effective_goal)
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
            auto_mode,
            args.fallback_launcher,
            not args.no_agent_preflight,
            args.agent_preflight_command,
        )
        persist_interruption_payload(
            state_file,
            event_log_file,
            root,
            effective_goal,
            payload,
            not args.no_stop_on_complete,
        )
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(format_interruption_text(payload))
        return 130
    except ValueError as exc:
        effective_goal = read_goal(root, args.goal)
        write_runtime_goal(root, effective_goal)
        payload = build_config_error_payload(
            root,
            effective_goal,
            str(exc),
            args.launcher,
            args.agent_template,
            args.stale_minutes,
            args.stale_seconds,
            args.interval_seconds,
            args.assignment_lease_seconds,
            args.launch_lease_seconds,
            target_dir,
            auto_mode,
            args.fallback_launcher,
            not args.no_agent_preflight,
            args.agent_preflight_command,
        )
        persist_interruption_payload(
            state_file,
            event_log_file,
            root,
            effective_goal,
            payload,
            not args.no_stop_on_complete,
        )
        print(exc, file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
