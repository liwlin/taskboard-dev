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


if __name__ == "__main__":
    unittest.main()
