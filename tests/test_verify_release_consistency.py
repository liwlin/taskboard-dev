from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_release_consistency.py"


def write_consistent_repo(root: Path, version: str = "v9.9") -> None:
    (root / "references").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\n"
        "name: taskboard-dev\n"
        "description: >\n"
        "  This skill should be used when starting a session.\n"
        "---\n"
        "\n"
        f"# TASKBOARD-Driven Development {version}\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        f"# taskboard-dev\n\n当前版本：**{version}**\n",
        encoding="utf-8",
    )
    (root / "USER-MANUAL.md").write_text(
        f"# taskboard-dev {version} 用户手册\n",
        encoding="utf-8",
    )
    (root / "references" / "taskboard-template.md").write_text(
        f"# TASKBOARD {version} Templates\n",
        encoding="utf-8",
    )
    (root / "scripts" / "demo_tool.py").write_text(
        "print('demo')\n",
        encoding="utf-8",
    )
    (root / "scripts" / "package.sh").write_text(
        "#!/usr/bin/env bash\n"
        f'VERSION="${{VERSION:-{version}}}"\n'
        'cp "$ROOT_DIR/SKILL.md" "$STAGE_DIR/SKILL.md"\n'
        'cp "$ROOT_DIR/USER-MANUAL.md" "$STAGE_DIR/USER-MANUAL.md"\n'
        'cp "$ROOT_DIR/README.md" "$STAGE_DIR/README.md"\n'
        'cp "$ROOT_DIR/references/taskboard-template.md" "$STAGE_DIR/references/taskboard-template.md"\n'
        'cp "$ROOT_DIR/scripts/package.sh" "$STAGE_DIR/scripts/package.sh"\n'
        'cp "$ROOT_DIR/scripts/demo_tool.py" "$STAGE_DIR/scripts/demo_tool.py"\n',
        encoding="utf-8",
    )


class VerifyReleaseConsistencyTest(unittest.TestCase):
    def run_check(self, root: Path) -> tuple[int, dict]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), "--format", "json"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        return result.returncode, json.loads(result.stdout)

    def test_consistent_repo_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_consistent_repo(root)
            returncode, payload = self.run_check(root)

        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["kind"], "taskboard-release-consistency")
        self.assertEqual(payload["version"], "v9.9")
        self.assertEqual(payload["mismatches"], [])

    def test_readme_version_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_consistent_repo(root)
            (root / "README.md").write_text(
                "# taskboard-dev\n\n当前版本：**v0.1**\n",
                encoding="utf-8",
            )
            returncode, payload = self.run_check(root)

        self.assertEqual(returncode, 1)
        self.assertTrue(any("README.md" in item for item in payload["mismatches"]), payload)

    def test_skill_title_version_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_consistent_repo(root)
            skill = root / "SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8").replace(
                    "# TASKBOARD-Driven Development v9.9",
                    "# TASKBOARD-Driven Development v0.1",
                ),
                encoding="utf-8",
            )
            returncode, payload = self.run_check(root)

        self.assertEqual(returncode, 1)
        self.assertTrue(any("SKILL.md" in item for item in payload["mismatches"]), payload)

    def test_missing_frontmatter_description_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_consistent_repo(root)
            (root / "SKILL.md").write_text(
                "---\nname: taskboard-dev\n---\n\n# TASKBOARD-Driven Development v9.9\n",
                encoding="utf-8",
            )
            returncode, payload = self.run_check(root)

        self.assertEqual(returncode, 1)
        self.assertTrue(any("description" in item for item in payload["mismatches"]), payload)

    def test_unstaged_script_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_consistent_repo(root)
            (root / "scripts" / "new_tool.py").write_text("print('new')\n", encoding="utf-8")
            returncode, payload = self.run_check(root)

        self.assertEqual(returncode, 1)
        self.assertTrue(any("new_tool.py" in item for item in payload["mismatches"]), payload)

    def test_unstaged_reference_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_consistent_repo(root)
            (root / "references" / "role-t9.md").write_text("# role\n", encoding="utf-8")
            returncode, payload = self.run_check(root)

        self.assertEqual(returncode, 1)
        self.assertTrue(any("role-t9.md" in item for item in payload["mismatches"]), payload)

    def test_staged_file_missing_from_repo_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_consistent_repo(root)
            (root / "scripts" / "demo_tool.py").unlink()
            returncode, payload = self.run_check(root)

        self.assertEqual(returncode, 1)
        self.assertTrue(any("demo_tool.py" in item for item in payload["mismatches"]), payload)

    def test_real_repo_is_consistent(self):
        returncode, payload = self.run_check(ROOT)
        self.assertEqual(returncode, 0, payload.get("mismatches"))
        self.assertEqual(payload["version"], "v4.5.26")


if __name__ == "__main__":
    unittest.main()
