# taskboard-dev v4.4.2 Development Record

Generated: 2026-06-10

## Purpose

Patch release for direct role-reference invocation parity. v4.4.1 added
external tool boundaries to generated T0 target files; v4.4.2 adds the same
boundaries to `references/role-t1.md`, `role-t2.md`, and `role-t3.md` so manual
role starts and resume flows get the same default behavior.

## Included Changes

- T1/T2/T3 role references now include `External Tool Boundaries`.
- The role references explicitly route:
  - GitHub tooling to repository, PR, issue, release, and CI-check evidence.
  - Chrome/Browser tooling to web UI inspection and rendered frontend evidence.
  - Computer Use to local desktop/GUI workflows that shell/browser/repo tools
    cannot cover.
- The rules require roles to use available tools themselves for routine role
  work while preserving T1/T2/T3 boundaries.
- `verify_t0_contract.py` and `tests/test_t0_contract.py` now guard the static
  role-reference contract.

## Verification

```text
python -m unittest -v                         -> 159 tests OK
python scripts/verify_t0_contract.py          -> passed
python scripts/verify_release_consistency.py  -> passed for v4.4.2
git diff --check                              -> passed
bash scripts/package.sh                       -> dist/taskboard-dev-v4.4.2.{tar.gz,zip}
scripts/sync-local-skill.ps1                  -> 24 bundle files synced
```

## Release Asset SHA256

- `taskboard-dev-v4.4.2.tar.gz`: `602198f8beee8be01556be3a94650da912209b2142dab182b4e7c160c23c7aee`
- `taskboard-dev-v4.4.2.zip`: `267f69d375e82204bfca53cf28c8f7f57b9eb37b4437f58218f874c6b502d743`
