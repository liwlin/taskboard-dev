# taskboard-dev v4.4.4 Development Record

Generated: 2026-06-11

## Purpose

Patch release from the LeLamp real-world T0 run. v4.4.4 keeps the v4.4 task
protocol intact while closing four practical gaps: managed-session spawn
refusal recovery, worker skill evidence, T0 overreach during initial seeding,
and missing regression coverage for those behaviors.

## Included Changes

- `taskboard_loop.py` now detects launcher failures that look like managed
  child-process auth refusal (`API Error: 403`, `Request not allowed`, or
  `Failed to authenticate`) and writes user-owned Windows Terminal recovery
  scripts instead of asking the user to manage T1/T2/T3 manually.
- `taskboard_t0.py` can write ASCII-only `.taskboard/open-tabs.ps1` and
  `.taskboard/launch-role.ps1` scripts that open the managed
  `taskboard-T1/T2/T3` role terminals from the user's own shell context.
- Generated role targets now include `Required skills evidence`; each worker
  must record the tool/skill used, result, and fallback reason before handoff.
- `role-t0.md` no longer allows T0 to create or refresh initial
  `REQUIREMENTS.md` / design context. T0 may create only a goal intake packet;
  requirements decomposition, architecture choices, task splitting, and
  acceptance criteria belong to T1.
- `role-t1.md`, `role-t2.md`, and `role-t3.md` now document required skill
  evidence directly in the role references.
- README, user manual, contract verifier, and regression tests now cover the
  new launch recovery and skill-evidence contracts.

## Verification

```text
python -m unittest tests.test_taskboard_t0.TaskboardT0Test.test_role_target_files_require_tooling_evidence
  -> passed
python -m unittest tests.test_taskboard_loop.TaskboardLoopTest.test_spawn_refused_launch_failure_writes_user_owned_windows_scripts
  -> passed
python -m unittest tests.test_t0_contract.T0ContractTest.test_t0_initial_seeding_cannot_be_requirements_or_design_work
  -> passed
python -m unittest tests.test_taskboard_t0 tests.test_taskboard_loop tests.test_t0_contract
  -> 69 tests OK
python scripts/verify_t0_contract.py
  -> T0 contract verification passed
python scripts/verify_release_consistency.py
  -> passed for v4.4.4
python -m unittest -v
  -> 164 tests OK
bash scripts/package.sh
  -> dist/taskboard-dev-v4.4.4.{tar.gz,zip}
tar -tzf dist/taskboard-dev-v4.4.4.tar.gz
  -> package manifest verified
tar -tf dist/taskboard-dev-v4.4.4.zip
  -> package manifest verified
```

## Release Asset SHA256

- `taskboard-dev-v4.4.4.tar.gz`: `ad4cd6123531443c0f77f9e983726d24dca67bcfa2f6d31301c5956b1b90cb20`
- `taskboard-dev-v4.4.4.zip`: `f0fbfaa9be042b62ba0ce41bd806c008b9861a80340ba82d3d05f705a36a583c`
