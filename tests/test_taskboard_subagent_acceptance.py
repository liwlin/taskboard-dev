from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / "scripts" / "taskboard_subagent_acceptance.py"
SMOKE = ROOT / "scripts" / "taskboard_subagent_smoke.py"
TASKBOARD = ROOT / "scripts" / "taskboard.py"


class TaskboardSubagentAcceptanceTest(unittest.TestCase):
    def run_smoke(self, root: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(SMOKE), "--root", str(root), "--force", "--format", "json"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def run_acceptance(self, root: Path, *args: str) -> tuple[int, dict]:
        result = subprocess.run(
            [sys.executable, str(ACCEPTANCE), "--root", str(root), "--format", "json", *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        return result.returncode, json.loads(result.stdout)

    def run_taskboard(self, root: Path, *args: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(TASKBOARD), "--root", str(root), "--format", "json", *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return json.loads(result.stdout)

    def write_real_spawn_records(self, root: Path) -> None:
        self.run_smoke(root)
        for role in ("T1", "T2", "T3"):
            agent_id = f"019eb736-{role.lower()}-real-agent"
            self.run_taskboard(
                root,
                "subagent",
                "ack",
                "--role",
                role,
                "--agent-id",
                agent_id,
                "--spawn-tool",
                "multi_agent_v1.spawn_agent",
                "--agent-nickname",
                f"{role} managed child",
            )
            self.run_taskboard(
                root,
                "subagent",
                "done",
                "--role",
                role,
                "--summary",
                f"{role} completed via native receipt",
                "--result-tool",
                "multi_agent_v1.wait_agent",
                "--result-status",
                "completed",
            )

    def test_acceptance_passes_completed_subagent_dispatch_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_smoke(root)
            returncode, payload = self.run_acceptance(root)

        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["kind"], "taskboard-subagent-acceptance")
        self.assertEqual(payload["state"], "passed")
        self.assertEqual(payload["required_roles"], ["T1", "T2", "T3"])
        self.assertEqual(payload["completed_roles"], ["T1", "T2", "T3"])
        self.assertEqual(payload["failure_count"], 0)
        self.assertTrue(any("T1: prompt includes skill" in item for item in payload["evidence"]))

    def test_real_agent_id_mode_rejects_smoke_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_smoke(root)
            returncode, payload = self.run_acceptance(root, "--require-real-agent-ids")

        self.assertEqual(returncode, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertTrue(any("placeholder" in item for item in payload["failures"]), payload)

    def test_spawn_evidence_mode_requires_native_spawn_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_smoke(root)
            state_file = root / ".taskboard" / "t0" / "subagents.json"
            state = json.loads(state_file.read_text(encoding="utf-8"))
            for role, record in state["roles"].items():
                record["agent_id"] = f"019eb736-{role.lower()}-real-agent"
            state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

            returncode, payload = self.run_acceptance(
                root,
                "--require-real-agent-ids",
                "--require-spawn-evidence",
            )

        self.assertEqual(returncode, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertTrue(any("T2: spawn_receipt missing" in item for item in payload["failures"]), payload)
        self.assertTrue(any("T2: completion_receipt agent_id mismatch" in item for item in payload["failures"]), payload)

    def test_spawn_evidence_mode_passes_with_native_spawn_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_real_spawn_records(root)

            returncode, payload = self.run_acceptance(
                root,
                "--require-real-agent-ids",
                "--require-spawn-evidence",
            )

        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["state"], "passed")
        self.assertTrue(payload["require_spawn_evidence"])

    def test_result_evidence_mode_requires_native_result_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_real_spawn_records(root)
            state_file = root / ".taskboard" / "t0" / "subagents.json"
            state = json.loads(state_file.read_text(encoding="utf-8"))
            del state["roles"]["T2"]["result_receipt"]
            state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

            returncode, payload = self.run_acceptance(
                root,
                "--require-real-agent-ids",
                "--require-spawn-evidence",
                "--require-result-evidence",
            )

        self.assertEqual(returncode, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertTrue(any("T2: result_receipt missing" in item for item in payload["failures"]), payload)

    def test_result_evidence_mode_passes_with_native_result_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_real_spawn_records(root)

            returncode, payload = self.run_acceptance(
                root,
                "--require-real-agent-ids",
                "--require-spawn-evidence",
                "--require-result-evidence",
            )

        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["state"], "passed")
        self.assertTrue(payload["require_result_evidence"])

    def test_result_evidence_mode_rejects_summary_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_real_spawn_records(root)
            state_file = root / ".taskboard" / "t0" / "subagents.json"
            state = json.loads(state_file.read_text(encoding="utf-8"))
            state["roles"]["T1"]["result_receipt"]["summary_hash"] = "sha256:" + ("0" * 64)
            state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

            returncode, payload = self.run_acceptance(
                root,
                "--require-real-agent-ids",
                "--require-spawn-evidence",
                "--require-result-evidence",
            )

        self.assertEqual(returncode, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertTrue(any("T1: result summary_hash mismatch" in item for item in payload["failures"]), payload)

    def test_spawn_evidence_mode_rejects_prompt_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_real_spawn_records(root)
            state_file = root / ".taskboard" / "t0" / "subagents.json"
            state = json.loads(state_file.read_text(encoding="utf-8"))
            state["roles"]["T1"]["spawn_receipt"]["prompt_hash"] = "sha256:" + ("0" * 64)
            state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

            returncode, payload = self.run_acceptance(
                root,
                "--require-real-agent-ids",
                "--require-spawn-evidence",
            )

        self.assertEqual(returncode, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertTrue(any("T1: prompt_hash mismatch" in item for item in payload["failures"]), payload)

    def test_acceptance_fails_when_required_role_is_not_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_smoke(root)
            state_file = root / ".taskboard" / "t0" / "subagents.json"
            state = json.loads(state_file.read_text(encoding="utf-8"))
            state["roles"]["T2"]["status"] = "failed"
            state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

            returncode, payload = self.run_acceptance(root)

        self.assertEqual(returncode, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertTrue(any("failed role(s) remain: T2" in item for item in payload["failures"]), payload)
        self.assertTrue(any("T2: expected completed status" in item for item in payload["failures"]), payload)

    def test_acceptance_fails_when_prompt_lacks_skill_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_smoke(root)
            packet_file = root / ".taskboard" / "t0" / "subagent-fallback.json"
            packet = json.loads(packet_file.read_text(encoding="utf-8"))
            prompt = packet["subagent_fallback"]["subagent_prompts"][0]["prompt"]
            packet["subagent_fallback"]["subagent_prompts"][0]["prompt"] = prompt.replace("Read SKILL.md", "Read docs")
            packet_file.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

            returncode, payload = self.run_acceptance(root)

        self.assertEqual(returncode, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertTrue(any("prompt missing required fragment" in item for item in payload["failures"]), payload)


if __name__ == "__main__":
    unittest.main()
