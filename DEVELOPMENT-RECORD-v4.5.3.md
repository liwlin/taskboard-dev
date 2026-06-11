# taskboard-dev v4.5.3 Development Record

Date: 2026-06-11

## Purpose

Patch release for the remaining T0 seeding gray zone captured by the LeLamp
field pressure evidence. v4.5.x already prevented T0 from writing
requirements, architecture, task splits, or acceptance criteria, but the
pressure notes still identified a softer failure mode: T0 could pre-fill REQ
counts, priority skeletons, interface signatures, task IDs, acceptance rows, or
MAP risk sections and rationalize them as "just a helpful skeleton."

## Changes

- Added machine-readable `forbidden_seed_patterns` to the T0 goal-intake
  packet in `scripts/taskboard_t0.py`.
- Extended generated role targets with an explicit instruction not to pre-fill
  REQ counts, priorities, interface signatures, task IDs, acceptance rows, or
  MAP risk sections.
- Updated T0 role documentation, README, USER-MANUAL, and contract tests so the
  gray-zone constraint is enforced by tests rather than only remembered from
  pressure-test notes.
- Bumped the release version from v4.5.2 to v4.5.3.

## Verification

```text
python -m unittest -v tests.test_taskboard_t0.TaskboardT0Test.test_t0_output_includes_goal_intake_packet_not_requirements tests.test_taskboard_t0.TaskboardT0Test.test_role_target_files_mark_t0_input_as_goal_intake_only tests.test_t0_contract.T0ContractTest.test_t0_initial_seeding_cannot_be_requirements_or_design_work
  -> 3 tests OK

python scripts/verify_t0_contract.py
  -> T0 contract verification passed

python -m unittest -v
  -> 204 tests OK

python scripts/verify_release_consistency.py
  -> Release consistency check passed for v4.5.3

git diff --check
  -> passed

bash scripts/package.sh
  -> dist/taskboard-dev-v4.5.3.{tar.gz,zip}
```

`bash scripts/package.sh` emitted the known local WSL localhost/NAT warning on
Windows, but returned exit code 0 and produced both archives.

## SHA256

- `taskboard-dev-v4.5.3.tar.gz`: `93dcac2ab89440e0d6e6b53fa426073d4251870a6b551262feb456572abfa604`
- `taskboard-dev-v4.5.3.zip`: `d637f3d36151f88f074abff20712e824114f6c70deb42ad675c1536c3f9395be`
