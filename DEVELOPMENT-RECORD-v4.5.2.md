# taskboard-dev v4.5.2 Development Record

Date: 2026-06-11

## Purpose

Patch release for the T0 completion-evidence control-plane gap. v4.5.1 proved
that T0 can assign a worker task and observe acknowledgement, but the smoke did
not prove the full closure path: active tasks archived, completion sentinel and
dev-log evidence written, completion audit ready, and T0 progress reporting the
goal as complete.

## Changes

- Fixed `taskboard.py move` archive semantics.
  - `archive-完成` now moves tasks into `docs/taskboard/archive/`.
  - Archive filenames strip the control prefix, producing
    `TASK-001.v1.完成.md` instead of leaving
    `TASK-001.v1.archive-完成.md` in the active taskboard directory.
- Extended `scripts/taskboard_e2e_smoke.py`.
  - It still proves T0 assigns a managed worker and observes acknowledgement.
  - It now archives all active demo tasks, writes `**Goal Complete**: yes`,
    records dev-log evidence, requires completion audit `complete-ready`, and
    requires final T0 progress state `complete`.
- Updated `taskboard_progress.py` so completion-ready evidence overrides stale
  or idle supervisor snapshots in the user-facing progress summary.
- Updated README, USER-MANUAL, template, contract checks, and release
  consistency tests to v4.5.2.

## Verification

```text
python scripts/taskboard_e2e_smoke.py --format json
  -> state=passed; completion.state=complete-ready; progress.state=complete

python -m unittest -v tests.test_taskboard_cli.TaskboardCliTest.test_move_archives_completed_task_under_archive_directory tests.test_taskboard_e2e_smoke tests.test_taskboard_progress.TaskboardProgressTest.test_progress_surfaces_completion_audit_when_t0_is_complete
  -> 4 tests OK

python scripts/verify_t0_contract.py
  -> T0 contract verification passed

python -m unittest -v
  -> 204 tests OK

python scripts/verify_release_consistency.py
  -> Release consistency check passed for v4.5.2

git diff --check
  -> passed

bash scripts/package.sh
  -> dist/taskboard-dev-v4.5.2.{tar.gz,zip}
```

`bash scripts/package.sh` emitted the known local WSL localhost/NAT warning on
Windows, but returned exit code 0 and produced both archives.

## SHA256

- `taskboard-dev-v4.5.2.tar.gz`: `ef5b43036513d61a48e0e866951b3f309a52eedddadcc22bd36ba9c8cdd4e21b`
- `taskboard-dev-v4.5.2.zip`: `0ee8244cefbba6546db0e29092b6b6fef35aeab9b204404ecfbcc08a55fc6e4a`
