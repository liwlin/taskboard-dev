#!/usr/bin/env python3
"""T0 native-subagent dispatch state helpers."""

from pathlib import Path
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
        "prompt_count": int(packet.get("subagent_prompt_count") or len(prompt_list)),
        "prompt_roles": [role for role in role_list if role],
        "prompts": prompt_list,
    }


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
    state = read_subagent_dispatch_state(root)
    records = dispatch_records(state)
    roles = prompt_roles(packet)
    dispatched = [role for role in roles if role in records]
    active = [role for role in dispatched if str(records[role].get("status") or "") == "dispatched"]
    completed = [role for role in dispatched if str(records[role].get("status") or "") == "completed"]
    failed = [role for role in dispatched if str(records[role].get("status") or "") == "failed"]
    pending = [role for role in roles if role not in records]
    return {
        "kind": "taskboard-subagent-dispatch",
        "packet_available": bool(packet.get("available")),
        "packet_file": str(packet.get("path") or default_subagent_fallback_file(root)),
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


def subagent_ack_payload(root: Path, role: str, agent_id: str, note: str = "") -> dict[str, object]:
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
    record = {
        "role": normalized_role,
        "agent_id": agent_id.strip(),
        "status": "dispatched",
        "dispatched_at": utc_now(),
        "note": note.strip(),
        "packet_file": str(packet.get("path") or default_subagent_fallback_file(root)),
    }
    role_records[normalized_role] = record
    state["roles"] = role_records
    write_subagent_dispatch_state(root, state)
    return {
        "kind": "taskboard-subagent-ack",
        "record": record,
        "state_file": str(default_subagent_dispatch_file(root)),
        "boundary": DISPATCH_BOUNDARY,
    }


def subagent_result_payload(root: Path, role: str, status: str, summary: str = "") -> dict[str, object]:
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
    role_records[normalized_role] = record
    state["roles"] = role_records
    write_subagent_dispatch_state(root, state)
    return {
        "kind": "taskboard-subagent-result",
        "record": record,
        "state_file": str(default_subagent_dispatch_file(root)),
        "boundary": DISPATCH_BOUNDARY,
    }
