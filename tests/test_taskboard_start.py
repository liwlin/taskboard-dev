from pathlib import Path
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "taskboard_start.py"
sys.path.insert(0, str(ROOT / "scripts"))
import taskboard_start as start_module  # noqa: E402


class TaskboardStartTest(unittest.TestCase):
    def run_start(self, root: Path, *args: str) -> list[dict]:
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

    def test_starter_uses_file_backed_t0_defaults_without_executing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_start(root, "--goal", "Ship demo", "--dry-run", "--iterations", "1")
            goal_file = root / ".taskboard" / "t0" / "goal.json"
            saved_goal = json.loads(goal_file.read_text(encoding="utf-8"))
            t1_target = root / ".taskboard" / "targets" / "taskboard-T1.md"
            t1_launch = root / ".taskboard" / "targets" / "taskboard-T1.launch.ps1"
            t1_exists = t1_target.exists()
            t1_launch_exists = t1_launch.exists()
            t1_launch_text = t1_launch.read_text(encoding="utf-8") if t1_launch_exists else ""
            event_log = root / ".taskboard" / "t0" / "events.jsonl"
            events = [
                json.loads(line)
                for line in event_log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        payload = output[0]
        self.assertEqual(saved_goal["kind"], "taskboard-t0-goal")
        self.assertEqual(saved_goal["goal"], "Ship demo")
        self.assertEqual(payload["dispatch"]["launcher"], "windows-terminal")
        self.assertEqual(len(payload["launch_commands"]), 3)
        self.assertEqual(payload["executed_commands"], [])
        self.assertIn("taskboard-T1.launch.ps1", payload["launch_commands"][0])
        self.assertIn("-File", payload["launch_commands"][0])
        self.assertNotIn("-Command", payload["launch_commands"][0])
        self.assertNotIn("Ship demo", payload["launch_commands"][0])
        self.assertTrue(t1_exists)
        self.assertTrue(t1_launch_exists)
        self.assertIn("read the UTF-8 target file", t1_launch_text)
        self.assertIn("taskboard-T1.md", t1_launch_text)
        self.assertIn("taskboard.py", t1_launch_text)
        self.assertIn("--root . alive T1", t1_launch_text)
        self.assertIn("CLAUDE_CODE_GIT_BASH_PATH", t1_launch_text)
        self.assertIn("--dangerously-skip-permissions", t1_launch_text)
        self.assertLess(
            t1_launch_text.index("--root . alive T1"),
            t1_launch_text.index("& claude --name 'taskboard-T1' --dangerously-skip-permissions $prompt"),
        )
        self.assertIn("& claude --name 'taskboard-T1' --dangerously-skip-permissions $prompt", t1_launch_text)
        self.assertNotIn("Ship demo", t1_launch_text)
        self.assertEqual(events[0]["kind"], "taskboard-t0-supervisor-event")
        self.assertEqual(events[0]["goal"], "Ship demo")

    def test_starter_goal_defaults_to_auto_mode_until_completion(self):
        captured = {}

        def fake_run_loop(*args):
            captured["execute_launches"] = args[6]
            captured["iterations"] = args[7]
            captured["metadata"] = args[16]
            return [{"state": "active"}]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            with patch("taskboard_start.run_loop", fake_run_loop):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = start_module.main(
                        [
                            "--root",
                            str(root),
                            "--goal",
                            "Ship demo",
                            "--launcher",
                            "none",
                            "--format",
                            "json",
                        ]
                    )

        self.assertEqual(code, 0)
        self.assertTrue(captured["execute_launches"])
        self.assertIsNone(captured["iterations"])
        self.assertTrue(captured["metadata"]["auto_mode"])
        self.assertEqual(captured["metadata"]["starter_mode"], "auto")

    def test_starter_rejects_target_file_template_when_targets_are_disabled(self):
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
                    "--no-target-files",
                    "--agent-template",
                    'codex --prompt-file "{target_file}"',
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            snapshot = json.loads((root / ".taskboard" / "t0" / "latest.json").read_text(encoding="utf-8"))
            events = [
                json.loads(line)
                for line in (root / ".taskboard" / "t0" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("agent-template references {target_file}", result.stdout)
        self.assertIn("enable target files or use {target}", result.stdout)
        self.assertEqual(snapshot["latest"]["state"], "config-error")
        self.assertIn("agent-template references {target_file}", snapshot["latest"]["error"])
        self.assertEqual(events[-1]["state"], "config-error")
        self.assertIn("agent-template references {target_file}", events[-1]["error"])

    def test_starter_preflights_missing_agent_command_before_launching_workers(self):
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
                    "__taskboard_missing_agent__ --prompt-file \"{target_file}\"",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            snapshot = json.loads((root / ".taskboard" / "t0" / "latest.json").read_text(encoding="utf-8"))
            events = [
                json.loads(line)
                for line in (root / ".taskboard" / "t0" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("agent command '__taskboard_missing_agent__'", result.stdout)
        self.assertIn("not found on PATH", result.stdout)
        self.assertEqual(snapshot["latest"]["state"], "config-error")
        self.assertIn("agent command '__taskboard_missing_agent__'", snapshot["latest"]["error"])
        self.assertEqual(snapshot["latest"]["launch_probe"]["recommended_backend"], "fix-config")
        self.assertEqual(events[-1]["state"], "config-error")
        self.assertIn("agent command '__taskboard_missing_agent__'", events[-1]["error"])
        self.assertEqual(events[-1]["launch_probe_recommended_backend"], "fix-config")

    def test_starter_auth_refused_preflight_generates_user_owned_worker_launcher(self):
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
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            payload = json.loads(result.stdout)[0]
            manual_files = payload["manual_launch_files"]
            open_tabs = Path(manual_files["open_tabs"])
            open_tabs_exists = open_tabs.exists()
            events = [
                json.loads(line)
                for line in (root / ".taskboard" / "t0" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(payload["launch_probe"]["kind"], "taskboard-launch-probe")
        self.assertEqual(payload["launch_probe"]["recommended_backend"], "subagent")
        self.assertEqual(payload["agent_preflight"]["state"], "spawn-refused")
        self.assertTrue(open_tabs_exists)
        self.assertIn("Run the generated user-owned Windows Terminal script", " ".join(payload["actions"]))
        self.assertEqual(events[-1]["state"], "attention")
        self.assertEqual(events[-1]["launch_probe_recommended_backend"], "subagent")
        self.assertEqual(events[-1]["launch_probe_state"], "spawn-refused")
        self.assertEqual(events[-1]["launch_failure_count"], 0)

    def test_starter_resumes_saved_goal_without_retyping_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_start(root, "--goal", "Ship demo", "--dry-run", "--iterations", "1")
            resumed = self.run_start(root, "--dry-run", "--iterations", "1")

        self.assertEqual(resumed[0]["goal"], "Ship demo")
        self.assertEqual(resumed[0]["dispatch"]["state"], "dispatch")
        self.assertIn("Ship demo", resumed[0]["dispatch"]["target"])

    def test_starter_can_use_tmux_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_start(root, "--goal", "Ship demo", "--dry-run", "--iterations", "1", "--launcher", "tmux")

        self.assertEqual(output[0]["dispatch"]["launcher"], "tmux")
        self.assertIn("tmux new-session", output[0]["launch_commands"][0])

    def test_starter_can_disable_event_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_start(root, "--goal", "Ship demo", "--dry-run", "--iterations", "1", "--no-event-log")

        self.assertFalse((root / ".taskboard" / "t0" / "events.jsonl").exists())

    def test_starter_auto_mode_marks_one_command_automation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_start(
                root,
                "--goal",
                "Ship demo",
                "--auto",
                "--iterations",
                "1",
                "--launcher",
                "none",
            )

        self.assertTrue(output[0]["auto_mode"])
        self.assertEqual(output[0]["starter_mode"], "auto")
        self.assertIn("T0 one-command auto mode", output[0]["starter_boundary"])

    def test_starter_auto_mode_stops_when_goal_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            output = self.run_start(root, "--auto", "--launcher", "none")

        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["state"], "needs-goal")
        self.assertEqual(output[0]["dispatch"]["state"], "needs-goal")
        self.assertIn("ask user for one T0 goal", output[0]["actions"])

    def test_starter_auto_mode_persists_in_latest_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_start(
                root,
                "--goal",
                "Ship demo",
                "--auto",
                "--iterations",
                "1",
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
            snapshot = json.loads((root / ".taskboard" / "t0" / "latest.json").read_text(encoding="utf-8"))

        self.assertTrue(snapshot["latest"]["auto_mode"])
        self.assertEqual(snapshot["latest"]["starter_mode"], "auto")
        self.assertIn("T0 one-command auto mode", snapshot["latest"]["starter_boundary"])
        self.assertEqual(snapshot["latest"]["resume_config"]["launcher"], "tmux")
        self.assertEqual(snapshot["latest"]["resume_config"]["stale_minutes"], 12)
        self.assertEqual(snapshot["latest"]["resume_config"]["stale_seconds"], 34)
        self.assertEqual(snapshot["latest"]["resume_config"]["assignment_lease_seconds"], 56)
        self.assertEqual(snapshot["latest"]["resume_config"]["launch_lease_seconds"], 78)

    def test_starter_auto_mode_persists_in_event_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)

            self.run_start(
                root,
                "--goal",
                "Ship demo",
                "--auto",
                "--iterations",
                "1",
                "--launcher",
                "none",
            )
            event_log = root / ".taskboard" / "t0" / "events.jsonl"
            events = [
                json.loads(line)
                for line in event_log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertTrue(events[0]["auto_mode"])
        self.assertEqual(events[0]["starter_mode"], "auto")

    def test_starter_auto_mode_runs_until_completion_by_default(self):
        captured = {}

        def fake_run_loop(*args):
            captured["execute_launches"] = args[6]
            captured["iterations"] = args[7]
            return [{"state": "active"}]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            with patch("taskboard_start.run_loop", fake_run_loop):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = start_module.main(
                        [
                            "--root",
                            str(root),
                            "--goal",
                            "Ship demo",
                            "--auto",
                            "--launcher",
                            "none",
                            "--format",
                            "json",
                        ]
                    )

        self.assertEqual(code, 0)
        self.assertTrue(captured["execute_launches"])
        self.assertIsNone(captured["iterations"])

    def test_starter_auto_mode_respects_equals_style_iterations(self):
        captured = {}

        def fake_run_loop(*args):
            captured["iterations"] = args[7]
            return [{"state": "active"}]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            with patch("taskboard_start.run_loop", fake_run_loop):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = start_module.main(
                        [
                            "--root",
                            str(root),
                            "--goal",
                            "Ship demo",
                            "--auto",
                            "--iterations=1",
                            "--launcher",
                            "none",
                            "--format",
                            "json",
                        ]
                    )

        self.assertEqual(code, 0)
        self.assertEqual(captured["iterations"], 1)

    def test_starter_can_disable_stop_gate_stop_for_monitoring(self):
        captured = {}

        def fake_run_loop(*args):
            captured["stop_on_stop_gate"] = args[15]
            return [{"state": "stop-gate"}]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            with patch("taskboard_start.run_loop", fake_run_loop):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = start_module.main(
                        [
                            "--root",
                            str(root),
                            "--goal",
                            "Ship demo",
                            "--iterations",
                            "1",
                            "--no-stop-on-stop-gate",
                            "--format",
                            "json",
                        ]
                    )

        self.assertEqual(code, 0)
        self.assertFalse(captured["stop_on_stop_gate"])

    def test_starter_forwards_fallback_launchers_to_t0_loop(self):
        captured = {}

        def fake_run_loop(*args):
            captured["fallback_launchers"] = args[17]
            return [{"state": "active"}]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            with patch("taskboard_start.run_loop", fake_run_loop):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = start_module.main(
                        [
                            "--root",
                            str(root),
                            "--goal",
                            "Ship demo",
                            "--auto",
                            "--launcher",
                            "windows-terminal",
                            "--fallback-launcher",
                            "powershell",
                            "--format",
                            "json",
                        ]
                    )

        self.assertEqual(code, 0)
        self.assertEqual(captured["fallback_launchers"], ["powershell"])

    def test_starter_reports_t0_resume_command_on_keyboard_interrupt_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            stdout = io.StringIO()
            with patch("taskboard_start.run_loop", side_effect=KeyboardInterrupt):
                with contextlib.redirect_stdout(stdout):
                    code = start_module.main(
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

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 130)
        self.assertEqual(payload["kind"], "taskboard-t0-interruption")
        self.assertEqual(payload["state"], "interrupted")
        self.assertEqual(payload["goal"], "Ship demo")
        self.assertIn(f'python scripts/taskboard_start.py --root "{root}"', payload["resume_command"])
        self.assertNotIn("--auto", payload["resume_command"])
        self.assertIn("--launcher tmux", payload["resume_command"])
        self.assertIn("--stale-minutes 12", payload["resume_command"])
        self.assertIn("--stale-seconds 34", payload["resume_command"])
        self.assertIn("--assignment-lease-seconds 56", payload["resume_command"])
        self.assertIn("--launch-lease-seconds 78", payload["resume_command"])
        self.assertIn("--interval-seconds 9", payload["resume_command"])
        self.assertIn("Resume T0", payload["user_action"])
        self.assertIn("do not manage T1/T2/T3", payload["user_action"])

    def test_starter_persists_t0_interruption_recovery_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "taskboard").mkdir(parents=True)
            with patch("taskboard_start.run_loop", side_effect=KeyboardInterrupt):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = start_module.main(
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
            snapshot = json.loads((root / ".taskboard" / "t0" / "latest.json").read_text(encoding="utf-8"))
            events = [
                json.loads(line)
                for line in (root / ".taskboard" / "t0" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        latest = snapshot["latest"]
        self.assertEqual(code, 130)
        self.assertEqual(latest["kind"], "taskboard-t0-interruption")
        self.assertEqual(latest["state"], "interrupted")
        self.assertEqual(latest["resume_config"]["launcher"], "tmux")
        self.assertEqual(latest["resume_config"]["stale_minutes"], 12)
        self.assertEqual(events[-1]["state"], "interrupted")
        self.assertEqual(events[-1]["dispatch_state"], "interrupted")
        self.assertEqual(events[-1]["resume_config"]["launcher"], "tmux")


if __name__ == "__main__":
    unittest.main()
