# taskboard-dev v4.5.0 Development Record

Generated: 2026-06-11

## Purpose

First v4.5 control-plane consolidation release. v4.5.0 adds a compact
`scripts/taskboard.py` CLI facade with the six verbs proposed by the
LeLamp-derived architecture review while preserving all v4.4 scripts and
runtime files for compatibility.

## Included Changes

- Added `scripts/taskboard.py` with:
  - `status`: combined queue health, stop gates, completion audit, and next
    role/task view.
  - `next <role>`: deterministic role/task selection through the existing
    filename priority rules.
  - `move <task> <status> [--note]`: validates destination status, renames the
    task file, appends `docs/taskboard/history/TASK-NNN.history.md`, and touches
    mtime in one operation.
  - `alive <role>`: touches `.taskboard/alive/T{N}` for mtime-based liveness.
  - `stall --minutes N`: read-only stalled-task view from task file mtime.
  - `decide <task> --answer`: wrapper around the existing T0 stop-gate decision
    recorder.
- Added `tests/test_taskboard_cli.py` covering all six verbs, invalid status
  rejection, history writing, and mtime updates.
- Documented `taskboard.py` as the preferred v4.5 compact control-plane CLI in
  README, user manual, T0 role reference, and the taskboard template.
- Added `taskboard.py` to the release package manifest and T0 contract verifier.
- Saved the implementation plan at
  `docs/superpowers/plans/2026-06-11-taskboard-single-cli.md`.

## Compatibility

Legacy scripts remain packaged and supported. v4.5.0 does not remove
`.taskboard/t0/latest.json`, `.taskboard/t0/events.jsonl`,
`.taskboard/t0/launches.json`, or existing supervisor loop behavior. Those
changes remain candidates for a later v5 protocol break.

## Verification

```text
python -m unittest tests.test_taskboard_cli -v
  -> 7 tests OK
python -m unittest tests.test_taskboard_cli tests.test_t0_contract tests.test_verify_release_consistency -v
  -> 32 tests OK
python -m unittest -v
  -> 171 tests OK
python scripts/verify_t0_contract.py
  -> T0 contract verification passed
python scripts/verify_release_consistency.py
  -> passed for v4.5.0
bash scripts/package.sh
  -> dist/taskboard-dev-v4.5.0.{tar.gz,zip}
tar -tzf dist/taskboard-dev-v4.5.0.tar.gz
  -> package manifest verified
tar -tf dist/taskboard-dev-v4.5.0.zip
  -> package manifest verified
```

## Release Asset SHA256

- `taskboard-dev-v4.5.0.tar.gz`: `9b1bc7054347259b9dd9be0f87754501f6be819d917f15502f9da7edbfec2096`
- `taskboard-dev-v4.5.0.zip`: `8ca383950b9f4adf73b6dd72456fbb92195c8ecf9ff7a70c83726b027c795e2a`
