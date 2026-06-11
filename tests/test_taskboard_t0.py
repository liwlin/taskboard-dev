from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_t0.py"


class TaskboardT0Test(unittest.TestCase):
    def run_t0(self, root: Path, *args: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), "--format", "json", *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return json.loads(result.stdout)

    def run_t0_text(self, root: Path, *args: str) -> str:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout

    def write_task(self, taskboard: Path, name: str) -> None:
        (taskboard / name).write_text("# task\n\n**Wave**: 1\n", encoding="utf-8")

    def test_dispatches_highest_priority_active_task_with_role_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            self.write_task(taskboard, "TASK-003.v1.T3-待执行.md")
            self.write_task(taskboard, "TASK-001.v1.T2-待审核代码-L2.md")

            output = self.run_t0(root, "--goal", "完成登录功能")

        self.assertEqual(output["state"], "dispatch")
        self.assertEqual(output["mode"], "terminal")
        self.assertEqual(output["next_role"], "T2")
        self.assertEqual(output["command"], "start managed terminals: /taskboard-dev T1, /taskboard-dev T2, /taskboard-dev T3")
        self.assertEqual(output["task"], "TASK-001.v1.T2-待审核代码-L2.md")
        self.assertIn("完成登录功能", output["target"])
        self.assertIn("T2", output["target"])
        self.assertIn("taskboard.py --root . alive T2", output["target"])
        self.assertIn("--task TASK-001.v1.", output["target"])
        self.assertIn("--assignment-id T2:TASK-001.v1.", output["target"])
        self.assertIn("Role runtime contract", output["target"])
        self.assertIn("assigned_role: T2", output["target"])
        self.assertIn("managed_by: T0", output["target"])
        self.assertIn("do not execute T0/T1/T3 responsibilities", output["target"])
        self.assertIn("do not rely on another role's chat context", output["target"])
        self.assertIn("Worker loop contract", output["target"])
        self.assertIn("Continue cycling this role while unblocked T2 work is available", output["target"])
        self.assertIn("Do not terminate just because this role queue is empty", output["target"])
        self.assertIn("refresh your heartbeat at the start of each cycle", output["target"])
        self.assertIn("T0 manager-only", output["boundary"])
        self.assertIn("不直接执行开发任务", output["boundary"])
        self.assertEqual(
            [session["role"] for session in output["managed_sessions"]],
            ["T1", "T2", "T3"],
        )
        self.assertEqual(
            [session["title"] for session in output["managed_sessions"]],
            ["taskboard-T1", "taskboard-T2", "taskboard-T3"],
        )
        manifest = output["session_manifest"]
        self.assertEqual(manifest["managed_by"], "T0")
        self.assertEqual(manifest["next_role"], "T2")
        self.assertEqual(manifest["roles"], ["T1", "T2", "T3"])
        self.assertEqual(manifest["recovery_order"][0], "T2")
        self.assertIn("TASKBOARD filenames", manifest["sync_contract"])
        self.assertIn("taskboard_next.py --role T0", " ".join(manifest["health_checks"]))

    def test_goal_without_active_tasks_dispatches_t1_to_create_board_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_t0(root, "--goal", "完成支付模块")

        self.assertEqual(output["state"], "dispatch")
        self.assertEqual(output["next_role"], "T1")
        self.assertEqual(output["status"], "T1-create-or-revise")
        self.assertEqual(len(output["managed_sessions"]), 3)
        self.assertEqual(output["managed_sessions"][0]["command"], "/taskboard-dev T1")
        self.assertIn("taskboard.py --root . alive T1", output["target"])
        self.assertIn("taskboard_sessions.py --root . heartbeat --role T1", output["target"])
        self.assertIn("创建或修订", output["target"])

    def test_empty_board_without_goal_requests_t0_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_t0(root)

        self.assertEqual(output["state"], "needs-goal")
        self.assertEqual(output["next_role"], "T0")
        self.assertEqual(output["command"], "/taskboard-dev T0")
        self.assertEqual(output["task"], "none")
        self.assertIn("用户目标", output["target"])
        self.assertIn("T0 manager-only", output["boundary"])
        self.assertEqual(output["managed_sessions"], [])
        self.assertEqual(output["session_manifest"]["roles"], [])

    def test_completion_sentinel_without_audit_evidence_dispatches_t1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\n## Goal\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text("# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8")

            output = self.run_t0(
                root,
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt-file "{target_file}"',
            )

        self.assertEqual(output["state"], "dispatch")
        self.assertEqual(output["next_role"], "T1")
        self.assertEqual(output["status"], "T1-create-or-revise")
        self.assertEqual(output["reason"], "completion-audit-missing-evidence")
        self.assertEqual(output["completion_audit"]["state"], "incomplete")
        self.assertIn("no archived TASK evidence", output["completion_audit"]["missing_evidence"])
        self.assertIn("taskboard-T1", output["launch_commands"][0])

    def test_windows_terminal_launcher_commands_use_agent_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_t0(
                root,
                "--goal",
                "完成支付模块",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt "{target}"',
            )

        commands = output["launch_commands"]
        self.assertEqual(len(commands), 3)
        self.assertIn("wt -w taskboard", commands[0])
        self.assertIn('--title "taskboard-T1"', commands[0])
        self.assertIn("codex --prompt", commands[0])
        self.assertIn('`"用户目标', commands[0])
        self.assertIn("完成支付模块", commands[0])
        self.assertIn("taskboard-T2", commands[1])
        self.assertIn("taskboard-T3", commands[2])

    def test_agent_template_can_reference_role_target_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_t0(
                root,
                "--goal",
                "完成支付模块",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt-file "{target_file}"',
            )
            t1_target = root / ".taskboard" / "targets" / "taskboard-T1.md"
            t1_target_exists = t1_target.exists()
            t1_target_text = t1_target.read_text(encoding="utf-8") if t1_target_exists else ""

        first_session = output["managed_sessions"][0]
        self.assertEqual(first_session["target_file"], str(root.resolve() / ".taskboard" / "targets" / "taskboard-T1.md"))
        self.assertIn("taskboard-T1.md", output["launch_commands"][0])
        self.assertIn("codex --prompt-file", output["launch_commands"][0])
        self.assertTrue(t1_target_exists)
        self.assertEqual(output["target_files"][0]["role"], "T1")
        self.assertIn("managed_by: T0", t1_target_text)
        self.assertIn("assigned_role: T1", t1_target_text)
        self.assertIn("Worker loop contract", t1_target_text)
        self.assertIn("Do not stop after one action if more T1 work is available", t1_target_text)

    def test_role_target_files_include_idle_recheck_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_t0(
                root,
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt-file "{target_file}"',
            )
            target_texts = [
                (root / ".taskboard" / "targets" / f"taskboard-{role}.md").read_text(encoding="utf-8")
                for role in ("T1", "T2", "T3")
            ]

        for text in target_texts:
            self.assertIn("Idle recheck contract", text)
            self.assertIn("Do not terminate just because this role queue is empty", text)
            self.assertIn("sleep/yield for the configured interval", text)
            self.assertIn("goal completion, stop gate, explicit user pause, or context-limit restart", text)

    def test_role_target_files_include_default_tooling_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_t0(
                root,
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt-file "{target_file}"',
            )
            t1_text = (root / ".taskboard" / "targets" / "taskboard-T1.md").read_text(encoding="utf-8")
            t2_text = (root / ".taskboard" / "targets" / "taskboard-T2.md").read_text(encoding="utf-8")
            t3_text = (root / ".taskboard" / "targets" / "taskboard-T3.md").read_text(encoding="utf-8")

        self.assertIn("Default tooling contract", t1_text)
        self.assertIn("T1 MUST use available planning/brainstorming skills", t1_text)
        self.assertIn("superpowers:brainstorming", t1_text)
        self.assertIn("superpowers:writing-plans", t1_text)
        self.assertIn("record the fallback reason", t1_text)

        self.assertIn("Default tooling contract", t2_text)
        self.assertIn("T2 L2 code reviews default to an independent review tool", t2_text)
        self.assertIn("Codex code review", t2_text)
        self.assertIn("superpowers:requesting-code-review", t2_text)
        self.assertIn("L3 code reviews MUST run dual-pass review", t2_text)

        self.assertIn("Default tooling contract", t3_text)
        self.assertIn("T3 MUST assess whether the implementation can be split", t3_text)
        self.assertIn("Codex native subagents", t3_text)
        self.assertIn("available multi-agent tools", t3_text)
        self.assertIn("T3 remains responsible for integration, final verification, and commit", t3_text)

    def test_role_target_files_require_tooling_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_t0(
                root,
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt-file "{target_file}"',
            )
            target_texts = [
                (root / ".taskboard" / "targets" / f"taskboard-{role}.md").read_text(encoding="utf-8")
                for role in ("T1", "T2", "T3")
            ]

        for text in target_texts:
            self.assertIn("Required skills evidence", text)
            self.assertIn("Record the tool or skill used", text)
            self.assertIn("fallback reason", text)

    def test_role_target_files_include_external_tool_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_t0(
                root,
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt-file "{target_file}"',
            )
            target_texts = [
                (root / ".taskboard" / "targets" / f"taskboard-{role}.md").read_text(encoding="utf-8")
                for role in ("T1", "T2", "T3")
            ]

        for text in target_texts:
            self.assertIn("External tool contract", text)
            self.assertIn("Use GitHub tooling for repository, PR, issue, release, and CI-check work", text)
            self.assertIn("Use Chrome/Browser tooling for web UI inspection", text)
            self.assertIn("Use Computer Use only for local desktop or GUI workflows", text)
            self.assertIn("Do not ask the user to operate these tools for routine role work", text)
            self.assertIn("Respect role boundaries when using external tools", text)

    def test_inline_agent_template_does_not_write_role_target_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_t0(
                root,
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt "{target}"',
            )
            target_dir_exists = (root / ".taskboard" / "targets").exists()

        self.assertEqual(len(output["launch_commands"]), 3)
        self.assertEqual(output["target_files"], [])
        self.assertFalse(target_dir_exists)

    def test_text_output_lists_written_role_target_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            text = self.run_t0_text(
                root,
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt-file "{target_file}"',
            )

        self.assertIn("target_files:", text)
        self.assertIn("T1 path=", text)
        self.assertIn("taskboard-T1.md", text)

    def test_tmux_launcher_commands_create_isolated_role_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_t0(
                root,
                "--goal",
                "完成支付模块",
                "--launcher",
                "tmux",
                "--agent-template",
                'codex --prompt "{target}"',
            )

        commands = output["launch_commands"]
        self.assertEqual(commands[0].split()[0:3], ["tmux", "new-session", "-d"])
        self.assertIn("-n taskboard-T1", commands[0])
        self.assertIn("tmux new-window", commands[1])
        self.assertIn("-n taskboard-T2", commands[1])
        self.assertIn("-n taskboard-T3", commands[2])


if __name__ == "__main__":
    unittest.main()
