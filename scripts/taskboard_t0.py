#!/usr/bin/env python3
"""Build the T0 terminal orchestration plan for TASKBOARD."""

from argparse import ArgumentParser
from pathlib import Path
import json
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
    return {
        "role": role,
        "title": f"taskboard-{role}",
        "command": f"/taskboard-dev {role}",
        "target": build_target(role, target_status, target_task, goal, target_reason),
    }


def build_sessions(goal: str, next_role: str, status: str, task_name: str, reason: str) -> list[dict[str, str]]:
    return [
        build_session(role, goal, next_role, status, task_name, reason)
        for role in ("T1", "T2", "T3")
    ]


def dispatch(root: Path, goal_arg: Optional[str], mode: str) -> dict[str, str]:
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
            "managed_sessions": [],
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
        target = build_target(role, status, task_name, goal, reason)
        sessions = build_sessions(goal, role, status, task_name, reason)

    return {
        "state": state,
        "mode": mode,
        "next_role": role,
        "role_label": ROLE_LABELS[role],
        "status": status,
        "task": task_name,
        "reason": reason,
        "command": command,
        "target": target,
        "managed_sessions": sessions,
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
        "target:",
        payload["target"],
    ]
    sessions = payload.get("managed_sessions", [])
    if sessions:
        lines.append("managed_sessions:")
        for session in sessions:
            lines.append(f"- title={session['title']} command={session['command']}")
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
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    payload = dispatch(Path(args.root).resolve(), args.goal, args.mode)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
