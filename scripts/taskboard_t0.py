#!/usr/bin/env python3
"""Build the T0 terminal orchestration plan for TASKBOARD."""

from argparse import ArgumentParser
from pathlib import Path
import json
import shlex
import sys
import time
from typing import Optional

from taskboard_completion import report_completion
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

ROLE_TOOLING_CONTRACTS = {
    "T1": (
        "Default tooling contract:\n"
        "- T1 MUST use available planning/brainstorming skills before creating or revising non-trivial active TASK files.\n"
        "- Preferred defaults: superpowers:brainstorming for requirement shaping and superpowers:writing-plans for implementation plans.\n"
        "- Use equivalent native planning tools when they are the active client's best fit.\n"
        "- If no planning tool is available or applicable, proceed manually and record the fallback reason in the spec, plan, or task.\n"
        "Required skills evidence:\n"
        "- Record the tool or skill used, the result, and any fallback reason in the TASK file, history entry, plan, or dev-log before handoff."
    ),
    "T2": (
        "Default tooling contract:\n"
        "- T2 L2 code reviews default to an independent review tool when available.\n"
        "- Preferred defaults: Codex code review, a review subagent, superpowers:requesting-code-review, or an equivalent domain review skill.\n"
        "- L3 code reviews MUST run dual-pass review: T2's own review plus one independent or specialized review pass.\n"
        "- If no independent review tool is available, run the manual checklist and record the fallback reason.\n"
        "Evidence enforcement gate:\n"
        "- Missing Required skills evidence is a review failure; return the task to the producing role unless a user override explicitly waives the evidence requirement.\n"
        "- For design reviews, missing T1 planning/brainstorming evidence returns to T1 for revision.\n"
        "- For code reviews, missing T3 split/solo decision or verification evidence returns to T3 for repair.\n"
        "Required skills evidence:\n"
        "- Record the tool or skill used, the result, and any fallback reason in the TASK file, history entry, review note, or dev-log before handoff."
    ),
    "T3": (
        "Default tooling contract:\n"
        "- T3 MUST assess whether the implementation can be split before editing source.\n"
        "- Use Codex native subagents or available multi-agent tools when slices have independent files or interfaces and clear acceptance checks.\n"
        "- Stay solo when work is tightly coupled, touches the same files, requires one continuous design decision, or involves destructive/shared-state operations.\n"
        "- T3 remains responsible for integration, final verification, and commit even when subagents perform implementation slices.\n"
        "Required skills evidence:\n"
        "- Record the tool or skill used, the split/solo decision, verification result, and any fallback reason in the TASK file, history entry, or dev-log before handoff."
    ),
}

EXTERNAL_TOOL_CONTRACT = (
    "External tool contract:\n"
    "- Use GitHub tooling for repository, PR, issue, release, and CI-check work when that evidence is needed for the task.\n"
    "- Use Chrome/Browser tooling for web UI inspection, browser-side debugging, screenshots, and rendered frontend verification.\n"
    "- Use Computer Use only for local desktop or GUI workflows that cannot be verified through shell, browser, or repository tools.\n"
    "- Do not ask the user to operate these tools for routine role work; use the available tool yourself unless a stop gate applies.\n"
    "- Respect role boundaries when using external tools: T1 plans, T2 reviews/verifies, and T3 implements/verifies/commits."
)

T0_INPUT_BOUNDARY_CONTRACT = (
    "T0 input boundary:\n"
    "- Treat the user goal, scheduling reason, and role target above as goal intake and source material only.\n"
    "- They are not T0-authored requirements, architecture, interface specs, task splits, or acceptance criteria.\n"
    "- T1 owns requirement decomposition and TASK creation; T2 owns review/verification; T3 owns implementation/commit.\n"
    "- If T0 text appears to decide design or acceptance details, treat it as source material and route the decision back through the assigned role."
)

def startup_skill_gate(role: str) -> str:
    return (
        "Startup skill gate:\n"
        f"- Before any TASKBOARD action, load `/taskboard-dev {role}` so the full shared protocol and role reference are active.\n"
        "- Then invoke the required role tools/skills listed below before planning, reviewing, implementing, or handing off.\n"
        "- If a required skill/tool is unavailable, record the fallback reason before proceeding."
    )


T0_BOUNDARY = (
    "T0 manager-only: T0 是管理员/调度器，不直接执行开发任务；"
    "开发、设计、审核、实现、验证、提交分别交给 T1/T2/T3。"
)


def runtime_goal_file(root: Path) -> Path:
    return root / ".taskboard" / "t0" / "goal.json"


def read_runtime_goal(root: Path) -> str:
    path = runtime_goal_file(root)
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    goal = payload.get("goal")
    return goal.strip() if isinstance(goal, str) else ""


def write_runtime_goal(root: Path, goal: Optional[str]) -> str:
    normalized = goal.strip() if goal else ""
    if not normalized:
        return ""
    path = runtime_goal_file(root)
    payload = {
        "kind": "taskboard-t0-goal",
        "version": 1,
        "goal": normalized,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return normalized


def build_goal_intake(goal: str, reason: str) -> dict[str, object]:
    return {
        "kind": "taskboard-t0-goal-intake",
        "version": 1,
        "created_by": "T0",
        "next_owner": "T1",
        "user_goal": goal,
        "reason": reason,
        "allowed_fields": [
            "user_goal",
            "user_constraints",
            "non_goals",
            "source_material",
            "known_stop_gates",
        ],
        "forbidden_fields": [
            "requirements",
            "architecture",
            "interface_specs",
            "task_splits",
            "acceptance_criteria",
        ],
        "boundary": (
            "T0 goal intake only; T1 owns requirement decomposition, context files, "
            "TASK creation, architecture options, and acceptance criteria."
        ),
    }


def read_goal(root: Path, explicit_goal: Optional[str]) -> str:
    if explicit_goal and explicit_goal.strip():
        return explicit_goal.strip()

    runtime_goal = read_runtime_goal(root)
    if runtime_goal:
        return runtime_goal

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
        "持续自主执行；队列暂空时进入 idle recheck，不要退出，直到目标完成、触发停止门、用户暂停或需要上下文重启。"
    )


def default_target_dir(root: Path) -> Path:
    return root / ".taskboard" / "targets"


def role_target_file(target_dir: Path, title: str) -> Path:
    return target_dir / f"{title}.md"


def build_session(
    role: str,
    goal: str,
    next_role: str,
    status: str,
    task_name: str,
    reason: str,
    target_dir: Optional[Path] = None,
) -> dict[str, str]:
    target_status = status if role == next_role else "managed-loop"
    target_task = task_name if role == next_role else "none"
    target_reason = reason if role == next_role else "t0-managed-background-role"
    target = build_target(role, target_status, target_task, goal, target_reason)
    alive_command = f"python scripts/taskboard.py --root . alive {role}"
    cycle_command = f"python scripts/taskboard.py --root . cycle {role} --sleep-seconds 120"
    heartbeat_command = f"python scripts/taskboard_sessions.py --root . heartbeat --role {role}"
    if role == next_role and task_name != "none":
        heartbeat_command += f" --task {task_name} --assignment-id {role}:{task_name}"
    heartbeat = (
        f"Worker cycle command: run `{cycle_command}` at the start of each worker cycle and follow its `action` field.\n"
        f"Liveness marker: run `{alive_command}` at the start of each worker cycle.\n"
        f"Assignment heartbeat: run `{heartbeat_command}` when handling a concrete TASK and after each TASKBOARD handoff."
    )
    other_roles = "/".join(item for item in ("T0", "T1", "T2", "T3") if item != role)
    role_contract = (
        "Role runtime contract:\n"
        f"assigned_role: {role}\n"
        "managed_by: T0\n"
        f"- Execute only {role} responsibilities; do not execute {other_roles} responsibilities.\n"
        "- do not rely on another role's chat context; use this target file, TASKBOARD filenames, stable docs, history, and HANDOFF only.\n"
        "- Write the liveness marker before work and refresh assignment heartbeat after TASKBOARD handoff using the commands above.\n"
        "- Return work through TASKBOARD filename state transitions; do not ask the user to manage routine T1/T2/T3 flow."
    )
    loop_contract = (
        "Worker loop contract:\n"
        f"- Start every loop with `{cycle_command}`; if it returns `idle-recheck`, do not exit.\n"
        f"- Continue cycling this role while unblocked {role} work is available; after each TASKBOARD handoff, check again before yielding.\n"
        "- At each cycle, re-read TASKBOARD filenames and stable docs instead of relying on prior chat context.\n"
        "- Always refresh your heartbeat at the start of each cycle: liveness marker first, then assignment heartbeat after each TASKBOARD handoff.\n"
        f"- Do not stop after one action if more {role} work is available; keep advancing the role queue under T0 management.\n"
        "Idle recheck contract:\n"
        "- Do not terminate just because this role queue is empty; an empty queue is an idle state, not completion.\n"
        "- When no unblocked role work is visible, write the liveness marker, sleep/yield for the configured interval, then re-read this target file and TASKBOARD filenames.\n"
        "- Suggest exit only for goal completion, stop gate, explicit user pause, or context-limit restart."
    )
    tooling_contract = ROLE_TOOLING_CONTRACTS[role]
    title = f"taskboard-{role}"
    session = {
        "role": role,
        "title": title,
        "command": f"/taskboard-dev {role}",
        "target": (
            f"{target}\n{T0_INPUT_BOUNDARY_CONTRACT}\n{startup_skill_gate(role)}\n{heartbeat}\n{role_contract}\n"
            f"{tooling_contract}\n{EXTERNAL_TOOL_CONTRACT}\n{loop_contract}"
        ),
    }
    if target_dir is not None:
        session["target_file"] = str(role_target_file(target_dir, title))
    return session


def build_sessions(
    goal: str,
    next_role: str,
    status: str,
    task_name: str,
    reason: str,
    target_dir: Optional[Path],
) -> list[dict[str, str]]:
    return [
        build_session(role, goal, next_role, status, task_name, reason, target_dir)
        for role in ("T1", "T2", "T3")
    ]


def write_role_target_files(sessions: list[dict[str, str]]) -> list[dict[str, object]]:
    target_files: list[dict[str, object]] = []
    for session in sessions:
        target_file = session.get("target_file")
        target = session.get("target")
        role = session.get("role")
        title = session.get("title")
        if not target_file or not target or not role or not title:
            continue
        path = Path(str(target_file))
        body = (
            f"# {title} target\n\n"
            "kind: taskboard-role-target\n"
            "managed_by: T0\n"
            f"role: {role}\n"
            f"title: {title}\n"
            f"updated_at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            "boundary: T0 writes role targets only; the isolated worker session executes its own role work.\n\n"
            "---\n\n"
            f"{target}\n"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        target_files.append(
            {
                "role": str(role),
                "title": str(title),
                "path": str(path),
                "kind": "taskboard-role-target",
            }
        )
    return target_files


def launcher_needs_target_files(launcher: str, agent_template: Optional[str]) -> bool:
    return launcher != "none" and bool(agent_template and "{target_file}" in agent_template)


def powershell_quote(value: str) -> str:
    escaped = value.replace("`", "``").replace('"', '`"').replace("$", "`$")
    return f'"{escaped}"'


def powershell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_agent_command(session: dict[str, str], agent_template: Optional[str]) -> str:
    if not agent_template:
        target = session["target"].replace("\n", "`n")
        return f"Write-Host {powershell_quote(target)}"
    if "{target_file}" in agent_template and not session.get("target_file"):
        raise ValueError(
            "agent-template references {target_file}, but target files are disabled; "
            "enable target files or use {target}"
        )

    compact_target = " ".join(session["target"].splitlines())
    return agent_template.format(
        role=session["role"],
        title=session["title"],
        command=session["command"],
        target=compact_target,
        target_file=session.get("target_file", ""),
    )


def write_manual_windows_launch_scripts(
    root: Path,
    sessions: list[dict[str, str]],
    agent_template: Optional[str],
    script_dir: Optional[Path] = None,
) -> dict[str, object]:
    if not sessions:
        return {}

    output_dir = script_dir or root / ".taskboard"
    output_dir.mkdir(parents=True, exist_ok=True)
    launch_role = output_dir / "launch-role.ps1"
    open_tabs = output_dir / "open-tabs.ps1"
    role_commands = []
    roles = []
    for session in sessions:
        role = str(session.get("role") or "")
        if role not in {"T1", "T2", "T3"}:
            continue
        command = render_agent_command(session, agent_template)
        roles.append(role)
        role_commands.append(f"  {powershell_single_quote(role)} = {powershell_single_quote(command)}")

    if not role_commands:
        return {}

    launch_role_body = "\n".join(
        [
            "param(",
            "  [Parameter(Mandatory=$true)]",
            "  [ValidateSet('T1','T2','T3')]",
            "  [string]$Role",
            ")",
            "$ErrorActionPreference = 'Stop'",
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8",
            f"Set-Location -LiteralPath {powershell_single_quote(str(root))}",
            "$commands = @{",
            *role_commands,
            "}",
            "Write-Host \"Starting taskboard-$Role\"",
            "Invoke-Expression $commands[$Role]",
            "",
        ]
    )
    launch_role.write_text(launch_role_body, encoding="utf-8")

    open_tab_lines = [
        "$ErrorActionPreference = 'Stop'",
        "$script = Join-Path $PSScriptRoot 'launch-role.ps1'",
    ]
    for role in roles:
        open_tab_lines.append(
            "wt -w taskboard new-tab "
            f"--title taskboard-{role} "
            f"-d {powershell_single_quote(str(root))} "
            "powershell -NoExit -ExecutionPolicy Bypass -File $script "
            f"-Role {role}"
        )
    open_tabs.write_text("\n".join(open_tab_lines) + "\n", encoding="utf-8")
    return {
        "kind": "taskboard-user-owned-windows-launch-scripts",
        "open_tabs": str(open_tabs),
        "launch_role": str(launch_role),
        "roles": roles,
        "user_command": f'powershell -ExecutionPolicy Bypass -File "{open_tabs}"',
    }


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


def build_backend(mode: str) -> dict[str, str]:
    if mode == "subagent":
        return {
            "kind": "taskboard-subagent-backend",
            "mode": "subagent",
            "isolation": "native-subagent-context",
            "boundary": "T0 dispatches isolated worker prompts; T0 does not execute T1/T2/T3 work.",
        }
    if mode == "inline":
        return {
            "kind": "taskboard-inline-backend",
            "mode": "inline",
            "isolation": "role-boundary-reset",
            "boundary": "Compatibility fallback only; enforce role boundaries before each role switch.",
        }
    return {
        "kind": "taskboard-terminal-backend",
        "mode": "terminal",
        "isolation": "managed-terminal-context",
        "boundary": "T0 launches or recovers separate managed worker terminals.",
    }


def build_subagent_prompts(
    sessions: list[dict[str, str]],
    recovery_order: list[str],
) -> list[dict[str, object]]:
    by_role = {session["role"]: session for session in sessions}
    ordered_roles = [role for role in recovery_order if role in by_role]
    ordered_roles.extend(session["role"] for session in sessions if session["role"] not in ordered_roles)
    prompts: list[dict[str, object]] = []
    for index, role in enumerate(ordered_roles, start=1):
        session = by_role[role]
        role_reference = f"references/role-{role.lower()}.md"
        prompt = "\n".join(
            [
                f"You are {session['title']}, an isolated native subagent managed by T0.",
                f"Read SKILL.md and {role_reference} before acting.",
                "Use this embedded target as the T0-managed role inbox.",
                "Do not inherit T0 private reasoning, another worker chat context, or hidden decisions.",
                "Return progress only through TASKBOARD filenames, history, dev-log, HANDOFF, and required heartbeat commands.",
                "",
                "--- embedded target ---",
                session["target"],
            ]
        )
        prompts.append(
            {
                "role": role,
                "title": session["title"],
                "dispatch_order": index,
                "prompt": prompt,
            }
        )
    return prompts


def dispatch(
    root: Path,
    goal_arg: Optional[str],
    mode: str,
    launcher: str = "none",
    agent_template: Optional[str] = None,
    target_dir: Optional[Path] = None,
) -> dict[str, object]:
    goal = read_goal(root, goal_arg)

    if not goal:
        reason = "missing-user-goal"
        return {
            "state": "needs-goal",
            "mode": mode,
            "backend": build_backend(mode),
            "next_role": "T0",
            "role_label": ROLE_LABELS["T0"],
            "status": "needs-goal",
            "task": "none",
            "reason": reason,
            "command": "/taskboard-dev T0",
            "target": build_target("T0", "needs-goal", "none", goal, reason),
            "boundary": T0_BOUNDARY,
            "goal_intake": build_goal_intake(goal, reason),
            "managed_sessions": [],
            "subagent_prompts": [],
            "launch_commands": [],
            "session_manifest": build_session_manifest(
                "needs-goal", "T0", "needs-goal", "none", reason, []
            ),
        }

    role, status, task, reason = select_task("T0", root)
    task_name = task.path.name if task is not None else "none"
    completion_audit = None

    if role == "T0" and status == "complete" and goal_arg and reason != "goal-complete-sentinel":
        role = "T1"
        status = "T1-create-or-revise"
        task_name = "none"
        reason = "explicit-goal-no-active-tasks"

    if role == "T0" and status == "complete":
        completion_audit = report_completion(root)
        if not completion_audit.get("completion_ready"):
            role = "T1"
            status = "T1-create-or-revise"
            task_name = "none"
            reason = "completion-audit-missing-evidence"

    if role == "T0" and status == "complete":
        state = "complete"
        command = "/taskboard-dev T0"
        target = f"用户目标：{goal}\n所有活跃 TASKBOARD 队列为空。请汇总完成情况并确认目标是否满足。"
        sessions = []
    else:
        state = "dispatch"
        sessions = build_sessions(goal, role, status, task_name, reason, target_dir)
        target = next(session["target"] for session in sessions if session["role"] == role)
    session_manifest = build_session_manifest(state, role, status, task_name, reason, sessions)
    recovery_order = list(session_manifest.get("recovery_order", []))
    if mode == "subagent" and state == "dispatch":
        command = "dispatch isolated subagents: /taskboard-dev T1, /taskboard-dev T2, /taskboard-dev T3"
        launch_commands = []
        subagent_prompts = build_subagent_prompts(sessions, recovery_order)
    elif state == "dispatch":
        command = f"start managed terminals: /taskboard-dev T1, /taskboard-dev T2, /taskboard-dev T3"
        launch_commands = build_launch_commands(root, sessions, launcher, agent_template)
        subagent_prompts = []
    else:
        launch_commands = []
        subagent_prompts = []

    return {
        "state": state,
        "mode": mode,
        "backend": build_backend(mode),
        "launcher": launcher,
        "next_role": role,
        "role_label": ROLE_LABELS[role],
        "status": status,
        "task": task_name,
        "reason": reason,
        "command": command,
        "target": target,
        "boundary": T0_BOUNDARY,
        "goal_intake": build_goal_intake(goal, reason),
        "managed_sessions": sessions,
        "subagent_prompts": subagent_prompts,
        "launch_commands": launch_commands,
        "session_manifest": session_manifest,
        "completion_audit": completion_audit,
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
    goal_intake = payload.get("goal_intake")
    if goal_intake:
        lines.append("goal_intake:")
        lines.append(json.dumps(goal_intake, ensure_ascii=False, sort_keys=True))
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
    subagent_prompts = payload.get("subagent_prompts", [])
    if subagent_prompts:
        lines.append("subagent_prompts:")
        for item in subagent_prompts:
            if isinstance(item, dict):
                lines.append(f"- role={item.get('role')} dispatch_order={item.get('dispatch_order')}")
    target_files = payload.get("target_files", [])
    if target_files:
        lines.append("target_files:")
        for item in target_files:
            if isinstance(item, dict):
                lines.append(f"- {item.get('role')} path={item.get('path')}")
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
        help=(
            "Command template used inside each launched role terminal. Supports "
            "{role}, {title}, {command}, {target}, and {target_file}."
        ),
    )
    parser.add_argument(
        "--target-dir",
        help="Directory for generated per-role target files referenced by {target_file}. Defaults to .taskboard/targets.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    target_dir = Path(args.target_dir).resolve() if args.target_dir else default_target_dir(root)
    write_runtime_goal(root, args.goal)

    try:
        payload = dispatch(root, args.goal, args.mode, args.launcher, args.agent_template, target_dir)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    managed_sessions = payload.get("managed_sessions", [])
    payload["target_files"] = (
        write_role_target_files(managed_sessions)
        if args.mode == "terminal"
        and launcher_needs_target_files(args.launcher, args.agent_template)
        and isinstance(managed_sessions, list)
        else []
    )
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
