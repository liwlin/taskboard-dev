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


if __name__ == "__main__":
    unittest.main()
