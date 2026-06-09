#!/usr/bin/env python3
"""Run the T0 supervisor loop without doing worker tasks."""

from argparse import ArgumentParser
from pathlib import Path
import json
import subprocess
import sys
import time
from typing import Optional

from taskboard_health import report_health
from taskboard_sessions import probe_sessions
from taskboard_t0 import dispatch


T0_BOUNDARY = (
    "T0 supervisor-only: combine session liveness, queue health, and dispatch; "
    "launch or recover T1/T2/T3 when requested, but do not perform design, review, "
    "implementation, verification, or commit work in T0."
)


def choose_launch_commands(session_probe: dict[str, object], dispatch_plan: dict[str, object]) -> list[str]:
    recovery_commands = session_probe.get("recovery_commands", [])
    if recovery_commands:
        return list(recovery_commands)
    return list(dispatch_plan.get("launch_commands", []))


def build_actions(
    session_probe: dict[str, object],
    queue_health: dict[str, object],
    dispatch_plan: dict[str, object],
    launch_commands: list[str],
) -> list[str]:
    actions: list[str] = []
    actions.extend(str(action) for action in session_probe.get("recovery_actions", []))
    actions.extend(str(action) for action in queue_health.get("actions", []))

    if launch_commands:
        actions.append("launch/recover managed role sessions with generated commands")
    elif dispatch_plan.get("state") == "needs-goal":
        actions.append("ask user for one T0 goal")
    elif dispatch_plan.get("state") == "dispatch":
        role = dispatch_plan.get("next_role")
        actions.append(f"keep taskboard-{role} active from the T0 dispatch plan")
    elif dispatch_plan.get("state") == "complete":
        actions.append("summarize completion to the user")

    deduped: list[str] = []
    for action in actions:
        if action not in deduped:
            deduped.append(action)
    return deduped


def execute_commands(commands: list[str]) -> list[dict[str, object]]:
    results = []
    for command in commands:
        completed = subprocess.run(
            command,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        results.append(
            {
                "command": command,
                "returncode": completed.returncode,
                "output": completed.stdout.strip(),
            }
        )
    return results


def run_once(
    root: Path,
    goal: Optional[str],
    stale_minutes: int,
    stale_seconds: int,
    launcher: str,
    agent_template: Optional[str],
    execute_launches: bool,
) -> dict[str, object]:
    session_probe = probe_sessions(
        root,
        stale_seconds,
        ["T1", "T2", "T3"],
        launcher,
        agent_template,
        goal,
    )
    queue_health = report_health(root, stale_minutes, goal)
    dispatch_plan = dispatch(root, goal, "terminal", launcher, agent_template)
    launch_commands = choose_launch_commands(session_probe, dispatch_plan)
    executed_commands = execute_commands(launch_commands) if execute_launches else []

    state = "attention"
    if dispatch_plan.get("state") == "needs-goal":
        state = "needs-goal"
    elif executed_commands and any(item["returncode"] != 0 for item in executed_commands):
        state = "attention"
    elif session_probe.get("state") == "healthy" and queue_health.get("state") in {"empty"}:
        state = "idle"
    elif session_probe.get("state") == "healthy" and queue_health.get("state") != "attention":
        state = "active"

    return {
        "state": state,
        "goal": goal or "",
        "boundary": T0_BOUNDARY,
        "session_probe": session_probe,
        "queue_health": queue_health,
        "dispatch": dispatch_plan,
        "launch_commands": launch_commands,
        "executed_commands": executed_commands,
        "actions": build_actions(session_probe, queue_health, dispatch_plan, launch_commands),
    }


def run_loop(
    root: Path,
    goal: Optional[str],
    stale_minutes: int,
    stale_seconds: int,
    launcher: str,
    agent_template: Optional[str],
    execute_launches: bool,
    iterations: Optional[int],
    interval_seconds: int,
) -> list[dict[str, object]]:
    if interval_seconds < 0:
        raise ValueError("--interval-seconds must be >= 0")
    if iterations is not None and iterations < 1:
        raise ValueError("--iterations must be >= 1")

    results: list[dict[str, object]] = []
    count = 0
    while iterations is None or count < iterations:
        results.append(
            run_once(
                root,
                goal,
                stale_minutes,
                stale_seconds,
                launcher,
                agent_template,
                execute_launches,
            )
        )
        count += 1
        if iterations is not None and count >= iterations:
            break
        time.sleep(interval_seconds)
    return results


def format_text(results: list[dict[str, object]]) -> str:
    lines = []
    for index, payload in enumerate(results, start=1):
        lines.extend(
            [
                f"iteration={index}",
                f"state={payload['state']}",
                f"boundary={payload['boundary']}",
                f"next_role={payload['dispatch'].get('next_role')}",
                f"queue_state={payload['queue_health'].get('state')}",
                f"session_state={payload['session_probe'].get('state')}",
                "actions:",
            ]
        )
        for action in payload["actions"]:
            lines.append(f"- {action}")
        launch_commands = payload["launch_commands"]
        if launch_commands:
            lines.append("launch_commands:")
            for command in launch_commands:
                lines.append(f"- {command}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing TASKBOARD files")
    parser.add_argument("--goal", help="Current user goal for T0")
    parser.add_argument("--stale-minutes", type=int, default=30)
    parser.add_argument("--stale-seconds", type=int, default=300)
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--forever",
        action="store_true",
        help="Run until interrupted instead of stopping after --iterations",
    )
    parser.add_argument(
        "--launcher",
        choices=("none", "windows-terminal", "powershell", "tmux"),
        default="none",
        help="Optional launcher command family for managed role recovery commands",
    )
    parser.add_argument(
        "--agent-template",
        help="Command template for generated role commands. Supports {role}, {title}, {command}, and {target}.",
    )
    parser.add_argument(
        "--execute-launches",
        action="store_true",
        help="Execute generated launcher commands. This only launches/recover roles; T0 still does not do worker tasks.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        results = run_loop(
            Path(args.root).resolve(),
            args.goal,
            args.stale_minutes,
            args.stale_seconds,
            args.launcher,
            args.agent_template,
            args.execute_launches,
            None if args.forever else args.iterations,
            args.interval_seconds,
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
