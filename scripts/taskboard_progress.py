#!/usr/bin/env python3
"""Report T0-managed TASKBOARD progress for the user."""

from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
from typing import Optional

from taskboard_completion import report_completion
from taskboard_health import report_health
from taskboard_loop import default_event_log_file, default_state_file, default_subagent_fallback_file
from taskboard_stopgates import report_stop_gates
from taskboard_subagents import subagent_status_payload
from taskboard_t0 import read_goal


ROLES = ("T1", "T2", "T3")
DEFAULT_RESUME_LAUNCHER = "windows-terminal"
DEFAULT_RESUME_AGENT_TEMPLATE = 'codex --prompt-file "{target_file}"'
T0_PROGRESS_BOUNDARY = (
    "T0 manager-only progress: summarize goal, queue, session, and assignment state for the user; "
    "do not perform design, review, implementation, verification, or commit work."
)
STARTER_AUTO_BOUNDARY = (
    "T0 one-command auto mode: run the supervisor as the user-facing manager, "
    "launch or recover T1/T2/T3 when needed, and keep T0 out of worker tasks."
)
STARTER_DRY_CHECK_BOUNDARY = "T0 starter dry-check mode: report orchestration without launching workers."


def build_decision_command(root: Path, first_stop_gate: dict[str, object]) -> str:
    task = str(first_stop_gate.get("task") or "")
    if not task:
        return ""
    return (
        f'python scripts/taskboard_decide.py --root "{root}" '
        f'--task {task} --decision "<user answer>"'
    )


def quote_cli_value(value: object) -> str:
    text = str(value)
    return '"' + text.replace('"', '\\"') + '"'


def build_resume_command(
    root: Path,
    goal: str,
    state: str,
    stop_gate_count: int,
    completion_ready: bool,
    resume_config: Optional[dict[str, object]] = None,
    auto_mode: bool = True,
) -> str:
    if not goal or state == "complete" or completion_ready or stop_gate_count:
        return ""
    parts = ["python", "scripts/taskboard_start.py", "--root", quote_cli_value(root)]
    if not auto_mode:
        parts.append("--dry-run")
    config = resume_config if isinstance(resume_config, dict) else {}
    launcher = str(config.get("launcher") or "")
    if launcher and launcher != DEFAULT_RESUME_LAUNCHER:
        parts.extend(["--launcher", launcher])
    fallback_launchers = config.get("fallback_launchers", [])
    if isinstance(fallback_launchers, list):
        for fallback_launcher in fallback_launchers:
            fallback_text = str(fallback_launcher or "")
            if fallback_text:
                parts.extend(["--fallback-launcher", fallback_text])
    agent_template = str(config.get("agent_template") or "")
    if agent_template and agent_template != DEFAULT_RESUME_AGENT_TEMPLATE:
        parts.extend(["--agent-template", quote_cli_value(agent_template)])
    if config.get("agent_preflight_enabled") is False:
        parts.append("--no-agent-preflight")
    agent_preflight_command = str(config.get("agent_preflight_command") or "")
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
        value = config.get(key)
        if value is not None and safe_int(value, default) != default:
            parts.extend([option, str(value)])
    target_dir = str(config.get("target_dir") or "")
    default_target_dir = str(root / ".taskboard" / "targets")
    if target_dir and target_dir != default_target_dir:
        parts.extend(["--target-dir", quote_cli_value(target_dir)])
    if config.get("target_files_enabled") is False:
        parts.append("--no-target-files")
    return " ".join(parts)


def read_latest_snapshot(root: Path) -> Optional[dict[str, object]]:
    path = default_state_file(root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def read_event_log_summary(root: Path) -> dict[str, object]:
    path = default_event_log_file(root)
    if not path.exists():
        return {
            "event_count": 0,
            "latest_event": {},
            "event_log_boundary": "T0 append-only event log not found.",
        }

    count = 0
    latest: dict[str, object] = {}
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            count += 1
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                latest = payload
    except (OSError, UnicodeDecodeError):
        return {
            "event_count": 0,
            "latest_event": {},
            "event_log_boundary": "T0 append-only event log could not be read.",
        }

    return {
        "event_count": count,
        "latest_event": latest,
        "event_log_boundary": (
            "T0 append-only event log summarizes supervisor decisions; "
            "it is not TASKBOARD state or worker memory."
        ),
    }


def read_subagent_fallback_packet(root: Path) -> dict[str, object]:
    path = default_subagent_fallback_file(root)
    if not path.exists():
        return {"available": False, "path": str(path)}
    try:
        packet = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"available": False, "path": str(path)}
    if not isinstance(packet, dict):
        return {"available": False, "path": str(path)}
    roles = packet.get("subagent_prompt_roles", [])
    role_list = [str(item) for item in roles if str(item)] if isinstance(roles, list) else []
    return {
        "available": True,
        "path": str(path),
        "kind": str(packet.get("kind") or ""),
        "prompt_count": safe_int(packet.get("subagent_prompt_count"), len(role_list)),
        "prompt_roles": role_list,
    }


def build_user_summary(
    state: str,
    goal: str,
    next_role: str,
    task: str,
    assignment_state: str,
    active_count: int,
    launch_failure_count: int = 0,
    suppressed_launch_count: int = 0,
    stop_gate_count: int = 0,
    stop_gate_question: str = "",
    queue_metrics: Optional[dict[str, object]] = None,
    error: str = "",
    fallback_launch_recovered: bool = False,
    fallback_launchers: Optional[list[str]] = None,
    subagent_fallback_available: bool = False,
    subagent_prompt_roles: Optional[list[str]] = None,
) -> str:
    if state == "config-error":
        return f"T0 configuration error for goal '{goal}': {error}"
    if stop_gate_count:
        return (
            f"T0 has {stop_gate_count} stop gate(s) for goal '{goal}'. "
            f"First question: {stop_gate_question}"
        )
    if subagent_fallback_available:
        roles = ", ".join(subagent_prompt_roles or [])
        return (
            f"T0 has native subagent fallback prompts for goal '{goal}'"
            f"{f' ({roles})' if roles else ''}. No T1/T2/T3 user management is required."
        )
    if launch_failure_count:
        if fallback_launch_recovered:
            launchers = ", ".join(fallback_launchers or [])
            return (
                f"T0 recovered managed role launch for goal '{goal}' with "
                f"fallback launcher {launchers}. No T1/T2/T3 user management is required."
            )
        return (
            f"T0 could not launch or recover {launch_failure_count} managed role command(s) "
            f"for goal '{goal}'. T0 should retry or switch launcher mode; this is not T1/T2/T3 user management."
        )
    if suppressed_launch_count:
        return (
            f"T0 is waiting for recent T0 launch attempt(s) to produce worker heartbeats for goal '{goal}'. "
            "It is not duplicating managed terminals while the launch lease is active."
        )
    if state == "needs-supervisor-run":
        return (
            f"T0 has the goal '{goal}' but no supervisor snapshot yet. "
            "Start or resume T0; this does not ask you to manage T1/T2/T3."
        )
    if state == "needs-goal":
        return "T0 needs one user goal before it can manage T1/T2/T3."
    if state == "interrupted":
        return (
            f"T0 was interrupted while managing goal '{goal}'. "
            "Resume T0 from the recorded command; this does not ask you to manage T1/T2/T3."
        )
    if state == "complete":
        return f"T0 sees the goal '{goal}' as complete and is ready to summarize completion to the user."
    if next_role and next_role != "T0":
        metrics_suffix = ""
        if queue_metrics:
            role_counts = queue_metrics.get("role_counts", {})
            role_count_payload = role_counts if isinstance(role_counts, dict) else {}
            metrics_suffix = (
                " queue_metrics: "
                f"T1={role_count_payload.get('T1', 0)}, "
                f"T2={role_count_payload.get('T2', 0)}, "
                f"T3={role_count_payload.get('T3', 0)}, "
                f"stalled={queue_metrics.get('stalled_count', 0)}."
            )
        return (
            f"T0 is managing T1/T2/T3 for goal '{goal}'. "
            f"Next managed role: {next_role}; task: {task}; active tasks: {active_count}; "
            f"assignment: {assignment_state}.{metrics_suffix}"
        )
    return f"T0 is managing the goal '{goal}' and monitoring for the next role action."


def build_user_action(
    state: str,
    dispatch_state: str,
    actions: list[str],
    launch_failure_count: int = 0,
    stop_gate_count: int = 0,
    completion_missing_evidence: Optional[list[str]] = None,
    assignment_state: str = "",
    assignment_role: str = "",
    t0_supervisor_state: str = "",
    error: str = "",
    fallback_launch_recovered: bool = False,
    fallback_launchers: Optional[list[str]] = None,
    stalled_recovery_count: int = 0,
    subagent_fallback_available: bool = False,
    subagent_prompt_roles: Optional[list[str]] = None,
) -> str:
    if state == "config-error":
        return (
            "T0 configuration failed; fix T0 launcher configuration before resuming. "
            f"Error: {error}"
        )
    if stop_gate_count:
        return "T0 stop gate requires user decision; answer T0's summarized question, not T1/T2/T3."
    if subagent_fallback_available:
        roles = ", ".join(subagent_prompt_roles or [])
        return (
            f"No user action required; T0 can dispatch native subagent fallback prompts"
            f"{f' for {roles}' if roles else ''}. If native subagents are unavailable, use the generated one-shot worker startup script."
        )
    if launch_failure_count:
        if fallback_launch_recovered:
            launchers = ", ".join(fallback_launchers or [])
            return (
                f"No user action required; T0 recovered managed role launch with "
                f"fallback launcher {launchers}."
            )
        return "T0 launch/recovery failed; fix the T0 launcher configuration or rerun T0 with another launcher."
    if state == "interrupted":
        return "Resume T0 with resume_command; do not manage T1/T2/T3 directly."
    if state == "needs-supervisor-run":
        return "Start or resume T0 with taskboard_start.py or taskboard_loop.py."
    if dispatch_state == "needs-goal":
        return "Provide one user goal to T0."
    if dispatch_state == "complete":
        return "Review T0's completion summary."
    if t0_supervisor_state == "stale":
        return "Resume T0 with resume_command; do not manage T1/T2/T3 directly."
    has_active_completion_gap = any(
        "active TASK files remain" in str(item)
        for item in (completion_missing_evidence or [])
    )
    if (
        assignment_state in {"pending-ack", "unassigned", "lease-expired"}
        and assignment_role
        and (has_active_completion_gap or not completion_missing_evidence)
    ):
        return f"No user action required; T0 will reissue target to taskboard-{assignment_role} until assignment is acknowledged."
    if assignment_state == "pending-ack-expired" and assignment_role:
        return (
            f"No user action required; T0 will recover taskboard-{assignment_role}; "
            "assignment acknowledgement timed out."
        )
    if stalled_recovery_count and assignment_role:
        return f"No user action required; T0 will recover taskboard-{assignment_role} for stalled TASK."
    if assignment_state == "acknowledged" and assignment_role:
        return (
            f"No user action required; T0 is monitoring taskboard-{assignment_role}'s "
            "already acknowledged assignment."
        )
    if completion_missing_evidence and not has_active_completion_gap:
        return "No user action required; T0 will wake T1 to record or revise missing completion evidence."
    if actions:
        return "No user action required; T0 is handling routine role recovery or dispatch."
    return "No user action required."


def safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def summarize_subagent_fallback(raw_value: object) -> dict[str, object]:
    payload = raw_value if isinstance(raw_value, dict) else {}
    prompts = payload.get("subagent_prompts", [])
    prompt_list = prompts if isinstance(prompts, list) else []
    roles = [
        str(item.get("role") or "")
        for item in prompt_list
        if isinstance(item, dict) and item.get("role")
    ]
    return {
        "available": bool(payload),
        "kind": str(payload.get("kind") or ""),
        "reason": str(payload.get("reason") or ""),
        "prompt_count": len(prompt_list),
        "prompt_roles": roles,
    }


def parse_iso_timestamp(raw_value: object) -> Optional[datetime]:
    if not raw_value:
        return None
    text = str(raw_value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_t0_supervisor_freshness(
    snapshot: Optional[dict[str, object]],
    resume_config: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    if snapshot is None:
        return {
            "state": "missing",
            "age_seconds": None,
            "stale_after_seconds": 0,
            "updated_at": "",
            "boundary": "T0 supervisor freshness summarizes control-plane liveness; it is not worker state.",
        }
    config = resume_config if isinstance(resume_config, dict) else {}
    interval_seconds = safe_int(config.get("interval_seconds"), 300)
    stale_after_seconds = max(60, interval_seconds * 2)
    updated_at = str(snapshot.get("updated_at") or "")
    updated_at_time = parse_iso_timestamp(updated_at)
    if updated_at_time is None:
        return {
            "state": "unknown",
            "age_seconds": None,
            "stale_after_seconds": stale_after_seconds,
            "updated_at": updated_at,
            "boundary": "T0 supervisor freshness summarizes control-plane liveness; it is not worker state.",
        }
    age_seconds = max(0, int((datetime.now(timezone.utc) - updated_at_time).total_seconds()))
    return {
        "state": "stale" if age_seconds > stale_after_seconds else "fresh",
        "age_seconds": age_seconds,
        "stale_after_seconds": stale_after_seconds,
        "updated_at": updated_at,
        "boundary": "T0 supervisor freshness summarizes control-plane liveness; it is not worker state.",
    }


def build_queue_metrics(
    queue_payload: dict[str, object],
    next_role: str,
    user_action_required: bool,
) -> dict[str, object]:
    role_counts = {role: 0 for role in ROLES}
    queues = queue_payload.get("queues", {})
    if isinstance(queues, dict):
        for role in ROLES:
            role_queue = queues.get(role, {})
            if not isinstance(role_queue, dict):
                continue
            role_counts[role] = sum(
                safe_int(entry.get("count")) for entry in role_queue.values() if isinstance(entry, dict)
            )

    stalled_tasks = queue_payload.get("stalled_tasks", [])
    stalled_count = len(stalled_tasks) if isinstance(stalled_tasks, list) else 0
    active_count = safe_int(queue_payload.get("active_count"), sum(role_counts.values()))
    if not active_count:
        active_count = sum(role_counts.values())

    return {
        "active_count": active_count,
        "stalled_count": stalled_count,
        "role_counts": role_counts,
        "next_role": next_role,
        "queue_state": str(queue_payload.get("state") or ""),
        "user_action_required": user_action_required,
        "boundary": (
            "T0 queue metrics summarize controlled role queues for the user; "
            "they are not TASKBOARD state or worker memory."
        ),
    }


def report_progress(root: Path) -> dict[str, object]:
    event_summary = read_event_log_summary(root)
    subagent_packet = read_subagent_fallback_packet(root)
    subagent_dispatch = subagent_status_payload(root)
    subagent_dispatched_roles = [
        str(item) for item in subagent_dispatch.get("dispatched_roles", []) if str(item)
    ]
    subagent_pending_roles = [
        str(item) for item in subagent_dispatch.get("pending_roles", []) if str(item)
    ]
    subagent_dispatch_records = subagent_dispatch.get("records", {})
    if not isinstance(subagent_dispatch_records, dict):
        subagent_dispatch_records = {}
    completion_audit = report_completion(root)
    completion_missing = completion_audit.get("missing_evidence", [])
    completion_missing_list = completion_missing if isinstance(completion_missing, list) else []
    stop_gate_report = report_stop_gates(root)
    stop_gates = stop_gate_report.get("stop_gates", [])
    stop_gate_list = stop_gates if isinstance(stop_gates, list) else []
    stop_gate_count = int(stop_gate_report.get("stop_gate_count") or 0)
    first_stop_gate = stop_gate_list[0] if stop_gate_list and isinstance(stop_gate_list[0], dict) else {}
    first_stop_gate_question = str(first_stop_gate.get("question") or "")
    decision_command = build_decision_command(root, first_stop_gate)
    snapshot = read_latest_snapshot(root)
    if snapshot is None:
        t0_supervisor = build_t0_supervisor_freshness(None)
        latest_event = event_summary.get("latest_event", {})
        latest_event_payload = latest_event if isinstance(latest_event, dict) else {}
        goal = read_goal(root, "") or str(latest_event_payload.get("goal") or "")
        latest_event_state = str(latest_event_payload.get("state") or "")
        if latest_event_state == "interrupted":
            fallback_state = "interrupted"
        elif latest_event_state == "config-error":
            fallback_state = "config-error"
        else:
            fallback_state = "needs-supervisor-run"
        latest_event_dispatch_state = str(latest_event_payload.get("dispatch_state") or "")
        if latest_event_dispatch_state == "needs-goal":
            fallback_state = "needs-goal"
        if stop_gate_count:
            fallback_state = "stop-gate"
        if bool(completion_audit.get("completion_ready")):
            fallback_state = "complete"
        latest_event_next_role = str(latest_event_payload.get("next_role") or "T0")
        latest_event_task = str(latest_event_payload.get("task") or "none")
        latest_event_assignment_state = str(latest_event_payload.get("assignment_state") or "none")
        latest_event_assignment_role = str(latest_event_payload.get("assignment_role") or "")
        latest_event_assignment_task = str(latest_event_payload.get("assignment_task") or "none")
        latest_event_assignment_reason = str(latest_event_payload.get("assignment_reason") or "")
        latest_event_assignment_expected_id = str(latest_event_payload.get("assignment_expected_id") or "")
        latest_event_assignment_pending_age_seconds = safe_int(
            latest_event_payload.get("assignment_pending_age_seconds"),
            0,
        )
        latest_event_error = str(latest_event_payload.get("error") or "")
        live_queue_health = report_health(root, 30, goal or None)
        live_queue_payload = live_queue_health if isinstance(live_queue_health, dict) else {}
        queue_metrics = build_queue_metrics(
            live_queue_payload,
            latest_event_next_role,
            bool(stop_gate_count),
        )
        active_count = safe_int(live_queue_payload.get("active_count"), safe_int(queue_metrics.get("active_count"), 0))
        latest_event_auto_mode = bool(latest_event_payload.get("auto_mode"))
        latest_event_starter_mode = str(latest_event_payload.get("starter_mode") or "")
        latest_event_starter_boundary = ""
        if latest_event_auto_mode:
            latest_event_starter_boundary = STARTER_AUTO_BOUNDARY
        elif latest_event_starter_mode == "dry-check":
            latest_event_starter_boundary = STARTER_DRY_CHECK_BOUNDARY
        latest_event_failures = latest_event_payload.get("launch_failures", [])
        latest_event_failure_list: list[dict[str, object]] = []
        if isinstance(latest_event_failures, list):
            for item in latest_event_failures:
                if not isinstance(item, dict):
                    continue
                latest_event_failure_list.append(
                    {
                        "command": str(item.get("command") or ""),
                        "returncode": safe_int(item.get("returncode"), 0),
                        "output": str(item.get("output") or ""),
                    }
                )
        latest_event_launch_failure_count = (
            len(latest_event_failure_list)
            if latest_event_failure_list
            else safe_int(latest_event_payload.get("launch_failure_count"), 0)
        )
        latest_event_fallback_launchers_raw = latest_event_payload.get("fallback_launchers", [])
        latest_event_fallback_launchers = (
            [str(item) for item in latest_event_fallback_launchers_raw]
            if isinstance(latest_event_fallback_launchers_raw, list)
            else []
        )
        latest_event_fallback_launch_recovered = bool(latest_event_payload.get("fallback_launch_recovered"))
        latest_event_suppressed = latest_event_payload.get("suppressed_launches", [])
        latest_event_suppressed_list: list[dict[str, object]] = []
        if isinstance(latest_event_suppressed, list):
            for item in latest_event_suppressed:
                if not isinstance(item, dict):
                    continue
                latest_event_suppressed_list.append(
                    {
                        "role": str(item.get("role") or ""),
                        "reason": str(item.get("reason") or ""),
                        "remaining_seconds": item.get("remaining_seconds"),
                    }
                )
        latest_event_suppressed_count = (
            len(latest_event_suppressed_list)
            if latest_event_suppressed_list
            else safe_int(latest_event_payload.get("suppressed_launch_count"), 0)
        )
        latest_event_stalled_recoveries_raw = latest_event_payload.get("stalled_recoveries", [])
        latest_event_stalled_recoveries = (
            [item for item in latest_event_stalled_recoveries_raw if isinstance(item, dict)]
            if isinstance(latest_event_stalled_recoveries_raw, list)
            else []
        )
        latest_event_stalled_recovery_count = (
            len(latest_event_stalled_recoveries)
            if latest_event_stalled_recoveries
            else safe_int(latest_event_payload.get("stalled_recovery_count"), 0)
        )
        latest_event_subagent_prompt_roles_raw = latest_event_payload.get("subagent_prompt_roles", [])
        latest_event_subagent_prompt_roles = (
            [str(item) for item in latest_event_subagent_prompt_roles_raw if str(item)]
            if isinstance(latest_event_subagent_prompt_roles_raw, list)
            else []
        )
        if not latest_event_subagent_prompt_roles and subagent_packet.get("available"):
            packet_roles = subagent_packet.get("prompt_roles", [])
            latest_event_subagent_prompt_roles = (
                [str(item) for item in packet_roles if str(item)] if isinstance(packet_roles, list) else []
            )
        latest_event_subagent_fallback_available = bool(
            latest_event_payload.get("subagent_fallback_available") or subagent_packet.get("available")
        )
        latest_event_subagent_fallback_kind = str(latest_event_payload.get("subagent_fallback_kind") or "")
        latest_event_subagent_fallback_reason = str(latest_event_payload.get("subagent_fallback_reason") or "")
        latest_event_subagent_prompt_count = safe_int(
            latest_event_payload.get("subagent_prompt_count"),
            safe_int(subagent_packet.get("prompt_count"), len(latest_event_subagent_prompt_roles)),
        )
        if (
            fallback_state == "needs-supervisor-run"
            and latest_event_state == "attention"
            and latest_event_assignment_state == "acknowledged"
            and latest_event_assignment_role
        ):
            fallback_state = "attention"
        if fallback_state == "needs-supervisor-run" and latest_event_suppressed_count:
            fallback_state = "attention"
        if (
            fallback_state == "needs-supervisor-run"
            and latest_event_assignment_state in {"pending-ack", "unassigned", "lease-expired", "pending-ack-expired"}
            and latest_event_assignment_role
        ):
            fallback_state = "attention"
        if (
            fallback_state == "needs-supervisor-run"
            and latest_event_state == "active"
            and latest_event_assignment_state == "acknowledged"
            and latest_event_assignment_role
        ):
            fallback_state = "active"
        latest_event_resume_config = latest_event_payload.get("resume_config", {})
        latest_event_resume_config_payload = (
            latest_event_resume_config if isinstance(latest_event_resume_config, dict) else {}
        )
        resume_command = build_resume_command(
            root,
            goal,
            fallback_state,
            stop_gate_count,
            bool(completion_audit.get("completion_ready")),
            latest_event_resume_config_payload,
            latest_event_auto_mode,
        )
        return {
            "kind": "taskboard-t0-progress",
            "state": fallback_state,
            "goal": goal,
            "next_role": latest_event_next_role,
            "task": latest_event_task,
            "assignment_state": latest_event_assignment_state,
            "assignment_role": latest_event_assignment_role,
            "assignment_task": latest_event_assignment_task,
            "assignment_reason": latest_event_assignment_reason,
            "assignment_expected_id": latest_event_assignment_expected_id,
            "assignment_pending_age_seconds": latest_event_assignment_pending_age_seconds,
            "auto_mode": latest_event_auto_mode,
            "starter_mode": latest_event_starter_mode,
            "starter_boundary": latest_event_starter_boundary,
            "active_count": active_count,
            "missing_roles": [],
            "stale_roles": [],
            "launch_failures": latest_event_failure_list,
            "launch_failure_count": latest_event_launch_failure_count,
            "fallback_launchers": latest_event_fallback_launchers,
            "fallback_launch_recovered": latest_event_fallback_launch_recovered,
            "suppressed_launches": latest_event_suppressed_list,
            "suppressed_launch_count": latest_event_suppressed_count,
            "subagent_fallback_available": latest_event_subagent_fallback_available,
            "subagent_fallback_kind": latest_event_subagent_fallback_kind,
            "subagent_fallback_reason": latest_event_subagent_fallback_reason,
            "subagent_fallback_packet_available": bool(subagent_packet.get("available")),
            "subagent_fallback_packet_file": str(subagent_packet.get("path") or ""),
            "subagent_prompt_count": latest_event_subagent_prompt_count,
            "subagent_prompt_roles": latest_event_subagent_prompt_roles,
            "subagent_dispatch_state_file": str(subagent_dispatch.get("state_file") or ""),
            "subagent_dispatched_roles": subagent_dispatched_roles,
            "subagent_pending_roles": subagent_pending_roles,
            "subagent_dispatch_records": subagent_dispatch_records,
            "stalled_recoveries": latest_event_stalled_recoveries,
            "stalled_recovery_count": latest_event_stalled_recovery_count,
            "stop_gates": stop_gate_list,
            "stop_gate_count": stop_gate_count,
            "decision_command": decision_command,
            "resume_command": resume_command,
            "completion_audit": completion_audit,
            "completion_ready": bool(completion_audit.get("completion_ready")),
            "completion_missing_evidence": completion_missing_list,
            "error": latest_event_error,
            "queue_metrics": queue_metrics,
            "t0_supervisor": t0_supervisor,
            "t0_supervisor_state": t0_supervisor.get("state"),
            "t0_supervisor_age_seconds": t0_supervisor.get("age_seconds"),
            "t0_supervisor_stale_after_seconds": t0_supervisor.get("stale_after_seconds"),
            **event_summary,
            "user_summary": build_user_summary(
                fallback_state,
                goal,
                latest_event_next_role,
                latest_event_task,
                latest_event_assignment_state,
                active_count,
                latest_event_launch_failure_count,
                latest_event_suppressed_count,
                stop_gate_count,
                first_stop_gate_question,
                queue_metrics,
                latest_event_error,
                latest_event_fallback_launch_recovered,
                latest_event_fallback_launchers,
                latest_event_subagent_fallback_available,
                latest_event_subagent_prompt_roles,
            ),
            "user_action": build_user_action(
                fallback_state,
                latest_event_dispatch_state or fallback_state,
                ["wait for recent T0 launch lease"] if latest_event_suppressed_count else [],
                latest_event_launch_failure_count,
                stop_gate_count,
                completion_missing_list,
                latest_event_assignment_state,
                latest_event_assignment_role,
                "",
                latest_event_error,
                latest_event_fallback_launch_recovered,
                latest_event_fallback_launchers,
                latest_event_stalled_recovery_count,
                latest_event_subagent_fallback_available,
                latest_event_subagent_prompt_roles,
            ),
            "boundary": T0_PROGRESS_BOUNDARY,
        }

    latest = snapshot.get("latest", {})
    latest_payload = latest if isinstance(latest, dict) else {}
    dispatch = latest_payload.get("dispatch", {})
    dispatch_payload = dispatch if isinstance(dispatch, dict) else {}
    assignment = latest_payload.get("assignment", {})
    assignment_payload = assignment if isinstance(assignment, dict) else {}
    queue_health = latest_payload.get("queue_health", {})
    queue_payload = queue_health if isinstance(queue_health, dict) else {}
    session_probe = latest_payload.get("session_probe", {})
    session_payload = session_probe if isinstance(session_probe, dict) else {}
    actions = latest_payload.get("actions", [])
    action_list = [str(action) for action in actions] if isinstance(actions, list) else []
    suppressed_launches = latest_payload.get("suppressed_launches", [])
    suppressed_launch_list: list[dict[str, object]] = []
    if isinstance(suppressed_launches, list):
        for item in suppressed_launches:
            if not isinstance(item, dict):
                continue
            suppressed_launch_list.append(
                {
                    "role": str(item.get("role") or ""),
                    "reason": str(item.get("reason") or ""),
                    "remaining_seconds": item.get("remaining_seconds"),
                }
            )
    stalled_recoveries_raw = latest_payload.get("stalled_recoveries", [])
    stalled_recoveries = (
        [item for item in stalled_recoveries_raw if isinstance(item, dict)]
        if isinstance(stalled_recoveries_raw, list)
        else []
    )
    stalled_recovery_count = len(stalled_recoveries)
    executed_commands = latest_payload.get("executed_commands", [])
    launch_failures: list[dict[str, object]] = []
    if isinstance(executed_commands, list):
        for item in executed_commands:
            if not isinstance(item, dict):
                continue
            try:
                returncode = int(item.get("returncode", 0))
            except (TypeError, ValueError):
                returncode = 0
            if returncode == 0:
                continue
            launch_failures.append(
                {
                    "command": str(item.get("command") or ""),
                    "returncode": returncode,
                    "output": str(item.get("output") or ""),
                }
            )
    fallback_attempts = latest_payload.get("fallback_launch_attempts", [])
    fallback_attempt_list = fallback_attempts if isinstance(fallback_attempts, list) else []
    fallback_launch_recovered = any(
        bool(item.get("success")) for item in fallback_attempt_list if isinstance(item, dict)
    )
    fallback_launchers = [
        str(item.get("launcher") or "")
        for item in fallback_attempt_list
        if isinstance(item, dict) and item.get("launcher")
    ]
    subagent_fallback_summary = summarize_subagent_fallback(latest_payload.get("subagent_fallback", {}))
    subagent_fallback_available = bool(subagent_fallback_summary.get("available") or subagent_packet.get("available"))
    subagent_fallback_kind = str(subagent_fallback_summary.get("kind") or "")
    subagent_fallback_reason = str(subagent_fallback_summary.get("reason") or "")
    subagent_prompt_count = safe_int(
        subagent_fallback_summary.get("prompt_count"),
        safe_int(subagent_packet.get("prompt_count"), 0),
    )
    subagent_prompt_roles_raw = subagent_fallback_summary.get("prompt_roles", [])
    subagent_prompt_roles = (
        [str(item) for item in subagent_prompt_roles_raw if str(item)]
        if isinstance(subagent_prompt_roles_raw, list)
        else []
    )
    if not subagent_prompt_roles and subagent_packet.get("available"):
        packet_roles = subagent_packet.get("prompt_roles", [])
        subagent_prompt_roles = [str(item) for item in packet_roles if str(item)] if isinstance(packet_roles, list) else []

    goal = str(snapshot.get("goal") or latest_payload.get("goal") or read_goal(root, ""))
    state = str(latest_payload.get("state") or dispatch_payload.get("state") or "unknown")
    next_role = str(dispatch_payload.get("next_role") or "T0")
    task = str(dispatch_payload.get("task") or "none")
    assignment_state = str(assignment_payload.get("state") or "none")
    assignment_role = str(assignment_payload.get("role") or "")
    assignment_task = str(assignment_payload.get("task") or "none")
    assignment_reason = str(assignment_payload.get("reason") or "")
    assignment_expected_id = str(assignment_payload.get("expected_assignment_id") or "")
    assignment_pending_age_seconds = safe_int(assignment_payload.get("pending_age_seconds"), 0)
    error = str(latest_payload.get("error") or "")
    auto_mode = bool(latest_payload.get("auto_mode"))
    starter_mode = str(latest_payload.get("starter_mode") or "")
    starter_boundary = str(latest_payload.get("starter_boundary") or "")
    resume_config = latest_payload.get("resume_config", {})
    resume_config_payload = resume_config if isinstance(resume_config, dict) else {}
    t0_supervisor = build_t0_supervisor_freshness(snapshot, resume_config_payload)
    t0_supervisor_state = str(t0_supervisor.get("state") or "")
    try:
        active_count = int(queue_payload.get("active_count") or 0)
    except (TypeError, ValueError):
        active_count = 0
    user_action_required = bool(stop_gate_count or launch_failures)
    queue_metrics = build_queue_metrics(queue_payload, next_role, user_action_required)
    resume_command = build_resume_command(
        root,
        goal,
        state,
        stop_gate_count,
        bool(completion_audit.get("completion_ready")),
        resume_config_payload,
        auto_mode,
    )

    return {
        "kind": "taskboard-t0-progress",
        "state": state,
        "goal": goal,
        "next_role": next_role,
        "task": task,
        "assignment_state": assignment_state,
        "assignment_role": assignment_role,
        "assignment_task": assignment_task,
        "assignment_reason": assignment_reason,
        "assignment_expected_id": assignment_expected_id,
        "assignment_pending_age_seconds": assignment_pending_age_seconds,
        "auto_mode": auto_mode,
        "starter_mode": starter_mode,
        "starter_boundary": starter_boundary,
        "active_count": active_count,
        "missing_roles": list(session_payload.get("missing_roles", []))
        if isinstance(session_payload.get("missing_roles", []), list)
        else [],
        "stale_roles": list(session_payload.get("stale_roles", []))
        if isinstance(session_payload.get("stale_roles", []), list)
        else [],
        "launch_failures": launch_failures,
        "launch_failure_count": len(launch_failures),
        "fallback_launchers": fallback_launchers,
        "fallback_launch_recovered": fallback_launch_recovered,
        "subagent_fallback_available": subagent_fallback_available,
        "subagent_fallback_kind": subagent_fallback_kind,
        "subagent_fallback_reason": subagent_fallback_reason,
        "subagent_fallback_packet_available": bool(subagent_packet.get("available")),
        "subagent_fallback_packet_file": str(subagent_packet.get("path") or ""),
        "subagent_prompt_count": subagent_prompt_count,
        "subagent_prompt_roles": subagent_prompt_roles,
        "subagent_dispatch_state_file": str(subagent_dispatch.get("state_file") or ""),
        "subagent_dispatched_roles": subagent_dispatched_roles,
        "subagent_pending_roles": subagent_pending_roles,
        "subagent_dispatch_records": subagent_dispatch_records,
        "suppressed_launches": suppressed_launch_list,
        "suppressed_launch_count": len(suppressed_launch_list),
        "stalled_recoveries": stalled_recoveries,
        "stalled_recovery_count": stalled_recovery_count,
        "stop_gates": stop_gate_list,
        "stop_gate_count": stop_gate_count,
        "decision_command": decision_command,
        "resume_command": resume_command,
        "completion_audit": completion_audit,
        "completion_ready": bool(completion_audit.get("completion_ready")),
        "completion_missing_evidence": completion_missing_list,
        "error": error,
        "queue_metrics": queue_metrics,
        "t0_supervisor": t0_supervisor,
        "t0_supervisor_state": t0_supervisor_state,
        "t0_supervisor_age_seconds": t0_supervisor.get("age_seconds"),
        "t0_supervisor_stale_after_seconds": t0_supervisor.get("stale_after_seconds"),
        **event_summary,
        "user_summary": build_user_summary(
            state,
            goal,
            next_role,
            task,
            assignment_state,
            active_count,
            len(launch_failures),
            len(suppressed_launch_list),
            stop_gate_count,
            first_stop_gate_question,
            queue_metrics,
            error,
            fallback_launch_recovered,
            fallback_launchers,
            subagent_fallback_available,
            subagent_prompt_roles,
        ),
        "user_action": build_user_action(
            state,
            str(dispatch_payload.get("state") or ""),
            action_list,
            len(launch_failures),
            stop_gate_count,
            completion_missing_list,
            assignment_state,
            assignment_role,
            t0_supervisor_state,
            error,
            fallback_launch_recovered,
            fallback_launchers,
            stalled_recovery_count,
            subagent_fallback_available,
            subagent_prompt_roles,
        ),
        "actions": action_list,
        "boundary": T0_PROGRESS_BOUNDARY,
    }


def format_text(payload: dict[str, object]) -> str:
    queue_metrics = payload.get("queue_metrics", {})
    metrics_payload = queue_metrics if isinstance(queue_metrics, dict) else {}
    role_counts = metrics_payload.get("role_counts", {})
    role_count_payload = role_counts if isinstance(role_counts, dict) else {}
    completion_audit = payload.get("completion_audit", {})
    completion_payload = completion_audit if isinstance(completion_audit, dict) else {}
    completion_missing = payload.get("completion_missing_evidence", [])
    completion_missing_list = completion_missing if isinstance(completion_missing, list) else []
    latest_event = payload.get("latest_event", {})
    latest_event_payload = latest_event if isinstance(latest_event, dict) else {}
    latest_event_failures = latest_event_payload.get("launch_failures", [])
    latest_event_failure_list = (
        latest_event_failures if isinstance(latest_event_failures, list) else []
    )
    latest_event_first_failure = (
        latest_event_failure_list[0]
        if latest_event_failure_list and isinstance(latest_event_failure_list[0], dict)
        else {}
    )
    lines = [
        f"state={payload['state']}",
        f"goal={payload['goal']}",
        f"next_role={payload['next_role']}",
        f"task={payload['task']}",
        f"assignment_state={payload['assignment_state']}",
        f"assignment_role={payload.get('assignment_role', '')}",
        f"assignment_task={payload.get('assignment_task', '')}",
        f"assignment_reason={payload.get('assignment_reason', '')}",
        f"assignment_expected_id={payload.get('assignment_expected_id', '')}",
        f"assignment_pending_age_seconds={payload.get('assignment_pending_age_seconds', 0)}",
        f"queue_metrics_active_count={metrics_payload.get('active_count', 0)}",
        f"queue_metrics_stalled_count={metrics_payload.get('stalled_count', 0)}",
        "queue_metrics_role_counts="
        + ",".join(f"{role}:{role_count_payload.get(role, 0)}" for role in ROLES),
        f"queue_metrics_next_role={metrics_payload.get('next_role', payload['next_role'])}",
        f"t0_supervisor_state={payload.get('t0_supervisor_state', '')}",
        f"t0_supervisor_age_seconds={payload.get('t0_supervisor_age_seconds', '')}",
        f"t0_supervisor_stale_after_seconds={payload.get('t0_supervisor_stale_after_seconds', '')}",
        f"event_count={payload.get('event_count', 0)}",
        f"latest_event_state={latest_event_payload.get('state', '')}",
        f"latest_event_dispatch_state={latest_event_payload.get('dispatch_state', '')}",
        f"latest_event_next_role={latest_event_payload.get('next_role', '')}",
        f"latest_event_task={latest_event_payload.get('task', '')}",
        f"latest_event_assignment_state={latest_event_payload.get('assignment_state', '')}",
        f"latest_event_assignment_role={latest_event_payload.get('assignment_role', '')}",
        f"latest_event_assignment_task={latest_event_payload.get('assignment_task', '')}",
        f"latest_event_assignment_reason={latest_event_payload.get('assignment_reason', '')}",
        f"latest_event_assignment_expected_id={latest_event_payload.get('assignment_expected_id', '')}",
        f"latest_event_launch_failure_count={latest_event_payload.get('launch_failure_count', 0)}",
        f"latest_event_launch_failure_command={latest_event_first_failure.get('command', '')}",
        f"latest_event_launch_failure_returncode={latest_event_first_failure.get('returncode', '')}",
        f"latest_event_launch_failure_output={latest_event_first_failure.get('output', '')}",
        f"fallback_launch_recovered={payload.get('fallback_launch_recovered', False)}",
        "fallback_launchers="
        + ",".join(str(item) for item in payload.get("fallback_launchers", []) if item),
        f"subagent_fallback_available={payload.get('subagent_fallback_available', False)}",
        f"subagent_fallback_kind={payload.get('subagent_fallback_kind', '')}",
        f"subagent_fallback_reason={payload.get('subagent_fallback_reason', '')}",
        f"subagent_fallback_packet_available={payload.get('subagent_fallback_packet_available', False)}",
        f"subagent_fallback_packet_file={payload.get('subagent_fallback_packet_file', '')}",
        f"subagent_prompt_count={payload.get('subagent_prompt_count', 0)}",
        "subagent_prompt_roles="
        + ",".join(str(item) for item in payload.get("subagent_prompt_roles", []) if item),
        f"subagent_dispatch_state_file={payload.get('subagent_dispatch_state_file', '')}",
        "subagent_dispatched_roles="
        + ",".join(str(item) for item in payload.get("subagent_dispatched_roles", []) if item),
        "subagent_pending_roles="
        + ",".join(str(item) for item in payload.get("subagent_pending_roles", []) if item),
        f"latest_event_subagent_fallback_available={latest_event_payload.get('subagent_fallback_available', False)}",
        f"stalled_recovery_count={payload.get('stalled_recovery_count', 0)}",
        f"latest_event_completion_ready={latest_event_payload.get('completion_ready', '')}",
        f"completion_ready={payload.get('completion_ready')}",
        f"completion_audit_state={completion_payload.get('state', '')}",
        f"starter_mode={payload.get('starter_mode')}",
        f"user_action={payload['user_action']}",
        f"summary={payload['user_summary']}",
        f"boundary={payload['boundary']}",
    ]
    if payload.get("error"):
        lines.insert(-3, f"error={payload['error']}")
    if completion_missing_list:
        lines.insert(-3, "completion_missing_evidence=" + "; ".join(str(item) for item in completion_missing_list))
    if payload.get("decision_command"):
        lines.insert(-1, f"decision_command={payload['decision_command']}")
    if payload.get("resume_command"):
        lines.insert(-1, f"resume_command={payload['resume_command']}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing T0 runtime state")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    payload = report_progress(Path(args.root).resolve())
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
