#!/usr/bin/env python3
"""Validate evidence from a T0-managed native-subagent run."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys
from typing import Optional

from taskboard_subagents import (
    SUBAGENT_ROLES,
    read_subagent_fallback_packet,
    subagent_status_payload,
)


PLACEHOLDER_AGENT_ID_PREFIXES = (
    "fake",
    "manual",
    "placeholder",
    "smoke",
    "test",
)


def prompt_required_fragments(role: str) -> list[str]:
    role_lower = role.lower()
    return [
        f"You are taskboard-{role}",
        f"references/role-{role_lower}.md",
        "Read SKILL.md",
        "Use this embedded target as the T0-managed role inbox.",
        "Do not inherit T0 private reasoning",
        "Return progress only through TASKBOARD",
        "T0 input boundary:",
        "Startup skill gate:",
        "Worker loop contract:",
        "Idle recheck contract:",
    ]


def normalize_roles(raw_roles: str) -> list[str]:
    roles = [item.strip().upper() for item in raw_roles.split(",") if item.strip()]
    invalid = [role for role in roles if role not in SUBAGENT_ROLES]
    if invalid:
        raise ValueError(f"invalid role(s): {', '.join(invalid)}")
    return roles


def is_placeholder_agent_id(agent_id: str) -> bool:
    lowered = agent_id.strip().lower()
    return not lowered or lowered.startswith(PLACEHOLDER_AGENT_ID_PREFIXES)


def collect_acceptance(root: Path, required_roles: list[str], require_real_agent_ids: bool) -> dict[str, object]:
    packet = read_subagent_fallback_packet(root)
    status = subagent_status_payload(root)
    records = status.get("records", {})
    record_map = records if isinstance(records, dict) else {}
    prompts = packet.get("prompts", [])
    prompt_list = [item for item in prompts if isinstance(item, dict)] if isinstance(prompts, list) else []
    prompt_by_role = {str(item.get("role") or ""): str(item.get("prompt") or "") for item in prompt_list}

    failures: list[str] = []
    evidence: list[str] = []

    if not packet.get("available"):
        failures.append(f"subagent fallback packet not found at {packet.get('path')}")
    else:
        evidence.append(f"fallback packet found: {packet.get('path')}")

    prompt_roles = packet.get("prompt_roles", [])
    if not isinstance(prompt_roles, list):
        prompt_roles = []
    missing_prompt_roles = [role for role in required_roles if role not in prompt_roles]
    if missing_prompt_roles:
        failures.append(f"missing prompt role(s): {', '.join(missing_prompt_roles)}")
    else:
        evidence.append(f"prompt roles present: {', '.join(required_roles)}")

    for role in required_roles:
        prompt = prompt_by_role.get(role, "")
        if not prompt:
            failures.append(f"{role}: prompt missing from fallback packet")
            continue
        missing_fragments = [fragment for fragment in prompt_required_fragments(role) if fragment not in prompt]
        if missing_fragments:
            failures.append(f"{role}: prompt missing required fragment(s): {', '.join(missing_fragments)}")
        else:
            evidence.append(f"{role}: prompt includes skill, role, boundary, and loop gates")

    pending_roles = status.get("pending_roles", [])
    active_roles = status.get("active_roles", [])
    failed_roles = status.get("failed_roles", [])
    if pending_roles:
        failures.append(f"pending role(s) remain: {', '.join(str(item) for item in pending_roles)}")
    if active_roles:
        failures.append(f"active role(s) remain: {', '.join(str(item) for item in active_roles)}")
    if failed_roles:
        failures.append(f"failed role(s) remain: {', '.join(str(item) for item in failed_roles)}")

    for role in required_roles:
        record = record_map.get(role)
        if not isinstance(record, dict):
            failures.append(f"{role}: dispatch record missing")
            continue
        if record.get("status") != "completed":
            failures.append(f"{role}: expected completed status, got {record.get('status')}")
        agent_id = str(record.get("agent_id") or "")
        if not agent_id.strip():
            failures.append(f"{role}: agent_id missing")
        elif require_real_agent_ids and is_placeholder_agent_id(agent_id):
            failures.append(f"{role}: agent_id looks like placeholder evidence: {agent_id}")
        summary = str(record.get("summary") or "")
        if not summary.strip():
            failures.append(f"{role}: completion summary missing")
        if not str(record.get("completed_at") or "").strip():
            failures.append(f"{role}: completed_at missing")
        attempts = record.get("attempts", [])
        if attempts is not None and not isinstance(attempts, list):
            failures.append(f"{role}: attempts must be a list when present")
        evidence.append(f"{role}: completed by agent_id={agent_id or '<missing>'}")

    return {
        "kind": "taskboard-subagent-acceptance",
        "state": "passed" if not failures else "failed",
        "root": str(root),
        "required_roles": required_roles,
        "require_real_agent_ids": require_real_agent_ids,
        "packet_file": str(packet.get("path") or ""),
        "state_file": str(status.get("state_file") or ""),
        "prompt_roles": prompt_roles,
        "pending_roles": pending_roles,
        "active_roles": active_roles,
        "failed_roles": failed_roles,
        "completed_roles": status.get("completed_roles", []),
        "failure_count": len(failures),
        "failures": failures,
        "evidence": evidence,
    }


def format_text(payload: dict[str, object]) -> str:
    lines = [
        f"state={payload['state']}",
        f"root={payload['root']}",
        f"required_roles={','.join(payload['required_roles'])}",
        f"completed_roles={','.join(str(item) for item in payload['completed_roles'])}",
        f"failure_count={payload['failure_count']}",
    ]
    for failure in payload["failures"]:
        lines.append(f"failure={failure}")
    return "\n".join(lines)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing .taskboard/t0 subagent files")
    parser.add_argument("--require-completed", default="T1,T2,T3", help="Comma-separated roles that must be complete")
    parser.add_argument(
        "--require-real-agent-ids",
        action="store_true",
        help="Reject placeholder/smoke/test agent ids when recording real field evidence",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        required_roles = normalize_roles(args.require_completed)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = collect_acceptance(Path(args.root).resolve(), required_roles, args.require_real_agent_ids)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(payload))
    return 0 if payload["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
