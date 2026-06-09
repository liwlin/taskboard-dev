#!/usr/bin/env python3
"""Run the T0 supervisor loop without doing worker tasks."""

from argparse import ArgumentParser
from pathlib import Path
import json
import re
import subprocess
import sys
import time
from typing import Optional

from taskboard_health import report_health
from taskboard_sessions import probe_sessions
from taskboard_stopgates import report_stop_gates
from taskboard_t0 import default_target_dir, dispatch, read_goal, write_runtime_goal


T0_BOUNDARY = (
    "T0 supervisor-only: combine session liveness, queue health, and dispatch; "
    "launch or recover T1/T2/T3 when requested, but do not perform design, review, "
    "implementation, verification, or commit work in T0."
)

LAUNCH_ROLE_RE = re.compile(r"taskboard-(T[123])")


def choose_launch_commands(session_probe: dict[str, object], dispatch_plan: dict[str, object]) -> list[str]:
    if dispatch_plan.get("state") == "complete":
        return []
    recovery_commands = session_probe.get("recovery_commands", [])
    if recovery_commands:
        return list(recovery_commands)
    return list(dispatch_plan.get("launch_commands", []))


def choose_executable_launch_commands(session_probe: dict[str, object], dispatch_plan: dict[str, object]) -> list[str]:
    if dispatch_plan.get("state") == "complete":
        return []
    recovery_commands = session_probe.get("recovery_commands", [])
    return list(recovery_commands) if recovery_commands else []


def default_launch_state_file(root: Path) -> Path:
    return root / ".taskboard" / "t0" / "launches.json"


def read_launch_state(root: Path) -> dict[str, object]:
    path = default_launch_state_file(root)
    if not path.exists():
        return {"kind": "taskboard-t0-launch-state", "version": 1, "roles": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"kind": "taskboard-t0-launch-state", "version": 1, "roles": {}}
    if not isinstance(payload, dict):
        return {"kind": "taskboard-t0-launch-state", "version": 1, "roles": {}}
    if not isinstance(payload.get("roles"), dict):
        payload["roles"] = {}
    return payload


def write_launch_state(root: Path, launch_state: dict[str, object], launch_lease_seconds: int) -> None:
    path = default_launch_state_file(root)
    launch_state["kind"] = "taskboard-t0-launch-state"
    launch_state["version"] = 1
    launch_state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    launch_state["launch_lease_seconds"] = launch_lease_seconds
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(launch_state, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def command_role(command: str) -> str:
    match = LAUNCH_ROLE_RE.search(command)
    return match.group(1) if match else ""


def filter_launch_commands(
    commands: list[str],
    launch_state: dict[str, object],
    launch_lease_seconds: int,
    current_time: float,
) -> tuple[list[str], list[dict[str, object]]]:
    roles = launch_state.get("roles", {})
    role_payloads = roles if isinstance(roles, dict) else {}
    executable: list[str] = []
    suppressed: list[dict[str, object]] = []

    for command in commands:
        role = command_role(command)
        role_state = role_payloads.get(role, {}) if role else {}
        last_success_at = role_state.get("last_success_at") if isinstance(role_state, dict) else None
        try:
            age_seconds = current_time - float(last_success_at) if last_success_at is not None else None
        except (TypeError, ValueError):
            age_seconds = None
        if role and age_seconds is not None and age_seconds < launch_lease_seconds:
            suppressed.append(
                {
                    "role": role,
                    "command": command,
                    "reason": "launch-lease-active",
                    "age_seconds": int(age_seconds),
                    "remaining_seconds": int(max(0, launch_lease_seconds - age_seconds)),
                }
            )
            continue
        executable.append(command)
    return executable, suppressed


def record_launch_successes(
    launch_state: dict[str, object],
    executed_commands: list[dict[str, object]],
    current_time: float,
) -> None:
    roles = launch_state.setdefault("roles", {})
    if not isinstance(roles, dict):
        roles = {}
        launch_state["roles"] = roles

    for item in executed_commands:
        try:
            returncode = int(item.get("returncode", 1))
        except (TypeError, ValueError):
            returncode = 1
        if returncode != 0:
            continue
        command = str(item.get("command") or "")
        role = command_role(command)
        if not role:
            continue
        roles[role] = {
            "last_success_at": current_time,
            "last_command": command,
        }


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
    suppressed_launches: list[dict[str, object]],
    completion_audit: Optional[dict[str, object]] = None,
) -> list[str]:
    actions: list[str] = []
    if completion_audit and not completion_audit.get("completion_ready"):
        actions.extend(str(action) for action in session_probe.get("recovery_actions", []))
        actions.append(str(completion_audit.get("user_action") or "Do not summarize completion yet."))
    elif completion_audit and dispatch_plan.get("state") == "complete":
        return [str(completion_audit.get("user_action") or "summarize completion to the user")]

    if dispatch_plan.get("state") == "complete":
        return ["summarize completion to the user"]

    if not actions:
        actions.extend(str(action) for action in session_probe.get("recovery_actions", []))
        actions.extend(str(action) for action in queue_health.get("actions", []))

    if launch_commands:
        actions.append("launch/recover managed role sessions with generated commands")
    elif suppressed_launches:
        roles = ", ".join(str(item.get("role")) for item in suppressed_launches)
        actions.append(f"wait for {roles} launch lease active; do not duplicate managed terminals")
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


def build_stop_gate_actions(stop_gate_report: dict[str, object]) -> list[str]:
    stop_gates = stop_gate_report.get("stop_gates", [])
    first_gate = stop_gates[0] if isinstance(stop_gates, list) and stop_gates else {}
    question = str(first_gate.get("question") or "Review the T0 stop gate.") if isinstance(first_gate, dict) else ""
    task = str(first_gate.get("task") or "none") if isinstance(first_gate, dict) else "none"
    return [
        f"ask user through T0 stop gate for {task}: {question}",
        "pause T1/T2/T3 launch and assignment until the T0 stop gate is answered",
    ]


def build_decision_command(root: Path, first_stop_gate: dict[str, object]) -> str:
    task = str(first_stop_gate.get("task") or "")
    if not task:
        return ""
    return (
        f'python scripts/taskboard_decide.py --root "{root}" '
        f'--task {task} --decision "<user answer>"'
    )


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
    launch_state: Optional[dict[str, object]] = None,
    launch_lease_seconds: int = 300,
) -> dict[str, object]:
    session_probe = probe_sessions(
        root,
        stale_seconds,
        ["T1", "T2", "T3"],
        launcher,
        agent_template,
        goal,
        target_dir,
    )
    queue_health = report_health(root, stale_minutes, goal)
    dispatch_plan = dispatch(root, goal, "terminal", launcher, agent_template, target_dir)
    stop_gate_report = report_stop_gates(root)
    stop_gate_count = int(stop_gate_report.get("stop_gate_count") or 0)
    if stop_gate_count:
        stop_gates = stop_gate_report.get("stop_gates", [])
        first_gate = stop_gates[0] if isinstance(stop_gates, list) and stop_gates else {}
        task = str(first_gate.get("task") or "none") if isinstance(first_gate, dict) else "none"
        decision_command = build_decision_command(root, first_gate if isinstance(first_gate, dict) else {})
        return {
            "state": "stop-gate",
            "goal": goal or "",
            "boundary": T0_BOUNDARY,
            "session_probe": session_probe,
            "queue_health": queue_health,
            "dispatch": dispatch_plan,
            "stop_gate_report": stop_gate_report,
            "assignment": {
                "state": "user-stop-gate",
                "role": "T0",
                "task": task,
                "assignment_id": "",
                "reason": "t0-user-decision-required",
                "boundary": "T0 asks the user for a decision; T0 does not assign this stop gate to T1/T2/T3.",
            },
            "target_files": [],
            "planned_launch_commands": [],
            "requested_launch_commands": [],
            "launch_commands": [],
            "suppressed_launches": [],
            "executed_commands": [],
            "decision_command": decision_command,
            "actions": build_stop_gate_actions(stop_gate_report),
        }

    target_files = write_role_target_files(dispatch_plan) if target_dir is not None else []
    planned_launch_commands = choose_launch_commands(session_probe, dispatch_plan)
    requested_launch_commands = (
        choose_executable_launch_commands(session_probe, dispatch_plan)
        if execute_launches
        else planned_launch_commands
    )
    current_time = time.time()
    launch_state_payload = launch_state if launch_state is not None else read_launch_state(root)
    if execute_launches:
        launch_commands, suppressed_launches = filter_launch_commands(
            requested_launch_commands,
            launch_state_payload,
            launch_lease_seconds,
            current_time,
        )
    else:
        launch_commands = requested_launch_commands
        suppressed_launches = []
    executed_commands = execute_commands(launch_commands) if execute_launches and launch_commands else []
    if execute_launches and executed_commands:
        record_launch_successes(launch_state_payload, executed_commands, current_time)
        write_launch_state(root, launch_state_payload, launch_lease_seconds)
    assignment = build_assignment(session_probe, dispatch_plan, assignment_lease_seconds)
    completion_audit = dispatch_plan.get("completion_audit")
    completion_audit_payload = completion_audit if isinstance(completion_audit, dict) else None

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

    payload = {
        "state": state,
        "goal": goal or "",
        "boundary": T0_BOUNDARY,
        "session_probe": session_probe,
        "queue_health": queue_health,
        "dispatch": dispatch_plan,
        "stop_gate_report": stop_gate_report,
        "assignment": assignment,
        "target_files": target_files,
        "planned_launch_commands": planned_launch_commands,
        "requested_launch_commands": requested_launch_commands,
        "launch_commands": launch_commands,
        "suppressed_launches": suppressed_launches,
        "executed_commands": executed_commands,
        "actions": build_actions(
            session_probe,
            queue_health,
            dispatch_plan,
            launch_commands,
            assignment,
            suppressed_launches,
            completion_audit_payload,
        ),
    }
    if completion_audit_payload is not None:
        payload["completion_audit"] = completion_audit_payload
    return payload


def default_state_file(root: Path) -> Path:
    return root / ".taskboard" / "t0" / "latest.json"


def default_event_log_file(root: Path) -> Path:
    return root / ".taskboard" / "t0" / "events.jsonl"


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


def next_event_index(event_log_file: Path) -> int:
    if not event_log_file.exists():
        return 1
    try:
        with event_log_file.open("r", encoding="utf-8-sig") as handle:
            return sum(1 for line in handle if line.strip()) + 1
    except OSError:
        return 1


def append_event_log(
    event_log_file: Path,
    root: Path,
    goal: Optional[str],
    iteration: int,
    payload: dict[str, object],
) -> None:
    dispatch = payload.get("dispatch", {})
    dispatch_payload = dispatch if isinstance(dispatch, dict) else {}
    assignment = payload.get("assignment", {})
    assignment_payload = assignment if isinstance(assignment, dict) else {}
    queue_health = payload.get("queue_health", {})
    queue_payload = queue_health if isinstance(queue_health, dict) else {}
    session_probe = payload.get("session_probe", {})
    session_payload = session_probe if isinstance(session_probe, dict) else {}
    actions = payload.get("actions", [])
    action_list = actions if isinstance(actions, list) else []
    launch_commands = payload.get("launch_commands", [])
    launch_command_list = launch_commands if isinstance(launch_commands, list) else []
    executed_commands = payload.get("executed_commands", [])
    executed_command_list = executed_commands if isinstance(executed_commands, list) else []
    suppressed_launches = payload.get("suppressed_launches", [])
    suppressed_launch_list = suppressed_launches if isinstance(suppressed_launches, list) else []
    stop_gate_report = payload.get("stop_gate_report", {})
    stop_gate_payload = stop_gate_report if isinstance(stop_gate_report, dict) else {}
    completion_audit = payload.get("completion_audit", {})
    completion_payload = completion_audit if isinstance(completion_audit, dict) else {}
    completion_missing = completion_payload.get("missing_evidence", [])
    completion_missing_list = (
        [str(item) for item in completion_missing] if isinstance(completion_missing, list) else []
    )
    auto_mode = payload.get("auto_mode")
    starter_mode = payload.get("starter_mode")
    launch_failure_count = 0
    for item in executed_command_list:
        if not isinstance(item, dict):
            continue
        try:
            returncode = int(item.get("returncode", 0))
        except (TypeError, ValueError):
            returncode = 0
        if returncode != 0:
            launch_failure_count += 1
    event = {
        "kind": "taskboard-t0-supervisor-event",
        "version": 1,
        "event_index": next_event_index(event_log_file),
        "iteration": iteration,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root": str(root),
        "goal": goal or "",
        "state": str(payload.get("state") or ""),
        "next_role": str(dispatch_payload.get("next_role") or ""),
        "task": str(dispatch_payload.get("task") or "none"),
        "dispatch_state": str(dispatch_payload.get("state") or ""),
        "assignment_state": str(assignment_payload.get("state") or "none"),
        "assignment_role": str(assignment_payload.get("role") or ""),
        "assignment_task": str(assignment_payload.get("task") or "none"),
        "assignment_reason": str(assignment_payload.get("reason") or ""),
        "assignment_expected_id": str(assignment_payload.get("expected_assignment_id") or ""),
        "queue_state": str(queue_payload.get("state") or ""),
        "session_state": str(session_payload.get("state") or ""),
        "action_count": len(action_list),
        "launch_command_count": len(launch_command_list),
        "executed_command_count": len(executed_command_list),
        "launch_failure_count": launch_failure_count,
        "suppressed_launch_count": len(suppressed_launch_list),
        "stop_gate_count": int(stop_gate_payload.get("stop_gate_count") or 0),
        "completion_ready": bool(completion_payload.get("completion_ready")),
        "completion_missing_evidence": completion_missing_list,
        "completion_user_action": str(completion_payload.get("user_action") or ""),
        "auto_mode": bool(auto_mode) if auto_mode is not None else False,
        "starter_mode": str(starter_mode or ""),
        "boundary": (
            "T0 append-only event log: record supervisor decisions for audit/recovery; "
            "do not treat events as TASKBOARD state or worker memory."
        ),
    }
    event_log_file.parent.mkdir(parents=True, exist_ok=True)
    with event_log_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


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
    launch_lease_seconds: int = 300,
    event_log_file: Optional[Path] = None,
    stop_on_stop_gate: bool = True,
    runtime_metadata: Optional[dict[str, object]] = None,
) -> list[dict[str, object]]:
    if interval_seconds < 0:
        raise ValueError("--interval-seconds must be >= 0")
    if iterations is not None and iterations < 1:
        raise ValueError("--iterations must be >= 1")
    if assignment_lease_seconds < 1:
        raise ValueError("--assignment-lease-seconds must be >= 1")
    if launch_lease_seconds < 1:
        raise ValueError("--launch-lease-seconds must be >= 1")

    write_runtime_goal(root, goal)
    effective_goal = read_goal(root, goal)
    launch_state = read_launch_state(root) if execute_launches else None
    results: list[dict[str, object]] = []
    count = 0
    while iterations is None or count < iterations:
        payload = run_once(
            root,
            effective_goal,
            stale_minutes,
            stale_seconds,
            launcher,
            agent_template,
            execute_launches,
            assignment_lease_seconds,
            target_dir,
            launch_state,
            launch_lease_seconds,
        )
        if runtime_metadata:
            payload.update(runtime_metadata)
        results.append(payload)
        count += 1
        if state_file is not None:
            write_state_snapshot(state_file, root, effective_goal, results, stop_on_complete)
        if event_log_file is not None:
            append_event_log(event_log_file, root, effective_goal, count, payload)
        if stop_on_stop_gate and payload.get("state") == "stop-gate":
            break
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
        suppressed_launches = payload.get("suppressed_launches", [])
        if suppressed_launches:
            lines.append("suppressed_launches:")
            for item in suppressed_launches:
                lines.append(
                    f"- role={item['role']} reason={item['reason']} remaining_seconds={item['remaining_seconds']}"
                )
        completion_audit = payload.get("completion_audit")
        if isinstance(completion_audit, dict):
            lines.append("completion_audit:")
            lines.append(
                f"- state={completion_audit.get('state')} "
                f"completion_ready={completion_audit.get('completion_ready')} "
                f"archived_count={completion_audit.get('archived_count')}"
            )
        decision_command = payload.get("decision_command")
        if decision_command:
            lines.append("decision_command:")
            lines.append(f"- {decision_command}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing TASKBOARD files")
    parser.add_argument("--goal", help="Current user goal for T0")
    parser.add_argument("--stale-minutes", type=int, default=30)
    parser.add_argument("--stale-seconds", type=int, default=300)
    parser.add_argument("--assignment-lease-seconds", type=int, default=300)
    parser.add_argument("--launch-lease-seconds", type=int, default=300)
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
    event_log_file = None
    if not args.no_event_log:
        event_log_file = Path(args.event_log_file).resolve() if args.event_log_file else default_event_log_file(root)
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
            args.launch_lease_seconds,
            event_log_file,
            not args.no_stop_on_stop_gate,
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
