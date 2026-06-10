# taskboard-dev v4.4.3 Development Record

Generated: 2026-06-10

## Purpose

Patch release for T0 worker-agent preflight. v4.4.3 makes T0 fail fast before
managed T1/T2/T3 launches when the configured worker agent command is missing
or when an optional CLI readiness check fails.

## Included Changes

- `taskboard_loop.py` now validates worker agent readiness before executing
  managed role launch/recovery commands.
- Default preflight parses the first command from `--agent-template` and checks
  that it exists on PATH.
- `--agent-preflight-command` runs a caller-provided non-destructive readiness
  command once before worker launches; non-zero exits become T0 `config-error`.
- `--no-agent-preflight` is available for advanced users who need to bypass the
  default command check.
- `taskboard_start.py`, `taskboard_loop.py`, and `taskboard_progress.py`
  preserve preflight settings through `resume_config` and generated resume
  commands.
- README, user manual, and T0 contract verification now document the preflight
  behavior.

## Verification

```text
python -m unittest -v tests.test_taskboard_start tests.test_taskboard_loop tests.test_taskboard_progress -> passed
python -m unittest -v                                                                         -> 161 tests OK
python scripts/verify_release_consistency.py                                                  -> passed for v4.4.3
python scripts/verify_t0_contract.py                                                        -> passed
python -m unittest -v tests.test_t0_contract.T0ContractTest.test_terminal_launcher_contract_is_documented -> passed
bash scripts/package.sh                                                                       -> dist/taskboard-dev-v4.4.3.{tar.gz,zip}
scripts/sync-local-skill.ps1                                                                  -> 24 bundle files synced
```

## Release Asset SHA256

- `taskboard-dev-v4.4.3.tar.gz`: `1da30f9b8f06d4afd3c0e2d866ef73e317a3a5748536b5a4e918cabce58c528b`
- `taskboard-dev-v4.4.3.zip`: `5835cd44886988f7086a0fa5d4036836ebd176137c0cde0296084199c8d50d32`
