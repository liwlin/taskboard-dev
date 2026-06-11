#!/usr/bin/env python3
"""Smoke-test that T0 startup does not create worker-owned artifacts."""

from argparse import ArgumentParser
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
from typing import Optional


GOAL = "Ship a demo feature without T0 writing worker artifacts."
ALLOWED_CREATED_FILES = {
    ".taskboard/t0/events.jsonl",
    ".taskboard/t0/goal.json",
    ".taskboard/t0/latest.json",
    ".taskboard/targets/taskboard-T1.md",
    ".taskboard/targets/taskboard-T2.md",
    ".taskboard/targets/taskboard-T3.md",
}
FORBIDDEN_WORKER_FILES = {
    "docs/HANDOFF.md",
    "docs/MAP.md",
    "docs/PROJECT.md",
    "docs/REQUIREMENTS.md",
    "docs/STATE.md",
    "docs/dev-log.md",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def relative_files(root: Path) -> set[str]:
    files: set[str] = set()
    for path in root.rglob("*"):
        if path.is_file():
            files.add(path.relative_to(root).as_posix())
    return files


def prepare_root(root: Path, force: bool) -> None:
    if root.exists() and any(root.iterdir()):
        if not force:
            raise RuntimeError(f"{root} is not empty; pass --force or choose an empty root")
        shutil.rmtree(root)
    (root / "docs" / "taskboard").mkdir(parents=True, exist_ok=True)


def run_start(root: Path, goal: str) -> tuple[list[dict[str, object]], str]:
    command = [
        sys.executable,
        str(repo_root() / "scripts" / "taskboard_start.py"),
        "--root",
        str(root),
        "--goal",
        goal,
        "--dry-run",
        "--iterations",
        "1",
        "--format",
        "json",
    ]
    result = subprocess.run(
        command,
        cwd=repo_root(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"taskboard_start.py failed with {result.returncode}:\n{result.stdout}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"taskboard_start.py did not emit JSON: {exc}\n{result.stdout}") from exc
    if not isinstance(payload, list):
        raise RuntimeError("taskboard_start.py JSON payload must be a list")
    return payload, " ".join(command)


def run_smoke(root: Path, goal: str, force: bool) -> dict[str, object]:
    root = root.resolve()
    prepare_root(root, force)
    before = relative_files(root)
    payload, command = run_start(root, goal)
    after = relative_files(root)

    created = sorted(after - before)
    unexpected = [path for path in created if path not in ALLOWED_CREATED_FILES]
    forbidden_existing = sorted(path for path in FORBIDDEN_WORKER_FILES if (root / path).exists())
    task_files = sorted(path for path in created if path.startswith("docs/taskboard/TASK-"))
    archive_files = sorted(path for path in created if path.startswith("docs/taskboard/archive/"))
    git_files = sorted(path for path in created if path.startswith(".git/"))

    failures = []
    if unexpected:
        failures.append(f"unexpected created file(s): {', '.join(unexpected)}")
    if forbidden_existing:
        failures.append(f"worker-owned context file(s) created: {', '.join(forbidden_existing)}")
    if task_files:
        failures.append(f"T0 created TASK file(s): {', '.join(task_files)}")
    if archive_files:
        failures.append(f"T0 created archive file(s): {', '.join(archive_files)}")
    if git_files:
        failures.append(f"T0 created git file(s): {', '.join(git_files)}")

    first = payload[0] if payload else {}
    if not isinstance(first, dict):
        failures.append("first T0 payload is not an object")
        first = {}
    if first.get("starter_mode") != "dry-check":
        failures.append(f"expected starter_mode=dry-check, got {first.get('starter_mode')}")
    if first.get("executed_commands") != []:
        failures.append("dry-run T0 startup executed worker launcher commands")

    return {
        "kind": "taskboard-t0-boundary-smoke",
        "state": "passed" if not failures else "failed",
        "root": str(root),
        "goal": goal,
        "command": command,
        "allowed_created_files": sorted(ALLOWED_CREATED_FILES),
        "created_files": created,
        "failure_count": len(failures),
        "failures": failures,
        "evidence": [
            "T0 dry-run created only T0 control-plane and target files",
            "T0 did not create PROJECT/MAP/REQUIREMENTS/STATE/dev-log/HANDOFF",
            "T0 did not create TASK, archive, source, or git files",
            "T0 did not execute worker launcher commands",
        ],
    }


def format_text(payload: dict[str, object]) -> str:
    lines = [
        f"state={payload['state']}",
        f"root={payload['root']}",
        f"created_files={','.join(payload['created_files'])}",
        f"failure_count={payload['failure_count']}",
    ]
    for failure in payload["failures"]:
        lines.append(f"failure={failure}")
    return "\n".join(lines)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Smoke root. Defaults to a temporary directory.")
    parser.add_argument("--goal", default=GOAL)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing non-empty --root.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.root:
        payload = run_smoke(Path(args.root), args.goal, args.force)
    else:
        with tempfile.TemporaryDirectory(prefix="taskboard-t0-boundary-smoke-") as tmp:
            payload = run_smoke(Path(tmp), args.goal, force=True)
            payload["root"] = "<temporary root removed>"
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(payload))
    return 0 if payload["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
