#!/usr/bin/env python3
"""T0 native-subagent dispatch state helpers."""

from pathlib import Path
import hashlib
import json
import time


SUBAGENT_ROLES = ("T1", "T2", "T3")
DISPATCH_BOUNDARY = (
    "T0 records native subagent dispatch ownership; this is control-plane recovery "
    "metadata, not TASKBOARD task state or worker memory."
)


def default_subagent_fallback_file(root: Path) -> Path:
    return root / ".taskboard" / "t0" / "subagent-fallback.json"


def default_subagent_dispatch_file(root: Path) -> Path:
    return root / ".taskboard" / "t0" / "subagents.json"


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_json_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_subagent_fallback_packet(root: Path) -> dict[str, object]:
    path = default_subagent_fallback_file(root)
    packet = read_json_file(path)
    if not packet:
        return {"available": False, "path": str(path), "prompts": []}

    fallback = packet.get("subagent_fallback", {})
    fallback_payload = fallback if isinstance(fallback, dict) else {}
    prompts = fallback_payload.get("subagent_prompts", [])
    prompt_list = [item for item in prompts if isinstance(item, dict)] if isinstance(prompts, list) else []
    roles = packet.get("subagent_prompt_roles", [])
    role_list = [str(item) for item in roles if str(item)] if isinstance(roles, list) else []
    if not role_list:
        role_list = [str(item.get("role") or "") for item in prompt_list if item.get("role")]

    return {
        "available": True,
        "path": str(path),
        "kind": str(packet.get("kind") or ""),
        "goal": str(packet.get("goal") or ""),
        "prompt_count": int(packet.get("subagent_prompt_count") or len(prompt_list)),
        "prompt_roles": [role for role in role_list if role],
        "prompts": prompt_list,
    }


def read_runtime_goal(root: Path) -> str:
    path = root / ".taskboard" / "t0" / "goal.json"
    payload = read_json_file(path)
    goal = payload.get("goal") if isinstance(payload, dict) else ""
    return goal.strip() if isinstance(goal, str) else ""


def fallback_packet_state(root: Path, packet: dict[str, object]) -> str:
    if not packet.get("available"):
        return "missing"
    current_goal = read_runtime_goal(root)
    packet_goal = str(packet.get("goal") or "").strip()
    if current_goal and packet_goal and current_goal != packet_goal:
        return "stale-goal"
    return "ready"


def empty_dispatch_state(root: Path) -> dict[str, object]:
    return {
        "kind": "taskboard-subagent-dispatch-state",
        "version": 1,
        "updated_at": "",
        "state_file": str(default_subagent_dispatch_file(root)),
        "roles": {},
        "boundary": DISPATCH_BOUNDARY,
    }


def read_subagent_dispatch_state(root: Path) -> dict[str, object]:
    state = read_json_file(default_subagent_dispatch_file(root))
    if state.get("kind") != "taskboard-subagent-dispatch-state":
        return empty_dispatch_state(root)
    roles = state.get("roles", {})
    state["roles"] = roles if isinstance(roles, dict) else {}
    state["boundary"] = str(state.get("boundary") or DISPATCH_BOUNDARY)
    state["state_file"] = str(default_subagent_dispatch_file(root))
    return state


def write_subagent_dispatch_state(root: Path, state: dict[str, object]) -> None:
    path = default_subagent_dispatch_file(root)
    state["kind"] = "taskboard-subagent-dispatch-state"
    state["version"] = 1
    state["updated_at"] = utc_now()
    state["state_file"] = str(path)
    state["boundary"] = DISPATCH_BOUNDARY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prompt_roles(packet: dict[str, object]) -> list[str]:
    roles = packet.get("prompt_roles", [])
    if not isinstance(roles, list):
        return []
    return [role for role in (str(item) for item in roles) if role in SUBAGENT_ROLES]


def prompt_for_role(packet: dict[str, object], role: str) -> str:
    prompts = packet.get("prompts", [])
    if not isinstance(prompts, list):
        return ""
    for item in prompts:
        if isinstance(item, dict) and str(item.get("role") or "") == role:
            return str(item.get("prompt") or "")
    return ""


def prompt_hash(prompt: str) -> str:
    return "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def text_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def quote_cli_value(value: object) -> str:
    text = str(value)
    escaped = text.replace('"', '\\"')
    return f'"{escaped}"'


def subagent_command_base(root: Path) -> str:
    return f"python scripts/taskboard.py --root {quote_cli_value(root)} subagent"


def subagent_acceptance_command(root: Path) -> str:
    return (
        f"python scripts/taskboard_subagent_acceptance.py --root {quote_cli_value(root)} "
        "--require-real-agent-ids --require-spawn-evidence --require-result-evidence"
    )


def dispatch_records(state: dict[str, object]) -> dict[str, dict[str, object]]:
    roles = state.get("roles", {})
    if not isinstance(roles, dict):
        return {}
    records: dict[str, dict[str, object]] = {}
    for role, record in roles.items():
        role_text = str(role)
        if role_text not in SUBAGENT_ROLES or not isinstance(record, dict):
            continue
        records[role_text] = record
    return records


def subagent_status_payload(root: Path) -> dict[str, object]:
    packet = read_subagent_fallback_packet(root)
    packet_state = fallback_packet_state(root, packet)
    state = read_subagent_dispatch_state(root)
    records = dispatch_records(state)
    roles = prompt_roles(packet)
    dispatched = [role for role in roles if role in records]
    active = [role for role in dispatched if str(records[role].get("status") or "") == "dispatched"]
    completed = [role for role in dispatched if str(records[role].get("status") or "") == "completed"]
    failed = [role for role in dispatched if str(records[role].get("status") or "") == "failed"]
    pending = [
        role
        for role in roles
        if role not in records or str(records[role].get("status") or "") == "retry-pending"
    ]
    return {
        "kind": "taskboard-subagent-dispatch",
        "packet_available": bool(packet.get("available")) and packet_state == "ready",
        "packet_state": packet_state,
        "packet_file": str(packet.get("path") or default_subagent_fallback_file(root)),
        "packet_goal": str(packet.get("goal") or ""),
        "current_goal": read_runtime_goal(root),
        "state_file": str(default_subagent_dispatch_file(root)),
        "prompt_roles": roles,
        "pending_roles": pending,
        "dispatched_roles": dispatched,
        "active_roles": active,
        "completed_roles": completed,
        "failed_roles": failed,
        "records": records,
        "boundary": DISPATCH_BOUNDARY,
    }


def subagent_next_payload(root: Path) -> dict[str, object]:
    status = subagent_status_payload(root)
    packet = read_subagent_fallback_packet(root)
    pending = status["pending_roles"] if isinstance(status.get("pending_roles"), list) else []
    if not packet.get("available"):
        return {
            "kind": "taskboard-subagent-next",
            "state": "missing-packet",
            "role": "",
            "prompt": "",
            "boundary": DISPATCH_BOUNDARY,
        }
    if not pending:
        return {
            "kind": "taskboard-subagent-next",
            "state": "complete",
            "role": "",
            "prompt": "",
            "boundary": DISPATCH_BOUNDARY,
        }

    role = str(pending[0])
    prompts = packet.get("prompts", [])
    prompt = ""
    if isinstance(prompts, list):
        for item in prompts:
            if isinstance(item, dict) and str(item.get("role") or "") == role:
                prompt = str(item.get("prompt") or "")
                break
    return {
        "kind": "taskboard-subagent-next",
        "state": "pending",
        "role": role,
        "prompt": prompt,
        "dispatch_order": prompt_roles(packet).index(role) + 1,
        "packet_file": str(packet.get("path") or default_subagent_fallback_file(root)),
        "boundary": DISPATCH_BOUNDARY,
    }


def subagent_plan_payload(root: Path) -> dict[str, object]:
    status = subagent_status_payload(root)
    packet = read_subagent_fallback_packet(root)
    packet_state = str(status.get("packet_state") or fallback_packet_state(root, packet))
    prompt_role_list = [str(item) for item in status.get("prompt_roles", []) if str(item)]
    pending_roles = [str(item) for item in status.get("pending_roles", []) if str(item)]
    active_roles = [str(item) for item in status.get("active_roles", []) if str(item)]
    completed_roles = [str(item) for item in status.get("completed_roles", []) if str(item)]
    failed_roles = [str(item) for item in status.get("failed_roles", []) if str(item)]
    base = subagent_command_base(root)
    acceptance = subagent_acceptance_command(root)

    plan: dict[str, object] = {
        "kind": "taskboard-subagent-plan",
        "packet_available": bool(status.get("packet_available")),
        "packet_state": packet_state,
        "packet_file": str(status.get("packet_file") or default_subagent_fallback_file(root)),
        "packet_goal": str(status.get("packet_goal") or ""),
        "current_goal": str(status.get("current_goal") or ""),
        "state_file": str(default_subagent_dispatch_file(root)),
        "prompt_roles": prompt_role_list,
        "pending_roles": pending_roles,
        "active_roles": active_roles,
        "completed_roles": completed_roles,
        "failed_roles": failed_roles,
        "state": "idle",
        "action": "none",
        "role": "",
        "prompt": "",
        "prompt_hash": "",
        "native_spawn": {},
        "ack_command": "",
        "done_command": "",
        "fail_command": "",
        "retry_command": "",
        "acceptance_command": acceptance,
        "boundary": (
            "T0 subagent plan is a read-only dispatch recipe. T0 must call the "
            "native subagent tool itself, then record ack/result receipts with "
            "taskboard.py subagent commands."
        ),
    }

    if not status.get("packet_available"):
        plan["state"] = "stale-packet" if packet_state == "stale-goal" else "missing-packet"
        plan["action"] = "create-subagent-fallback-packet"
        return plan

    if failed_roles:
        role = failed_roles[0]
        plan["state"] = "retry-or-escalate"
        plan["action"] = "retry-failed-subagent"
        plan["role"] = role
        plan["retry_command"] = f'{base} retry --role {role} --note "<retry reason>"'
        return plan

    if pending_roles:
        role = pending_roles[0]
        prompt = prompt_for_role(packet, role)
        plan["state"] = "dispatch-next"
        plan["action"] = "spawn-native-subagent"
        plan["role"] = role
        plan["prompt"] = prompt
        plan["prompt_hash"] = prompt_hash(prompt)
        plan["dispatch_order"] = prompt_role_list.index(role) + 1 if role in prompt_role_list else 0
        plan["native_spawn"] = {
            "tool_hint": "multi_agent_v1.spawn_agent",
            "receipt_required": True,
            "recorded_fields": [
                "agent_id",
                "agent_nickname",
                "spawn_tool",
                "prompt_hash",
            ],
            "prompt_field": "prompt",
        }
        plan["ack_command"] = (
            f'{base} ack --role {role} --agent-id "<agent id>" '
            f'--spawn-tool "<native spawn tool>" --agent-nickname "<agent nickname>"'
        )
        plan["done_command"] = (
            f'{base} done --role {role} --summary "<result>" '
            f'--result-tool "<native wait tool>" --result-status "<native final status>"'
        )
        plan["fail_command"] = (
            f'{base} fail --role {role} --summary "<failure>" '
            f'--result-tool "<native wait tool>" --result-status "<native final status>"'
        )
        return plan

    if active_roles:
        role = active_roles[0]
        plan["state"] = "await-results"
        plan["action"] = "record-subagent-result"
        plan["role"] = role
        plan["done_command"] = (
            f'{base} done --role {role} --summary "<result>" '
            f'--result-tool "<native wait tool>" --result-status "<native final status>"'
        )
        plan["fail_command"] = (
            f'{base} fail --role {role} --summary "<failure>" '
            f'--result-tool "<native wait tool>" --result-status "<native final status>"'
        )
        return plan

    if prompt_role_list and set(completed_roles) >= set(prompt_role_list):
        plan["state"] = "complete"
        plan["action"] = "run-acceptance"
        return plan

    return plan


def subagent_ack_payload(
    root: Path,
    role: str,
    agent_id: str,
    note: str = "",
    spawn_tool: str = "",
    agent_nickname: str = "",
) -> dict[str, object]:
    normalized_role = role.upper()
    if normalized_role not in SUBAGENT_ROLES:
        raise ValueError(f"invalid subagent role: {role}")
    if not agent_id.strip():
        raise ValueError("agent-id is required")

    packet = read_subagent_fallback_packet(root)
    valid_roles = prompt_roles(packet)
    if valid_roles and normalized_role not in valid_roles:
        raise ValueError(f"role not present in subagent fallback packet: {normalized_role}")

    state = read_subagent_dispatch_state(root)
    roles = state.get("roles", {})
    role_records = roles if isinstance(roles, dict) else {}
    existing = role_records.get(normalized_role)
    attempts = []
    if isinstance(existing, dict):
        previous_attempts = existing.get("attempts", [])
        attempts = [item for item in previous_attempts if isinstance(item, dict)] if isinstance(previous_attempts, list) else []
    record = {
        "role": normalized_role,
        "agent_id": agent_id.strip(),
        "status": "dispatched",
        "dispatched_at": utc_now(),
        "note": note.strip(),
        "packet_file": str(packet.get("path") or default_subagent_fallback_file(root)),
    }
    if spawn_tool.strip():
        record["spawn_tool"] = spawn_tool.strip()
    if agent_nickname.strip():
        record["agent_nickname"] = agent_nickname.strip()
    if spawn_tool.strip() or agent_nickname.strip():
        record["spawn_receipt"] = {
            "agent_id": agent_id.strip(),
            "agent_nickname": agent_nickname.strip(),
            "native_status": "spawned",
            "prompt_hash": prompt_hash(prompt_for_role(packet, normalized_role)),
            "recorded_at": record["dispatched_at"],
            "role": normalized_role,
            "spawn_tool": spawn_tool.strip(),
        }
    if attempts:
        record["attempts"] = attempts
    role_records[normalized_role] = record
    state["roles"] = role_records
    write_subagent_dispatch_state(root, state)
    return {
        "kind": "taskboard-subagent-ack",
        "record": record,
        "state_file": str(default_subagent_dispatch_file(root)),
        "boundary": DISPATCH_BOUNDARY,
    }


def subagent_result_payload(
    root: Path,
    role: str,
    status: str,
    summary: str = "",
    result_tool: str = "",
    result_status: str = "",
) -> dict[str, object]:
    normalized_role = role.upper()
    if normalized_role not in SUBAGENT_ROLES:
        raise ValueError(f"invalid subagent role: {role}")
    if status not in {"completed", "failed"}:
        raise ValueError(f"invalid subagent result status: {status}")

    state = read_subagent_dispatch_state(root)
    roles = state.get("roles", {})
    role_records = roles if isinstance(roles, dict) else {}
    existing = role_records.get(normalized_role)
    if not isinstance(existing, dict):
        raise ValueError(f"subagent dispatch is not acknowledged for role: {normalized_role}")

    record = dict(existing)
    record["role"] = normalized_role
    record["status"] = status
    record["summary"] = summary.strip()
    timestamp_key = "completed_at" if status == "completed" else "failed_at"
    record[timestamp_key] = utc_now()
    record["completion_receipt"] = {
        "agent_id": str(record.get("agent_id") or ""),
        "native_status": status,
        "recorded_at": record[timestamp_key],
        "role": normalized_role,
    }
    if result_tool.strip() or result_status.strip():
        record["result_receipt"] = {
            "agent_id": str(record.get("agent_id") or ""),
            "native_status": status,
            "recorded_at": record[timestamp_key],
            "result_status": result_status.strip(),
            "result_tool": result_tool.strip(),
            "role": normalized_role,
            "summary_hash": text_hash(summary.strip()),
        }
    role_records[normalized_role] = record
    state["roles"] = role_records
    write_subagent_dispatch_state(root, state)
    return {
        "kind": "taskboard-subagent-result",
        "record": record,
        "state_file": str(default_subagent_dispatch_file(root)),
        "boundary": DISPATCH_BOUNDARY,
    }


def subagent_retry_payload(root: Path, role: str, note: str = "") -> dict[str, object]:
    normalized_role = role.upper()
    if normalized_role not in SUBAGENT_ROLES:
        raise ValueError(f"invalid subagent role: {role}")

    packet = read_subagent_fallback_packet(root)
    valid_roles = prompt_roles(packet)
    if valid_roles and normalized_role not in valid_roles:
        raise ValueError(f"role not present in subagent fallback packet: {normalized_role}")

    state = read_subagent_dispatch_state(root)
    roles = state.get("roles", {})
    role_records = roles if isinstance(roles, dict) else {}
    existing = role_records.get(normalized_role)
    if not isinstance(existing, dict):
        raise ValueError(f"subagent dispatch record not found for role: {normalized_role}")

    previous_attempts = existing.get("attempts", [])
    attempts = [item for item in previous_attempts if isinstance(item, dict)] if isinstance(previous_attempts, list) else []
    archived = {
        key: value
        for key, value in existing.items()
        if key not in {"attempts", "retry_note", "status", "retried_at"}
    }
    archived["status"] = str(existing.get("status") or "")
    attempts.append(archived)
    record = {
        "role": normalized_role,
        "agent_id": "",
        "status": "retry-pending",
        "retry_note": note.strip(),
        "retried_at": utc_now(),
        "packet_file": str(packet.get("path") or default_subagent_fallback_file(root)),
        "attempts": attempts,
    }
    role_records[normalized_role] = record
    state["roles"] = role_records
    write_subagent_dispatch_state(root, state)
    return {
        "kind": "taskboard-subagent-retry",
        "record": record,
        "state_file": str(default_subagent_dispatch_file(root)),
        "boundary": DISPATCH_BOUNDARY,
    }
