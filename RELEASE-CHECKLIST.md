# Release checklist

Run every step in order. Do not skip a step because "nothing relevant
changed" — the v4.2/v4.3 drift between repo, installed skill, and release
package happened exactly that way.

## 1. Verify

```bash
python -m unittest
python scripts/verify_t0_contract.py
python scripts/verify_release_consistency.py
```

All three must pass. `verify_release_consistency.py` confirms the version in
`scripts/package.sh` matches SKILL.md, README.md, USER-MANUAL.md, and the
template, and that every script and reference file is staged by the manifest.

## 2. Package

```bash
bash scripts/package.sh
```

Produces `dist/taskboard-dev-<version>.tar.gz` and `.zip`.

## 3. Record digests

```powershell
Get-FileHash dist\taskboard-dev-*.tar.gz, dist\taskboard-dev-*.zip -Algorithm SHA256
```

Record the SHA256 values in the development record for the release.

## 4. Publish

1. Push `main` (`git push origin main`). If the normal push path is
   unavailable, use the GitHub API publish path.
2. Create or update the version tag on the published commit.
3. Upload both archives as release assets.
4. Verify the release: tag target commit matches the published `main`, and
   downloaded asset digests match step 3.

## 5. Sync the local skill

```powershell
.\scripts\sync-local-skill.ps1
```

Confirm `~/.claude/skills/taskboard-dev/SKILL.md` matches the repo and
`taskboard_watchdog.py` is present.

## Git divergence policy

- Prefer normal `git push` whenever the push path works.
- Fall back to the GitHub API publish path only when push is unavailable.
- After any API publish, reset/sync local `main` to the remote commit
  immediately. Never keep a long-lived divergent `main`.
- Rationale: the v4.3 API publish created ~59 pairs of duplicate commits;
  convergence required a verified hard reset (2026-06-10).
