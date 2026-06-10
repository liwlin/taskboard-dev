# taskboard-dev v4.4.1 Development Record

Generated: 2026-06-10

## Purpose

Patch release for the post-v4.4 T0 default-behavior work. v4.4.1 avoids
force-moving the existing `v4.4` tag while publishing the current `main`
state as a new non-destructive release.

## Included Changes

- `taskboard_start.py --goal "<user goal>"` is the documented default T0
  one-command automatic supervisor entry.
- Generated T0 role target files now include `Default tooling contract`
  blocks for T1 planning, T2 independent review, and T3 parallelization
  assessment.
- Generated T0 role target files now include `External tool contract` blocks
  for GitHub, Chrome/Browser, and Computer Use boundaries.

## Verification

```text
python -m unittest -v                         -> 159 tests OK
python scripts/verify_t0_contract.py          -> passed
python scripts/verify_release_consistency.py  -> passed for v4.4.1
git diff --check                              -> passed
bash scripts/package.sh                       -> dist/taskboard-dev-v4.4.1.{tar.gz,zip}
scripts/sync-local-skill.ps1                  -> 24 bundle files synced
```

## Release Asset SHA256

- `taskboard-dev-v4.4.1.tar.gz`: `359d787424f887c2134cc88172599ceb6fc5a8d48e3bcc70f37668ded56307c2`
- `taskboard-dev-v4.4.1.zip`: `8014227142990b9d19ee18c71bba29bad3f6f9461d5b7927214c710a67acec95`

## Release Plan

- Push `main`.
- Create tag `v4.4.1` on the pushed commit.
- Create GitHub Release `taskboard-dev v4.4.1`.
- Upload both release assets and verify remote digests.
