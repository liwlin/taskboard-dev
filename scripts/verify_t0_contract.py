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
    require_contains("USER-MANUAL.md", "T0 不新增 `T0-*` 任务状态")
    require_contains("USER-MANUAL.md", "| T0 | `T1-待决策`")
    require_not_contains("USER-MANUAL.md", "| `T0-")

    require_contains("README.md", "当前版本：**v4.3**")
    require_contains("README.md", "T0 用户入口")
    require_contains("README.md", "执行：/taskboard-dev T0")

    require_contains("references/taskboard-template.md", "# TASKBOARD v4.3 Templates")
    require_contains("references/taskboard-template.md", "目标(T0):")
    require_contains("references/taskboard-template.md", "执行: /taskboard-dev T0")

    require_contains("scripts/package.sh", 'VERSION="${VERSION:-v4.3}"')


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
