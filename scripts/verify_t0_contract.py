#!/usr/bin/env python3
"""Verify the taskboard-dev T0 orchestration contract."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require_contains(path: str, needle: str) -> None:
    text = read_text(path)
    if needle not in text:
        raise AssertionError(f"{path} is missing required text: {needle}")


def require_not_contains(path: str, needle: str) -> None:
    text = read_text(path)
    if needle in text:
        raise AssertionError(f"{path} contains forbidden text: {needle}")


def verify_t0_contract() -> None:
    require_contains("SKILL.md", "/taskboard-dev T0    # User-facing Orchestrator")
    require_contains("SKILL.md", "## Role: T0 — User-Facing Orchestrator")
    require_contains("SKILL.md", "### T0 Operating Loop")
    require_contains("SKILL.md", "T0 is manager-only")
    require_contains("SKILL.md", "must not directly execute development tasks")
    require_contains("SKILL.md", "### T0 Terminal Launcher")
    require_contains("SKILL.md", "--launcher windows-terminal")
    require_contains("SKILL.md", "--agent-template")
    require_contains("SKILL.md", "session_manifest")
    require_contains("SKILL.md", "not a new shared state database")
    require_contains("SKILL.md", "auto-terminal mode")
    require_contains("SKILL.md", "separate terminal session and isolated agent context")
    require_contains("SKILL.md", "must not reuse one role's conversation context")
    require_contains("SKILL.md", "### Multi-Agent Synchronization")
    require_contains("SKILL.md", "Use blackboard synchronization, not chat-context synchronization")
    require_contains("SKILL.md", "### T0 Scheduling Logic")
    require_contains("SKILL.md", "T0 schedules by event priority, not by arbitrary rotation")
    require_contains("SKILL.md", "### Multi-Agent Patterns Adopted")
    require_contains("SKILL.md", "**Manager/Worker**")
    require_contains("SKILL.md", "**Blackboard**")
    require_contains("SKILL.md", "**Independent Critic**")
    require_contains("SKILL.md", "**Liveness / Heartbeat**")
    require_contains("SKILL.md", "**Stop-Gate Aggregation**")
    require_contains("SKILL.md", "### T0 Liveness / Heartbeat Rules")
    require_contains("SKILL.md", "**T0 MUST NOT**")
    require_contains("SKILL.md", "it does not add `T0-*` task statuses")
    require_contains("SKILL.md", "**T0 next** (priority order):")
    require_contains(
        "SKILL.md",
        "All tasks archived and goal satisfied → \"T0 complete\"",
    )
    require_not_contains("SKILL.md", "| `T0-")

    require_contains("USER-MANUAL.md", "# taskboard-dev v4.3 用户手册")
    require_contains("USER-MANUAL.md", "## 5. T0 编排器操作手册")
    require_contains("USER-MANUAL.md", "## Multi-agent 借鉴原则")
    require_contains("USER-MANUAL.md", "T0 是 manager，不是 worker")
    require_contains("USER-MANUAL.md", "T0 是管理员，不是开发执行者")
    require_contains("USER-MANUAL.md", "T0 不直接执行开发任务")
    require_contains("USER-MANUAL.md", "### T0 启动器脚本")
    require_contains("USER-MANUAL.md", "Windows Terminal")
    require_contains("USER-MANUAL.md", "tmux")
    require_contains("USER-MANUAL.md", "session_manifest")
    require_contains("USER-MANUAL.md", "不是新的共享状态数据库")
    require_contains("USER-MANUAL.md", "auto-terminal 模式")
    require_contains("USER-MANUAL.md", "角色之间不共享聊天上下文")
    require_contains("USER-MANUAL.md", "### 多 agent 信息同步机制")
    require_contains("USER-MANUAL.md", "blackboard synchronization")
    require_contains("USER-MANUAL.md", "不是聊天上下文同步")
    require_contains("USER-MANUAL.md", "T0 的调度逻辑是")
    require_contains("USER-MANUAL.md", "交付闭环优先")
    require_contains("USER-MANUAL.md", "修复优先于新执行")
    require_contains("USER-MANUAL.md", "### 与常见 multi-agent 调度方法对比")
    require_contains("USER-MANUAL.md", "中心调度器 / Manager-Worker")
    require_contains("USER-MANUAL.md", "Swarm / Peer-to-Peer")
    require_contains("USER-MANUAL.md", "### 是否适合用户程序开发")
    require_contains("USER-MANUAL.md", "推荐采用分层策略")
    require_contains("USER-MANUAL.md", "完整 T0 auto-terminal")
    require_contains("USER-MANUAL.md", "T0 不新增 `T0-*` 任务状态")
    require_contains("USER-MANUAL.md", "| T0 | `T1-待决策`")
    require_not_contains("USER-MANUAL.md", "| `T0-")

    require_contains("README.md", "当前版本：**v4.3**")
    require_contains("README.md", "T0 用户入口")
    require_contains("README.md", "执行：/taskboard-dev T0")
    require_contains("README.md", "用户默认只需要手动打开 1 个入口终端")
    require_contains("README.md", "自动创建或恢复 `taskboard-T1`")
    require_contains("README.md", "不需要手动开 4 个终端")
    require_contains("README.md", "T0 只做管理员和调度器")
    require_contains("README.md", "不直接执行开发任务")
    require_contains("README.md", "--launcher windows-terminal")
    require_contains("README.md", "python scripts/taskboard_t0.py --goal")
    require_contains("README.md", "python scripts/taskboard_demo.py --root .taskboard-demo --with-heartbeats")
    require_contains("README.md", "python scripts/taskboard_loop.py --root . --goal")
    require_contains("README.md", "--assignment-lease-seconds 300")
    require_contains("README.md", "**Goal Complete**: yes")
    require_contains("README.md", "--no-stop-on-complete")
    require_contains("README.md", "python scripts/taskboard_health.py --root . --stale-minutes 30")
    require_contains("README.md", "python scripts/taskboard_sessions.py --root . probe --stale-seconds 300")
    require_contains("README.md", "--assignment-id T2:TASK-003.v1.T2-review.md")
    require_contains("README.md", "python scripts/taskboard_next.py --role T0 --root .")

    require_contains("references/taskboard-template.md", "# TASKBOARD v4.3 Templates")
    require_contains("references/taskboard-template.md", "目标(T0):")
    require_contains("references/taskboard-template.md", "执行: /taskboard-dev T0")

    require_contains("scripts/package.sh", 'VERSION="${VERSION:-v4.3}"')
    require_contains("scripts/package.sh", 'cp "$ROOT_DIR/scripts/taskboard_start.py"')
    require_contains("scripts/package.sh", 'cp "$ROOT_DIR/scripts/taskboard_t0.py"')
    require_contains("scripts/package.sh", 'cp "$ROOT_DIR/scripts/taskboard_loop.py"')
    require_contains("scripts/package.sh", 'cp "$ROOT_DIR/scripts/taskboard_demo.py"')
    require_contains("scripts/package.sh", 'cp "$ROOT_DIR/scripts/taskboard_progress.py"')
    require_contains("scripts/taskboard_demo.py", "dry-run demo")
    require_contains("scripts/taskboard_demo.py", "--with-heartbeats")
    require_contains("scripts/taskboard_demo.py", "pass --force or choose an empty demo root")
    require_contains("scripts/taskboard_loop.py", "T0 supervisor-only")
    require_contains("scripts/taskboard_start.py", "DEFAULT_AGENT_TEMPLATE")
    require_contains("scripts/taskboard_start.py", 'default="windows-terminal"')
    require_contains("scripts/taskboard_start.py", "--execute-launches")
    require_contains("scripts/taskboard_start.py", "run_loop")
    require_contains("scripts/taskboard_t0.py", "runtime_goal_file")
    require_contains("scripts/taskboard_t0.py", "taskboard-t0-goal")
    require_contains("README.md", ".taskboard/t0/goal.json")
    require_contains("scripts/taskboard_loop.py", "build_assignment")
    require_contains("scripts/taskboard_progress.py", "taskboard-t0-progress")
    require_contains("scripts/taskboard_progress.py", "No user action required")
    require_contains("scripts/taskboard_progress.py", "T0 launch/recovery failed")
    require_contains("scripts/taskboard_progress.py", "do not perform design")
    require_contains("README.md", "T0 launch/recovery failed")
    require_contains("scripts/taskboard_loop.py", "pending-ack")
    require_contains("scripts/taskboard_loop.py", "lease-expired")
    require_contains("scripts/taskboard_loop.py", "--assignment-lease-seconds")
    require_contains("scripts/taskboard_loop.py", "--no-stop-on-complete")
    require_contains("scripts/taskboard_loop.py", "--state-file")
    require_contains("scripts/taskboard_loop.py", "--no-state-file")
    require_contains("scripts/taskboard_loop.py", "--target-dir")
    require_contains("scripts/taskboard_loop.py", "--no-target-files")
    require_contains("scripts/taskboard_loop.py", "taskboard-role-target")
    require_contains("scripts/taskboard_loop.py", ".taskboard")
    require_contains("scripts/taskboard_loop.py", "taskboard-t0-supervisor-state")
    require_contains("scripts/taskboard_loop.py", "stop_on_complete")
    require_contains("scripts/taskboard_next.py", "has_goal_complete_sentinel")
    require_contains("scripts/taskboard_next.py", "goal-complete-sentinel")
    require_contains("scripts/taskboard_loop.py", "--execute-launches")
    require_contains("scripts/taskboard_loop.py", "do not perform design")
    require_contains("scripts/taskboard_t0.py", 'default="terminal"')
    require_contains("scripts/taskboard_t0.py", "T0 manager-only")
    require_contains("scripts/taskboard_t0.py", "--launcher")
    require_contains("scripts/taskboard_t0.py", "{target_file}")
    require_contains("scripts/taskboard_t0.py", "default_target_dir")
    require_contains("scripts/taskboard_t0.py", "build_launch_commands")
    require_contains("scripts/taskboard_t0.py", "build_session_manifest")
    require_contains("scripts/taskboard_t0.py", 'f"taskboard-{role}"')
    require_contains("scripts/taskboard_t0.py", "taskboard_sessions.py --root . heartbeat --role {role}")
    require_contains("scripts/taskboard_t0.py", "--assignment-id {role}:{task_name}")
    require_contains("scripts/taskboard_t0.py", 'python scripts/taskboard_sessions.py --root . probe --stale-seconds 300 --goal "<user goal>"')
    require_contains("scripts/taskboard_t0.py", 'python scripts/taskboard_health.py --root . --stale-minutes 30 --goal "<user goal>"')
    require_contains("scripts/package.sh", 'cp "$ROOT_DIR/scripts/taskboard_health.py"')
    require_contains("scripts/package.sh", 'cp "$ROOT_DIR/scripts/taskboard_sessions.py"')
    require_contains("scripts/taskboard_health.py", "T0 manager-only")
    require_contains("scripts/taskboard_health.py", "--goal")
    require_contains("scripts/taskboard_health.py", "explicit-goal-no-active-tasks")
    require_contains("scripts/taskboard_health.py", "stalled_tasks")
    require_contains("scripts/taskboard_health.py", "do not execute the development task in T0")
    require_contains("scripts/taskboard_sessions.py", "heartbeat")
    require_contains("scripts/taskboard_sessions.py", "--assignment-id")
    require_contains("scripts/taskboard_sessions.py", "--target-dir")
    require_contains("scripts/taskboard_sessions.py", "{target_file}")
    require_contains("scripts/taskboard_sessions.py", "default_target_dir")
    require_contains("scripts/taskboard_sessions.py", "stale_roles")
    require_contains("scripts/taskboard_sessions.py", "do not execute development")
    require_contains("scripts/package.sh", 'cp "$ROOT_DIR/scripts/taskboard_next.py"')
    require_contains("scripts/taskboard_next.py", 'ROLE_PRIORITY = {')
    require_contains("scripts/taskboard_next.py", '"T0":')


def main() -> int:
    try:
        verify_t0_contract()
    except AssertionError as exc:
        print(f"T0 contract verification failed: {exc}", file=sys.stderr)
        return 1

    print("T0 contract verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
