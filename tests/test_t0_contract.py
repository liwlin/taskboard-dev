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
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_stopgates.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_decide.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_health.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_sessions.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/taskboard_next.py"', package_script)
        self.assertIn('cp "$ROOT_DIR/scripts/verify_t0_contract.py"', package_script)

    def test_multi_agent_patterns_are_explicit(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
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

        self.assertIn("### T0 Liveness / Heartbeat Rules", skill)
        self.assertIn("stalled", skill)
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
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("auto-terminal mode", skill)
        self.assertIn("separate terminal session and isolated agent context", skill)
        self.assertIn("must not reuse one role's conversation context", skill)
        self.assertIn("auto-terminal 模式", manual)
        self.assertIn("角色之间不共享聊天上下文", manual)
        self.assertIn("python scripts/taskboard_t0.py --goal", readme)

    def test_multi_agent_synchronization_contract_is_documented(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")

        self.assertIn("### Multi-Agent Synchronization", skill)
        self.assertIn("Use blackboard synchronization, not chat-context synchronization", skill)
        self.assertIn("### 多 agent 信息同步机制", manual)
        self.assertIn("不是聊天上下文同步", manual)
        self.assertIn("角色之间的“记忆”必须先落到共享文件里", manual)

    def test_t0_scheduling_logic_is_documented(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")

        self.assertIn("### T0 Scheduling Logic", skill)
        self.assertIn("T0 schedules by event priority, not by arbitrary rotation", skill)
        self.assertIn("T0 的调度逻辑是", manual)
        self.assertIn("交付闭环优先", manual)
        self.assertIn("修复优先于新执行", manual)

    def test_t0_manager_only_boundary_is_documented(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")

        self.assertIn("T0 is manager-only", skill)
        self.assertIn("must not directly execute development tasks", skill)
        self.assertIn("T0 是管理员，不是开发执行者", manual)
        self.assertIn("T0 不直接执行开发任务", manual)

    def test_terminal_launcher_contract_is_documented(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("### T0 Terminal Launcher", skill)
        self.assertIn("--launcher windows-terminal", skill)
        self.assertIn("--agent-template", skill)
        self.assertIn("### T0 启动器脚本", manual)
        self.assertIn("Windows Terminal", manual)
        self.assertIn("tmux", manual)
        self.assertIn("--launcher windows-terminal", readme)
        self.assertIn("python scripts/taskboard_demo.py --root .taskboard-demo --with-heartbeats", readme)
        self.assertIn("python scripts/taskboard_start.py --goal", readme)
        self.assertIn("--auto", readme)
        self.assertIn("--auto --iterations 1 --launcher none", readme)
        self.assertIn("suppresses worker launch/target/assignment", readme)
        self.assertIn("asks the summarized question through T0 only", readme)
        self.assertIn("--no-stop-on-stop-gate", readme)
        self.assertIn("stops after one `stop-gate` iteration", readme)
        self.assertIn("The stop-gate loop output includes `decision_command`", readme)
        self.assertIn("python scripts/taskboard_completion.py --root .", readme)
        self.assertIn("python scripts/taskboard_progress.py --root .", readme)
        self.assertIn("python scripts/taskboard_stopgates.py --root .", readme)
        self.assertIn("python scripts/taskboard_decide.py --root . --decision", readme)
        self.assertIn("decision_command", readme)
        self.assertIn("让 T1 根据用户决策继续修订", readme)
        self.assertIn("T0 launch/recovery failed", readme)
        self.assertIn("healthy roles are not relaunched", readme)
        self.assertIn("python scripts/taskboard_loop.py --root . --goal", readme)
        self.assertIn("--assignment-lease-seconds 300", readme)
        self.assertIn("--launch-lease-seconds 300", readme)
        self.assertIn("**Goal Complete**: yes", readme)
        self.assertIn("--no-stop-on-complete", readme)
        self.assertIn(".taskboard/t0/latest.json", readme)
        self.assertIn(".taskboard/t0/launches.json", readme)
        self.assertIn(".taskboard/t0/events.jsonl", readme)
        self.assertIn("--no-event-log", readme)
        self.assertIn(".taskboard/t0/goal.json", readme)
        self.assertIn("--no-state-file", readme)
        self.assertIn(".taskboard/targets/taskboard-T1.md", readme)
        self.assertIn("--no-target-files", readme)
        self.assertIn("{target_file}", readme)
        self.assertIn("python scripts/taskboard_health.py --root . --stale-minutes 30", readme)
        self.assertIn("python scripts/taskboard_sessions.py --root . probe --stale-seconds 300", readme)
        self.assertIn("--assignment-id T2:TASK-003.v1.T2-review.md", readme)

    def test_session_manifest_contract_is_documented(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        manual = (ROOT / "USER-MANUAL.md").read_text(encoding="utf-8")

        self.assertIn("session_manifest", skill)
        self.assertIn("not a new shared state database", skill)
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
