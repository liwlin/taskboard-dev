from pathlib import Path
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_loop.py"
sys.path.insert(0, str(ROOT / "scripts"))
import taskboard_loop as loop_module  # noqa: E402
from taskboard_next import ROLE_PRIORITY  # noqa: E402


T2_CODE_REVIEW = ROLE_PRIORITY["T0"][1][1]


class TaskboardLoopTest(unittest.TestCase):
    def run_loop(self, root: Path, *args: str) -> list[dict]:
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

    def run_loop_text(self, root: Path, *args: str) -> str:
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

    def test_once_combines_session_probe_health_and_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(root, "--goal", "Ship demo")

        self.assertEqual(len(output), 1)
        payload = output[0]
        self.assertEqual(payload["state"], "attention")
        self.assertEqual(payload["session_probe"]["missing_roles"], ["T1", "T2", "T3"])
        self.assertEqual(payload["queue_health"]["next"]["role"], "T1")
        self.assertEqual(payload["dispatch"]["next_role"], "T1")
        self.assertIn("T0 supervisor-only", payload["boundary"])
        self.assertIn("recover taskboard-T1", " ".join(payload["actions"]))

    def test_loop_stops_after_needs_goal_iteration_without_sleeping(self):
        payload = {
            "state": "needs-goal",
            "goal": "",
            "boundary": "T0 supervisor-only",
            "dispatch": {"state": "needs-goal"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("taskboard_loop.run_once", return_value=payload), patch(
                "taskboard_loop.time.sleep",
                side_effect=AssertionError("T0 must not sleep-loop without a user goal"),
            ):
                output = loop_module.run_loop(
                    root,
                    None,
                    30,
                    300,
                    "none",
                    None,
                    False,
                    None,
                    0,
                    300,
                    True,
                    None,
                    None,
                    300,
                    None,
                )

        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["dispatch"]["state"], "needs-goal")

    def test_loop_generates_recovery_commands_without_executing_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt "{target}"',
            )

        payload = output[0]
        self.assertEqual(len(payload["launch_commands"]), 3)
        self.assertEqual(payload["executed_commands"], [])
        self.assertIn("taskboard-T2", payload["launch_commands"][1])
        self.assertIn("codex --prompt", payload["launch_commands"][1])

    def test_execute_commands_stops_after_first_launcher_failure(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)

            class Completed:
                returncode = 1 if "taskboard-T1" in command else 0
                stdout = "launcher failed" if returncode else ""

            return Completed()

        commands = [
            "wt -w taskboard new-tab --title taskboard-T1",
            "wt -w taskboard new-tab --title taskboard-T2",
            "wt -w taskboard new-tab --title taskboard-T3",
        ]
        with patch("taskboard_loop.subprocess.run", fake_run):
            results = loop_module.execute_commands(commands)

        self.assertEqual(calls, [commands[0]])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["returncode"], 1)
        self.assertEqual(results[0]["output"], "launcher failed")

    def test_loop_recovery_commands_can_reference_written_target_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt-file "{target_file}"',
            )
            t1_target = root / ".taskboard" / "targets" / "taskboard-T1.md"
            t1_exists = t1_target.exists()

        payload = output[0]
        self.assertEqual(len(payload["launch_commands"]), 3)
        self.assertTrue(t1_exists)
        self.assertIn("codex --prompt-file", payload["launch_commands"][0])
        self.assertIn("taskboard-T1.md", payload["launch_commands"][0])
        self.assertNotIn('prompt-file ""', payload["launch_commands"][0])

    def test_loop_reports_needs_goal_without_goal_or_project_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(root)

        self.assertEqual(output[0]["state"], "needs-goal")
        self.assertEqual(output[0]["dispatch"]["state"], "needs-goal")
        self.assertIn("ask user for one T0 goal", output[0]["actions"])

    def test_loop_resumes_saved_t0_goal_without_retyping_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            first = self.run_loop(root, "--goal", "Ship demo")
            resumed = self.run_loop(root)

        self.assertEqual(first[0]["goal"], "Ship demo")
        self.assertEqual(resumed[0]["goal"], "Ship demo")
        self.assertEqual(resumed[0]["dispatch"]["state"], "dispatch")
        self.assertIn("Ship demo", resumed[0]["dispatch"]["target"])

    def test_loop_stops_when_goal_complete_sentinel_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "docs" / "taskboard" / "archive"
            archive.mkdir(parents=True)
            (archive / "TASK-001.v1.done.md").write_text("# completed task\n", encoding="utf-8")
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\n## Goal\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text("# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8")
            (root / "docs" / "dev-log.md").write_text(
                "# Development Log\n\n- TASK-001 completed and verified by T2.\n",
                encoding="utf-8",
            )

            output = self.run_loop(root, "--goal", "Ship demo")

        self.assertEqual(output[0]["state"], "idle")
        self.assertEqual(output[0]["dispatch"]["state"], "complete")
        self.assertEqual(output[0]["dispatch"]["reason"], "goal-complete-sentinel")
        self.assertEqual(output[0]["completion_audit"]["state"], "complete-ready")
        self.assertTrue(output[0]["completion_audit"]["completion_ready"])
        self.assertIn("archived task and dev-log evidence", output[0]["actions"][0])

    def test_loop_keeps_waking_t1_when_completion_audit_is_missing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\n## Goal\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text("# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8")

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--iterations",
                "2",
                "--interval-seconds",
                "0",
            )

        self.assertEqual(len(output), 2)
        self.assertEqual(output[0]["state"], "attention")
        self.assertEqual(output[0]["dispatch"]["state"], "dispatch")
        self.assertEqual(output[0]["dispatch"]["next_role"], "T1")
        self.assertEqual(output[0]["dispatch"]["reason"], "completion-audit-missing-evidence")
        self.assertEqual(output[0]["completion_audit"]["state"], "incomplete")
        self.assertFalse(output[0]["completion_audit"]["completion_ready"])
        self.assertIn("no archived TASK evidence", output[0]["completion_audit"]["missing_evidence"])
        self.assertIn("wake T1", output[0]["completion_audit"]["user_action"])
        self.assertIn("wake T1", " ".join(output[0]["actions"]))

    def test_loop_event_log_records_missing_completion_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\n## Goal\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text("# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8")

            self.run_loop(root, "--goal", "Ship demo")
            event_log = root / ".taskboard" / "t0" / "events.jsonl"
            events = [
                json.loads(line)
                for line in event_log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertFalse(events[0]["completion_ready"])
        self.assertIn("no archived TASK evidence", events[0]["completion_missing_evidence"])
        self.assertIn("wake T1", events[0]["completion_user_action"])

    def test_loop_pauses_worker_launches_for_user_stop_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            (taskboard / "TASK-001.v1.T1-待决策.md").write_text(
                "\n".join(
                    [
                        "# Decide scope",
                        "",
                        "**Wave**: 1",
                        "**Gate**: Product decision",
                        "**Question**: Should T0 continue with option A?",
                        "**Options**:",
                        "- A",
                        "- B",
                        "**Recommended**: A",
                    ]
                ),
                encoding="utf-8",
            )

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--launcher",
                "windows-terminal",
                "--agent-template",
                'codex --prompt-file "{target_file}"',
            )

        payload = output[0]
        self.assertEqual(payload["state"], "stop-gate")
        self.assertEqual(payload["assignment"]["state"], "user-stop-gate")
        self.assertEqual(payload["launch_commands"], [])
        self.assertEqual(payload["target_files"], [])
        self.assertEqual(payload["stop_gate_report"]["stop_gate_count"], 1)
        self.assertIn("taskboard_decide.py", payload["decision_command"])
        self.assertIn("--task TASK-001.v1.T1-待决策.md", payload["decision_command"])
        self.assertIn('--decision "<user answer>"', payload["decision_command"])
        self.assertIn("Should T0 continue with option A?", " ".join(payload["actions"]))
        self.assertNotIn("reissue target to taskboard-T1", " ".join(payload["actions"]))

    def test_loop_stops_after_first_stop_gate_iteration_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            (taskboard / "TASK-001.v1.T1-待决策.md").write_text(
                "\n".join(
                    [
                        "# Decide scope",
                        "",
                        "**Wave**: 1",
                        "**Gate**: Product decision",
                        "**Question**: Which option should T0 resume with?",
                    ]
                ),
                encoding="utf-8",
            )

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--iterations",
                "3",
                "--interval-seconds",
                "0",
            )

        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["state"], "stop-gate")

    def test_loop_text_output_includes_stop_gate_decision_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            (taskboard / "TASK-001.v1.T1-待决策.md").write_text(
                "# Decide scope\n\n**Wave**: 1\n**Gate**: Product decision\n**Question**: Continue?\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--goal",
                    "Ship demo",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("decision_command:", result.stdout)
        self.assertIn("taskboard_decide.py", result.stdout)

    def test_loop_can_continue_after_stop_gate_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            (taskboard / "TASK-001.v1.T1-待决策.md").write_text(
                "# Decide scope\n\n**Wave**: 1\n**Gate**: Product decision\n**Question**: Continue?\n",
                encoding="utf-8",
            )

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--iterations",
                "2",
                "--interval-seconds",
                "0",
                "--no-stop-on-stop-gate",
            )

        self.assertEqual(len(output), 2)
        self.assertEqual(output[0]["state"], "stop-gate")
        self.assertEqual(output[1]["state"], "stop-gate")

    def test_loop_stops_after_first_complete_iteration_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "docs" / "taskboard" / "archive"
            archive.mkdir(parents=True)
            (archive / "TASK-001.v1.done.md").write_text("# completed task\n", encoding="utf-8")
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\n## Goal\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text("# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8")
            (root / "docs" / "dev-log.md").write_text(
                "# Development Log\n\n- TASK-001 completed.\n",
                encoding="utf-8",
            )

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--iterations",
                "3",
                "--interval-seconds",
                "0",
            )

        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["dispatch"]["state"], "complete")

    def test_loop_text_output_includes_completion_audit_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "docs" / "taskboard" / "archive"
            archive.mkdir(parents=True)
            (archive / "TASK-001.v1.done.md").write_text("# completed task\n", encoding="utf-8")
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\n## Goal\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text("# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8")
            (root / "docs" / "dev-log.md").write_text(
                "# Development Log\n\n- TASK-001 completed.\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--goal",
                    "Ship demo",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("completion_audit:", result.stdout)
        self.assertIn("completion_ready=True", result.stdout)
        self.assertIn("archived_count=1", result.stdout)

    def test_loop_can_continue_after_complete_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "docs" / "taskboard" / "archive"
            archive.mkdir(parents=True)
            (archive / "TASK-001.v1.done.md").write_text("# completed task\n", encoding="utf-8")
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\n## Goal\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text("# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8")
            (root / "docs" / "dev-log.md").write_text(
                "# Development Log\n\n- TASK-001 completed.\n",
                encoding="utf-8",
            )

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--iterations",
                "2",
                "--interval-seconds",
                "0",
                "--no-stop-on-complete",
            )

        self.assertEqual(len(output), 2)
        self.assertEqual(output[0]["dispatch"]["state"], "complete")
        self.assertEqual(output[1]["dispatch"]["state"], "complete")

    def test_iterations_runs_multiple_bounded_cycles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(root, "--goal", "Ship demo", "--iterations", "2", "--interval-seconds", "0")

        self.assertEqual(len(output), 2)

    def test_execute_launches_is_throttled_until_launch_lease_expires(self):
        executed_batches = []

        def fake_execute(commands):
            executed_batches.append(list(commands))
            return [
                {
                    "command": command,
                    "returncode": 0,
                    "output": "",
                }
                for command in commands
            ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            with patch("taskboard_loop.execute_commands", fake_execute):
                output = loop_module.run_loop(
                    root,
                    "Ship demo",
                    30,
                    300,
                    "windows-terminal",
                    'codex --prompt-file "{target_file}"',
                    True,
                    2,
                    0,
                    300,
                    True,
                    root / ".taskboard" / "t0" / "latest.json",
                    root / ".taskboard" / "targets",
                    300,
                    root / ".taskboard" / "t0" / "events.jsonl",
                )
            events = [
                json.loads(line)
                for line in (root / ".taskboard" / "t0" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual([len(batch) for batch in executed_batches], [3])
        self.assertEqual(len(output[0]["executed_commands"]), 3)
        self.assertEqual(output[1]["executed_commands"], [])
        self.assertEqual(
            [item["role"] for item in output[1]["suppressed_launches"]],
            ["T1", "T2", "T3"],
        )
        self.assertEqual(events[1]["suppressed_launch_count"], 3)
        self.assertEqual(
            [item["role"] for item in events[1]["suppressed_launches"]],
            ["T1", "T2", "T3"],
        )
        self.assertEqual(events[1]["suppressed_launches"][0]["reason"], "launch-lease-active")
        self.assertGreater(events[1]["suppressed_launches"][0]["remaining_seconds"], 0)
        self.assertIn("launch lease active", " ".join(output[1]["actions"]))

    def test_execute_launches_does_not_relaunch_healthy_roles_after_launch_lease(self):
        executed_batches = []

        def fake_execute(commands):
            executed_batches.append(list(commands))
            return [
                {
                    "command": command,
                    "returncode": 0,
                    "output": "",
                }
                for command in commands
            ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            session_dir = root / ".taskboard" / "sessions"
            session_dir.mkdir(parents=True)
            for role in ("T1", "T2", "T3"):
                (session_dir / f"taskboard-{role}.json").write_text(
                    json.dumps(
                        {
                            "role": role,
                            "title": f"taskboard-{role}",
                            "status": "alive",
                            "last_seen": time.time(),
                        }
                    ),
                    encoding="utf-8",
                )
            launch_dir = root / ".taskboard" / "t0"
            launch_dir.mkdir(parents=True)
            old_success = time.time() - 600
            (launch_dir / "launches.json").write_text(
                json.dumps(
                    {
                        "kind": "taskboard-t0-launch-state",
                        "version": 1,
                        "roles": {
                            role: {
                                "last_success_at": old_success,
                                "last_command": f"wt -w taskboard new-tab --title taskboard-{role}",
                            }
                            for role in ("T1", "T2", "T3")
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch("taskboard_loop.execute_commands", fake_execute):
                output = loop_module.run_loop(
                    root,
                    "Ship demo",
                    30,
                    999999999,
                    "windows-terminal",
                    'codex --prompt-file "{target_file}"',
                    True,
                    1,
                    0,
                    300,
                    True,
                    root / ".taskboard" / "t0" / "latest.json",
                    root / ".taskboard" / "targets",
                    1,
                )

        self.assertEqual(executed_batches, [])
        self.assertEqual(output[0]["session_probe"]["state"], "healthy")
        self.assertEqual(len(output[0]["planned_launch_commands"]), 3)
        self.assertEqual(output[0]["requested_launch_commands"], [])
        self.assertEqual(output[0]["launch_commands"], [])
        self.assertIn("keep taskboard-T1 active", " ".join(output[0]["actions"]))

    def test_execute_launches_stops_when_checkout_is_owned_by_peer_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            owner_file = root / ".taskboard" / "t0" / "checkout-owner.json"
            owner_file.parent.mkdir(parents=True)
            owner_file.write_text(
                json.dumps(
                    {
                        "kind": "taskboard-checkout-owner",
                        "owner_id": "claudecode-live-run",
                        "updated_at_epoch": time.time(),
                        "lease_seconds": 300,
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "taskboard_loop.execute_commands",
                side_effect=AssertionError("checkout conflict must suppress worker launches"),
            ):
                output = loop_module.run_once(
                    root,
                    "Ship demo",
                    30,
                    300,
                    "powershell",
                    'python "{target}"',
                    True,
                    300,
                    root / ".taskboard" / "targets",
                    agent_preflight={"state": "passed"},
                    checkout_owner_id="codex-live-run",
                )

        self.assertEqual(output["checkout_owner"]["state"], "conflict")
        self.assertEqual(output["checkout_owner"]["owner_id"], "claudecode-live-run")
        self.assertEqual(output["launch_commands"], [])
        self.assertEqual(output["executed_commands"], [])
        self.assertIn("checkout ownership conflict", " ".join(output["actions"]))

    def test_execute_launches_reclaims_expired_checkout_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            owner_file = root / ".taskboard" / "t0" / "checkout-owner.json"
            owner_file.parent.mkdir(parents=True)
            owner_file.write_text(
                json.dumps(
                    {
                        "kind": "taskboard-checkout-owner",
                        "owner_id": "stale-peer",
                        "updated_at_epoch": time.time() - 600,
                        "lease_seconds": 300,
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "taskboard_loop.execute_commands",
                return_value=[
                    {"command": "fake launch", "returncode": 0, "output": ""},
                ],
            ) as execute_mock:
                output = loop_module.run_once(
                    root,
                    "Ship demo",
                    30,
                    300,
                    "powershell",
                    'python "{target}"',
                    True,
                    300,
                    root / ".taskboard" / "targets",
                    agent_preflight={"state": "passed"},
                    checkout_owner_id="codex-live-run",
                )
            owner_payload = json.loads(owner_file.read_text(encoding="utf-8"))

        self.assertTrue(execute_mock.called)
        self.assertEqual(output["checkout_owner"]["state"], "acquired")
        self.assertEqual(output["checkout_owner"]["previous_state"], "expired")
        self.assertEqual(owner_payload["owner_id"], "codex-live-run")

    def test_loop_writes_latest_t0_state_snapshot_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(root, "--goal", "Ship demo")
            state_file = root / ".taskboard" / "t0" / "latest.json"
            snapshot = json.loads(state_file.read_text(encoding="utf-8"))

        self.assertEqual(snapshot["kind"], "taskboard-t0-supervisor-state")
        self.assertEqual(snapshot["iteration_count"], 1)
        self.assertEqual(snapshot["latest"]["state"], output[0]["state"])
        self.assertEqual(snapshot["latest"]["dispatch"]["next_role"], output[0]["dispatch"]["next_role"])
        self.assertIn("T0 supervisor-only", snapshot["boundary"])
        self.assertIn("do not perform design", snapshot["boundary"])

    def test_loop_can_disable_t0_state_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_loop(root, "--goal", "Ship demo", "--no-state-file")

        self.assertFalse((root / ".taskboard" / "t0" / "latest.json").exists())

    def test_loop_appends_t0_event_log_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--iterations",
                "2",
                "--interval-seconds",
                "0",
                "--launcher",
                "tmux",
                "--stale-minutes",
                "12",
                "--stale-seconds",
                "34",
                "--assignment-lease-seconds",
                "56",
                "--launch-lease-seconds",
                "78",
            )
            event_log = root / ".taskboard" / "t0" / "events.jsonl"
            events = [
                json.loads(line)
                for line in event_log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["kind"], "taskboard-t0-supervisor-event")
        self.assertEqual(events[0]["iteration"], 1)
        self.assertEqual(events[1]["iteration"], 2)
        self.assertEqual(events[0]["goal"], "Ship demo")
        self.assertIn("next_role", events[0])
        self.assertEqual(events[0]["resume_config"]["launcher"], "tmux")
        self.assertEqual(events[0]["resume_config"]["stale_minutes"], 12)
        self.assertEqual(events[0]["resume_config"]["stale_seconds"], 34)
        self.assertEqual(events[0]["resume_config"]["assignment_lease_seconds"], 56)
        self.assertEqual(events[0]["resume_config"]["launch_lease_seconds"], 78)
        self.assertIn("append-only", events[0]["boundary"])

    def test_loop_event_log_records_launch_failure_counts(self):
        def fake_execute(commands):
            return [
                {
                    "command": command,
                    "returncode": 1 if index == 0 else 0,
                    "output": "launcher failed" if index == 0 else "",
                }
                for index, command in enumerate(commands)
            ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            with patch("taskboard_loop.execute_commands", fake_execute):
                loop_module.run_loop(
                    root,
                    "Ship demo",
                    30,
                    300,
                    "windows-terminal",
                    'codex --prompt-file "{target_file}"',
                    True,
                    1,
                    0,
                    300,
                    True,
                    root / ".taskboard" / "t0" / "latest.json",
                    root / ".taskboard" / "targets",
                    300,
                    root / ".taskboard" / "t0" / "events.jsonl",
                )
            event_log = root / ".taskboard" / "t0" / "events.jsonl"
            events = [
                json.loads(line)
                for line in event_log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(events[0]["launch_command_count"], 3)
        self.assertEqual(events[0]["launch_failure_count"], 1)
        self.assertEqual(events[0]["launch_failures"][0]["returncode"], 1)
        self.assertIn("taskboard-T1", events[0]["launch_failures"][0]["command"])
        self.assertEqual(events[0]["launch_failures"][0]["output"], "launcher failed")
        self.assertEqual(events[0]["executed_command_count"], 3)
        self.assertEqual(events[0]["suppressed_launch_count"], 0)

    def test_loop_actions_surface_launch_failure_as_t0_control_plane_recovery(self):
        def fake_execute(commands):
            return [
                {
                    "command": command,
                    "returncode": 1,
                    "output": "launcher missing",
                }
                for command in commands
            ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            with patch("taskboard_loop.execute_commands", fake_execute):
                output = loop_module.run_loop(
                    root,
                    "Ship demo",
                    30,
                    300,
                    "windows-terminal",
                    'codex --prompt-file "{target_file}"',
                    True,
                    1,
                    0,
                    300,
                    True,
                    root / ".taskboard" / "t0" / "latest.json",
                    root / ".taskboard" / "targets",
                    300,
                    root / ".taskboard" / "t0" / "events.jsonl",
                )

        actions = " ".join(output[0]["actions"])
        self.assertEqual(output[0]["state"], "attention")
        self.assertIn("T0 launch/recovery failed", actions)
        self.assertIn("fix the T0 launcher configuration", actions)
        self.assertIn("do not manage T1/T2/T3", actions)

    def test_execute_launches_tries_fallback_launcher_after_primary_failure(self):
        calls = []

        def fake_execute(commands):
            calls.append(list(commands))
            if len(calls) == 1:
                return [
                    {
                        "command": commands[0],
                        "returncode": 1,
                        "output": "wt missing",
                    }
                ]
            return [
                {
                    "command": command,
                    "returncode": 0,
                    "output": "",
                }
                for command in commands
            ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            with patch("taskboard_loop.execute_commands", fake_execute):
                output = loop_module.run_loop(
                    root,
                    "Ship demo",
                    30,
                    300,
                    "windows-terminal",
                    'codex --prompt-file "{target_file}"',
                    True,
                    1,
                    0,
                    300,
                    True,
                    root / ".taskboard" / "t0" / "latest.json",
                    root / ".taskboard" / "targets",
                    300,
                    root / ".taskboard" / "t0" / "events.jsonl",
                    fallback_launchers=["powershell"],
                )
            events = [
                json.loads(line)
                for line in (root / ".taskboard" / "t0" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(calls), 2)
        self.assertIn("taskboard-T1", calls[0][0])
        self.assertTrue(all("Start-Process powershell" in command for command in calls[1]))
        self.assertEqual(output[0]["fallback_launch_attempts"][0]["launcher"], "powershell")
        self.assertTrue(output[0]["fallback_launch_attempts"][0]["success"])
        actions = " ".join(output[0]["actions"])
        self.assertIn("fallback launcher powershell", actions)
        self.assertNotIn("fix the T0 launcher configuration", actions)
        self.assertEqual(events[0]["fallback_launch_count"], 1)
        self.assertEqual(events[0]["fallback_launchers"], ["powershell"])
        self.assertTrue(events[0]["fallback_launch_recovered"])

    def test_loop_event_log_records_assignment_recovery_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-006.v1.{T2_CODE_REVIEW}-L2.md"
            (taskboard / task_name).write_text("# review\n\n**Wave**: 1\n", encoding="utf-8")

            self.run_loop(root, "--goal", "Ship demo")
            event_log = root / ".taskboard" / "t0" / "events.jsonl"
            events = [
                json.loads(line)
                for line in event_log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(events[0]["assignment_state"], "unassigned")
        self.assertEqual(events[0]["assignment_role"], "T2")
        self.assertEqual(events[0]["assignment_task"], task_name)
        self.assertEqual(events[0]["assignment_expected_id"], f"T2:{task_name}")
        self.assertIn("taskboard-T2 is missing", events[0]["assignment_reason"])

    def test_loop_can_disable_t0_event_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_loop(root, "--goal", "Ship demo", "--no-event-log")

        self.assertFalse((root / ".taskboard" / "t0" / "events.jsonl").exists())

    def test_loop_appends_event_log_across_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_loop(root, "--goal", "Ship demo")
            self.run_loop(root)
            event_log = root / ".taskboard" / "t0" / "events.jsonl"
            events = [
                json.loads(line)
                for line in event_log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event_index"], 1)
        self.assertEqual(events[1]["event_index"], 2)
        self.assertEqual(events[1]["goal"], "Ship demo")

    def test_loop_text_output_lists_written_role_target_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            text = self.run_loop_text(
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

    def test_loop_writes_isolated_role_target_files_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-003.v1.{T2_CODE_REVIEW}-L2.md"
            (taskboard / task_name).write_text("# task\n\n**Wave**: 1\n", encoding="utf-8")

            output = self.run_loop(root, "--goal", "Ship demo")
            t1_target = root / ".taskboard" / "targets" / "taskboard-T1.md"
            t2_target = root / ".taskboard" / "targets" / "taskboard-T2.md"
            t3_target = root / ".taskboard" / "targets" / "taskboard-T3.md"
            target_files_exist = [t1_target.exists(), t2_target.exists(), t3_target.exists()]
            t2_text = t2_target.read_text(encoding="utf-8")
            t1_text = t1_target.read_text(encoding="utf-8")

        self.assertEqual(
            [item["role"] for item in output[0]["target_files"]],
            ["T1", "T2", "T3"],
        )
        self.assertEqual(target_files_exist, [True, True, True])
        self.assertIn("managed_by: T0", t2_text)
        self.assertIn(task_name, t2_text)
        self.assertIn(f"--assignment-id T2:{task_name}", t2_text)
        self.assertIn("managed-loop", t1_text)
        self.assertIn("T0 writes role targets only", t2_text)
        self.assertIn("Role runtime contract", t2_text)
        self.assertIn("assigned_role: T2", t2_text)
        self.assertIn("managed_by: T0", t2_text)
        self.assertIn("do not execute T0/T1/T3 responsibilities", t2_text)
        self.assertIn("do not rely on another role's chat context", t2_text)

    def test_loop_can_disable_role_target_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(root, "--goal", "Ship demo", "--no-target-files")

        self.assertEqual(output[0]["target_files"], [])
        self.assertFalse((root / ".taskboard" / "targets").exists())

    def test_loop_persists_config_error_before_first_iteration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--format",
                    "json",
                    "--goal",
                    "Ship demo",
                    "--launcher",
                    "windows-terminal",
                    "--agent-template",
                    'codex --prompt-file "{target_file}"',
                    "--no-target-files",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            state_file = root / ".taskboard" / "t0" / "latest.json"
            event_log = root / ".taskboard" / "t0" / "events.jsonl"

            self.assertTrue(state_file.exists(), result.stdout)
            self.assertTrue(event_log.exists(), result.stdout)
            snapshot = json.loads(state_file.read_text(encoding="utf-8"))
            events = [
                json.loads(line)
                for line in event_log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("agent-template references {target_file}", result.stdout)
        self.assertEqual(snapshot["latest"]["kind"], "taskboard-t0-config-error")
        self.assertEqual(snapshot["latest"]["state"], "config-error")
        self.assertIn("agent-template references {target_file}", snapshot["latest"]["error"])
        self.assertIn("fix T0 launcher configuration", snapshot["latest"]["user_action"])
        self.assertIn("do not ask the user to manage T1/T2/T3 directly", snapshot["latest"]["boundary"])
        self.assertEqual(events[0]["state"], "config-error")
        self.assertEqual(events[0]["dispatch_state"], "config-error")
        self.assertIn("agent-template references {target_file}", events[0]["error"])

    def test_loop_persists_agent_preflight_failure_before_launching_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--format",
                    "json",
                    "--goal",
                    "Ship demo",
                    "--iterations",
                    "1",
                    "--launcher",
                    "powershell",
                    "--agent-template",
                    f'"{sys.executable}" -c "import sys; sys.exit(0)" --prompt-file "{{target_file}}"',
                    "--agent-preflight-command",
                    f'"{sys.executable}" -c "import sys; sys.exit(7)"',
                    "--execute-launches",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            state_file = root / ".taskboard" / "t0" / "latest.json"
            event_log = root / ".taskboard" / "t0" / "events.jsonl"

            self.assertTrue(state_file.exists(), result.stdout)
            self.assertTrue(event_log.exists(), result.stdout)
            snapshot = json.loads(state_file.read_text(encoding="utf-8"))
            events = [
                json.loads(line)
                for line in event_log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("agent preflight command failed", result.stdout)
        self.assertIn("returncode=7", result.stdout)
        self.assertEqual(snapshot["latest"]["state"], "config-error")
        self.assertIn("agent preflight command failed", snapshot["latest"]["error"])
        self.assertEqual(events[0]["state"], "config-error")
        self.assertIn("agent preflight command failed", events[0]["error"])

    def test_auth_refused_agent_preflight_writes_user_owned_launch_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--format",
                    "json",
                    "--goal",
                    "Ship demo",
                    "--iterations",
                    "1",
                    "--launcher",
                    "powershell",
                    "--agent-template",
                    f'"{sys.executable}" -c "print(123)" --prompt-file "{{target_file}}"',
                    "--agent-preflight-command",
                    (
                        f'"{sys.executable}" -c '
                        '"import sys; print(\'Failed to authenticate. API Error: 403 Request not allowed\'); sys.exit(7)"'
                    ),
                    "--execute-launches",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            payload = json.loads(result.stdout)[0]
            manual_files = payload["manual_launch_files"]
            open_tabs = Path(manual_files["open_tabs"])
            launch_role = Path(manual_files["launch_role"])
            open_tabs_exists = open_tabs.exists()
            launch_role_exists = launch_role.exists()
            open_tabs_text = open_tabs.read_text(encoding="utf-8")
            launch_role_text = launch_role.read_text(encoding="utf-8")

        self.assertEqual(payload["agent_preflight"]["state"], "spawn-refused")
        self.assertIn("API Error: 403", payload["agent_preflight"]["output"])
        self.assertEqual(payload["executed_commands"], [])
        self.assertEqual(payload["launch_commands"], [])
        self.assertTrue(open_tabs_exists)
        self.assertTrue(launch_role_exists)
        open_tabs_text.encode("ascii")
        launch_role_text.encode("ascii")
        self.assertIn("taskboard-T1", open_tabs_text)
        self.assertIn("Run the generated user-owned Windows Terminal script", " ".join(payload["actions"]))
        fallback = payload["subagent_fallback"]
        self.assertEqual(fallback["kind"], "taskboard-subagent-fallback")
        self.assertEqual(fallback["backend"]["kind"], "taskboard-subagent-backend")
        self.assertEqual(len(fallback["subagent_prompts"]), 3)
        self.assertIn("references/role-t1.md", fallback["subagent_prompts"][0]["prompt"])
        self.assertIn("Do not inherit T0 private reasoning", fallback["subagent_prompts"][0]["prompt"])
        self.assertIn("Startup skill gate", fallback["subagent_prompts"][0]["prompt"])
        self.assertIn("native subagent fallback", " ".join(payload["actions"]))

    def test_loop_emits_subagent_control_plan_after_spawn_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--iterations",
                "1",
                "--launcher",
                "powershell",
                "--agent-template",
                f'"{sys.executable}" -c "print(123)" --prompt-file "{{target_file}}"',
                "--agent-preflight-command",
                (
                    f'"{sys.executable}" -c '
                    '"import sys; print(\'Failed to authenticate. API Error: 403 Request not allowed\'); sys.exit(7)"'
                ),
                "--execute-launches",
            )
            payload = output[0]
            event_log = root / ".taskboard" / "t0" / "events.jsonl"
            events = [
                json.loads(line)
                for line in event_log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        control = payload["subagent_control"]
        self.assertEqual(control["kind"], "taskboard-subagent-loop-control")
        self.assertEqual(control["state"], "dispatch-next")
        self.assertEqual(control["action"], "spawn-native-subagent")
        self.assertEqual(control["role"], "T1")
        self.assertRegex(control["prompt_hash"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(control["native_spawn"]["tool_hint"], "multi_agent_v1.spawn_agent")
        self.assertEqual(payload["executed_commands"], [])
        self.assertNotIn("manage T1/T2/T3", " ".join(payload["actions"]))
        self.assertEqual(events[-1]["subagent_control_state"], "dispatch-next")
        self.assertEqual(events[-1]["subagent_control_action"], "spawn-native-subagent")
        self.assertEqual(events[-1]["subagent_control_role"], "T1")

    def test_loop_records_injected_native_spawn_receipt_and_advances_subagent_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            payload = loop_module.run_once(
                root,
                "Ship demo",
                30,
                300,
                "powershell",
                f'"{sys.executable}" -c "print(123)" --prompt-file "{{target_file}}"',
                True,
                300,
                loop_module.default_target_dir(root),
                agent_preflight={
                    "kind": "taskboard-agent-preflight",
                    "state": "spawn-refused",
                    "output": "Failed to authenticate. API Error: 403 Request not allowed",
                },
                native_spawn_result={
                    "role": "T1",
                    "agent_id": "019eb760-native-t1",
                    "agent_nickname": "T1 architect child",
                    "spawn_tool": "multi_agent_v1.spawn_agent",
                    "note": "spawned by T0 loop bridge",
                },
            )
            state = json.loads((root / ".taskboard" / "t0" / "subagents.json").read_text(encoding="utf-8"))

        control = payload["subagent_control"]
        self.assertEqual(control["state"], "dispatched")
        self.assertEqual(control["action"], "recorded-native-spawn")
        self.assertEqual(control["role"], "T1")
        self.assertEqual(control["subagent_ack"]["record"]["spawn_receipt"]["spawn_tool"], "multi_agent_v1.spawn_agent")
        self.assertEqual(control["subagent_next_plan"]["state"], "dispatch-next")
        self.assertEqual(control["subagent_next_plan"]["role"], "T2")
        self.assertEqual(state["roles"]["T1"]["status"], "dispatched")
        self.assertEqual(state["roles"]["T1"]["agent_id"], "019eb760-native-t1")

    def test_loop_persists_interruption_recovery_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            stdout = io.StringIO()
            with patch("taskboard_loop.run_loop", side_effect=KeyboardInterrupt):
                with contextlib.redirect_stdout(stdout):
                    code = loop_module.main(
                        [
                            "--root",
                            str(root),
                            "--goal",
                            "Ship demo",
                            "--launcher",
                            "tmux",
                            "--agent-template",
                            'codex --prompt "{target}"',
                            "--no-target-files",
                            "--stale-minutes",
                            "12",
                            "--stale-seconds",
                            "34",
                            "--assignment-lease-seconds",
                            "56",
                            "--launch-lease-seconds",
                            "78",
                            "--interval-seconds",
                            "9",
                            "--format",
                            "json",
                        ]
                    )
            snapshot = json.loads((root / ".taskboard" / "t0" / "latest.json").read_text(encoding="utf-8"))
            events = [
                json.loads(line)
                for line in (root / ".taskboard" / "t0" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        payload = json.loads(stdout.getvalue())
        latest = snapshot["latest"]
        self.assertEqual(code, 130)
        self.assertEqual(payload["kind"], "taskboard-t0-interruption")
        self.assertEqual(payload["state"], "interrupted")
        self.assertEqual(latest["kind"], "taskboard-t0-interruption")
        self.assertEqual(latest["state"], "interrupted")
        self.assertIn(f'python scripts/taskboard_start.py --root "{root}" --auto', payload["resume_command"])
        self.assertIn("--launcher tmux", payload["resume_command"])
        self.assertIn('--agent-template "codex --prompt \\"{target}\\""', payload["resume_command"])
        self.assertIn("--no-target-files", payload["resume_command"])
        self.assertEqual(latest["resume_config"]["stale_minutes"], 12)
        self.assertFalse(latest["resume_config"]["target_files_enabled"])
        self.assertEqual(events[-1]["state"], "interrupted")
        self.assertEqual(events[-1]["dispatch_state"], "interrupted")
        self.assertEqual(events[-1]["resume_config"]["launcher"], "tmux")
        self.assertFalse(events[-1]["resume_config"]["target_files_enabled"])

    def test_assignment_moves_from_pending_to_acknowledged_by_worker_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-003.v1.{T2_CODE_REVIEW}-L2.md"
            (taskboard / task_name).write_text("# task\n\n**Wave**: 1\n", encoding="utf-8")

            session_dir = root / ".taskboard" / "sessions"
            session_dir.mkdir(parents=True)
            base_session = {
                "role": "T2",
                "title": "taskboard-T2",
                "status": "alive",
                "pid": 123,
                "last_seen": 4102444800,
            }
            (session_dir / "taskboard-T1.json").write_text(
                json.dumps({**base_session, "role": "T1", "title": "taskboard-T1"}),
                encoding="utf-8",
            )
            (session_dir / "taskboard-T2.json").write_text(json.dumps(base_session), encoding="utf-8")
            (session_dir / "taskboard-T3.json").write_text(
                json.dumps({**base_session, "role": "T3", "title": "taskboard-T3"}),
                encoding="utf-8",
            )

            pending = self.run_loop(root, "--goal", "Ship demo", "--stale-seconds", "999999999")
            (session_dir / "taskboard-T2.json").write_text(
                json.dumps({**base_session, "task": task_name, "assignment_id": f"T2:{task_name}"}),
                encoding="utf-8",
            )
            acknowledged = self.run_loop(root, "--goal", "Ship demo", "--stale-seconds", "999999999")

        self.assertEqual(pending[0]["assignment"]["state"], "pending-ack")
        self.assertIn("reissue target to taskboard-T2", " ".join(pending[0]["actions"]))
        self.assertEqual(acknowledged[0]["assignment"]["state"], "acknowledged")
        self.assertEqual(acknowledged[0]["assignment"]["assignment_id"], f"T2:{task_name}")

    def test_assignment_lease_expiry_reissues_acknowledged_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-003.v1.{T2_CODE_REVIEW}-L2.md"
            (taskboard / task_name).write_text("# task\n\n**Wave**: 1\n", encoding="utf-8")

            session_dir = root / ".taskboard" / "sessions"
            session_dir.mkdir(parents=True)
            old_assignment_time = time.time() - 600
            for role in ("T1", "T2", "T3"):
                payload = {
                    "role": role,
                    "title": f"taskboard-{role}",
                    "status": "alive",
                    "pid": 123,
                    "last_seen": time.time(),
                }
                if role == "T2":
                    payload.update(
                        {
                            "status": "reviewing",
                            "last_seen": old_assignment_time,
                            "task": task_name,
                            "assignment_id": f"T2:{task_name}",
                        }
                    )
                (session_dir / f"taskboard-{role}.json").write_text(json.dumps(payload), encoding="utf-8")

            output = self.run_loop(
                root,
                "--goal",
                "Ship demo",
                "--stale-seconds",
                "999999999",
                "--assignment-lease-seconds",
                "300",
            )

        self.assertEqual(output[0]["assignment"]["state"], "lease-expired")
        self.assertGreaterEqual(output[0]["assignment"]["age_seconds"], 599)
        self.assertIn("lease expired", " ".join(output[0]["actions"]))

    def test_pending_assignment_ack_timeout_recovers_only_selected_role(self):
        executed_batches = []
        time_calls = 0

        def fake_execute(commands):
            executed_batches.append(list(commands))
            return [
                {
                    "command": command,
                    "returncode": 0,
                    "output": "",
                }
                for command in commands
            ]

        def fake_time():
            nonlocal time_calls
            time_calls += 1
            return 1000.0 if time_calls <= 3 else 1010.0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-003.v1.{T2_CODE_REVIEW}-L2.md"
            (taskboard / task_name).write_text("# task\n\n**Wave**: 1\n", encoding="utf-8")

            session_dir = root / ".taskboard" / "sessions"
            session_dir.mkdir(parents=True)
            for role in ("T1", "T2", "T3"):
                payload = {
                    "role": role,
                    "title": f"taskboard-{role}",
                    "status": "alive",
                    "pid": 123,
                    "last_seen": 4102444800,
                }
                if role == "T2":
                    payload.update({"task": "TASK-OLD.v1.T2-review-L2.md", "assignment_id": "T2:old"})
                (session_dir / f"taskboard-{role}.json").write_text(json.dumps(payload), encoding="utf-8")

            with patch("taskboard_loop.time.time", fake_time), patch(
                "taskboard_loop.execute_commands",
                fake_execute,
            ):
                output = loop_module.run_loop(
                    root,
                    "Ship demo",
                    30,
                    999999999,
                    "powershell",
                    'codex --prompt-file "{target_file}"',
                    True,
                    2,
                    0,
                    5,
                    True,
                    root / ".taskboard" / "t0" / "latest.json",
                    root / ".taskboard" / "targets",
                    300,
                    root / ".taskboard" / "t0" / "events.jsonl",
                )
            events = [
                json.loads(line)
                for line in (root / ".taskboard" / "t0" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(output[0]["assignment"]["state"], "pending-ack")
        self.assertEqual(output[1]["assignment"]["state"], "pending-ack-expired")
        self.assertGreaterEqual(output[1]["assignment"]["pending_age_seconds"], 10)
        self.assertEqual(len(executed_batches), 1)
        self.assertEqual(len(executed_batches[0]), 1)
        self.assertIn("taskboard-T2", executed_batches[0][0])
        self.assertNotIn("taskboard-T1", executed_batches[0][0])
        self.assertIn("assignment acknowledgement timed out", " ".join(output[1]["actions"]))
        self.assertEqual(events[1]["assignment_state"], "pending-ack-expired")
        self.assertEqual(events[1]["assignment_pending_age_seconds"], 10)

    def test_execute_launches_recovers_selected_role_for_stalled_task_when_liveness_is_missing(self):
        executed_batches = []

        def fake_execute(commands):
            executed_batches.append(list(commands))
            return [
                {
                    "command": command,
                    "returncode": 0,
                    "output": "",
                }
                for command in commands
            ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-004.v1.{ROLE_PRIORITY['T0'][5][1]}.md"
            task_path = taskboard / task_name
            task_path.write_text("# execute\n\n**Wave**: 1\n", encoding="utf-8")
            old_time = task_path.stat().st_mtime - (45 * 60)
            os.utime(task_path, (old_time, old_time))

            session_dir = root / ".taskboard" / "sessions"
            session_dir.mkdir(parents=True)
            for role in ("T1", "T2", "T3"):
                payload = {
                    "role": role,
                    "title": f"taskboard-{role}",
                    "status": "alive",
                    "pid": 123,
                    "last_seen": 4102444800,
                }
                if role == "T3":
                    payload.update({"task": task_name, "assignment_id": f"T3:{task_name}"})
                (session_dir / f"taskboard-{role}.json").write_text(json.dumps(payload), encoding="utf-8")

            with patch("taskboard_loop.execute_commands", fake_execute):
                output = loop_module.run_loop(
                    root,
                    "Ship demo",
                    30,
                    999999999,
                    "powershell",
                    'codex --prompt-file "{target_file}"',
                    True,
                    1,
                    0,
                    300,
                    True,
                    root / ".taskboard" / "t0" / "latest.json",
                    root / ".taskboard" / "targets",
                    300,
                    root / ".taskboard" / "t0" / "events.jsonl",
                )
            events = [
                json.loads(line)
                for line in (root / ".taskboard" / "t0" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(output[0]["state"], "attention")
        self.assertEqual(output[0]["assignment"]["state"], "acknowledged")
        self.assertEqual(len(executed_batches), 1)
        self.assertEqual(len(executed_batches[0]), 1)
        self.assertIn("taskboard-T3", executed_batches[0][0])
        self.assertNotIn("taskboard-T1", executed_batches[0][0])
        self.assertIn("stalled TASK", " ".join(output[0]["actions"]))
        self.assertEqual(events[0]["stalled_recovery_count"], 1)
        self.assertEqual(events[0]["stalled_recoveries"][0]["role"], "T3")
        self.assertEqual(events[0]["stalled_recoveries"][0]["role_liveness_state"], "missing")

    def test_execute_launches_reissues_target_for_stalled_task_when_liveness_is_alive(self):
        executed_batches = []

        def fake_execute(commands):
            executed_batches.append(list(commands))
            return [
                {
                    "command": command,
                    "returncode": 0,
                    "output": "",
                }
                for command in commands
            ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-004.v1.{ROLE_PRIORITY['T0'][5][1]}.md"
            task_path = taskboard / task_name
            task_path.write_text("# execute\n\n**Wave**: 1\n", encoding="utf-8")
            old_time = task_path.stat().st_mtime - (45 * 60)
            os.utime(task_path, (old_time, old_time))

            alive = root / ".taskboard" / "alive" / "T3"
            alive.parent.mkdir(parents=True)
            alive.touch()
            session_dir = root / ".taskboard" / "sessions"
            session_dir.mkdir(parents=True)
            for role in ("T1", "T2", "T3"):
                payload = {
                    "role": role,
                    "title": f"taskboard-{role}",
                    "status": "alive",
                    "pid": 123,
                    "last_seen": 4102444800,
                }
                if role == "T3":
                    payload.update({"task": task_name, "assignment_id": f"T3:{task_name}"})
                (session_dir / f"taskboard-{role}.json").write_text(json.dumps(payload), encoding="utf-8")

            with patch("taskboard_loop.execute_commands", fake_execute):
                output = loop_module.run_loop(
                    root,
                    "Ship demo",
                    30,
                    999999999,
                    "powershell",
                    'codex --prompt-file "{target_file}"',
                    True,
                    1,
                    0,
                    300,
                    True,
                    root / ".taskboard" / "t0" / "latest.json",
                    root / ".taskboard" / "targets",
                    300,
                    root / ".taskboard" / "t0" / "events.jsonl",
                )
            events = [
                json.loads(line)
                for line in (root / ".taskboard" / "t0" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        actions = " ".join(output[0]["actions"])
        self.assertEqual(output[0]["state"], "attention")
        self.assertEqual(output[0]["queue_health"]["stalled_tasks"][0]["action_kind"], "reissue-target")
        self.assertEqual(output[0]["stalled_recovery_commands"], [])
        self.assertEqual(output[0]["executed_commands"], [])
        self.assertEqual(executed_batches, [])
        self.assertIn("reissue target to taskboard-T3", actions)
        self.assertEqual(events[0]["stalled_recovery_count"], 0)

    def test_spawn_refused_launch_failure_writes_user_owned_windows_scripts(self):
        def fake_execute(commands):
            return [
                {
                    "command": commands[0],
                    "returncode": 1,
                    "output": "Failed to authenticate. API Error: 403 Request not allowed",
                }
            ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            with patch("taskboard_loop.execute_commands", fake_execute):
                output = loop_module.run_loop(
                    root,
                    "Ship demo",
                    30,
                    300,
                    "powershell",
                    f'"{sys.executable}" -c "print(123)" --prompt-file "{{target_file}}"',
                    True,
                    1,
                    0,
                    300,
                    True,
                    root / ".taskboard" / "t0" / "latest.json",
                    root / ".taskboard" / "targets",
                    300,
                    root / ".taskboard" / "t0" / "events.jsonl",
                )
            payload = output[0]
            manual_files = payload["manual_launch_files"]
            open_tabs = Path(manual_files["open_tabs"])
            launch_role = Path(manual_files["launch_role"])
            open_tabs_exists = open_tabs.exists()
            launch_role_exists = launch_role.exists()
            open_tabs_text = open_tabs.read_text(encoding="utf-8")
            launch_role_text = launch_role.read_text(encoding="utf-8")

        self.assertTrue(open_tabs_exists)
        self.assertTrue(launch_role_exists)
        open_tabs_text.encode("ascii")
        launch_role_text.encode("ascii")
        self.assertIn("taskboard-T1", open_tabs_text)
        self.assertIn("taskboard-T2", open_tabs_text)
        self.assertIn("taskboard-T3", open_tabs_text)
        self.assertIn("Invoke-Expression", launch_role_text)
        self.assertIn("Run the generated user-owned Windows Terminal script", " ".join(payload["actions"]))


if __name__ == "__main__":
    unittest.main()
