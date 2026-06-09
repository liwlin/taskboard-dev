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
from taskboard_t0 import default_target_dir, dispatch


T0_BOUNDARY = (
    "T0 supervisor-only: combine session liveness, queue health, and dispatch; "
    "launch or recover T1/T2/T3 when requested, but do not perform design, review, "
    "implementation, verification, or commit work in T0."
)


def choose_launch_commands(session_probe: dict[str, object], dispatch_plan: dict[str, object]) -> list[str]:
    if dispatch_plan.get("state") == "complete":
        return []
    recovery_commands = session_probe.get("recovery_commands", [])
    if recovery_commands:
        return list(recovery_commands)
    return list(dispatch_plan.get("launch_commands", []))


def build_assignment(
    session_probe: dict[str, object],
    dispatch_plan: dict[str, object],
    assignment_lease_seconds: int,
) -> dict[str, object]:
    role = str(dispatch_plan.get("next_role") or "")
    task = str(dispatch_plan.get("task") or "none")
    if dispatch_plan.get("state") != "dispatch" or role not in {"T1", "T2", "T3"} or task == "none":
        return {
            "state": "none",
            "role": role,
            "task": task,
            "assignment_id": "",
            "reason": "no-active-worker-task",
        }

    assignment_id = f"{role}:{task}"
    sessions = session_probe.get("sessions", {})
    session = sessions.get(role, {}) if isinstance(sessions, dict) else {}
    session_state = session.get("state") if isinstance(session, dict) else "missing"
    acknowledged_task = session.get("task") if isinstance(session, dict) else None
    acknowledged_assignment = session.get("assignment_id") if isinstance(session, dict) else None
    age_seconds = session.get("age_seconds") if isinstance(session, dict) else None
    try:
        normalized_age = int(age_seconds) if age_seconds is not None else None
    except (TypeError, ValueError):
        normalized_age = None

    if session_state != "alive":
        state = "unassigned"
        reason = f"taskboard-{role} is {session_state or 'missing'}"
    elif (
        acknowledged_task == task
        and acknowledged_assignment == assignment_id
        and normalized_age is not None
        and normalized_age >= assignment_lease_seconds
    ):
        state = "lease-expired"
        reason = "worker-heartbeat-assignment-lease-expired"
    elif acknowledged_task == task and acknowledged_assignment == assignment_id:
        state = "acknowledged"
        reason = "worker-heartbeat-acknowledged-task"
    elif acknowledged_task == task:
        state = "pending-ack"
        reason = "worker-heartbeat-missing-or-mismatched-assignment-id"
    else:
        state = "pending-ack"
        reason = "worker-heartbeat-has-not-acknowledged-task"

    return {
        "state": state,
        "role": role,
        "task": task,
        "assignment_id": acknowledged_assignment or assignment_id,
        "expected_assignment_id": assignment_id,
        "acknowledged_task": acknowledged_task,
        "age_seconds": normalized_age,
        "lease_seconds": assignment_lease_seconds,
        "reason": reason,
        "boundary": "T0 tracks assignment acknowledgement only; T0 does not execute the worker task.",
    }


def build_actions(
    session_probe: dict[str, object],
    queue_health: dict[str, object],
    dispatch_plan: dict[str, object],
    launch_commands: list[str],
    assignment: dict[str, object],
) -> list[str]:
    actions: list[str] = []
    if dispatch_plan.get("state") == "complete":
        return ["summarize completion to the user"]

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

    if assignment.get("state") in {"pending-ack", "unassigned"}:
        role = assignment.get("role")
        task = assignment.get("task")
        actions.append(f"reissue target to taskboard-{role} until heartbeat acknowledges {task}")
    elif assignment.get("state") == "lease-expired":
        role = assignment.get("role")
        task = assignment.get("task")
        actions.append(f"reissue target to taskboard-{role}; assignment lease expired for {task}")

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


def write_role_target_files(dispatch_plan: dict[str, object]) -> list[dict[str, object]]:
    target_files: list[dict[str, object]] = []
    sessions = dispatch_plan.get("managed_sessions", [])
    if not isinstance(sessions, list):
        return target_files

    for session in sessions:
        if not isinstance(session, dict):
            continue
        target_file = session.get("target_file")
        target = session.get("target")
        role = session.get("role")
        title = session.get("title")
        if not target_file or not target or not role or not title:
            continue
        path = Path(str(target_file))
        body = (
            f"# {title} target\n\n"
            "kind: taskboard-role-target\n"
            "managed_by: T0\n"
            f"role: {role}\n"
            f"title: {title}\n"
            f"updated_at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            "boundary: T0 writes role targets only; the isolated worker session executes its own role work.\n\n"
            "---\n\n"
            f"{target}\n"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        target_files.append(
            {
                "role": str(role),
                "title": str(title),
                "path": str(path),
                "kind": "taskboard-role-target",
            }
        )
    return target_files


def run_once(
    root: Path,
    goal: Optional[str],
    stale_minutes: int,
    stale_seconds: int,
    launcher: str,
    agent_template: Optional[str],
    execute_launches: bool,
    assignment_lease_seconds: int,
    target_dir: Optional[Path],
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
    dispatch_plan = dispatch(root, goal, "terminal", launcher, agent_template, target_dir)
    target_files = write_role_target_files(dispatch_plan) if target_dir is not None else []
    launch_commands = choose_launch_commands(session_probe, dispatch_plan)
    executed_commands = execute_commands(launch_commands) if execute_launches else []
    assignment = build_assignment(session_probe, dispatch_plan, assignment_lease_seconds)

    state = "attention"
    if dispatch_plan.get("state") == "needs-goal":
        state = "needs-goal"
    elif dispatch_plan.get("state") == "complete":
        state = "idle"
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
        "assignment": assignment,
        "target_files": target_files,
        "launch_commands": launch_commands,
        "executed_commands": executed_commands,
        "actions": build_actions(session_probe, queue_health, dispatch_plan, launch_commands, assignment),
    }


def default_state_file(root: Path) -> Path:
    return root / ".taskboard" / "t0" / "latest.json"


def write_state_snapshot(
    state_file: Path,
    root: Path,
    goal: Optional[str],
    results: list[dict[str, object]],
    stop_on_complete: bool,
) -> None:
    if not results:
        return

    snapshot = {
        "kind": "taskboard-t0-supervisor-state",
        "version": 1,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root": str(root),
        "goal": goal or "",
        "iteration_count": len(results),
        "stop_on_complete": stop_on_complete,
        "boundary": T0_BOUNDARY,
        "latest": results[-1],
    }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


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
    assignment_lease_seconds: int,
    stop_on_complete: bool,
    state_file: Optional[Path],
    target_dir: Optional[Path],
) -> list[dict[str, object]]:
    if interval_seconds < 0:
        raise ValueError("--interval-seconds must be >= 0")
    if iterations is not None and iterations < 1:
        raise ValueError("--iterations must be >= 1")
    if assignment_lease_seconds < 1:
        raise ValueError("--assignment-lease-seconds must be >= 1")

    results: list[dict[str, object]] = []
    count = 0
    while iterations is None or count < iterations:
        payload = run_once(
            root,
            goal,
            stale_minutes,
            stale_seconds,
            launcher,
            agent_template,
            execute_launches,
            assignment_lease_seconds,
            target_dir,
        )
        results.append(payload)
        count += 1
        if state_file is not None:
            write_state_snapshot(state_file, root, goal, results, stop_on_complete)
        if stop_on_complete and payload["dispatch"].get("state") == "complete":
            break
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
                f"assignment_state={payload['assignment'].get('state')}",
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
    parser.add_argument("--assignment-lease-seconds", type=int, default=300)
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--forever",
        action="store_true",
        help="Run until completion or interruption instead of stopping after --iterations",
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
    root = Path(args.root).resolve()
    state_file = None
    if not args.no_state_file:
        state_file = Path(args.state_file).resolve() if args.state_file else default_state_file(root)
    target_dir = None
    if not args.no_target_files:
        target_dir = Path(args.target_dir).resolve() if args.target_dir else default_target_dir(root)

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
