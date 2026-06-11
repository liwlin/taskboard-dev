#!/usr/bin/env python3
"""Run the T0 supervisor loop without doing worker tasks."""

from argparse import ArgumentParser
from pathlib import Path
import os
import json
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
from typing import Optional

from taskboard_health import report_health
from taskboard_sessions import probe_sessions
from taskboard_stopgates import report_stop_gates
from taskboard_subagents import subagent_ack_payload, subagent_plan_payload, subagent_result_payload
from taskboard_t0 import (
    build_backend,
    build_launch_commands,
    build_subagent_prompts,
    default_target_dir,
    dispatch,
    write_manual_windows_launch_scripts,
    read_goal,
    write_role_target_files,
    write_runtime_goal,
)


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


def default_checkout_owner_file(root: Path) -> Path:
    return root / ".taskboard" / "t0" / "checkout-owner.json"


def default_checkout_owner_id() -> str:
    return f"taskboard-t0:{socket.gethostname()}:{os.getpid()}"


def process_is_alive(pid: object) -> bool:
    try:
        normalized = int(pid)
    except (TypeError, ValueError):
        return True
    if normalized <= 0:
        return True
    if normalized == os.getpid():
        return True
    try:
        os.kill(normalized, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def read_checkout_owner(root: Path) -> dict[str, object]:
    path = default_checkout_owner_file(root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def acquire_checkout_owner(
    root: Path,
    owner_id: str,
    lease_seconds: int,
    current_time: float,
) -> dict[str, object]:
    path = default_checkout_owner_file(root)
    existing = read_checkout_owner(root)
    existing_owner = str(existing.get("owner_id") or "")
    previous_state = "missing"
    if existing_owner:
        try:
            updated_at_epoch = float(existing.get("updated_at_epoch") or 0)
        except (TypeError, ValueError):
            updated_at_epoch = 0
        try:
            existing_lease = int(existing.get("lease_seconds") or lease_seconds)
        except (TypeError, ValueError):
            existing_lease = lease_seconds
        age_seconds = int(max(0, current_time - updated_at_epoch)) if updated_at_epoch else lease_seconds + 1
        if existing_owner == owner_id:
            previous_state = "same-owner"
        elif age_seconds >= existing_lease:
            previous_state = "expired"
        elif not process_is_alive(existing.get("pid")):
            previous_state = "abandoned"
        else:
            return {
                "kind": "taskboard-checkout-owner",
                "state": "conflict",
                "owner_id": existing_owner,
                "requested_owner_id": owner_id,
                "age_seconds": age_seconds,
                "remaining_seconds": int(max(0, existing_lease - age_seconds)),
                "path": str(path),
                "boundary": (
                    "Another top-level agent owns this checkout. T0 must not "
                    "launch worker writers in the same Git checkout; wait or use a worktree."
                ),
            }

    payload = {
        "kind": "taskboard-checkout-owner",
        "version": 1,
        "state": "acquired",
        "previous_state": previous_state,
        "owner_id": owner_id,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(current_time)),
        "updated_at_epoch": current_time,
        "lease_seconds": lease_seconds,
        "path": str(path),
        "boundary": (
            "T0 owns launcher execution for this checkout only; this marker is "
            "not TASKBOARD task state and does not authorize T0 to do worker tasks."
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return payload


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


def update_assignment_watch(
    assignment: dict[str, object],
    assignment_watch: dict[str, object],
    current_time: float,
) -> None:
    role = str(assignment.get("role") or "")
    expected_assignment_id = str(assignment.get("expected_assignment_id") or "")
    state = str(assignment.get("state") or "")
    if role not in {"T1", "T2", "T3"}:
        return

    if state == "pending-ack" and expected_assignment_id:
        previous = assignment_watch.get(role, {})
        previous_payload = previous if isinstance(previous, dict) else {}
        if previous_payload.get("expected_assignment_id") == expected_assignment_id:
            try:
                pending_since = float(previous_payload.get("pending_since", current_time))
            except (TypeError, ValueError):
                pending_since = current_time
        else:
            pending_since = current_time

        pending_age_seconds = int(max(0, current_time - pending_since))
        assignment["pending_since"] = pending_since
        assignment["pending_age_seconds"] = pending_age_seconds
        assignment_watch[role] = {
            "expected_assignment_id": expected_assignment_id,
            "task": str(assignment.get("task") or "none"),
            "pending_since": pending_since,
            "pending_age_seconds": pending_age_seconds,
        }
        try:
            lease_seconds = int(assignment.get("lease_seconds") or 0)
        except (TypeError, ValueError):
            lease_seconds = 0
        if lease_seconds > 0 and pending_age_seconds >= lease_seconds:
            assignment["state"] = "pending-ack-expired"
            assignment["reason"] = "worker-heartbeat-assignment-ack-timeout"
        return

    current = assignment_watch.get(role, {})
    current_payload = current if isinstance(current, dict) else {}
    if state == "acknowledged" or current_payload.get("expected_assignment_id") == expected_assignment_id:
        assignment_watch.pop(role, None)


def assignment_recovery_sessions(
    dispatch_plan: dict[str, object],
    assignment: dict[str, object],
) -> list[dict[str, str]]:
    if assignment.get("state") != "pending-ack-expired":
        return []
    role = str(assignment.get("role") or "")
    raw_sessions = dispatch_plan.get("managed_sessions", [])
    if not isinstance(raw_sessions, list):
        return []
    return [
        item
        for item in raw_sessions
        if isinstance(item, dict) and str(item.get("role") or "") == role
    ]


def stalled_recoveries(
    queue_health: dict[str, object],
    dispatch_plan: dict[str, object],
) -> list[dict[str, object]]:
    role = str(dispatch_plan.get("next_role") or "")
    task = str(dispatch_plan.get("task") or "none")
    if role not in {"T1", "T2", "T3"} or task == "none":
        return []

    raw_stalled = queue_health.get("stalled_tasks", [])
    if not isinstance(raw_stalled, list):
        return []

    recoveries = []
    for item in raw_stalled:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "") != role or str(item.get("task") or "") != task:
            continue
        if str(item.get("action_kind") or "") != "recover-worker":
            continue
        recoveries.append(
            {
                "role": role,
                "task": task,
                "age_minutes": int(item.get("age_minutes") or 0),
                "role_liveness_state": str(item.get("role_liveness_state") or "missing"),
                "reason": "stalled-task",
            }
        )
    return recoveries


def stalled_recovery_sessions(
    dispatch_plan: dict[str, object],
    recoveries: list[dict[str, object]],
) -> list[dict[str, str]]:
    if not recoveries:
        return []
    recovery_roles = {str(item.get("role") or "") for item in recoveries if isinstance(item, dict)}
    raw_sessions = dispatch_plan.get("managed_sessions", [])
    if not isinstance(raw_sessions, list):
        return []
    return [
        item
        for item in raw_sessions
        if isinstance(item, dict) and str(item.get("role") or "") in recovery_roles
    ]


def build_subagent_fallback(
    dispatch_plan: dict[str, object],
    source_sessions: list[dict[str, str]],
    reason: str,
) -> dict[str, object]:
    sessions = source_sessions
    if not sessions:
        raw_sessions = dispatch_plan.get("managed_sessions", [])
        sessions = [item for item in raw_sessions if isinstance(item, dict)] if isinstance(raw_sessions, list) else []
    if not sessions:
        return {}

    manifest = dispatch_plan.get("session_manifest", {})
    raw_recovery_order = manifest.get("recovery_order", []) if isinstance(manifest, dict) else []
    recovery_order = [str(role) for role in raw_recovery_order if str(role)]
    return {
        "kind": "taskboard-subagent-fallback",
        "reason": reason,
        "backend": build_backend("subagent"),
        "subagent_prompts": build_subagent_prompts(sessions, recovery_order),
        "boundary": (
            "T0 may dispatch these prompts to native isolated subagents; "
            "do not share T0 or worker chat context."
        ),
    }


def dedupe_commands(commands: list[str]) -> list[str]:
    deduped: list[str] = []
    for command in commands:
        if command not in deduped:
            deduped.append(command)
    return deduped


def build_actions(
    session_probe: dict[str, object],
    queue_health: dict[str, object],
    dispatch_plan: dict[str, object],
    launch_commands: list[str],
    assignment: dict[str, object],
    suppressed_launches: list[dict[str, object]],
    completion_audit: Optional[dict[str, object]] = None,
    executed_commands: Optional[list[dict[str, object]]] = None,
    fallback_launch_attempts: Optional[list[dict[str, object]]] = None,
    stalled_recovery_items: Optional[list[dict[str, object]]] = None,
    manual_launch_files: Optional[dict[str, object]] = None,
    subagent_fallback: Optional[dict[str, object]] = None,
    checkout_owner: Optional[dict[str, object]] = None,
) -> list[str]:
    actions: list[str] = []
    if checkout_owner and checkout_owner.get("state") == "conflict":
        actions.append(
            "checkout ownership conflict: wait for the current checkout owner to finish "
            "or move the peer top-level agent to a separate git worktree before launching workers."
        )
    launch_failure_count = 0
    recovered_fallback_launcher = ""
    for attempt in fallback_launch_attempts or []:
        if isinstance(attempt, dict) and attempt.get("success"):
            recovered_fallback_launcher = str(attempt.get("launcher") or "")
            break
    for item in executed_commands or []:
        if not isinstance(item, dict):
            continue
        try:
            returncode = int(item.get("returncode", 0))
        except (TypeError, ValueError):
            returncode = 0
        if returncode != 0:
            launch_failure_count += 1
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
        if recovered_fallback_launcher:
            actions.append(
                f"primary launcher failed; T0 recovered managed role sessions with "
                f"fallback launcher {recovered_fallback_launcher}."
            )
        elif launch_failure_count:
            actions.append(
                "T0 launch/recovery failed; fix the T0 launcher configuration or retry another launcher; "
                "do not manage T1/T2/T3 directly."
            )
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
    elif assignment.get("state") == "pending-ack-expired":
        role = assignment.get("role")
        task = assignment.get("task")
        actions.append(
            f"recover taskboard-{role}; assignment acknowledgement timed out for {task}"
        )
    elif assignment.get("state") == "lease-expired":
        role = assignment.get("role")
        task = assignment.get("task")
        actions.append(f"reissue target to taskboard-{role}; assignment lease expired for {task}")

    for item in stalled_recovery_items or []:
        role = item.get("role")
        task = item.get("task")
        actions.append(f"recover taskboard-{role} for stalled TASK {task}")

    if manual_launch_files:
        user_command = str(manual_launch_files.get("user_command") or "")
        actions.append(
            "Run the generated user-owned Windows Terminal script for managed worker launch; "
            f"this is one T0-directed startup action, not manual T1/T2/T3 management: {user_command}"
        )
    if subagent_fallback:
        actions.append(
            "native subagent fallback available for managed T1/T2/T3 startup; "
            "T0 may dispatch subagent_prompts instead of asking the user to manage workers."
        )

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
        if completed.returncode != 0:
            break
    return results


def command_failed(item: dict[str, object]) -> bool:
    try:
        return int(item.get("returncode", 0)) != 0
    except (TypeError, ValueError):
        return True


def launch_failure_is_spawn_refusal(item: dict[str, object]) -> bool:
    if not command_failed(item):
        return False
    output = str(item.get("output") or "").lower()
    return any(
        marker in output
        for marker in (
            "403 request not allowed",
            "api error: 403",
            "failed to authenticate",
            "request not allowed",
            "spawn refused",
        )
    )


def extract_agent_command(agent_template: Optional[str]) -> str:
    if not agent_template or not agent_template.strip():
        return ""
    try:
        tokens = shlex.split(agent_template, posix=False)
    except ValueError:
        tokens = agent_template.strip().split()
    if not tokens:
        return ""
    return tokens[0].strip("\"'")


def validate_agent_preflight(
    agent_template: Optional[str],
    execute_launches: bool,
    launcher: str,
    enabled: bool = True,
    preflight_command: Optional[str] = None,
) -> dict[str, object]:
    if not execute_launches or launcher == "none":
        return {
            "enabled": enabled,
            "state": "skipped",
            "reason": "launches-disabled",
            "command": "",
        }
    if not enabled:
        return {
            "enabled": False,
            "state": "disabled",
            "reason": "agent-preflight-disabled",
            "command": "",
        }
    if preflight_command and preflight_command.strip():
        completed = subprocess.run(
            preflight_command,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        output = completed.stdout.strip()
        if completed.returncode != 0:
            probe_item = {"returncode": completed.returncode, "output": output}
            if launch_failure_is_spawn_refusal(probe_item):
                return {
                    "enabled": True,
                    "state": "spawn-refused",
                    "mode": "command",
                    "command": preflight_command,
                    "returncode": completed.returncode,
                    "output": output[:2000],
                    "reason": "agent-preflight-spawn-refused",
                }
            raise ValueError(
                "agent preflight command failed "
                f"returncode={completed.returncode}: {preflight_command}: {output}"
            )
        return {
            "enabled": True,
            "state": "passed",
            "mode": "command",
            "command": preflight_command,
            "returncode": completed.returncode,
            "output": output[:2000],
        }

    command = extract_agent_command(agent_template)
    if not command:
        raise ValueError("agent-template is empty; configure a worker agent command before launching roles")
    if shutil.which(command) is None:
        raise ValueError(
            f"agent command '{command}' from --agent-template was not found on PATH; "
            "fix T0 --agent-template or install/login to the agent CLI before launching workers"
        )
    return {
        "enabled": True,
        "state": "passed",
        "mode": "path",
        "command": command,
    }


def build_launch_probe(launcher: str, agent_preflight: Optional[dict[str, object]]) -> dict[str, object]:
    preflight = agent_preflight if isinstance(agent_preflight, dict) else {}
    preflight_state = str(preflight.get("state") or "")
    if preflight_state == "spawn-refused":
        state = "spawn-refused"
        recommended_backend = "subagent"
        reason = "agent-preflight-spawn-refused"
        user_action = (
            "Use native subagent fallback for T1/T2/T3. If native subagents are "
            "unavailable, generate a single T0-owned user terminal launcher."
        )
    elif preflight_state == "skipped":
        state = "launch-disabled"
        recommended_backend = "none"
        reason = "launches-disabled"
        user_action = "Launcher execution is disabled; keep this as a dry-run probe."
    elif preflight_state == "disabled":
        state = "unverified"
        recommended_backend = "terminal"
        reason = "agent-preflight-disabled"
        user_action = (
            "Use the T0-managed terminal launcher only if the operator intentionally "
            "disabled preflight."
        )
    elif preflight_state == "config-error":
        state = "config-error"
        recommended_backend = "fix-config"
        reason = "agent-preflight-config-error"
        user_action = "Fix the T0 launcher or agent-template configuration before starting workers."
    elif preflight_state == "passed":
        state = "ready"
        recommended_backend = "terminal"
        reason = "agent-preflight-passed"
        user_action = "Use the T0-managed terminal launcher for T1/T2/T3 worker loops."
    else:
        state = "unverified"
        recommended_backend = "terminal"
        reason = "agent-preflight-unavailable"
        user_action = "Use the T0-managed terminal launcher only after preflight evidence is available."
    return {
        "kind": "taskboard-launch-probe",
        "state": state,
        "launcher": launcher,
        "agent_preflight": preflight,
        "recommended_backend": recommended_backend,
        "reason": reason,
        "user_action": user_action,
        "boundary": (
            "T0 launch probe is read-only; T0 chooses the worker backend; do "
            "not ask the user to manage T1/T2/T3 directly."
        ),
    }


def successful_launch_roles(executed_commands: list[dict[str, object]]) -> set[str]:
    roles: set[str] = set()
    for item in executed_commands:
        if command_failed(item):
            continue
        role = command_role(str(item.get("command") or ""))
        if role:
            roles.add(role)
    return roles


def filter_commands_for_unlaunched_roles(commands: list[str], launched_roles: set[str]) -> list[str]:
    filtered = []
    for command in commands:
        role = command_role(command)
        if role and role in launched_roles:
            continue
        filtered.append(command)
    return filtered


def fallback_source_sessions(
    session_probe: dict[str, object],
    dispatch_plan: dict[str, object],
    used_recovery_commands: bool,
) -> list[dict[str, str]]:
    raw_sessions = (
        session_probe.get("recovery_sessions", [])
        if used_recovery_commands
        else dispatch_plan.get("managed_sessions", [])
    )
    if not isinstance(raw_sessions, list):
        return []
    return [item for item in raw_sessions if isinstance(item, dict)]


def execute_fallback_launchers(
    root: Path,
    source_sessions: list[dict[str, str]],
    agent_template: Optional[str],
    fallback_launchers: list[str],
    launched_roles: set[str],
    launch_state: dict[str, object],
    launch_lease_seconds: int,
    current_time: float,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    executed_commands: list[dict[str, object]] = []
    suppressed_launches: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []

    if not source_sessions:
        return executed_commands, suppressed_launches, attempts

    for fallback_launcher in fallback_launchers:
        fallback_commands = build_launch_commands(root, source_sessions, fallback_launcher, agent_template)
        fallback_commands = filter_commands_for_unlaunched_roles(fallback_commands, launched_roles)
        executable_commands, suppressed = filter_launch_commands(
            fallback_commands,
            launch_state,
            launch_lease_seconds,
            current_time,
        )
        suppressed_launches.extend(suppressed)
        if not executable_commands:
            continue
        fallback_results = execute_commands(executable_commands)
        executed_commands.extend(fallback_results)
        launched_roles.update(successful_launch_roles(fallback_results))
        success = bool(fallback_results) and not any(command_failed(item) for item in fallback_results)
        attempts.append(
            {
                "launcher": fallback_launcher,
                "launch_commands": executable_commands,
                "executed_commands": fallback_results,
                "success": success,
            }
        )
        if success:
            break
    return executed_commands, suppressed_launches, attempts


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
    fallback_launchers: Optional[list[str]] = None,
    assignment_watch: Optional[dict[str, object]] = None,
    agent_preflight: Optional[dict[str, object]] = None,
    checkout_owner_id: Optional[str] = None,
    checkout_owner_lease_seconds: int = 1800,
    native_spawn_result: Optional[dict[str, object]] = None,
    native_result_receipt: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    launch_probe = build_launch_probe(launcher, agent_preflight)
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
            "fallback_launch_attempts": [],
            "launch_probe": launch_probe,
            "decision_command": decision_command,
            "actions": build_stop_gate_actions(stop_gate_report),
        }

    managed_sessions = dispatch_plan.get("managed_sessions", [])
    target_files = (
        write_role_target_files(managed_sessions)
        if target_dir is not None and isinstance(managed_sessions, list)
        else []
    )
    current_time = time.time()
    assignment_watch_payload = assignment_watch if assignment_watch is not None else {}
    assignment = build_assignment(session_probe, dispatch_plan, assignment_lease_seconds)
    update_assignment_watch(assignment, assignment_watch_payload, current_time)
    assignment_recovery_session_list = assignment_recovery_sessions(dispatch_plan, assignment)
    stalled_recovery_list = stalled_recoveries(queue_health, dispatch_plan)
    stalled_recovery_session_list = stalled_recovery_sessions(dispatch_plan, stalled_recovery_list)
    assignment_recovery_command_list = build_launch_commands(
        root,
        assignment_recovery_session_list,
        launcher,
        agent_template,
    )
    stalled_recovery_command_list = build_launch_commands(
        root,
        stalled_recovery_session_list,
        launcher,
        agent_template,
    )
    planned_launch_commands = choose_launch_commands(session_probe, dispatch_plan)
    used_recovery_commands = bool(session_probe.get("recovery_commands"))
    requested_launch_commands = (
        dedupe_commands(
            choose_executable_launch_commands(session_probe, dispatch_plan)
            + assignment_recovery_command_list
            + stalled_recovery_command_list
        )
        if execute_launches
        else planned_launch_commands
    )
    launch_state_payload = launch_state if launch_state is not None else read_launch_state(root)
    manual_launch_files: dict[str, object] = {}
    subagent_fallback: dict[str, object] = {}
    preflight_spawn_refused = bool(
        isinstance(agent_preflight, dict) and agent_preflight.get("state") == "spawn-refused"
    )
    checkout_owner = (
        acquire_checkout_owner(
            root,
            checkout_owner_id or default_checkout_owner_id(),
            checkout_owner_lease_seconds,
            current_time,
        )
        if execute_launches
        else {"kind": "taskboard-checkout-owner", "state": "skipped", "reason": "launches-disabled"}
    )
    if execute_launches and preflight_spawn_refused:
        source_sessions = assignment_recovery_session_list or stalled_recovery_session_list or fallback_source_sessions(
            session_probe, dispatch_plan, used_recovery_commands
        )
        subagent_fallback = build_subagent_fallback(
            dispatch_plan,
            source_sessions,
            "agent-preflight-spawn-refused",
        )
        manual_launch_files = write_manual_windows_launch_scripts(
            root,
            source_sessions,
            agent_template,
        )
        launch_commands = []
        suppressed_launches = []
    elif execute_launches and checkout_owner.get("state") == "conflict":
        launch_commands = []
        suppressed_launches = []
    elif execute_launches:
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
    fallback_attempts: list[dict[str, object]] = []
    if execute_launches and executed_commands and any(command_failed(item) for item in executed_commands):
        source_sessions = assignment_recovery_session_list or stalled_recovery_session_list or fallback_source_sessions(
            session_probe, dispatch_plan, used_recovery_commands
        )
        fallback_executed, fallback_suppressed, fallback_attempts = execute_fallback_launchers(
            root,
            source_sessions,
            agent_template,
            fallback_launchers or [],
            successful_launch_roles(executed_commands),
            launch_state_payload,
            launch_lease_seconds,
            current_time,
        )
        executed_commands.extend(fallback_executed)
        suppressed_launches.extend(fallback_suppressed)
    if execute_launches and any(launch_failure_is_spawn_refusal(item) for item in executed_commands):
        source_sessions = assignment_recovery_session_list or stalled_recovery_session_list or fallback_source_sessions(
            session_probe, dispatch_plan, used_recovery_commands
        )
        subagent_fallback = build_subagent_fallback(
            dispatch_plan,
            source_sessions,
            "managed-child-process-spawn-refused",
        )
        manual_launch_files = write_manual_windows_launch_scripts(
            root,
            source_sessions,
            agent_template,
        )
    if execute_launches and executed_commands:
        record_launch_successes(launch_state_payload, executed_commands, current_time)
        write_launch_state(root, launch_state_payload, launch_lease_seconds)
    completion_audit = dispatch_plan.get("completion_audit")
    completion_audit_payload = completion_audit if isinstance(completion_audit, dict) else None

    state = "attention"
    if dispatch_plan.get("state") == "needs-goal":
        state = "needs-goal"
    elif dispatch_plan.get("state") == "complete":
        state = "idle"
    elif executed_commands and any(item["returncode"] != 0 for item in executed_commands):
        state = "attention"
    elif checkout_owner.get("state") == "conflict":
        state = "attention"
    elif assignment.get("state") == "pending-ack-expired":
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
        "assignment_recovery_commands": assignment_recovery_command_list,
        "stalled_recovery_commands": stalled_recovery_command_list,
        "stalled_recoveries": stalled_recovery_list,
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
            executed_commands,
            fallback_attempts,
            stalled_recovery_list,
            manual_launch_files,
            subagent_fallback,
            checkout_owner,
        ),
        "fallback_launch_attempts": fallback_attempts,
        "manual_launch_files": manual_launch_files,
        "subagent_fallback": subagent_fallback,
        "subagent_fallback_packet": {},
        "checkout_owner": checkout_owner,
        "assignment_watch": json.loads(json.dumps(assignment_watch_payload, ensure_ascii=False)),
        "agent_preflight": agent_preflight or {},
        "launch_probe": launch_probe,
    }
    if subagent_fallback:
        payload["subagent_fallback_packet"] = write_subagent_fallback_packet(root, goal, subagent_fallback)
    payload["subagent_control"] = build_subagent_loop_control(
        root,
        native_spawn_result,
        native_result_receipt,
    )
    if completion_audit_payload is not None:
        payload["completion_audit"] = completion_audit_payload
    return payload


def default_state_file(root: Path) -> Path:
    return root / ".taskboard" / "t0" / "latest.json"


def default_event_log_file(root: Path) -> Path:
    return root / ".taskboard" / "t0" / "events.jsonl"


def default_subagent_fallback_file(root: Path) -> Path:
    return root / ".taskboard" / "t0" / "subagent-fallback.json"


def build_subagent_loop_control(
    root: Path,
    native_spawn_result: Optional[dict[str, object]] = None,
    native_result_receipt: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    if isinstance(native_result_receipt, dict) and native_result_receipt:
        role = str(native_result_receipt.get("role") or "").upper()
        native_status = str(native_result_receipt.get("native_status") or native_result_receipt.get("result_status") or "")
        status = "failed" if native_status.lower() in {"failed", "failure", "error"} else "completed"
        result = subagent_result_payload(
            root,
            role,
            status,
            str(native_result_receipt.get("summary") or ""),
            str(native_result_receipt.get("result_tool") or ""),
            str(native_result_receipt.get("result_status") or native_status),
        )
        next_plan = subagent_plan_payload(root)
        return {
            "kind": "taskboard-subagent-loop-control",
            "state": "result-recorded",
            "action": "recorded-native-result",
            "role": role,
            "prompt_hash": "",
            "native_spawn": {},
            "subagent_plan": {},
            "subagent_ack": {},
            "subagent_result": result,
            "subagent_next_plan": next_plan,
            "boundary": (
                "T0 loop recorded a native-subagent result receipt from the outer "
                "runtime; this is control-plane evidence, not worker memory."
            ),
        }

    plan = subagent_plan_payload(root)
    control = {
        "kind": "taskboard-subagent-loop-control",
        "state": str(plan.get("state") or ""),
        "action": str(plan.get("action") or ""),
        "role": str(plan.get("role") or ""),
        "prompt_hash": str(plan.get("prompt_hash") or ""),
        "native_spawn": plan.get("native_spawn", {}),
        "subagent_plan": plan,
        "subagent_ack": {},
        "subagent_result": {},
        "subagent_next_plan": {},
        "boundary": (
            "T0 loop owns native-subagent dispatch control. It may emit a spawn "
            "plan or record an injected native spawn receipt, but it must not "
            "fabricate agent ids or perform worker responsibilities."
        ),
    }
    if (
        str(plan.get("state") or "") != "dispatch-next"
        or not isinstance(native_spawn_result, dict)
        or not native_spawn_result
    ):
        return control

    role = str(plan.get("role") or "")
    result_role = str(native_spawn_result.get("role") or role).upper()
    if result_role != role:
        control["state"] = "spawn-receipt-mismatch"
        control["action"] = "reject-native-spawn-receipt"
        control["error"] = f"native spawn receipt role {result_role} does not match planned role {role}"
        return control

    ack = subagent_ack_payload(
        root,
        role,
        str(native_spawn_result.get("agent_id") or ""),
        str(native_spawn_result.get("note") or "spawned by T0 loop bridge"),
        str(native_spawn_result.get("spawn_tool") or ""),
        str(native_spawn_result.get("agent_nickname") or ""),
    )
    next_plan = subagent_plan_payload(root)
    control["state"] = "dispatched"
    control["action"] = "recorded-native-spawn"
    control["subagent_ack"] = ack
    control["subagent_next_plan"] = next_plan
    return control


def read_assignment_watch(state_file: Optional[Path]) -> dict[str, object]:
    if state_file is None or not state_file.exists():
        return {}
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    latest = payload.get("latest", {})
    latest_payload = latest if isinstance(latest, dict) else {}
    assignment_watch = latest_payload.get("assignment_watch", {})
    return assignment_watch if isinstance(assignment_watch, dict) else {}


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


def write_subagent_fallback_packet(
    root: Path,
    goal: Optional[str],
    subagent_fallback: dict[str, object],
) -> dict[str, object]:
    if not subagent_fallback:
        return {}
    prompts = subagent_fallback.get("subagent_prompts", [])
    prompt_list = prompts if isinstance(prompts, list) else []
    packet = {
        "kind": "taskboard-subagent-fallback-packet",
        "version": 1,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root": str(root),
        "goal": goal or "",
        "subagent_fallback": subagent_fallback,
        "subagent_prompt_count": len(prompt_list),
        "subagent_prompt_roles": [
            str(item.get("role") or "")
            for item in prompt_list
            if isinstance(item, dict) and item.get("role")
        ],
        "boundary": (
            "T0 recovery packet for dispatching isolated native subagents; "
            "do not treat this as TASKBOARD state or worker memory."
        ),
    }
    path = default_subagent_fallback_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {"path": str(path), "prompt_count": packet["subagent_prompt_count"]}


def build_resume_config(
    launcher: str,
    agent_template: Optional[str],
    stale_minutes: int,
    stale_seconds: int,
    interval_seconds: int,
    assignment_lease_seconds: int,
    launch_lease_seconds: int,
    target_dir: Optional[Path],
    fallback_launchers: Optional[list[str]] = None,
    agent_preflight_enabled: bool = True,
    agent_preflight_command: Optional[str] = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "launcher": launcher,
        "agent_template": agent_template or "",
        "fallback_launchers": fallback_launchers or [],
        "agent_preflight_enabled": agent_preflight_enabled,
        "agent_preflight_command": agent_preflight_command or "",
        "stale_minutes": stale_minutes,
        "stale_seconds": stale_seconds,
        "interval_seconds": interval_seconds,
        "assignment_lease_seconds": assignment_lease_seconds,
        "launch_lease_seconds": launch_lease_seconds,
        "target_files_enabled": target_dir is not None,
    }
    if target_dir is not None:
        payload["target_dir"] = str(target_dir)
    return payload


def quote_cli_value(value: object) -> str:
    text = str(value)
    return '"' + text.replace('"', '\\"') + '"'


def build_t0_resume_command(
    root: Path,
    goal: str,
    resume_config: dict[str, object],
) -> str:
    if not goal:
        return ""
    parts = ["python", "scripts/taskboard_start.py", "--root", quote_cli_value(root), "--auto"]
    launcher = str(resume_config.get("launcher") or "")
    if launcher and launcher != "windows-terminal":
        parts.extend(["--launcher", launcher])
    fallback_launchers = resume_config.get("fallback_launchers", [])
    if isinstance(fallback_launchers, list):
        for fallback_launcher in fallback_launchers:
            fallback_text = str(fallback_launcher or "")
            if fallback_text:
                parts.extend(["--fallback-launcher", fallback_text])
    agent_template = str(resume_config.get("agent_template") or "")
    default_agent_template = 'claude "{target}"'
    if agent_template and agent_template != default_agent_template:
        parts.extend(["--agent-template", quote_cli_value(agent_template)])
    if resume_config.get("agent_preflight_enabled") is False:
        parts.append("--no-agent-preflight")
    agent_preflight_command = str(resume_config.get("agent_preflight_command") or "")
    if agent_preflight_command:
        parts.extend(["--agent-preflight-command", quote_cli_value(agent_preflight_command)])
    numeric_options = (
        ("stale_minutes", "--stale-minutes", 30),
        ("stale_seconds", "--stale-seconds", 300),
        ("assignment_lease_seconds", "--assignment-lease-seconds", 300),
        ("launch_lease_seconds", "--launch-lease-seconds", 300),
        ("interval_seconds", "--interval-seconds", 300),
    )
    for key, option, default in numeric_options:
        value = resume_config.get(key)
        if value is not None:
            try:
                normalized = int(value)
            except (TypeError, ValueError):
                normalized = default
            if normalized != default:
                parts.extend([option, str(value)])
    target_dir = str(resume_config.get("target_dir") or "")
    default_target_dir_path = str(root / ".taskboard" / "targets")
    if target_dir and target_dir != default_target_dir_path:
        parts.extend(["--target-dir", quote_cli_value(target_dir)])
    if resume_config.get("target_files_enabled") is False:
        parts.append("--no-target-files")
    return " ".join(parts)


def build_interruption_payload(
    root: Path,
    goal: str,
    launcher: str,
    agent_template: Optional[str],
    stale_minutes: int,
    stale_seconds: int,
    interval_seconds: int,
    assignment_lease_seconds: int,
    launch_lease_seconds: int,
    target_dir: Optional[Path],
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
    return {
        "kind": "taskboard-t0-interruption",
        "state": "interrupted",
        "goal": goal,
        "boundary": (
            "T0 interruption report: user-facing resume guidance only; "
            "T0 does not ask the user to manage T1/T2/T3."
        ),
        "resume_config": resume_config,
        "resume_command": build_t0_resume_command(root, goal, resume_config),
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
    }


def build_config_error_payload(
    root: Path,
    goal: str,
    error: str,
    launcher: str,
    agent_template: Optional[str],
    stale_minutes: int,
    stale_seconds: int,
    interval_seconds: int,
    assignment_lease_seconds: int,
    launch_lease_seconds: int,
    target_dir: Optional[Path],
    fallback_launchers: Optional[list[str]] = None,
    agent_preflight_enabled: bool = True,
    agent_preflight_command: Optional[str] = None,
) -> dict[str, object]:
    return {
        "kind": "taskboard-t0-config-error",
        "state": "config-error",
        "goal": goal,
        "error": error,
        "boundary": (
            "T0 configuration error report: fix the T0 launcher/template configuration; "
            "do not ask the user to manage T1/T2/T3 directly."
        ),
        "resume_config": build_resume_config(
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
        ),
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
    }


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
    stalled_recoveries_payload = payload.get("stalled_recoveries", [])
    stalled_recovery_list = stalled_recoveries_payload if isinstance(stalled_recoveries_payload, list) else []
    fallback_attempts = payload.get("fallback_launch_attempts", [])
    fallback_attempt_list = fallback_attempts if isinstance(fallback_attempts, list) else []
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
    resume_config = payload.get("resume_config", {})
    resume_config_payload = resume_config if isinstance(resume_config, dict) else {}
    launch_failure_count = 0
    launch_failures: list[dict[str, object]] = []
    for item in executed_command_list:
        if not isinstance(item, dict):
            continue
        try:
            returncode = int(item.get("returncode", 0))
        except (TypeError, ValueError):
            returncode = 0
        if returncode != 0:
            launch_failure_count += 1
            launch_failures.append(
                {
                    "command": str(item.get("command") or ""),
                    "returncode": returncode,
                    "output": str(item.get("output") or "")[:2000],
                }
            )
    suppressed_launch_events: list[dict[str, object]] = []
    for item in suppressed_launch_list:
        if not isinstance(item, dict):
            continue
        suppressed_launch_events.append(
            {
                "role": str(item.get("role") or ""),
                "reason": str(item.get("reason") or ""),
                "remaining_seconds": int(item.get("remaining_seconds") or 0),
                "age_seconds": int(item.get("age_seconds") or 0),
                "command": str(item.get("command") or "")[:2000],
            }
        )
    subagent_fallback = payload.get("subagent_fallback", {})
    subagent_fallback_payload = subagent_fallback if isinstance(subagent_fallback, dict) else {}
    subagent_prompts = subagent_fallback_payload.get("subagent_prompts", [])
    subagent_prompt_list = subagent_prompts if isinstance(subagent_prompts, list) else []
    subagent_packet = payload.get("subagent_fallback_packet", {})
    subagent_packet_payload = subagent_packet if isinstance(subagent_packet, dict) else {}
    subagent_control = payload.get("subagent_control", {})
    subagent_control_payload = subagent_control if isinstance(subagent_control, dict) else {}
    launch_probe = payload.get("launch_probe", {})
    launch_probe_payload = launch_probe if isinstance(launch_probe, dict) else {}
    checkout_owner = payload.get("checkout_owner", {})
    checkout_owner_payload = checkout_owner if isinstance(checkout_owner, dict) else {}
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
        "assignment_pending_age_seconds": int(assignment_payload.get("pending_age_seconds") or 0),
        "queue_state": str(queue_payload.get("state") or ""),
        "session_state": str(session_payload.get("state") or ""),
        "action_count": len(action_list),
        "launch_command_count": len(launch_command_list),
        "executed_command_count": len(executed_command_list),
        "launch_failure_count": launch_failure_count,
        "launch_failures": launch_failures,
        "launch_probe_state": str(launch_probe_payload.get("state") or ""),
        "launch_probe_recommended_backend": str(launch_probe_payload.get("recommended_backend") or ""),
        "launch_probe_reason": str(launch_probe_payload.get("reason") or ""),
        "checkout_owner_state": str(checkout_owner_payload.get("state") or ""),
        "checkout_owner_id": str(checkout_owner_payload.get("owner_id") or ""),
        "checkout_owner_requested_id": str(checkout_owner_payload.get("requested_owner_id") or ""),
        "checkout_owner_remaining_seconds": int(checkout_owner_payload.get("remaining_seconds") or 0),
        "fallback_launch_count": len(fallback_attempt_list),
        "fallback_launchers": [
            str(item.get("launcher") or "")
            for item in fallback_attempt_list
            if isinstance(item, dict)
        ],
        "fallback_launch_recovered": any(
            bool(item.get("success")) for item in fallback_attempt_list if isinstance(item, dict)
        ),
        "suppressed_launch_count": len(suppressed_launch_list),
        "suppressed_launches": suppressed_launch_events,
        "subagent_fallback_available": bool(subagent_fallback_payload),
        "subagent_fallback_kind": str(subagent_fallback_payload.get("kind") or ""),
        "subagent_fallback_reason": str(subagent_fallback_payload.get("reason") or ""),
        "subagent_fallback_packet_file": str(subagent_packet_payload.get("path") or ""),
        "subagent_prompt_count": len(subagent_prompt_list),
        "subagent_prompt_roles": [
            str(item.get("role") or "")
            for item in subagent_prompt_list
            if isinstance(item, dict) and item.get("role")
        ],
        "subagent_control_state": str(subagent_control_payload.get("state") or ""),
        "subagent_control_action": str(subagent_control_payload.get("action") or ""),
        "subagent_control_role": str(subagent_control_payload.get("role") or ""),
        "subagent_control_prompt_hash": str(subagent_control_payload.get("prompt_hash") or ""),
        "stalled_recovery_count": len(stalled_recovery_list),
        "stalled_recoveries": [
            {
                "role": str(item.get("role") or ""),
                "task": str(item.get("task") or "none"),
                "age_minutes": int(item.get("age_minutes") or 0),
                "role_liveness_state": str(item.get("role_liveness_state") or ""),
                "reason": str(item.get("reason") or ""),
            }
            for item in stalled_recovery_list
            if isinstance(item, dict)
        ],
        "stop_gate_count": int(stop_gate_payload.get("stop_gate_count") or 0),
        "completion_ready": bool(completion_payload.get("completion_ready")),
        "completion_missing_evidence": completion_missing_list,
        "completion_user_action": str(completion_payload.get("user_action") or ""),
        "error": str(payload.get("error") or ""),
        "auto_mode": bool(auto_mode) if auto_mode is not None else False,
        "starter_mode": str(starter_mode or ""),
        "resume_config": resume_config_payload,
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
    fallback_launchers: Optional[list[str]] = None,
    agent_preflight_enabled: bool = True,
    agent_preflight_command: Optional[str] = None,
    checkout_owner_id: Optional[str] = None,
    checkout_owner_lease_seconds: int = 1800,
) -> list[dict[str, object]]:
    if interval_seconds < 0:
        raise ValueError("--interval-seconds must be >= 0")
    if iterations is not None and iterations < 1:
        raise ValueError("--iterations must be >= 1")
    if assignment_lease_seconds < 1:
        raise ValueError("--assignment-lease-seconds must be >= 1")
    if launch_lease_seconds < 1:
        raise ValueError("--launch-lease-seconds must be >= 1")
    if checkout_owner_lease_seconds < 1:
        raise ValueError("--checkout-owner-lease-seconds must be >= 1")

    write_runtime_goal(root, goal)
    effective_goal = read_goal(root, goal)
    launch_state = read_launch_state(root) if execute_launches else None
    agent_preflight = validate_agent_preflight(
        agent_template,
        execute_launches,
        launcher,
        agent_preflight_enabled,
        agent_preflight_command,
    )
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
    results: list[dict[str, object]] = []
    count = 0
    assignment_watch = read_assignment_watch(state_file)
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
            fallback_launchers,
            assignment_watch,
            agent_preflight,
            checkout_owner_id,
            checkout_owner_lease_seconds,
        )
        if runtime_metadata:
            payload.update(runtime_metadata)
        payload["resume_config"] = resume_config
        results.append(payload)
        count += 1
        if state_file is not None:
            write_state_snapshot(state_file, root, effective_goal, results, stop_on_complete)
        if event_log_file is not None:
            append_event_log(event_log_file, root, effective_goal, count, payload)
        if payload["dispatch"].get("state") == "needs-goal":
            break
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
        target_files = payload.get("target_files", [])
        if target_files:
            lines.append("target_files:")
            for item in target_files:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('role')} path={item.get('path')}")
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
        "--fallback-launcher",
        action="append",
        choices=("windows-terminal", "powershell", "tmux"),
        default=[],
        help="Fallback launcher to try after the primary launcher fails. Repeat to set priority order.",
    )
    parser.add_argument(
        "--agent-template",
        default='claude "{target}"',
        help="Command template for generated role commands. Supports {role}, {title}, {command}, and {target}.",
    )
    parser.add_argument(
        "--execute-launches",
        action="store_true",
        help="Execute generated launcher commands. This only launches/recover roles; T0 still does not do worker tasks.",
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
        "--checkout-owner-id",
        help="Optional stable top-level checkout owner id for launcher execution guard.",
    )
    parser.add_argument(
        "--checkout-owner-lease-seconds",
        type=int,
        default=1800,
        help="Freshness window for .taskboard/t0/checkout-owner.json before T0 may reclaim launcher ownership.",
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
            fallback_launchers=args.fallback_launcher,
            agent_preflight_enabled=not args.no_agent_preflight,
            agent_preflight_command=args.agent_preflight_command,
            checkout_owner_id=args.checkout_owner_id,
            checkout_owner_lease_seconds=args.checkout_owner_lease_seconds,
        )
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
            args.fallback_launcher,
            not args.no_agent_preflight,
            args.agent_preflight_command,
        )
        if state_file is not None:
            write_state_snapshot(state_file, root, effective_goal, [payload], not args.no_stop_on_complete)
        if event_log_file is not None:
            append_event_log(event_log_file, root, effective_goal, 1, payload)
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
            args.fallback_launcher,
            not args.no_agent_preflight,
            args.agent_preflight_command,
        )
        if state_file is not None:
            write_state_snapshot(state_file, root, effective_goal, [payload], not args.no_stop_on_complete)
        if event_log_file is not None:
            append_event_log(event_log_file, root, effective_goal, 1, payload)
        print(exc, file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
