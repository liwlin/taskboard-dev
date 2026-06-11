#!/usr/bin/env python3
"""Track managed T1/T2/T3 session heartbeats for T0 recovery."""

from argparse import ArgumentParser, Namespace
from pathlib import Path
import json
import os
import sys
import time
from typing import Optional

from taskboard_t0 import build_launch_commands, build_session, default_target_dir, write_role_target_files


ROLES = ("T1", "T2", "T3")
RUNTIME_DIR = ".taskboard"
SESSION_DIR = "sessions"
ALIVE_DIR = "alive"
T0_BOUNDARY = (
    "T0 manager-only: probe role session heartbeats and recover missing or stale T1/T2/T3; "
    "do not execute development, design, review, implementation, verification, or commit tasks in T0."
)


def session_dir(root: Path) -> Path:
    return root / RUNTIME_DIR / SESSION_DIR


def session_path(root: Path, role: str) -> Path:
    return session_dir(root) / f"taskboard-{role}.json"


def alive_dir(root: Path) -> Path:
    return root / RUNTIME_DIR / ALIVE_DIR


def alive_path(root: Path, role: str) -> Path:
    return alive_dir(root) / role


def now_epoch() -> float:
    return time.time()


def write_heartbeat(
    root: Path,
    role: str,
    title: Optional[str],
    status: str,
    pid: Optional[int],
    task: Optional[str] = None,
    assignment_id: Optional[str] = None,
) -> dict[str, object]:
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
    if task:
        payload["task"] = task
    if assignment_id:
        payload["assignment_id"] = assignment_id
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


def classify_alive_marker(root: Path, role: str, stale_seconds: int, current_time: float) -> Optional[dict[str, object]]:
    path = alive_path(root, role)
    if not path.exists():
        return None
    try:
        last_seen = path.stat().st_mtime
    except OSError:
        last_seen = 0
    age_seconds = max(0, int(current_time - last_seen))
    state = "stale" if age_seconds >= stale_seconds else "alive"
    return {
        "role": role,
        "title": f"taskboard-{role}",
        "state": state,
        "age_seconds": age_seconds,
        "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(last_seen)) if last_seen else None,
        "status": "alive-marker",
        "source": ".taskboard/alive",
    }


def classify_session(root: Path, role: str, stale_seconds: int, current_time: float) -> dict[str, object]:
    payload = read_session(root, role)
    if payload is None:
        alive_marker = classify_alive_marker(root, role, stale_seconds, current_time)
        if alive_marker is not None:
            return alive_marker
        return {
            "role": role,
            "title": f"taskboard-{role}",
            "state": "missing",
            "age_seconds": None,
            "last_seen": None,
            "status": "missing",
            "source": ".taskboard/sessions",
        }

    raw_last_seen = payload.get("last_seen", 0)
    try:
        last_seen = float(raw_last_seen)
    except (TypeError, ValueError):
        last_seen = 0
    age_seconds = max(0, int(current_time - last_seen))
    state = "stale" if age_seconds >= stale_seconds else "alive"
    if state == "stale":
        alive_marker = classify_alive_marker(root, role, stale_seconds, current_time)
        if alive_marker is not None and alive_marker["state"] == "alive":
            return alive_marker
    return {
        "role": role,
        "title": str(payload.get("title") or f"taskboard-{role}"),
        "state": state,
        "age_seconds": age_seconds,
        "last_seen": payload.get("last_seen_iso") or last_seen,
        "status": str(payload.get("status") or state),
        "pid": payload.get("pid"),
        "task": payload.get("task"),
        "assignment_id": payload.get("assignment_id"),
        "source": ".taskboard/sessions",
    }


def build_recovery_sessions(
    roles: list[str],
    goal: str,
    reason: str,
    target_dir: Optional[Path] = None,
) -> list[dict[str, str]]:
    sessions = []
    for role in roles:
        sessions.append(build_session(role, goal, role, "managed-loop", "none", reason, target_dir))
    return sessions


def recovery_needs_target_files(agent_template: Optional[str]) -> bool:
    return bool(agent_template and "{target_file}" in agent_template)


def probe_sessions(
    root: Path,
    stale_seconds: int,
    expected_roles: list[str],
    launcher: str = "none",
    agent_template: Optional[str] = None,
    goal: Optional[str] = None,
    target_dir: Optional[Path] = None,
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
    recovery_sessions = build_recovery_sessions(
        recovery_roles,
        goal or "<user goal>",
        "session-missing-or-stale",
        target_dir,
    )
    target_files = (
        write_role_target_files(recovery_sessions)
        if target_dir is not None and recovery_needs_target_files(agent_template)
        else []
    )
    return {
        "state": "attention" if recovery_roles else "healthy",
        "expected_roles": normalized_roles,
        "sessions": sessions,
        "missing_roles": missing_roles,
        "stale_roles": stale_roles,
        "recovery_actions": recovery_actions,
        "recovery_sessions": recovery_sessions,
        "recovery_commands": build_launch_commands(root, recovery_sessions, launcher, agent_template),
        "target_files": target_files,
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
    if payload.get("target_files"):
        lines.append("target_files:")
        for item in payload["target_files"]:
            lines.append(f"- {item['role']} path={item['path']}")
    return "\n".join(lines)


def parse_expected(raw_values: Optional[list[str]]) -> list[str]:
    if not raw_values:
        return list(ROLES)
    roles: list[str] = []
    for raw in raw_values:
        roles.extend(item.strip().upper() for item in raw.split(",") if item.strip())
    return roles or list(ROLES)


def run_heartbeat(root: Path, args: Namespace) -> dict[str, object]:
    return write_heartbeat(root, args.role, args.title, args.status, args.pid, args.task, args.assignment_id)


def run_probe(root: Path, args: Namespace) -> dict[str, object]:
    return probe_sessions(
        root,
        args.stale_seconds,
        parse_expected(args.expected),
        args.launcher,
        args.agent_template,
        args.goal,
        args.target_dir,
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
    heartbeat.add_argument("--task", help="Current TASKBOARD filename this role has acknowledged")
    heartbeat.add_argument("--assignment-id", help="Current T0 assignment id, normally <role>:<task>")

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
        help=(
            "Command template for generated recovery commands. Supports "
            "{role}, {title}, {command}, {target}, and {target_file}."
        ),
    )
    probe.add_argument(
        "--target-dir",
        help="Directory for generated per-role target files referenced by {target_file}. Defaults to .taskboard/targets.",
    )

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if getattr(args, "command", None) == "probe" and args.target_dir is None:
        args.target_dir = default_target_dir(root)
    elif getattr(args, "command", None) == "probe":
        args.target_dir = Path(args.target_dir).resolve()
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
