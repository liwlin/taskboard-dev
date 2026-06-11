#!/usr/bin/env python3
"""Validate field evidence from a real T0-managed milestone."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys
from typing import Optional

from taskboard_completion import report_completion
from taskboard_subagents import SUBAGENT_ROLES


PLACEHOLDER_AGENT_ID_PREFIXES = (
    "demo",
    "fake",
    "manual",
    "placeholder",
    "smoke",
    "test",
)

BOUNDARY = (
    "taskboard live milestone acceptance is read-only; it audits evidence that T0 managed "
    "T1/T2/T3 through completion and must not launch workers, edit taskboard files, or create proof."
)


def read_json_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_event_log(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def normalize_roles(raw_roles: str) -> list[str]:
    roles = [item.strip().upper() for item in raw_roles.split(",") if item.strip()]
    invalid = [role for role in roles if role not in SUBAGENT_ROLES]
    if invalid:
        raise ValueError(f"invalid role(s): {', '.join(invalid)}")
    return roles


def is_placeholder_agent_id(agent_id: str) -> bool:
    lowered = agent_id.strip().lower()
    return not lowered or lowered.startswith(PLACEHOLDER_AGENT_ID_PREFIXES)


def event_values(events: list[dict[str, object]], key: str) -> list[object]:
    return [event[key] for event in events if key in event]


def bool_from_sources(latest: dict[str, object], events: list[dict[str, object]], key: str) -> bool:
    if bool(latest.get(key)):
        return True
    return any(bool(value) for value in event_values(events, key))


def text_from_sources(latest: dict[str, object], events: list[dict[str, object]], key: str) -> str:
    value = latest.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    for event in reversed(events):
        raw = event.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def has_checkout_conflict(latest: dict[str, object], events: list[dict[str, object]]) -> bool:
    checkout = latest.get("checkout_owner")
    if isinstance(checkout, dict) and checkout.get("state") == "conflict":
        return True
    if latest.get("checkout_owner_state") == "conflict":
        return True
    return any(event.get("checkout_owner_state") == "conflict" for event in events)


def is_smoke_starter_mode(starter_mode: str) -> bool:
    lowered = starter_mode.strip().lower()
    return any(token in lowered for token in ("demo", "smoke", "test"))


def t0_observed_completion(latest: dict[str, object], events: list[dict[str, object]]) -> bool:
    if latest.get("state") == "complete" or bool(latest.get("completion_ready")):
        return True
    for event in events:
        if event.get("state") == "complete" or bool(event.get("completion_ready")):
            return True
    return False


def role_session_file(root: Path, role: str) -> Path:
    return root / ".taskboard" / "sessions" / f"taskboard-{role}.json"


def role_alive_file(root: Path, role: str) -> Path:
    return root / ".taskboard" / "alive" / role


def collect_role_evidence(root: Path, role: str, events: list[dict[str, object]]) -> tuple[dict[str, object], list[str]]:
    failures: list[str] = []
    session_path = role_session_file(root, role)
    alive_path = role_alive_file(root, role)
    session = read_json_file(session_path)
    assigned_events = [
        event
        for event in events
        if event.get("assignment_role") == role
        or event.get("next_role") == role
        or event.get("role") == role
    ]

    agent_id = str(session.get("agent_id") or "")
    task = str(session.get("task") or "")
    assignment_id = str(session.get("assignment_id") or "")
    status = str(session.get("status") or session.get("state") or "")
    summary = str(session.get("summary") or session.get("note") or "")

    if not session:
        failures.append(f"{role}: missing live worker evidence")
    if session and is_placeholder_agent_id(agent_id):
        failures.append(f"{role}: agent_id looks like placeholder evidence: {agent_id or '<missing>'}")
    if session and not task.strip():
        failures.append(f"{role}: session task missing")
    if session and not assignment_id.strip():
        failures.append(f"{role}: assignment_id missing")
    if session and not (status.strip() or summary.strip()):
        failures.append(f"{role}: status/summary missing")

    state = "accepted" if not failures else "failed"
    return {
        "state": state,
        "session_file": str(session_path),
        "session_present": bool(session),
        "alive_marker_present": alive_path.exists(),
        "event_count": len(assigned_events),
        "agent_id": agent_id,
        "status": status,
        "task": task,
        "assignment_id": assignment_id,
    }, failures


def collect_acceptance(root: Path, required_roles: list[str]) -> dict[str, object]:
    root = root.resolve()
    latest_file = root / ".taskboard" / "t0" / "latest.json"
    event_log_file = root / ".taskboard" / "t0" / "events.jsonl"
    latest = read_json_file(latest_file)
    events = read_event_log(event_log_file)
    completion = report_completion(root)

    failures: list[str] = []
    evidence: list[str] = []

    auto_mode = bool_from_sources(latest, events, "auto_mode")
    starter_mode = text_from_sources(latest, events, "starter_mode")
    goal = text_from_sources(latest, events, "goal") or str(completion.get("goal") or "")
    completion_ready = bool(completion.get("completion_ready"))

    if not latest and not events:
        failures.append("missing T0 control-plane snapshot/event evidence")
    else:
        evidence.append("T0 control-plane snapshot/event evidence found")
    if not auto_mode:
        failures.append("T0 auto_mode evidence missing")
    if starter_mode and is_smoke_starter_mode(starter_mode):
        failures.append(f"T0 starter_mode looks like smoke/test/demo evidence: {starter_mode}")
    elif starter_mode and starter_mode != "auto":
        evidence.append(f"T0 starter_mode recorded: {starter_mode}")
    elif starter_mode == "auto":
        evidence.append("T0 one-command auto starter_mode recorded")
    if not t0_observed_completion(latest, events):
        failures.append("T0 completion observation missing")
    if has_checkout_conflict(latest, events):
        failures.append("checkout owner conflict evidence present")

    missing_completion = completion.get("missing_evidence", [])
    if isinstance(missing_completion, list):
        failures.extend(str(item) for item in missing_completion)
    if completion_ready:
        evidence.append("completion audit is complete-ready")
    archived = completion.get("archived_tasks", [])
    if isinstance(archived, list) and archived:
        evidence.append(f"archived TASK evidence: {', '.join(str(item) for item in archived)}")

    roles: dict[str, object] = {}
    for role in required_roles:
        role_payload, role_failures = collect_role_evidence(root, role, events)
        roles[role] = role_payload
        failures.extend(role_failures)
        if not role_failures:
            evidence.append(f"{role}: live worker evidence accepted")

    state = "passed" if not failures else "failed"
    return {
        "kind": "taskboard-live-milestone-acceptance",
        "state": state,
        "root": str(root),
        "required_roles": required_roles,
        "failure_count": len(failures),
        "failures": failures,
        "evidence": evidence,
        "t0_control_plane": {
            "latest_file": str(latest_file),
            "event_log_file": str(event_log_file),
            "latest_present": bool(latest),
            "event_count": len(events),
            "auto_mode": auto_mode,
            "starter_mode": starter_mode,
            "goal": goal,
            "checkout_owner_conflict": has_checkout_conflict(latest, events),
            "completion_observed": t0_observed_completion(latest, events),
        },
        "completion": {
            "state": completion.get("state"),
            "completion_ready": completion_ready,
            "archived_count": completion.get("archived_count"),
            "archived_tasks": completion.get("archived_tasks"),
            "goal_complete_sentinel": completion.get("goal_complete_sentinel"),
            "dev_log_has_completion_entries": completion.get("dev_log_has_completion_entries"),
            "missing_evidence": missing_completion,
        },
        "roles": roles,
        "boundary": BOUNDARY,
    }


def format_text(payload: dict[str, object]) -> str:
    lines = [
        f"state={payload['state']}",
        f"root={payload['root']}",
        f"required_roles={','.join(payload['required_roles'])}",
        f"failure_count={payload['failure_count']}",
        f"boundary={payload['boundary']}",
    ]
    for failure in payload["failures"]:
        lines.append(f"failure={failure}")
    for item in payload["evidence"]:
        lines.append(f"evidence={item}")
    return "\n".join(lines)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing docs/ and .taskboard/")
    parser.add_argument("--require-roles", default="T1,T2,T3", help="Comma-separated roles required for acceptance")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        required_roles = normalize_roles(args.require_roles)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = collect_acceptance(Path(args.root), required_roles)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(payload))
    return 0 if payload["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
