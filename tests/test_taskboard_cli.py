from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard.py"


class TaskboardCliTest(unittest.TestCase):
    def run_cli(self, root: Path, *args: str, ok: bool = True) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), "--format", "json", *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result.returncode, result.stdout

    def write_task(self, root: Path, name: str, text: str = "# task\n\n**Wave**: 1\n") -> Path:
        taskboard = root / "docs" / "taskboard"
        taskboard.mkdir(parents=True, exist_ok=True)
        path = taskboard / name
        path.write_text(text, encoding="utf-8")
        return path

    def write_subagent_packet(self, root: Path) -> Path:
        t0_dir = root / ".taskboard" / "t0"
        t0_dir.mkdir(parents=True, exist_ok=True)
        packet = {
            "kind": "taskboard-subagent-fallback-packet",
            "version": 1,
            "subagent_prompt_count": 3,
            "subagent_prompt_roles": ["T1", "T2", "T3"],
            "subagent_fallback": {
                "kind": "taskboard-subagent-fallback",
                "reason": "agent-preflight-spawn-refused",
                "subagent_prompts": [
                    {"role": "T1", "prompt": "T1 prompt: read SKILL.md and references/role-t1.md"},
                    {"role": "T2", "prompt": "T2 prompt: read SKILL.md and references/role-t2.md"},
                    {"role": "T3", "prompt": "T3 prompt: read SKILL.md and references/role-t3.md"},
                ],
            },
        }
        path = t0_dir / "subagent-fallback.json"
        path.write_text(json.dumps(packet), encoding="utf-8")
        return path

    def test_next_selects_t0_priority_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_task(root, "TASK-002.v1.T3-待执行.md")
            self.write_task(root, "TASK-001.v1.T2-待审核代码-L2.md")

            _, stdout = self.run_cli(root, "next", "T0")
            payload = json.loads(stdout)

        self.assertEqual(payload["kind"], "taskboard-next")
        self.assertEqual(payload["role"], "T2")
        self.assertEqual(payload["status"], "T2-待审核代码")
        self.assertEqual(payload["task"], "TASK-001.v1.T2-待审核代码-L2.md")

    def test_status_combines_queue_stop_gate_completion_and_next(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_task(root, "TASK-001.v1.T1-待决策.md", "# Decide\n\n**Wave**: 1\n**Gate**: Product\n**Question**: Continue?\n")

            _, stdout = self.run_cli(root, "status")
            payload = json.loads(stdout)

        self.assertEqual(payload["kind"], "taskboard-status")
        self.assertEqual(payload["next"]["role"], "T1")
        self.assertEqual(payload["queue_health"]["active_count"], 1)
        self.assertEqual(payload["stop_gates"]["stop_gate_count"], 1)
        self.assertIn("completion_ready", payload["completion"])

    def test_alive_touches_role_mtime_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            _, stdout = self.run_cli(root, "alive", "T2")
            first = json.loads(stdout)
            alive_path = Path(first["path"])
            first_mtime = alive_path.stat().st_mtime
            time.sleep(0.01)
            _, stdout = self.run_cli(root, "alive", "T2")
            second_mtime = alive_path.stat().st_mtime

        self.assertEqual(first["kind"], "taskboard-alive")
        self.assertEqual(first["role"], "T2")
        self.assertGreater(second_mtime, first_mtime)
        self.assertIn(".taskboard", first["path"])

    def test_stall_reports_old_task_without_writing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self.write_task(root, "TASK-001.v1.T3-待执行.md")
            old_time = time.time() - 3600
            os.utime(task, (old_time, old_time))

            _, stdout = self.run_cli(root, "stall", "--minutes", "30")
            payload = json.loads(stdout)

        self.assertEqual(payload["kind"], "taskboard-stall")
        self.assertEqual(payload["stalled_count"], 1)
        self.assertEqual(payload["stalled_tasks"][0]["task"], "TASK-001.v1.T3-待执行.md")
        self.assertFalse((root / ".taskboard" / "t0" / "latest.json").exists())

    def test_decide_wraps_stop_gate_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = "TASK-001.v1.T1-待决策.md"
            self.write_task(root, original, "# Decide\n\n**Wave**: 1\n**Gate**: Product\n**Question**: Continue?\n")

            _, stdout = self.run_cli(root, "decide", original, "--answer", "Use option A")
            payload = json.loads(stdout)
            resumed = root / "docs" / "taskboard" / "TASK-001.v1.T1-方案需修改.md"
            resumed_exists = resumed.exists()
            resumed_text = resumed.read_text(encoding="utf-8") if resumed_exists else ""

        self.assertEqual(payload["kind"], "taskboard-t0-decision")
        self.assertTrue(resumed_exists)
        self.assertIn("Use option A", resumed_text)

    def test_move_validates_renames_appends_history_and_touches_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self.write_task(root, "TASK-001.v1.T3-待执行.md")
            old_time = time.time() - 3600
            os.utime(task, (old_time, old_time))

            _, stdout = self.run_cli(root, "move", task.name, "T3-待验证", "--note", "verified locally")
            payload = json.loads(stdout)
            moved = root / "docs" / "taskboard" / "TASK-001.v1.T3-待验证.md"
            history = root / "docs" / "taskboard" / "history" / "TASK-001.history.md"
            moved_exists = moved.exists()
            moved_mtime = moved.stat().st_mtime if moved_exists else 0
            history_text = history.read_text(encoding="utf-8") if history.exists() else ""

        self.assertEqual(payload["kind"], "taskboard-move")
        self.assertEqual(payload["from"], "TASK-001.v1.T3-待执行.md")
        self.assertEqual(payload["to"], "TASK-001.v1.T3-待验证.md")
        self.assertTrue(moved_exists)
        self.assertGreater(moved_mtime, old_time)
        self.assertIn("verified locally", history_text)

    def test_move_rejects_fabricated_status_without_renaming(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self.write_task(root, "TASK-001.v1.T3-待执行.md")

            _, stdout = self.run_cli(root, "move", task.name, "T3-待合并-L2", ok=False)
            original_exists = task.exists()
            fabricated_exists = (root / "docs" / "taskboard" / "TASK-001.v1.T3-待合并-L2.md").exists()

        self.assertIn("invalid status", stdout)
        self.assertTrue(original_exists)
        self.assertFalse(fabricated_exists)

    def test_subagent_status_next_and_ack_track_native_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet = self.write_subagent_packet(root)

            _, stdout = self.run_cli(root, "subagent", "status")
            initial = json.loads(stdout)
            _, stdout = self.run_cli(root, "subagent", "next")
            next_item = json.loads(stdout)
            _, stdout = self.run_cli(
                root,
                "subagent",
                "ack",
                "--role",
                "T1",
                "--agent-id",
                "019eb5de-749f-79c2-a355-7fb95d946c99",
                "--note",
                "spawned by T0 native subagent tool",
            )
            ack = json.loads(stdout)
            _, stdout = self.run_cli(root, "subagent", "status")
            after_ack = json.loads(stdout)
            _, stdout = self.run_cli(root, "subagent", "next")
            next_after_ack = json.loads(stdout)
            state_file = root / ".taskboard" / "t0" / "subagents.json"
            state = json.loads(state_file.read_text(encoding="utf-8"))

        self.assertEqual(initial["kind"], "taskboard-subagent-dispatch")
        self.assertTrue(initial["packet_available"])
        self.assertEqual(initial["packet_file"], str(packet))
        self.assertEqual(initial["prompt_roles"], ["T1", "T2", "T3"])
        self.assertEqual(initial["pending_roles"], ["T1", "T2", "T3"])
        self.assertEqual(initial["dispatched_roles"], [])
        self.assertEqual(next_item["kind"], "taskboard-subagent-next")
        self.assertEqual(next_item["role"], "T1")
        self.assertIn("references/role-t1.md", next_item["prompt"])
        self.assertEqual(ack["kind"], "taskboard-subagent-ack")
        self.assertEqual(ack["record"]["role"], "T1")
        self.assertEqual(ack["record"]["agent_id"], "019eb5de-749f-79c2-a355-7fb95d946c99")
        self.assertEqual(after_ack["pending_roles"], ["T2", "T3"])
        self.assertEqual(after_ack["dispatched_roles"], ["T1"])
        self.assertEqual(next_after_ack["role"], "T2")
        self.assertEqual(state["kind"], "taskboard-subagent-dispatch-state")
        self.assertIn("T1", state["roles"])
        self.assertIn("T0 records native subagent dispatch", state["boundary"])

    def test_subagent_done_and_fail_record_worker_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_subagent_packet(root)
            self.run_cli(root, "subagent", "ack", "--role", "T1", "--agent-id", "agent-t1")
            self.run_cli(root, "subagent", "ack", "--role", "T2", "--agent-id", "agent-t2")

            _, stdout = self.run_cli(
                root,
                "subagent",
                "done",
                "--role",
                "T1",
                "--summary",
                "T1 created TASK files",
            )
            done = json.loads(stdout)
            _, stdout = self.run_cli(
                root,
                "subagent",
                "fail",
                "--role",
                "T2",
                "--summary",
                "review tool unavailable",
            )
            failed = json.loads(stdout)
            _, stdout = self.run_cli(root, "subagent", "status")
            status = json.loads(stdout)

        self.assertEqual(done["kind"], "taskboard-subagent-result")
        self.assertEqual(done["record"]["status"], "completed")
        self.assertEqual(done["record"]["summary"], "T1 created TASK files")
        self.assertEqual(failed["record"]["status"], "failed")
        self.assertEqual(failed["record"]["summary"], "review tool unavailable")
        self.assertEqual(status["completed_roles"], ["T1"])
        self.assertEqual(status["failed_roles"], ["T2"])
        self.assertEqual(status["active_roles"], [])
        self.assertEqual(status["pending_roles"], ["T3"])
        self.assertIn("completed_at", status["records"]["T1"])
        self.assertIn("failed_at", status["records"]["T2"])

    def test_subagent_retry_returns_failed_role_to_pending_without_losing_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_subagent_packet(root)
            self.run_cli(root, "subagent", "ack", "--role", "T1", "--agent-id", "agent-t1")
            self.run_cli(root, "subagent", "done", "--role", "T1", "--summary", "T1 done")
            self.run_cli(root, "subagent", "ack", "--role", "T2", "--agent-id", "agent-t2")
            self.run_cli(root, "subagent", "fail", "--role", "T2", "--summary", "review timeout")

            _, stdout = self.run_cli(root, "subagent", "retry", "--role", "T2", "--note", "retry with smaller scope")
            retry = json.loads(stdout)
            _, stdout = self.run_cli(root, "subagent", "status")
            status = json.loads(stdout)
            _, stdout = self.run_cli(root, "subagent", "next")
            next_item = json.loads(stdout)
            t2_record = status["records"]["T2"]

        self.assertEqual(retry["kind"], "taskboard-subagent-retry")
        self.assertEqual(retry["record"]["status"], "retry-pending")
        self.assertEqual(status["completed_roles"], ["T1"])
        self.assertEqual(status["failed_roles"], [])
        self.assertEqual(status["pending_roles"], ["T2", "T3"])
        self.assertEqual(next_item["role"], "T2")
        self.assertEqual(len(t2_record["attempts"]), 1)
        self.assertEqual(t2_record["attempts"][0]["status"], "failed")
        self.assertEqual(t2_record["attempts"][0]["summary"], "review timeout")
        self.assertEqual(t2_record["retry_note"], "retry with smaller scope")


if __name__ == "__main__":
    unittest.main()
