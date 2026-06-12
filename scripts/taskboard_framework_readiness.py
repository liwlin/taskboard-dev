#!/usr/bin/env python3
"""Audit taskboard-dev readiness against the T0-managed automation goal."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys
from typing import Optional


BOUNDARY = (
    "T0 manager-only framework readiness audit: inspect repo evidence and remaining field gaps; "
    "do not execute T1/T2/T3 development, review, verification, or commit work."
)


def read_text(root: Path, relative: str) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def path_exists(root: Path, relative: str) -> bool:
    return (root / relative).exists()


def contains(root: Path, relative: str, needle: str) -> bool:
    return needle in read_text(root, relative)


def build_check(
    check_id: str,
    title: str,
    requirements: list[tuple[str, bool]],
    evidence: list[str],
    remediation: str,
) -> dict[str, object]:
    missing = [name for name, passed in requirements if not passed]
    return {
        "id": check_id,
        "title": title,
        "state": "passed" if not missing else "missing",
        "missing": missing,
        "evidence": evidence if not missing else [],
        "remediation": "" if not missing else remediation,
    }


def collect_readiness(root: Path) -> dict[str, object]:
    root = root.resolve()
    checks = [
        build_check(
            "one-command-t0-entry",
            "User gives one goal to T0 through one command",
            [
                ("taskboard_start.py exists", path_exists(root, "scripts/taskboard_start.py")),
                ("README documents taskboard_start.py --goal", contains(root, "README.md", "taskboard_start.py --goal")),
                ("starter tests cover auto mode", contains(root, "tests/test_taskboard_start.py", "test_starter_auto_mode_runs_until_completion_by_default")),
            ],
            ["taskboard_start.py --goal", "auto_mode", "starter_mode"],
            "Restore taskboard_start.py, auto-mode tests, and user docs for the one-command T0 entry.",
        ),
        build_check(
            "t0-manager-only-boundary",
            "T0 is a manager and does not perform worker tasks",
            [
                ("role-t0 manager boundary exists", contains(root, "references/role-t0.md", "T0 is manager")),
                ("boundary smoke exists", path_exists(root, "scripts/taskboard_t0_boundary_smoke.py")),
                ("boundary smoke test exists", contains(root, "tests/test_taskboard_t0_boundary_smoke.py", "test_smoke_fails_when_t0_creates_worker_owned_context")),
            ],
            ["T0 manager-only", "taskboard_t0_boundary_smoke.py"],
            "Restore role-t0 boundary text and the T0 boundary smoke tests.",
        ),
        build_check(
            "automatic-worker-management",
            "T0 manages T1/T2/T3 assignment, liveness, recovery, and progress",
            [
                ("loop supervisor exists", path_exists(root, "scripts/taskboard_loop.py")),
                ("session heartbeat exists", path_exists(root, "scripts/taskboard_sessions.py")),
                ("watchdog exists", path_exists(root, "scripts/taskboard_watchdog.py")),
                ("progress reports no user worker management", contains(root, "scripts/taskboard_progress.py", "No user action required")),
                ("assignment recovery tests exist", contains(root, "tests/test_taskboard_progress.py", "test_progress_surfaces_assignment_recovery_without_user_role_management")),
            ],
            ["taskboard_loop.py", "taskboard_sessions.py", "taskboard_watchdog.py", "No user action required"],
            "Restore T0 loop/session/watchdog/progress recovery behavior and tests.",
        ),
        build_check(
            "backend-selection-and-fallback",
            "T0 can choose terminal or native-subagent backend without user-managed workers",
            [
                ("launch probe exists", contains(root, "scripts/taskboard.py", "taskboard-launch-probe")),
                ("subagent fallback exists", path_exists(root, "scripts/taskboard_subagents.py")),
                ("subagent smoke exists", path_exists(root, "scripts/taskboard_subagent_smoke.py")),
                ("subagent acceptance exists", path_exists(root, "scripts/taskboard_subagent_acceptance.py")),
                ("backend docs exist", contains(root, "README.md", "launch_probe_recommended_backend")),
            ],
            ["taskboard-launch-probe", "taskboard_subagents.py", "taskboard_subagent_acceptance.py"],
            "Restore launch-probe and native-subagent fallback scripts, tests, and docs.",
        ),
        build_check(
            "cross-day-cold-resume",
            "Fresh next-day workers recover topic from board state",
            [
                ("cold smoke exists", path_exists(root, "scripts/taskboard_cold_resume_smoke.py")),
                ("progress readiness exists", contains(root, "scripts/taskboard_progress.py", "cold_resume_readiness")),
                ("field cold acceptance exists", path_exists(root, "scripts/taskboard_cold_resume_acceptance.py")),
                ("cold acceptance tests exist", contains(root, "tests/test_taskboard_cold_resume_acceptance.py", "test_acceptance_passes_with_real_t0_progress_and_cold_resume_evidence")),
                ("docs explain board-first resume", contains(root, "README.md", "Cross-day cold resume")),
            ],
            ["taskboard_cold_resume_smoke.py", "taskboard_cold_resume_acceptance.py", "cold_resume_readiness"],
            "Restore cold-resume smoke, progress readiness, field acceptance, and docs.",
        ),
        build_check(
            "field-acceptance-gates",
            "Real field claims are gated separately from smoke tests",
            [
                ("live milestone acceptance exists", path_exists(root, "scripts/taskboard_live_milestone_acceptance.py")),
                ("cold resume acceptance exists", path_exists(root, "scripts/taskboard_cold_resume_acceptance.py")),
                ("native subagent acceptance exists", path_exists(root, "scripts/taskboard_subagent_acceptance.py")),
                ("live acceptance rejects placeholders", contains(root, "tests/test_taskboard_live_milestone_acceptance.py", "test_acceptance_rejects_smoke_placeholders_and_checkout_conflict")),
            ],
            ["taskboard_live_milestone_acceptance.py", "taskboard_cold_resume_acceptance.py", "taskboard_subagent_acceptance.py"],
            "Restore real-evidence acceptance gates and placeholder rejection tests.",
        ),
        build_check(
            "release-and-installation-consistency",
            "Release package and installed skill stay consistent",
            [
                ("package includes cold acceptance", contains(root, "scripts/package.sh", "taskboard_cold_resume_acceptance.py")),
                ("sync script exists", path_exists(root, "scripts/sync-local-skill.ps1")),
                ("release consistency verifier exists", path_exists(root, "scripts/verify_release_consistency.py")),
                ("T0 contract verifier exists", path_exists(root, "scripts/verify_t0_contract.py")),
            ],
            ["package.sh", "sync-local-skill.ps1", "verify_release_consistency.py", "verify_t0_contract.py"],
            "Restore package manifest, sync script, and release/T0 contract verifiers.",
        ),
        {
            "id": "real-overnight-field-run",
            "title": "Actual overnight worker terminals are closed and reopened successfully",
            "state": "missing",
            "missing": ["real overnight field run"],
            "evidence": [],
            "remediation": (
                "Run a real project overnight test: start T0, let it assign a worker TASK, close/reopen "
                "worker terminals the next day, run taskboard_cold_resume_acceptance.py, then complete "
                "the milestone through taskboard_live_milestone_acceptance.py."
            ),
        },
    ]
    remaining_gaps = [
        str(missing)
        for check in checks
        if check.get("state") != "passed"
        for missing in check.get("missing", [])
    ]
    passed_count = sum(1 for check in checks if check.get("state") == "passed")
    return {
        "kind": "taskboard-framework-readiness",
        "state": "ready" if not remaining_gaps else "field-verification-required",
        "goal_complete": not remaining_gaps,
        "root": str(root),
        "passed_count": passed_count,
        "check_count": len(checks),
        "remaining_gaps": remaining_gaps,
        "checks": checks,
        "boundary": BOUNDARY,
    }


def format_text(payload: dict[str, object]) -> str:
    lines = [
        f"state={payload['state']}",
        f"goal_complete={payload['goal_complete']}",
        f"passed_count={payload['passed_count']}",
        f"check_count={payload['check_count']}",
        f"boundary={payload['boundary']}",
    ]
    for gap in payload["remaining_gaps"]:
        lines.append(f"gap={gap}")
    for check in payload["checks"]:
        lines.append(f"check={check['id']} state={check['state']}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root to audit")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    payload = collect_readiness(Path(args.root))
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
