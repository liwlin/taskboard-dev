# taskboard-dev v4.5.4 Development Record

Date: 2026-06-11

## Purpose

Patch release for the native-subagent fallback control-plane gap. The prior
releases documented and unit-tested subagent dispatch bookkeeping, but there
was no single smoke command proving that T0 can generate isolated subagent
prompts, persist a fallback packet, drive `next/ack/done/fail/retry`, preserve
failed attempt history, and reach a completed T1/T2/T3 dispatch state without
asking the user to manage the workers.

## Changes

- Added `scripts/taskboard_subagent_smoke.py`.
  - Creates a temporary TASKBOARD root by default.
  - Uses `taskboard_t0.dispatch(..., mode="subagent")` to generate the T0
    native-subagent backend plan.
  - Persists the fallback packet through the same `taskboard_loop.py`
    packet writer used by supervisor fallback paths.
  - Exercises `subagent next`, `ack`, `done`, `fail`, `retry`, and final
    `complete` state through the shared helper functions.
- Fixed `subagent_ack_payload` so a retry acknowledgement preserves archived
  failed attempts instead of overwriting the retry history.
- Added `tests/test_taskboard_subagent_smoke.py`.
- Extended the existing CLI retry test to prove retry history survives the
  second acknowledgement.
- Added the smoke script to the release package and documented it in README and
  USER-MANUAL.
- Bumped the release version from v4.5.3 to v4.5.4.

## Verification

```text
python scripts/taskboard_subagent_smoke.py --format json
  -> state=passed; completed_roles=T1,T2,T3; next_state=complete

python -m unittest -v tests.test_taskboard_subagent_smoke tests.test_taskboard_cli.TaskboardCliTest.test_subagent_retry_returns_failed_role_to_pending_without_losing_attempt
  -> 3 tests OK

python scripts/verify_t0_contract.py
  -> T0 contract verification passed

python -m unittest -v
  -> 206 tests OK

python scripts/verify_release_consistency.py
  -> Release consistency check passed for v4.5.4

git diff --check
  -> passed

bash scripts/package.sh
  -> dist/taskboard-dev-v4.5.4.{tar.gz,zip}
```

`bash scripts/package.sh` emitted the known local WSL localhost/NAT warning on
Windows, but returned exit code 0 and produced both archives.

## SHA256

- `taskboard-dev-v4.5.4.tar.gz`: `331f2b9d47a35b8adbf9ad4e72d3d191577563ad7d7bcb268c3ff7629ea03d0c`
- `taskboard-dev-v4.5.4.zip`: `946c7a2f82fa3560201c82af1e6ab594e3a501eb2769f8f64c189f366a58a009`
