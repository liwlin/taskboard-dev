# taskboard-dev v4.5.1 Development Record

Date: 2026-06-11

## Purpose

Patch release for the T0 end-to-end control-plane acceptance gap. v4.5.0
covered the compact CLI, worker liveness, native subagent fallback, and
field-pressure fixes, but it lacked one single command that proves the key
goal-facing path: T0 accepts one user goal, assigns a worker task, the worker
acknowledges that assignment, and T0 progress reports the acknowledgement
without asking the user to manage T1/T2/T3.

## Changes

- Added `scripts/taskboard_e2e_smoke.py`.
  - Creates a temporary demo TASKBOARD.
  - Runs one T0 supervisor cycle.
  - Simulates the selected worker's `taskboard.py cycle` and heartbeat.
  - Runs a second T0 supervisor cycle.
  - Fails unless T0 reports the assignment as `acknowledged`.
- Added `tests/test_taskboard_e2e_smoke.py`.
- Added the smoke script to `scripts/package.sh`.
- Documented the smoke command in README and USER-MANUAL.
- Bumped the release version from v4.5.0 to v4.5.1.

## Verification

```text
python scripts/taskboard_e2e_smoke.py --format json
  -> state=passed; assignment_state=acknowledged

python -m unittest -v tests.test_taskboard_e2e_smoke
  -> 2 tests OK

python scripts/verify_t0_contract.py
  -> T0 contract verification passed

python -m unittest -v
  -> 203 tests OK

python scripts/verify_release_consistency.py
  -> passed for v4.5.1

git diff --check
  -> passed

bash scripts/package.sh
  -> dist/taskboard-dev-v4.5.1.{tar.gz,zip}
```

`bash scripts/package.sh` emitted the known local WSL localhost/NAT warning on
Windows, but returned exit code 0 and produced both archives.

## SHA256

- `taskboard-dev-v4.5.1.tar.gz`: `33a5554343596d6d278d3ce7373a85cf2ed287537c07881b3977d6c948a3c5a2`
- `taskboard-dev-v4.5.1.zip`: `f43ceb3e6d43b561456ceb530722ac8ceb23f63c2be860d445eec2b56b6809a5`
