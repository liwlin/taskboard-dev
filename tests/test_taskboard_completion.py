from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_completion.py"


class TaskboardCompletionTest(unittest.TestCase):
    def run_completion(self, root: Path) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), "--format", "json"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return json.loads(result.stdout)

    def run_completion_markdown(self, root: Path) -> str:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), "--format", "markdown"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout

    def test_reports_completion_ready_only_with_archived_work_and_goal_sentinel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "docs" / "taskboard" / "archive"
            archive.mkdir(parents=True)
            (archive / "TASK-001.v1.done.md").write_text("# completed task\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text(
                "# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8"
            )
            (root / "docs" / "dev-log.md").write_text(
                "# Development Log\n\n- TASK-001 completed and verified by T2.\n",
                encoding="utf-8",
            )

            payload = self.run_completion(root)

        self.assertEqual(payload["kind"], "taskboard-t0-completion-audit")
        self.assertEqual(payload["state"], "complete-ready")
        self.assertTrue(payload["completion_ready"])
        self.assertEqual(payload["active_count"], 0)
        self.assertEqual(payload["archived_count"], 1)
        self.assertEqual(payload["missing_evidence"], [])
        self.assertIn("summarize completion", payload["user_action"])
        self.assertIn("must not execute T1/T2/T3 work", payload["boundary"])

    def test_reports_incomplete_when_active_task_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            (taskboard / "TASK-002.v1.T3-do.md").write_text(
                "# active task\n\n**Wave**: 1\n", encoding="utf-8"
            )
            (taskboard / "archive").mkdir()
            (taskboard / "archive" / "TASK-001.v1.done.md").write_text(
                "# completed task\n", encoding="utf-8"
            )
            (root / "docs" / "STATE.md").write_text(
                "# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8"
            )
            (root / "docs" / "dev-log.md").write_text(
                "# Development Log\n\n- TASK-001 completed.\n", encoding="utf-8"
            )

            payload = self.run_completion(root)

        self.assertEqual(payload["state"], "incomplete")
        self.assertFalse(payload["completion_ready"])
        self.assertEqual(payload["active_count"], 1)
        self.assertIn("active TASK files remain", payload["missing_evidence"])
        self.assertIn("wake taskboard-T3", payload["user_action"])

    def test_reports_missing_completion_evidence_for_empty_unsentinelled_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            (root / "docs" / "dev-log.md").write_text("# Development Log\n", encoding="utf-8")

            payload = self.run_completion(root)

        self.assertEqual(payload["state"], "incomplete")
        self.assertFalse(payload["completion_ready"])
        self.assertIn("no goal completion sentinel", payload["missing_evidence"])
        self.assertIn("no archived TASK evidence", payload["missing_evidence"])
        self.assertIn("dev-log has no completion entries", payload["missing_evidence"])
        self.assertIn("wake T1", payload["user_action"])

    def test_markdown_completion_report_summarizes_user_ready_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "docs" / "taskboard" / "archive"
            archive.mkdir(parents=True)
            (archive / "TASK-001.v1.done.md").write_text("# completed task\n", encoding="utf-8")
            (root / ".taskboard" / "t0").mkdir(parents=True)
            (root / ".taskboard" / "t0" / "goal.json").write_text(
                json.dumps({"goal": "Ship demo feature"}),
                encoding="utf-8",
            )
            (root / "docs" / "STATE.md").write_text(
                "# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8"
            )
            (root / "docs" / "dev-log.md").write_text(
                "# Development Log\n\n- TASK-001 completed and verified by T2.\n",
                encoding="utf-8",
            )

            report = self.run_completion_markdown(root)

        self.assertIn("# T0 Completion Report", report)
        self.assertIn("**Goal**: Ship demo feature", report)
        self.assertIn("**Outcome**: complete-ready", report)
        self.assertIn("## Completion Evidence", report)
        self.assertIn("- Archived task files: 1", report)
        self.assertIn("- `TASK-001.v1.done.md`", report)
        self.assertIn("## User Action", report)
        self.assertIn("T0 may summarize completion", report)
        self.assertIn("## Boundary", report)
        self.assertIn("must not execute T1/T2/T3 work", report)

    def test_markdown_completion_report_blocks_when_evidence_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            (root / "docs" / "dev-log.md").write_text("# Development Log\n", encoding="utf-8")

            report = self.run_completion_markdown(root)

        self.assertIn("**Outcome**: incomplete", report)
        self.assertIn("## Missing Evidence", report)
        self.assertIn("- no goal completion sentinel", report)
        self.assertIn("- no archived TASK evidence", report)
        self.assertIn("wake T1", report)


if __name__ == "__main__":
    unittest.main()
