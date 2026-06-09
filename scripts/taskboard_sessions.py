#!/usr/bin/env python3
"""Track managed T1/T2/T3 session heartbeats for T0 recovery."""

from argparse import ArgumentParser, Namespace
from pathlib import Path
import json
import os
import sys
import time
from typing import Optional

from taskboard_t0 import build_launch_commands, build_session


ROLES = ("T1", "T2", "T3")
RUNTIME_DIR = ".taskboard"
SESSION_DIR = "sessions"
T0_BOUNDARY = (
    "T0 manager-only: probe role session heartbeats and recover missing or stale T1/T2/T3; "
    "do not execute development, design, review, implementation, verification, or commit tasks in T0."
)


def session_dir(root: Path) -> Path:
    return root / RUNTIME_DIR / SESSION_DIR


def session_path(root: Path, role: str) -> Path:
    return session_dir(root) / f"taskboard-{role}.json"


def now_epoch() -> float:
    return time.time()


def write_heartbeat(root: Path, role: str, title: Optional[str], status: str, pid: Optional[int]) -> dict[str, object]:
    role = role.upper()
    if role not in ROLES:
        raise ValueError(f"unknown role: {role}")

    current_time = now_epoch()
    payload = {
        "role": role,
        "title": title or f"taskboard-{role}",
        "status": status,
        "pid": pid if pid is not None else os.getpid(),
        "last_seen": current_time,
        "last_seen_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(current_time)),
    }
    path = session_path(root, role)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def read_session(root: Path, role: str) -> Optional[dict[str, object]]:
    path = session_path(root, role)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {
            "role": role,
            "title": f"taskboard-{role}",
            "status": "unreadable",
            "last_seen": 0,
        }
    return payload if isinstance(payload, dict) else None


def classify_session(root: Path, role: str, stale_seconds: int, current_time: float) -> dict[str, object]:
    payload = read_session(root, role)
    if payload is None:
        return {
            "role": role,
            "title": f"taskboard-{role}",
            "state": "missing",
            "age_seconds": None,
            "last_seen": None,
            "status": "missing",
        }

    raw_last_seen = payload.get("last_seen", 0)
    try:
        last_seen = float(raw_last_seen)
    except (TypeError, ValueError):
        last_seen = 0
    age_seconds = max(0, int(current_time - last_seen))
    state = "stale" if age_seconds >= stale_seconds else "alive"
    return {
        "role": role,
        "title": str(payload.get("title") or f"taskboard-{role}"),
        "state": state,
        "age_seconds": age_seconds,
        "last_seen": payload.get("last_seen_iso") or last_seen,
        "status": str(payload.get("status") or state),
        "pid": payload.get("pid"),
    }


def build_recovery_sessions(roles: list[str], goal: str, reason: str) -> list[dict[str, str]]:
    sessions = []
    for role in roles:
        sessions.append(build_session(role, goal, role, "managed-loop", "none", reason))
    return sessions


def probe_sessions(
    root: Path,
    stale_seconds: int,
    expected_roles: list[str],
    launcher: str = "none",
    agent_template: Optional[str] = None,
    goal: Optional[str] = None,
) -> dict[str, object]:
    if stale_seconds < 0:
        raise ValueError("--stale-seconds must be >= 0")

    normalized_roles = [role.upper() for role in expected_roles]
    unknown_roles = [role for role in normalized_roles if role not in ROLES]
    if unknown_roles:
        raise ValueError(f"unknown role: {unknown_roles[0]}")

    current_time = now_epoch()
    sessions = {
        role: classify_session(root, role, stale_seconds, current_time)
        for role in normalized_roles
    }
    missing_roles = [role for role, item in sessions.items() if item["state"] == "missing"]
    stale_roles = [role for role, item in sessions.items() if item["state"] == "stale"]
    recovery_roles = missing_roles + [role for role in stale_roles if role not in missing_roles]
    recovery_actions = [
        f"recover taskboard-{role}; reissue role target and keep T0 manager-only"
        for role in recovery_roles
    ]
    recovery_sessions = build_recovery_sessions(recovery_roles, goal or "<user goal>", "session-missing-or-stale")
    return {
        "state": "attention" if recovery_roles else "healthy",
        "expected_roles": normalized_roles,
        "sessions": sessions,
        "missing_roles": missing_roles,
        "stale_roles": stale_roles,
        "recovery_actions": recovery_actions,
        "recovery_commands": build_launch_commands(root, recovery_sessions, launcher, agent_template),
        "boundary": T0_BOUNDARY,
    }


def format_text(payload: dict[str, object]) -> str:
    lines = [
        f"state={payload['state']}",
        f"boundary={payload['boundary']}",
        "sessions:",
    ]
    sessions = payload["sessions"]
    for role in payload["expected_roles"]:
        item = sessions[role]
        lines.append(
            f"- {role} state={item['state']} age_seconds={item['age_seconds']} status={item['status']}"
        )
    if payload["recovery_actions"]:
        lines.append("recovery_actions:")
        for action in payload["recovery_actions"]:
            lines.append(f"- {action}")
    if payload["recovery_commands"]:
        lines.append("recovery_commands:")
        for command in payload["recovery_commands"]:
            lines.append(f"- {command}")
    return "\n".join(lines)


def parse_expected(raw_values: Optional[list[str]]) -> list[str]:
    if not raw_values:
        return list(ROLES)
    roles: list[str] = []
    for raw in raw_values:
        roles.extend(item.strip().upper() for item in raw.split(",") if item.strip())
    return roles or list(ROLES)


def run_heartbeat(root: Path, args: Namespace) -> dict[str, object]:
    return write_heartbeat(root, args.role, args.title, args.status, args.pid)


def run_probe(root: Path, args: Namespace) -> dict[str, object]:
    return probe_sessions(
        root,
        args.stale_seconds,
        parse_expected(args.expected),
        args.launcher,
        args.agent_template,
        args.goal,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing runtime session heartbeats")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    subparsers = parser.add_subparsers(dest="command", required=True)

    heartbeat = subparsers.add_parser("heartbeat", help="Write one role heartbeat")
    heartbeat.add_argument("--role", choices=ROLES, required=True)
    heartbeat.add_argument("--title", help="Managed terminal title")
    heartbeat.add_argument("--status", default="alive", help="Free-form role loop status")
    heartbeat.add_argument("--pid", type=int, help="Agent process id if known")

    probe = subparsers.add_parser("probe", help="Probe expected managed role heartbeats")
    probe.add_argument("--stale-seconds", type=int, default=300)
    probe.add_argument("--expected", action="append", help="Expected roles, repeatable or comma-separated")
    probe.add_argument("--goal", help="Current user goal for generated recovery targets")
    probe.add_argument(
        "--launcher",
        choices=("none", "windows-terminal", "powershell", "tmux"),
        default="none",
        help="Optional launcher command family for missing/stale role recovery commands",
    )
    probe.add_argument(
        "--agent-template",
        help="Command template for generated recovery commands. Supports {role}, {title}, {command}, and {target}.",
    )

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        payload = run_heartbeat(root, args) if args.command == "heartbeat" else run_probe(root, args)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
