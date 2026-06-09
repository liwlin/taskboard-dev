from pathlib import Path
import json
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
                )

        self.assertEqual([len(batch) for batch in executed_batches], [3])
        self.assertEqual(len(output[0]["executed_commands"]), 3)
        self.assertEqual(output[1]["executed_commands"], [])
        self.assertEqual(
            [item["role"] for item in output[1]["suppressed_launches"]],
            ["T1", "T2", "T3"],
        )
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


if __name__ == "__main__":
    unittest.main()
