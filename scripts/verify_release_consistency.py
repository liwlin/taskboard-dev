#!/usr/bin/env python3
"""Verify version and package-manifest consistency across release files.

Prevents releases where the repo says one version while SKILL.md, README,
USER-MANUAL, the template, or the package manifest say another, and catches
scripts or reference files that exist in the repo but were never added to
scripts/package.sh.
"""

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import argparse
import json
import re


CP_LINE = re.compile(r'cp "\$ROOT_DIR/([^"]+)"')
VERSION_DEFAULT = re.compile(r'VERSION="\$\{VERSION:-(v[0-9][0-9.]*)\}"')
PACKAGED_SCRIPT_SUFFIXES = (".py", ".sh", ".ps1")


def read_text(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def parse_package_version(package_text: str) -> Optional[str]:
    match = VERSION_DEFAULT.search(package_text)
    return match.group(1) if match else None


def parse_manifest(package_text: str) -> Set[str]:
    return set(CP_LINE.findall(package_text))


def parse_frontmatter(skill_text: str) -> Dict[str, str]:
    lines = skill_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: Dict[str, str] = {}
    current_key = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key_match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$", line)
        if key_match:
            current_key = key_match.group(1)
            value = key_match.group(2).strip()
            fields[current_key] = "" if value in (">", "|") else value
        elif current_key and line.startswith(" "):
            fields[current_key] = (fields[current_key] + " " + line.strip()).strip()
    return fields


def collect_mismatches(root: Path) -> Tuple[str, List[str]]:
    mismatches: List[str] = []

    try:
        package_text = read_text(root, "scripts/package.sh")
    except FileNotFoundError:
        return "unknown", ["scripts/package.sh: file not found"]

    version = parse_package_version(package_text)
    if version is None:
        return "unknown", ["scripts/package.sh: VERSION default not found"]

    version_checks = [
        ("SKILL.md", f"# TASKBOARD-Driven Development {version}"),
        ("README.md", f"当前版本：**{version}**"),
        ("USER-MANUAL.md", f"# taskboard-dev {version} 用户手册"),
        ("references/taskboard-template.md", f"# TASKBOARD {version} Templates"),
    ]
    for relative, needle in version_checks:
        try:
            text = read_text(root, relative)
        except FileNotFoundError:
            mismatches.append(f"{relative}: file not found")
            continue
        if needle not in text:
            mismatches.append(f"{relative}: expected '{needle}' for version {version}")

    try:
        frontmatter = parse_frontmatter(read_text(root, "SKILL.md"))
        if frontmatter.get("name") != "taskboard-dev":
            mismatches.append("SKILL.md: frontmatter name must be 'taskboard-dev'")
        if not frontmatter.get("description"):
            mismatches.append("SKILL.md: frontmatter description is missing or empty")
    except FileNotFoundError:
        pass

    manifest = parse_manifest(package_text)

    for staged in sorted(manifest):
        if not (root / staged).is_file():
            mismatches.append(f"scripts/package.sh: staged file missing from repo: {staged}")

    for required in ("SKILL.md", "USER-MANUAL.md", "README.md"):
        if required not in manifest:
            mismatches.append(f"scripts/package.sh: {required} is not staged")

    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        for path in sorted(scripts_dir.iterdir()):
            if not path.is_file() or path.suffix not in PACKAGED_SCRIPT_SUFFIXES:
                continue
            relative = f"scripts/{path.name}"
            if relative not in manifest:
                mismatches.append(f"scripts/package.sh: {relative} exists but is not staged")

    references_dir = root / "references"
    if references_dir.is_dir():
        for path in sorted(references_dir.glob("*.md")):
            relative = f"references/{path.name}"
            if relative not in manifest:
                mismatches.append(f"scripts/package.sh: {relative} exists but is not staged")

    return version, mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repo root to check")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    version, mismatches = collect_mismatches(root)

    payload = {
        "kind": "taskboard-release-consistency",
        "version": version,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if mismatches:
            print(f"Release consistency check failed for {version}:")
            for item in mismatches:
                print(f"  - {item}")
        else:
            print(f"Release consistency check passed for {version}")

    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
