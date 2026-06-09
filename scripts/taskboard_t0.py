#!/usr/bin/env python3
"""Build the T0 terminal orchestration plan for TASKBOARD."""

from argparse import ArgumentParser
from pathlib import Path
import json
import shlex
import sys
from typing import Optional

from taskboard_next import format_selection, select_task


ROLE_LABELS = {
    "T0": "orchestrator",
    "T1": "architect/scheduler",
    "T2": "reviewer/verifier",
    "T3": "executor",
}

ROLE_TARGETS = {
    "T1": "T1: 基于用户目标创建或修订 PROJECT/MAP/REQUIREMENTS/STATE 和 TASK 文件，保持任务队列可执行。",
    "T2": "T2: 审核待审核方案或代码，运行必要验证，通过则归档，失败则退回对应角色。",
    "T3": "T3: 完成未阻塞 T3 任务，在任务 Files/Acceptance 范围内实现、验证并提交。",
}

T0_BOUNDARY = (
    "T0 manager-only: T0 是管理员/调度器，不直接执行开发任务；"
    "开发、设计、审核、实现、验证、提交分别交给 T1/T2/T3。"
)


def read_goal(root: Path, explicit_goal: Optional[str]) -> str:
    if explicit_goal and explicit_goal.strip():
        return explicit_goal.strip()

    for relative in ("docs/PROJECT.md", "docs/REQUIREMENTS.md"):
        path = root / relative
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    return ""


def build_target(role: str, status: str, task_name: str, goal: str, reason: str) -> str:
    if role == "T0":
        return "请先提供用户目标。T0 需要目标后才能自动管理 T1/T2/T3。"

    base = ROLE_TARGETS[role]
    if status == "T1-create-or-revise":
        action = "当前没有活跃任务；请创建或修订下一批 TASK 文件。"
    elif task_name != "none":
        action = f"请处理 {task_name}，完成后按 TASKBOARD 状态机交接。"
    else:
        action = f"请根据状态 {status} 继续推进。"

    return (
        f"用户目标：{goal}\n"
        f"调度原因：{reason}\n"
        f"角色目标：{base}\n"
        f"本轮动作：{action}\n"
        "持续自主执行，直到该角色队列清空、任务交接完成或触发停止门。"
    )


def build_session(role: str, goal: str, next_role: str, status: str, task_name: str, reason: str) -> dict[str, str]:
    target_status = status if role == next_role else "managed-loop"
    target_task = task_name if role == next_role else "none"
    target_reason = reason if role == next_role else "t0-managed-background-role"
    target = build_target(role, target_status, target_task, goal, target_reason)
    heartbeat_command = f"python scripts/taskboard_sessions.py --root . heartbeat --role {role}"
    if role == next_role and task_name != "none":
        heartbeat_command += f" --task {task_name} --assignment-id {role}:{task_name}"
    heartbeat = f"Session heartbeat: run `{heartbeat_command}` at loop start and after each TASKBOARD handoff."
    return {
        "role": role,
        "title": f"taskboard-{role}",
        "command": f"/taskboard-dev {role}",
        "target": f"{target}\n{heartbeat}",
    }


def build_sessions(goal: str, next_role: str, status: str, task_name: str, reason: str) -> list[dict[str, str]]:
    return [
        build_session(role, goal, next_role, status, task_name, reason)
        for role in ("T1", "T2", "T3")
    ]


def powershell_quote(value: str) -> str:
    escaped = value.replace("`", "``").replace('"', '`"').replace("$", "`$")
    return f'"{escaped}"'


def render_agent_command(session: dict[str, str], agent_template: Optional[str]) -> str:
    if not agent_template:
        target = session["target"].replace("\n", "`n")
        return f"Write-Host {powershell_quote(target)}"

    compact_target = " ".join(session["target"].splitlines())
    return agent_template.format(
        role=session["role"],
        title=session["title"],
        command=session["command"],
        target=compact_target,
    )


def build_launch_commands(
    root: Path,
    sessions: list[dict[str, str]],
    launcher: str,
    agent_template: Optional[str],
) -> list[str]:
    if launcher == "none" or not sessions:
        return []

    commands = []
    root_text = str(root)
    for index, session in enumerate(sessions):
        agent_command = render_agent_command(session, agent_template)
        if launcher == "windows-terminal":
            commands.append(
                "wt -w taskboard new-tab "
                f"--title {powershell_quote(session['title'])} "
                f"-d {powershell_quote(root_text)} "
                f"powershell -NoExit -Command {powershell_quote(agent_command)}"
            )
        elif launcher == "powershell":
            commands.append(
                "Start-Process powershell "
                f"-WorkingDirectory {powershell_quote(root_text)} "
                f"-ArgumentList '-NoExit','-Command',{powershell_quote(agent_command)}"
            )
        elif launcher == "tmux":
            shell_command = f"cd {shlex.quote(root_text)} && {agent_command}"
            if index == 0:
                commands.append(
                    "tmux new-session -d -s taskboard "
                    f"-n {session['title']} {shlex.quote(shell_command)}"
                )
            else:
                commands.append(
                    "tmux new-window -t taskboard "
                    f"-n {session['title']} {shlex.quote(shell_command)}"
                )
        else:
            raise ValueError(f"unknown launcher: {launcher}")
    return commands


def build_session_manifest(
    state: str,
    next_role: str,
    status: str,
    task_name: str,
    reason: str,
    sessions: list[dict[str, str]],
) -> dict[str, object]:
    roles = [session["role"] for session in sessions]
    recovery_order = [next_role] + [role for role in roles if role != next_role] if sessions else []
    return {
        "managed_by": "T0",
        "state": state,
        "roles": roles,
        "next_role": next_role,
        "status": status,
        "task": task_name,
        "reason": reason,
        "recovery_order": recovery_order,
        "sync_contract": "TASKBOARD filenames + stable context files + history/HANDOFF; no shared chat context",
        "health_checks": [
            'python scripts/taskboard_sessions.py --root . probe --stale-seconds 300 --goal "<user goal>"',
            'python scripts/taskboard_health.py --root . --stale-minutes 30 --goal "<user goal>"',
            "python scripts/taskboard_next.py --role T0 --root .",
            "check managed terminal titles: taskboard-T1, taskboard-T2, taskboard-T3",
            "check docs/taskboard/TASK-*.T*.md mtime for stalled work",
        ],
    }


def dispatch(
    root: Path,
    goal_arg: Optional[str],
    mode: str,
    launcher: str = "none",
    agent_template: Optional[str] = None,
) -> dict[str, str]:
    goal = read_goal(root, goal_arg)

    if not goal:
        return {
            "state": "needs-goal",
            "mode": mode,
            "next_role": "T0",
            "role_label": ROLE_LABELS["T0"],
            "status": "needs-goal",
            "task": "none",
            "reason": "missing-user-goal",
            "command": "/taskboard-dev T0",
            "target": build_target("T0", "needs-goal", "none", goal, "missing-user-goal"),
            "boundary": T0_BOUNDARY,
            "managed_sessions": [],
            "launch_commands": [],
            "session_manifest": build_session_manifest(
                "needs-goal", "T0", "needs-goal", "none", "missing-user-goal", []
            ),
        }

    role, status, task, reason = select_task("T0", root)
    task_name = task.path.name if task is not None else "none"

    if role == "T0" and status == "complete" and goal_arg:
        role = "T1"
        status = "T1-create-or-revise"
        task_name = "none"
        reason = "explicit-goal-no-active-tasks"

    if role == "T0" and status == "complete":
        state = "complete"
        command = "/taskboard-dev T0"
        target = f"用户目标：{goal}\n所有活跃 TASKBOARD 队列为空。请汇总完成情况并确认目标是否满足。"
        sessions = []
    else:
        state = "dispatch"
        command = f"start managed terminals: /taskboard-dev T1, /taskboard-dev T2, /taskboard-dev T3"
        sessions = build_sessions(goal, role, status, task_name, reason)
        target = next(session["target"] for session in sessions if session["role"] == role)
    launch_commands = build_launch_commands(root, sessions, launcher, agent_template)
    session_manifest = build_session_manifest(state, role, status, task_name, reason, sessions)

    return {
        "state": state,
        "mode": mode,
        "launcher": launcher,
        "next_role": role,
        "role_label": ROLE_LABELS[role],
        "status": status,
        "task": task_name,
        "reason": reason,
        "command": command,
        "target": target,
        "boundary": T0_BOUNDARY,
        "managed_sessions": sessions,
        "launch_commands": launch_commands,
        "session_manifest": session_manifest,
    }


def format_text(payload: dict[str, str]) -> str:
    lines = [
        f"state={payload['state']}",
        f"mode={payload['mode']}",
        format_selection(
            payload["next_role"],
            payload["status"],
            None,
            payload["reason"],
        ).replace("task=none", f"task={payload['task']}"),
        f"command={payload['command']}",
        f"boundary={payload['boundary']}",
        "target:",
        payload["target"],
    ]
    sessions = payload.get("managed_sessions", [])
    if sessions:
        lines.append("managed_sessions:")
        for session in sessions:
            lines.append(f"- title={session['title']} command={session['command']}")
    launch_commands = payload.get("launch_commands", [])
    if launch_commands:
        lines.append("launch_commands:")
        for command in launch_commands:
            lines.append(f"- {command}")
    manifest = payload.get("session_manifest")
    if manifest:
        lines.append("session_manifest:")
        lines.append(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root containing docs/taskboard")
    parser.add_argument("--goal", help="User goal for the T0 run")
    parser.add_argument(
        "--mode",
        choices=("terminal", "subagent", "inline"),
        default="terminal",
        help="Dispatch execution mode to describe in the output",
    )
    parser.add_argument(
        "--launcher",
        choices=("none", "windows-terminal", "powershell", "tmux"),
        default="none",
        help="Optional shell launcher command family to emit for managed role sessions",
    )
    parser.add_argument(
        "--agent-template",
        help="Command template used inside each launched role terminal. Supports {role}, {title}, {command}, and {target}.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        payload = dispatch(Path(args.root).resolve(), args.goal, args.mode, args.launcher, args.agent_template)
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
