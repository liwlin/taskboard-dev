from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_stopgates.py"


class TaskboardStopGatesTest(unittest.TestCase):
    def run_stopgates(self, root: Path) -> dict:
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

    def test_reports_t1_decision_task_as_user_facing_stop_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = "TASK-009.v2.T1-decision.md"
            (taskboard / task_name).write_text(
                """# Decide release behavior

**Wave**: 2
**Gate**: Product decision
**Question**: Should the beta banner be visible to all users?
**Options**:
- A: Show to everyone
- B: Show only to admins
**Recommended**: B
""",
                encoding="utf-8",
            )

            payload = self.run_stopgates(root)

        self.assertEqual(payload["kind"], "taskboard-t0-stop-gates")
        self.assertEqual(payload["stop_gate_count"], 1)
        self.assertEqual(payload["stop_gates"][0]["task"], task_name)
        self.assertEqual(payload["stop_gates"][0]["gate"], "Product decision")
        self.assertIn("beta banner", payload["stop_gates"][0]["question"])
        self.assertEqual(payload["stop_gates"][0]["options"], ["A: Show to everyone", "B: Show only to admins"])
        self.assertEqual(payload["stop_gates"][0]["recommended"], "B")
        self.assertIn("T0 aggregates stop gates", payload["boundary"])


if __name__ == "__main__":
    unittest.main()
