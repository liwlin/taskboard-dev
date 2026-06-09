from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
import contextlib
import io
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LOOP_SCRIPT = ROOT / "scripts" / "taskboard_loop.py"
PROGRESS_SCRIPT = ROOT / "scripts" / "taskboard_progress.py"
START_SCRIPT = ROOT / "scripts" / "taskboard_start.py"
sys.path.insert(0, str(ROOT / "scripts"))
from taskboard_next import ROLE_PRIORITY  # noqa: E402
import taskboard_start as start_module  # noqa: E402


T2_CODE_REVIEW = ROLE_PRIORITY["T0"][1][1]
T3_EXECUTE = ROLE_PRIORITY["T0"][5][1]
T1_REVISE = ROLE_PRIORITY["T0"][6][1]


class TaskboardProgressTest(unittest.TestCase):
    def run_text(self, script: Path, root: Path, *args: str) -> str:
        result = subprocess.run(
            [sys.executable, str(script), "--root", str(root), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout

    def run_json(self, script: Path, root: Path, *args: str):
        result = subprocess.run(
            [sys.executable, str(script), "--root", str(root), "--format", "json", *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return json.loads(result.stdout)

    def test_progress_summarizes_latest_t0_snapshot_for_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-003.v1.{T2_CODE_REVIEW}-L2.md"
            (taskboard / task_name).write_text("# task\n\n**Wave**: 1\n", encoding="utf-8")

            self.run_json(LOOP_SCRIPT, root, "--goal", "Ship demo")
            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["kind"], "taskboard-t0-progress")
        self.assertEqual(progress["goal"], "Ship demo")
        self.assertEqual(progress["state"], "attention")
        self.assertEqual(progress["next_role"], "T2")
        self.assertEqual(progress["task"], task_name)
        self.assertEqual(
            progress["resume_command"],
            f'python scripts/taskboard_start.py --root "{root}" --auto',
        )
        self.assertEqual(progress["assignment_state"], "unassigned")
        self.assertIn("T0 is managing T1/T2/T3", progress["user_summary"])
        self.assertIn("No user action required", progress["user_action"])
        self.assertIn("manager-only", progress["boundary"])

    def test_progress_surfaces_assignment_recovery_without_user_role_management(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-005.v1.{T2_CODE_REVIEW}-L2.md"
            (taskboard / task_name).write_text("# review\n\n**Wave**: 1\n", encoding="utf-8")

            self.run_json(LOOP_SCRIPT, root, "--goal", "Ship demo")
            progress = self.run_json(PROGRESS_SCRIPT, root)
            text = self.run_text(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["assignment_role"], "T2")
        self.assertEqual(progress["assignment_task"], task_name)
        self.assertIn("missing", progress["assignment_reason"])
        self.assertIn("T0 will reissue target to taskboard-T2", progress["user_action"])
        self.assertIn("assignment_role=T2", text)
        self.assertIn(f"assignment_task={task_name}", text)
        self.assertIn("assignment_reason=taskboard-T2 is missing", text)

    def test_progress_uses_saved_goal_when_no_snapshot_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_json(START_SCRIPT, root, "--goal", "Ship demo", "--iterations", "1", "--no-state-file")
            progress = self.run_json(PROGRESS_SCRIPT, root)
            text = self.run_text(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["goal"], "Ship demo")
        self.assertEqual(progress["state"], "needs-supervisor-run")
        self.assertEqual(
            progress["resume_command"],
            f'python scripts/taskboard_start.py --root "{root}" --auto',
        )
        self.assertIn(f'resume_command=python scripts/taskboard_start.py --root "{root}" --auto', text)
        self.assertIn("Start or resume T0", progress["user_action"])
        self.assertIn("not ask you to manage T1/T2/T3", progress["user_summary"])

    def test_progress_recovers_needs_goal_from_latest_event_without_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_json(
                START_SCRIPT,
                root,
                "--auto",
                "--no-state-file",
                "--launcher",
                "none",
            )
            progress = self.run_json(PROGRESS_SCRIPT, root)
            text = self.run_text(PROGRESS_SCRIPT, root)

        self.assertFalse((root / ".taskboard" / "t0" / "latest.json").exists())
        self.assertEqual(progress["latest_event"]["dispatch_state"], "needs-goal")
        self.assertEqual(progress["state"], "needs-goal")
        self.assertEqual(progress["resume_command"], "")
        self.assertEqual(progress["user_action"], "Provide one user goal to T0.")
        self.assertIn("needs one user goal", progress["user_summary"])
        self.assertIn("state=needs-goal", text)
        self.assertIn("latest_event_dispatch_state=needs-goal", text)

    def test_progress_surfaces_one_command_auto_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_json(
                START_SCRIPT,
                root,
                "--goal",
                "Ship demo",
                "--auto",
                "--iterations",
                "1",
                "--launcher",
                "none",
            )
            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertTrue(progress["auto_mode"])
        self.assertEqual(progress["starter_mode"], "auto")
        self.assertIn("one-command", progress["starter_boundary"])

    def test_progress_resume_command_preserves_t0_runtime_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_json(
                START_SCRIPT,
                root,
                "--goal",
                "Ship demo",
                "--auto",
                "--iterations",
                "1",
                "--launcher",
                "tmux",
                "--agent-template",
                'custom-agent --file "{target_file}"',
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
            )
            progress = self.run_json(PROGRESS_SCRIPT, root)
            text = self.run_text(PROGRESS_SCRIPT, root)

        self.assertIn("--launcher tmux", progress["resume_command"])
        self.assertIn('--agent-template "custom-agent --file \\"{target_file}\\""', progress["resume_command"])
        self.assertIn("--stale-minutes 12", progress["resume_command"])
        self.assertIn("--stale-seconds 34", progress["resume_command"])
        self.assertIn("--assignment-lease-seconds 56", progress["resume_command"])
        self.assertIn("--launch-lease-seconds 78", progress["resume_command"])
        self.assertIn("--interval-seconds 9", progress["resume_command"])
        self.assertIn(progress["resume_command"], text)

    def test_progress_resume_command_uses_latest_event_resume_config_without_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_json(
                START_SCRIPT,
                root,
                "--goal",
                "Ship demo",
                "--auto",
                "--iterations",
                "1",
                "--no-state-file",
                "--launcher",
                "tmux",
                "--agent-template",
                'custom-agent --file "{target_file}"',
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
            )
            progress = self.run_json(PROGRESS_SCRIPT, root)
            text = self.run_text(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["state"], "needs-supervisor-run")
        self.assertIn("--launcher tmux", progress["resume_command"])
        self.assertIn('--agent-template "custom-agent --file \\"{target_file}\\""', progress["resume_command"])
        self.assertIn("--stale-minutes 12", progress["resume_command"])
        self.assertIn("--stale-seconds 34", progress["resume_command"])
        self.assertIn("--assignment-lease-seconds 56", progress["resume_command"])
        self.assertIn("--launch-lease-seconds 78", progress["resume_command"])
        self.assertIn("--interval-seconds 9", progress["resume_command"])
        self.assertIn(progress["resume_command"], text)

    def test_progress_resumes_t0_from_persisted_interruption_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            with patch("taskboard_start.run_loop", side_effect=KeyboardInterrupt):
                with contextlib.redirect_stdout(io.StringIO()):
                    result = start_module.main(
                        [
                            "--root",
                            str(root),
                            "--goal",
                            "Ship demo",
                            "--auto",
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
                            "--interval-seconds",
                            "9",
                            "--format",
                            "json",
                        ]
                    )
            progress = self.run_json(PROGRESS_SCRIPT, root)
            text = self.run_text(PROGRESS_SCRIPT, root)

        self.assertEqual(result, 130)
        self.assertEqual(progress["state"], "interrupted")
        self.assertIn("--launcher tmux", progress["resume_command"])
        self.assertIn("--stale-minutes 12", progress["resume_command"])
        self.assertIn("--stale-seconds 34", progress["resume_command"])
        self.assertIn("--assignment-lease-seconds 56", progress["resume_command"])
        self.assertIn("--launch-lease-seconds 78", progress["resume_command"])
        self.assertIn("--interval-seconds 9", progress["resume_command"])
        self.assertIn("Resume T0", progress["user_action"])
        self.assertIn("do not manage T1/T2/T3", progress["user_action"])
        self.assertIn(progress["resume_command"], text)

    def test_progress_resumes_t0_from_interruption_event_without_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            with patch("taskboard_start.run_loop", side_effect=KeyboardInterrupt):
                with contextlib.redirect_stdout(io.StringIO()):
                    result = start_module.main(
                        [
                            "--root",
                            str(root),
                            "--goal",
                            "Ship demo",
                            "--auto",
                            "--no-state-file",
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
                            "--interval-seconds",
                            "9",
                            "--format",
                            "json",
                        ]
                    )
            progress = self.run_json(PROGRESS_SCRIPT, root)
            text = self.run_text(PROGRESS_SCRIPT, root)

        self.assertEqual(result, 130)
        self.assertFalse((root / ".taskboard" / "t0" / "latest.json").exists())
        self.assertEqual(progress["state"], "interrupted")
        self.assertEqual(progress["latest_event"]["state"], "interrupted")
        self.assertIn("--launcher tmux", progress["resume_command"])
        self.assertIn("--stale-minutes 12", progress["resume_command"])
        self.assertIn("--stale-seconds 34", progress["resume_command"])
        self.assertIn("--assignment-lease-seconds 56", progress["resume_command"])
        self.assertIn("--launch-lease-seconds 78", progress["resume_command"])
        self.assertIn("--interval-seconds 9", progress["resume_command"])
        self.assertIn("Resume T0", progress["user_action"])
        self.assertIn("do not manage T1/T2/T3", progress["user_action"])
        self.assertIn("latest_event_state=interrupted", text)
        self.assertIn(progress["resume_command"], text)

    def test_progress_surfaces_failed_t0_launch_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".taskboard" / "t0"
            state_dir.mkdir(parents=True)
            snapshot = {
                "kind": "taskboard-t0-supervisor-state",
                "goal": "Ship demo",
                "latest": {
                    "state": "attention",
                    "actions": ["launch/recover managed role sessions with generated commands"],
                    "dispatch": {
                        "state": "dispatch",
                        "next_role": "T1",
                        "task": "none",
                    },
                    "assignment": {"state": "none"},
                    "queue_health": {"active_count": 0},
                    "session_probe": {"missing_roles": ["T1"], "stale_roles": []},
                    "executed_commands": [
                        {
                            "command": "wt -w taskboard new-tab --title taskboard-T1",
                            "returncode": 1,
                            "output": "wt was not found",
                        }
                    ],
                },
            }
            (state_dir / "latest.json").write_text(json.dumps(snapshot), encoding="utf-8")

            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["launch_failure_count"], 1)
        self.assertIn("wt was not found", progress["launch_failures"][0]["output"])
        self.assertIn("T0 launch/recovery failed", progress["user_action"])
        self.assertIn("T0 could not launch or recover", progress["user_summary"])

    def test_progress_reads_bom_encoded_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".taskboard" / "t0"
            state_dir.mkdir(parents=True)
            snapshot = {
                "kind": "taskboard-t0-supervisor-state",
                "goal": "Ship demo",
                "latest": {
                    "state": "attention",
                    "dispatch": {"state": "dispatch", "next_role": "T1", "task": "none"},
                    "assignment": {"state": "none"},
                    "queue_health": {"active_count": 0},
                    "session_probe": {"missing_roles": ["T1"], "stale_roles": []},
                },
            }
            (state_dir / "latest.json").write_bytes(
                json.dumps(snapshot).encode("utf-8-sig")
            )

            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["goal"], "Ship demo")
        self.assertEqual(progress["state"], "attention")

    def test_progress_summarizes_suppressed_launches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".taskboard" / "t0"
            state_dir.mkdir(parents=True)
            snapshot = {
                "kind": "taskboard-t0-supervisor-state",
                "goal": "Ship demo",
                "latest": {
                    "state": "attention",
                    "actions": ["wait for T1 launch lease active; do not duplicate managed terminals"],
                    "dispatch": {"state": "dispatch", "next_role": "T1", "task": "none"},
                    "assignment": {"state": "none"},
                    "queue_health": {"active_count": 0},
                    "session_probe": {"missing_roles": ["T1"], "stale_roles": []},
                    "suppressed_launches": [
                        {
                            "role": "T1",
                            "reason": "launch-lease-active",
                            "remaining_seconds": 240,
                        }
                    ],
                },
            }
            (state_dir / "latest.json").write_text(json.dumps(snapshot), encoding="utf-8")

            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["suppressed_launch_count"], 1)
        self.assertIn("T1", progress["suppressed_launches"][0]["role"])
        self.assertIn("waiting for recent T0 launch", progress["user_summary"])
        self.assertIn("No user action required", progress["user_action"])

    def test_progress_surfaces_t0_stop_gate_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            (taskboard / "TASK-009.v2.T1-decision.md").write_text(
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
            self.run_json(LOOP_SCRIPT, root, "--goal", "Ship demo")

            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["stop_gate_count"], 1)
        self.assertIn("Product decision", progress["stop_gates"][0]["gate"])
        self.assertIn("T0 stop gate requires user decision", progress["user_action"])
        self.assertIn("beta banner", progress["user_summary"])
        self.assertIn("taskboard_decide.py", progress["decision_command"])
        self.assertIn("--task TASK-009.v2.T1-decision.md", progress["decision_command"])
        self.assertIn('--decision "<user answer>"', progress["decision_command"])

    def test_progress_surfaces_completion_audit_when_t0_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "docs" / "taskboard" / "archive"
            archive.mkdir(parents=True)
            (archive / "TASK-001.v1.done.md").write_text("# done\n", encoding="utf-8")
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text(
                "# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8"
            )
            (root / "docs" / "dev-log.md").write_text(
                "# Development Log\n\n- TASK-001 completed and verified.\n",
                encoding="utf-8",
            )
            self.run_json(LOOP_SCRIPT, root, "--goal", "Ship demo")

            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertTrue(progress["completion_ready"])
        self.assertEqual(progress["completion_missing_evidence"], [])
        self.assertEqual(progress["completion_audit"]["state"], "complete-ready")
        self.assertEqual(progress["resume_command"], "")
        self.assertIn("Review T0's completion summary", progress["user_action"])

    def test_progress_recovers_complete_state_from_latest_event_without_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "docs" / "taskboard" / "archive"
            archive.mkdir(parents=True)
            (archive / "TASK-001.v1.done.md").write_text("# done\n", encoding="utf-8")
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text(
                "# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8"
            )
            (root / "docs" / "dev-log.md").write_text(
                "# Development Log\n\n- TASK-001 completed and verified.\n",
                encoding="utf-8",
            )
            self.run_json(
                LOOP_SCRIPT,
                root,
                "--goal",
                "Ship demo",
                "--no-state-file",
            )

            progress = self.run_json(PROGRESS_SCRIPT, root)
            text = self.run_text(PROGRESS_SCRIPT, root)

        self.assertFalse((root / ".taskboard" / "t0" / "latest.json").exists())
        self.assertEqual(progress["latest_event"]["dispatch_state"], "complete")
        self.assertTrue(progress["latest_event"]["completion_ready"])
        self.assertEqual(progress["state"], "complete")
        self.assertTrue(progress["completion_ready"])
        self.assertEqual(progress["resume_command"], "")
        self.assertIn("Review T0's completion summary", progress["user_action"])
        self.assertIn("state=complete", text)
        self.assertIn("latest_event_completion_ready=True", text)

    def test_progress_text_prints_missing_completion_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            (root / "docs" / "PROJECT.md").write_text("# PROJECT\n\nShip demo\n", encoding="utf-8")
            (root / "docs" / "STATE.md").write_text(
                "# STATE\n\n**Goal Complete**: yes\n", encoding="utf-8"
            )
            (root / "docs" / "dev-log.md").write_text("# Development Log\n", encoding="utf-8")
            self.run_json(LOOP_SCRIPT, root, "--goal", "Ship demo")

            text = self.run_text(PROGRESS_SCRIPT, root)
            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertIn("completion_ready=False", text)
        self.assertIn("completion_audit_state=incomplete", text)
        self.assertIn("completion_missing_evidence=no archived TASK evidence", text)
        self.assertIn("dev-log has no completion entries", text)
        self.assertIn("No user action required", progress["user_action"])
        self.assertIn("T0 will wake T1", progress["user_action"])

    def test_progress_surfaces_t0_event_log_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            self.run_json(
                LOOP_SCRIPT,
                root,
                "--goal",
                "Ship demo",
                "--iterations",
                "2",
                "--interval-seconds",
                "0",
            )

            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["event_count"], 2)
        self.assertEqual(progress["latest_event"]["kind"], "taskboard-t0-supervisor-event")
        self.assertEqual(progress["latest_event"]["iteration"], 2)
        self.assertIn("append-only", progress["event_log_boundary"])

    def test_progress_text_prints_t0_event_log_recovery_lines_without_latest_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            task_name = f"TASK-004.v1.{T3_EXECUTE}.md"
            (taskboard / task_name).write_text("# execute\n\n**Wave**: 1\n", encoding="utf-8")
            self.run_json(
                LOOP_SCRIPT,
                root,
                "--goal",
                "Ship demo",
                "--no-state-file",
            )

            text = self.run_text(PROGRESS_SCRIPT, root)
            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertIn("event_count=1", text)
        self.assertEqual(progress["next_role"], "T3")
        self.assertEqual(progress["task"], task_name)
        self.assertEqual(progress["assignment_state"], "unassigned")
        self.assertEqual(progress["assignment_role"], "T3")
        self.assertEqual(progress["assignment_task"], task_name)
        self.assertEqual(progress["assignment_reason"], "taskboard-T3 is missing")
        self.assertEqual(progress["assignment_expected_id"], f"T3:{task_name}")
        self.assertIn("T0 will reissue target to taskboard-T3", progress["user_action"])
        self.assertIn("latest_event_state=attention", text)
        self.assertIn("latest_event_next_role=T3", text)
        self.assertIn(f"latest_event_task={task_name}", text)
        self.assertIn("latest_event_assignment_role=T3", text)
        self.assertIn(f"latest_event_assignment_task={task_name}", text)
        self.assertIn("latest_event_assignment_reason=taskboard-T3 is missing", text)
        self.assertIn(f"latest_event_assignment_expected_id=T3:{task_name}", text)
        self.assertIn("latest_event_completion_ready=False", text)

    def test_progress_text_prints_latest_event_launch_failure_details_without_latest_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".taskboard" / "t0"
            state_dir.mkdir(parents=True)
            (state_dir / "goal.json").write_text(
                json.dumps({"goal": "Ship demo"}),
                encoding="utf-8",
            )
            event = {
                "kind": "taskboard-t0-supervisor-event",
                "iteration": 1,
                "state": "attention",
                "next_role": "T1",
                "task": "none",
                "launch_failure_count": 1,
                "launch_failures": [
                    {
                        "command": "wt -w taskboard new-tab --title taskboard-T1",
                        "returncode": 1,
                        "output": "wt was not found",
                    }
                ],
                "completion_ready": False,
            }
            (state_dir / "events.jsonl").write_text(
                json.dumps(event) + "\n",
                encoding="utf-8",
            )

            text = self.run_text(PROGRESS_SCRIPT, root)
            progress = self.run_json(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["launch_failure_count"], 1)
        self.assertIn("wt was not found", progress["launch_failures"][0]["output"])
        self.assertIn("T0 launch/recovery failed", progress["user_action"])
        self.assertIn("T0 could not launch or recover", progress["user_summary"])
        self.assertIn("latest_event_launch_failure_count=1", text)
        self.assertIn(
            "latest_event_launch_failure_command=wt -w taskboard new-tab --title taskboard-T1",
            text,
        )
        self.assertIn("latest_event_launch_failure_returncode=1", text)
        self.assertIn("latest_event_launch_failure_output=wt was not found", text)

    def test_progress_surfaces_latest_event_suppressed_launches_without_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".taskboard" / "t0"
            state_dir.mkdir(parents=True)
            (state_dir / "goal.json").write_text(
                json.dumps({"goal": "Ship demo"}),
                encoding="utf-8",
            )
            event = {
                "kind": "taskboard-t0-supervisor-event",
                "iteration": 1,
                "state": "attention",
                "next_role": "T1",
                "task": "none",
                "suppressed_launch_count": 1,
                "suppressed_launches": [
                    {
                        "role": "T1",
                        "reason": "launch-lease-active",
                        "remaining_seconds": 240,
                    }
                ],
                "completion_ready": False,
            }
            (state_dir / "events.jsonl").write_text(
                json.dumps(event) + "\n",
                encoding="utf-8",
            )

            progress = self.run_json(PROGRESS_SCRIPT, root)
            text = self.run_text(PROGRESS_SCRIPT, root)

        self.assertEqual(progress["suppressed_launch_count"], 1)
        self.assertEqual(progress["suppressed_launches"][0]["role"], "T1")
        self.assertIn("waiting for recent T0 launch", progress["user_summary"])
        self.assertIn("No user action required", progress["user_action"])
        self.assertIn("latest_event_state=attention", text)

    def test_progress_surfaces_queue_metrics_for_user_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            (taskboard / f"TASK-001.v1.{T1_REVISE}.md").write_text(
                "# revise\n\n**Wave**: 3\n", encoding="utf-8"
            )
            (taskboard / f"TASK-002.v1.{T2_CODE_REVIEW}.md").write_text(
                "# review\n\n**Wave**: 1\n", encoding="utf-8"
            )
            stale_task = taskboard / f"TASK-003.v1.{T3_EXECUTE}.md"
            stale_task.write_text("# execute\n\n**Wave**: 2\n", encoding="utf-8")
            old_time = stale_task.stat().st_mtime - (45 * 60)
            os.utime(stale_task, (old_time, old_time))

            self.run_json(
                LOOP_SCRIPT,
                root,
                "--goal",
                "Ship dashboard",
                "--stale-minutes",
                "30",
            )
            progress = self.run_json(PROGRESS_SCRIPT, root)

        metrics = progress["queue_metrics"]
        self.assertEqual(metrics["active_count"], 3)
        self.assertEqual(metrics["stalled_count"], 1)
        self.assertEqual(metrics["role_counts"], {"T1": 1, "T2": 1, "T3": 1})
        self.assertEqual(metrics["next_role"], "T2")
        self.assertFalse(metrics["user_action_required"])
        self.assertIn("queue metrics", metrics["boundary"])
        self.assertIn("queue_metrics", progress["user_summary"])

    def test_progress_text_prints_queue_metrics_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taskboard = root / "docs" / "taskboard"
            taskboard.mkdir(parents=True)
            (taskboard / f"TASK-001.v1.{T1_REVISE}.md").write_text(
                "# revise\n\n**Wave**: 3\n", encoding="utf-8"
            )
            (taskboard / f"TASK-002.v1.{T2_CODE_REVIEW}.md").write_text(
                "# review\n\n**Wave**: 1\n", encoding="utf-8"
            )
            stale_task = taskboard / f"TASK-003.v1.{T3_EXECUTE}.md"
            stale_task.write_text("# execute\n\n**Wave**: 2\n", encoding="utf-8")
            old_time = stale_task.stat().st_mtime - (45 * 60)
            os.utime(stale_task, (old_time, old_time))

            self.run_json(
                LOOP_SCRIPT,
                root,
                "--goal",
                "Ship dashboard",
                "--stale-minutes",
                "30",
            )
            text = self.run_text(PROGRESS_SCRIPT, root)

        self.assertIn("queue_metrics_active_count=3", text)
        self.assertIn("queue_metrics_stalled_count=1", text)
        self.assertIn("queue_metrics_role_counts=T1:1,T2:1,T3:1", text)
        self.assertIn("queue_metrics_next_role=T2", text)


if __name__ == "__main__":
    unittest.main()
