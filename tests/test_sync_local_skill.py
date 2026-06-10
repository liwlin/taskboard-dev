from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync-local-skill.ps1"


def powershell_exe():
    return shutil.which("powershell") or shutil.which("pwsh")


@unittest.skipUnless(powershell_exe(), "PowerShell is required for sync-local-skill tests")
class SyncLocalSkillTest(unittest.TestCase):
    def make_repo(self, base: Path) -> Path:
        repo = base / "repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / "references").mkdir()
        (repo / "SKILL.md").write_text("skill\n", encoding="utf-8")
        (repo / "references" / "role-t0.md").write_text("role\n", encoding="utf-8")
        (repo / "scripts" / "package.sh").write_text(
            '\n'.join(
                [
                    'cp "$ROOT_DIR/SKILL.md" "$STAGE_DIR/SKILL.md"',
                    'cp "$ROOT_DIR/references/role-t0.md" "$STAGE_DIR/references/role-t0.md"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return repo

    def run_sync(self, repo: Path, destination: Path, *extra_args: str) -> subprocess.CompletedProcess:
        ps = powershell_exe()
        self.assertIsNotNone(ps)
        return subprocess.run(
            [
                ps,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-RepoRoot",
                str(repo),
                "-Destination",
                str(destination),
                *extra_args,
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_sync_preserves_destination_local_state_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = self.make_repo(base)
            destination = base / "dest"
            (destination / ".git").mkdir(parents=True)
            (destination / ".taskboard").mkdir()
            (destination / ".git" / "config").write_text("local git\n", encoding="utf-8")
            (destination / ".taskboard" / "latest.json").write_text("{}\n", encoding="utf-8")
            (destination / "local-note.md").write_text("keep me\n", encoding="utf-8")

            result = self.run_sync(repo, destination)

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual((destination / "SKILL.md").read_text(encoding="utf-8"), "skill\n")
            self.assertTrue((destination / ".git" / "config").exists())
            self.assertTrue((destination / ".taskboard" / "latest.json").exists())
            self.assertTrue((destination / "local-note.md").exists())

    def test_prune_stale_preserves_protected_local_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = self.make_repo(base)
            destination = base / "dest"
            (destination / ".git").mkdir(parents=True)
            (destination / ".taskboard").mkdir()
            (destination / ".git" / "config").write_text("local git\n", encoding="utf-8")
            (destination / ".taskboard" / "latest.json").write_text("{}\n", encoding="utf-8")
            (destination / "stale.md").write_text("remove me\n", encoding="utf-8")

            result = self.run_sync(repo, destination, "-PruneStale")

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertFalse((destination / "stale.md").exists())
            self.assertTrue((destination / ".git" / "config").exists())
            self.assertTrue((destination / ".taskboard" / "latest.json").exists())
