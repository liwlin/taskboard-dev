from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class T0ContractTest(unittest.TestCase):
    def test_verifier_script_exists_and_is_documented(self):
        script = ROOT / "scripts" / "verify_t0_contract.py"
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertTrue(script.exists(), "scripts/verify_t0_contract.py should exist")
        self.assertIn("python scripts/verify_t0_contract.py", readme)

    def test_verifier_script_passes(self):
        script = ROOT / "scripts" / "verify_t0_contract.py"

        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("T0 contract verification passed", result.stdout)

    def test_release_package_includes_maintenance_scripts(self):
        package_script = (ROOT / "scripts" / "package.sh").read_text(encoding="utf-8")

        self.assertIn('mkdir -p "$STAGE_DIR/references" "$STAGE_DIR/scripts"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/package.sh"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_start.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_t0.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_loop.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_demo.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_completion.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_progress.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_watchdog.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_stopgates.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_decide.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_health.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_sessions.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_next.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/verify_t0_contract.py"', package_script)

    def test_role_default_tooling_contracts_are_documented(self):
        role_t1 = (ROOT / "references" / "role-t1.md").read_text(encoding="utf-8")
        role_t2 = (ROOT / "references" / "role-t2.md").read_text(encoding="utf-8")
        role_t3 = (ROOT / "references" / "role-t3.md").read_text(encoding="utf-8")

        self.assertIn("T1 MUST use available planning/brainstorming skills", role_t1)
        self.assertIn("manual planning only when", role_t1)

        self.assertIn("L2 code reviews default to an independent review tool", role_t2)
        self.assertIn("L3 code reviews MUST run dual-pass review", role_t2)
        self.assertIn("record the fallback reason", role_t2)

        self.assertIn("T3 MUST assess whether the implementation can be split", role_t3)
        self.assertIn(
            "T3 remains responsible for integration, final verification, and commit",
            role_t3,
        )
        self.assertIn("stay solo and record the reason", role_t3)

    def test_multi_agent_patterns_are_explicit(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        role_t0 = (ROOT / "references" / "role-t0.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")

        for required in (
            "### Multi-Agent Patterns Adopted",
            "**Manager/Worker**",
            "**Blackboard**",
            "**Independent Critic**",
            "**Liveness / Heartbeat**",
            "**Stop-Gate Aggregation**",
        ):
            self.assertIn(required, skill)

        self.assertIn("### T0 Liveness / Heartbeat Rules", role_t0)
        self.assertIn("stalled", role_t0)
        self.assertIn("## Multi-agent 借鉴原则", manual)
        self.assertIn("T0 是 manager，不是 worker", manual)

    def test_one_terminal_t0_default_is_unambiguous(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")

        self.assertIn("用户默认只需要手动打开 1 个入口终端", readme)
        self.assertIn("自动创建或恢复 `taskboard-T1`", readme)
        self.assertIn("不需要手动开 4 个终端", readme)
        self.assertIn("用户默认只需要手动打开 1 个入口终端", manual)
        self.assertIn("自动创建或恢复 `taskboard-T1`", manual)
        self.assertIn("不需要手动开 4 个终端", manual)

    def test_auto_terminal_isolation_contract_is_documented(self):
        role_t0 = (ROOT / "references" / "role-t0.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("auto-terminal mode", role_t0)
        self.assertIn("separate terminal session and isolated agent context", role_t0)
        self.assertIn("must not reuse one role's conversation context", role_t0)
        self.assertIn("auto-terminal 模式", manual)
        self.assertIn("角色之间不共享聊天上下文", manual)
        self.assertIn("python scripts/taskboard_t0.py --goal", readme)

    def test_multi_agent_synchronization_contract_is_documented(self):
        role_t0 = (ROOT / "references" / "role-t0.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")

        self.assertIn("### Multi-Agent Synchronization", role_t0)
        self.assertIn("Use blackboard synchronization, not chat-context synchronization", role_t0)
        self.assertIn("### 多 agent 信息同步机制", manual)
        self.assertIn("不是聊天上下文同步", manual)
        self.assertIn("角色之间的“记忆”必须先落到共享文件里", manual)

    def test_t0_scheduling_logic_is_documented(self):
        role_t0 = (ROOT / "references" / "role-t0.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")

        self.assertIn("### T0 Scheduling Logic", role_t0)
        self.assertIn("T0 schedules by event priority, not by arbitrary rotation", role_t0)
        self.assertIn("T0 的调度逻辑是", manual)
        self.assertIn("交付闭环优先", manual)
        self.assertIn("修复优先于新执行", manual)

    def test_t0_manager_only_boundary_is_documented(self):
        role_t0 = (ROOT / "references" / "role-t0.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")

        self.assertIn("T0 is manager-only", role_t0)
        self.assertIn("must not directly execute development tasks", role_t0)
        self.assertIn("T0 是管理员，不是开发执行者", manual)
        self.assertIn("T0 不直接执行开发任务", manual)

    def test_terminal_launcher_contract_is_documented(self):
        role_t0 = (ROOT / "references" / "role-t0.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        template = (ROOT / "references" / "taskboard-template.md").read_text(encoding="utf-8")

        self.assertIn("### T0 Terminal Launcher", role_t0)
        self.assertIn("--launcher windows-terminal", role_t0)
        self.assertIn("--agent-template", role_t0)
        self.assertIn("### T0 启动器脚本", manual)
        self.assertIn("Windows Terminal", manual)
        self.assertIn("tmux", manual)
        self.assertIn("--launcher windows-terminal", readme)
        self.assertIn("python scripts/taskboard_demo.py --root .taskboard-demo --with-heartbeats", readme)
        self.assertIn("python scripts/taskboard_start.py --goal", readme)
        self.assertIn("--auto", readme)
        self.assertIn("auto_mode", readme)
        self.assertIn("starter_mode", readme)
        self.assertIn("resume_config", readme)
        self.assertIn("--auto --iterations 1 --launcher none", readme)
        self.assertIn("needs-goal", readme)
        self.assertIn("suppresses worker launch/target/assignment", readme)
        self.assertIn("asks the summarized question through T0 only", readme)
        self.assertIn("--no-stop-on-stop-gate", readme)
        self.assertIn("stops after one `stop-gate` iteration", readme)
        self.assertIn("The stop-gate loop output includes `decision_command`", readme)
        self.assertIn("python scripts/taskboard_completion.py --root .", readme)
        self.assertIn("python scripts/taskboard_progress.py --root .", readme)
        self.assertIn("python scripts/taskboard_watchdog.py --root . --execute", readme)
        self.assertIn("taskboard-t0-watchdog", readme)
        self.assertIn("python scripts/taskboard_watchdog.py --root . --execute", manual)
        self.assertIn("taskboard-t0-watchdog", manual)
        self.assertIn("## Current T0 Control-Plane Entries", template)
        self.assertIn("python scripts/taskboard_watchdog.py --root . --execute", template)
        self.assertIn("taskboard-t0-watchdog", template)
        self.assertIn(".taskboard/t0/latest.json", template)
        self.assertIn(".taskboard/t0/events.jsonl", template)
        self.assertIn("Assignment lease expiry", template)
        self.assertIn("python scripts/taskboard_stopgates.py --root .", readme)
        self.assertIn("python scripts/taskboard_decide.py --root . --decision", readme)
        self.assertIn("decision_command", readme)
        self.assertIn("让 T1 根据用户决策继续修订", readme)
        self.assertIn("T0 launch/recovery failed", readme)
        self.assertIn("fix T0 launcher configuration", readme)
        self.assertIn("not to manage T1/T2/T3 directly", readme)
        self.assertIn("config-error", readme)
        self.assertIn("`error` text", readme)
        self.assertIn("stops launching further worker commands after the first launcher failure", readme)
        self.assertIn("healthy roles are not relaunched", readme)
        self.assertIn("python scripts/taskboard_loop.py --root . --goal", readme)
        self.assertIn("--assignment-lease-seconds 300", readme)
        self.assertIn("--launch-lease-seconds 300", readme)
        self.assertIn("**Goal Complete**: yes", readme)
        self.assertIn("completion audit is `complete-ready`", readme)
        self.assertIn("completion-audit-missing-evidence", readme)
        self.assertIn("completion_missing_evidence", readme)
        self.assertIn("T0 will wake T1", readme)
        self.assertIn("--no-stop-on-complete", readme)
        self.assertIn(".taskboard/t0/latest.json", readme)
        self.assertIn(".taskboard/t0/launches.json", readme)
        self.assertIn(".taskboard/t0/events.jsonl", readme)
        self.assertIn("launch_failure_count", readme)
        self.assertIn("launch_failures", readme)
        self.assertIn("latest_event_launch_failure_count", readme)
        self.assertIn("latest_event_launch_failure_output", readme)
        self.assertIn("latest event 的 `launch_failures`", readme)
        self.assertIn("resume_command", readme)
        self.assertIn("agent-template", readme)
        self.assertIn("latest event 的 `suppressed_launches`", readme)
        self.assertIn("taskboard-t0-interruption", readme)
        self.assertIn("KeyboardInterrupt", readme)
        self.assertIn("即使终端输出丢失", readme)
        self.assertIn("latest event 的 `interrupted` 状态", readme)
        self.assertIn("用户不需要改去手动管理 T1/T2/T3", readme)
        self.assertIn("latest event", readme)
        self.assertIn("suppressed_launch_count", readme)
        self.assertIn("events.jsonl` also records `auto_mode`", readme)
        self.assertIn("completion_missing_evidence", readme)
        self.assertIn("completion_user_action", readme)
        self.assertIn("latest_event_state", readme)
        self.assertIn("latest_event_dispatch_state", readme)
        self.assertIn("latest_event_next_role", readme)
        self.assertIn("top-level JSON progress", readme)
        self.assertIn("latest event `auto_mode`, `starter_mode`, `next_role`, `task`, and `assignment_*`", readme)
        self.assertIn("confirm one-command T0 auto entry", readme)
        self.assertIn("current taskboard has a stop gate", readme)
        self.assertIn("state=stop-gate", readme)
        self.assertIn("current completion audit is ready", readme)
        self.assertIn("state=complete", readme)
        self.assertIn("dispatch_state=needs-goal", readme)
        self.assertIn("state=needs-goal", readme)
        self.assertIn("latest_event_assignment_role", readme)
        self.assertIn("latest_event_assignment_expected_id", readme)
        self.assertIn("assignment_role", readme)
        self.assertIn("assignment_reason", readme)
        self.assertIn("assignment_expected_id", readme)
        self.assertIn("queue_metrics", readme)
        self.assertIn("queue_metrics_active_count", readme)
        self.assertIn("current taskboard live health", readme)
        self.assertIn("T1/T2/T3 队列规模", readme)
        self.assertIn("t0_supervisor_state", readme)
        self.assertIn("t0_supervisor_age_seconds", readme)
        self.assertIn("t0_supervisor_stale_after_seconds", readme)
        self.assertIn("恢复 T0，而不是管理 T1/T2/T3", readme)
        self.assertIn("--no-event-log", readme)
        self.assertIn(".taskboard/t0/goal.json", readme)
        self.assertIn("--no-state-file", readme)
        self.assertIn(".taskboard/targets/taskboard-T1.md", readme)
        self.assertIn("--no-target-files", readme)
        self.assertIn("{target_file}", readme)
        self.assertIn("agent-template references {target_file}", readme)
        self.assertIn("enable target files", readme)
        self.assertIn("use `--launcher none` for no-write dry checks", readme)
        self.assertIn("Role runtime contract", readme)
        self.assertIn("assigned_role", readme)
        self.assertIn("managed_by: T0", readme)
        self.assertIn("do not rely on another role's chat context", readme)
        self.assertIn("python scripts/taskboard_health.py --root . --stale-minutes 30", readme)
        self.assertIn("python scripts/taskboard_sessions.py --root . probe --stale-seconds 300", readme)
        self.assertIn("--assignment-id T2:TASK-003.v1.T2-review.md", readme)

    def test_session_manifest_contract_is_documented(self):
        role_t0 = (ROOT / "references" / "role-t0.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")

        self.assertIn("session_manifest", role_t0)
        self.assertIn("not a new shared state database", role_t0)
        self.assertIn("session_manifest", manual)
        self.assertIn("不是新的共享状态数据库", manual)

    def test_user_program_development_fit_is_documented(self):
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")

        self.assertIn("### 是否适合用户程序开发", manual)
        self.assertIn("推荐采用分层策略", manual)
        self.assertIn("单 agent 直接执行", manual)
        self.assertIn("完整 T0 auto-terminal", manual)
        self.assertIn("不适合默认启用完整 T0/T1/T2/T3", manual)


if __name__ == "__main__":
    unittest.main()
