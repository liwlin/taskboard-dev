#!/usr/bin/env bash
set -euo pipefail

VERSION="${VERSION:-v4.5.36}"
NAME="taskboard-dev"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
STAGE_DIR="$DIST_DIR/$NAME"

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR/references" "$STAGE_DIR/scripts" "$DIST_DIR"

cp "$ROOT_DIR/SKILL.md" "$STAGE_DIR/SKILL.md"
cp "$ROOT_DIR/USER-MANUAL.md" "$STAGE_DIR/USER-MANUAL.md"
cp "$ROOT_DIR/README.md" "$STAGE_DIR/README.md"
cp "$ROOT_DIR/references/taskboard-template.md" "$STAGE_DIR/references/taskboard-template.md"
cp "$ROOT_DIR/references/role-t0.md" "$STAGE_DIR/references/role-t0.md"
cp "$ROOT_DIR/references/role-t1.md" "$STAGE_DIR/references/role-t1.md"
cp "$ROOT_DIR/references/role-t2.md" "$STAGE_DIR/references/role-t2.md"
cp "$ROOT_DIR/references/role-t3.md" "$STAGE_DIR/references/role-t3.md"
cp "$ROOT_DIR/scripts/package.sh" "$STAGE_DIR/scripts/package.sh"
cp "$ROOT_DIR/scripts/taskboard_start.py" "$STAGE_DIR/scripts/taskboard_start.py"
cp "$ROOT_DIR/scripts/taskboard.py" "$STAGE_DIR/scripts/taskboard.py"
cp "$ROOT_DIR/scripts/taskboard_t0.py" "$STAGE_DIR/scripts/taskboard_t0.py"
cp "$ROOT_DIR/scripts/taskboard_loop.py" "$STAGE_DIR/scripts/taskboard_loop.py"
cp "$ROOT_DIR/scripts/taskboard_demo.py" "$STAGE_DIR/scripts/taskboard_demo.py"
cp "$ROOT_DIR/scripts/taskboard_e2e_smoke.py" "$STAGE_DIR/scripts/taskboard_e2e_smoke.py"
cp "$ROOT_DIR/scripts/taskboard_cold_resume_smoke.py" "$STAGE_DIR/scripts/taskboard_cold_resume_smoke.py"
cp "$ROOT_DIR/scripts/taskboard_cold_resume_acceptance.py" "$STAGE_DIR/scripts/taskboard_cold_resume_acceptance.py"
cp "$ROOT_DIR/scripts/taskboard_t0_boundary_smoke.py" "$STAGE_DIR/scripts/taskboard_t0_boundary_smoke.py"
cp "$ROOT_DIR/scripts/taskboard_subagent_smoke.py" "$STAGE_DIR/scripts/taskboard_subagent_smoke.py"
cp "$ROOT_DIR/scripts/taskboard_subagent_acceptance.py" "$STAGE_DIR/scripts/taskboard_subagent_acceptance.py"
cp "$ROOT_DIR/scripts/taskboard_live_milestone_acceptance.py" "$STAGE_DIR/scripts/taskboard_live_milestone_acceptance.py"
cp "$ROOT_DIR/scripts/taskboard_framework_readiness.py" "$STAGE_DIR/scripts/taskboard_framework_readiness.py"
cp "$ROOT_DIR/scripts/taskboard_overnight_field_run.py" "$STAGE_DIR/scripts/taskboard_overnight_field_run.py"
cp "$ROOT_DIR/scripts/taskboard_completion.py" "$STAGE_DIR/scripts/taskboard_completion.py"
cp "$ROOT_DIR/scripts/taskboard_progress.py" "$STAGE_DIR/scripts/taskboard_progress.py"
cp "$ROOT_DIR/scripts/taskboard_watchdog.py" "$STAGE_DIR/scripts/taskboard_watchdog.py"
cp "$ROOT_DIR/scripts/taskboard_stopgates.py" "$STAGE_DIR/scripts/taskboard_stopgates.py"
cp "$ROOT_DIR/scripts/taskboard_subagents.py" "$STAGE_DIR/scripts/taskboard_subagents.py"
cp "$ROOT_DIR/scripts/taskboard_decide.py" "$STAGE_DIR/scripts/taskboard_decide.py"
cp "$ROOT_DIR/scripts/taskboard_health.py" "$STAGE_DIR/scripts/taskboard_health.py"
cp "$ROOT_DIR/scripts/taskboard_sessions.py" "$STAGE_DIR/scripts/taskboard_sessions.py"
cp "$ROOT_DIR/scripts/taskboard_next.py" "$STAGE_DIR/scripts/taskboard_next.py"
cp "$ROOT_DIR/scripts/verify_t0_contract.py" "$STAGE_DIR/scripts/verify_t0_contract.py"
cp "$ROOT_DIR/scripts/verify_release_consistency.py" "$STAGE_DIR/scripts/verify_release_consistency.py"
cp "$ROOT_DIR/scripts/sync-local-skill.ps1" "$STAGE_DIR/scripts/sync-local-skill.ps1"

(
  cd "$DIST_DIR"
  tar -czf "$NAME-$VERSION.tar.gz" "$NAME"
  if command -v zip >/dev/null 2>&1; then
    rm -f "$NAME-$VERSION.zip"
    zip -qr "$NAME-$VERSION.zip" "$NAME"
  elif command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
    rm -f "$NAME-$VERSION.zip"
    PYTHON_BIN="$(command -v python3 || command -v python)"
    "$PYTHON_BIN" - "$NAME" "$NAME-$VERSION.zip" <<'PY'
import os
import sys
import zipfile

source_dir, output_path = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for root, _, files in os.walk(source_dir):
        for file_name in files:
            path = os.path.join(root, file_name)
            archive.write(path, path.replace(os.sep, "/"))
PY
  else
    echo "zip and python not found; skipped $NAME-$VERSION.zip" >&2
  fi
)

echo "Packaged:"
echo "  $DIST_DIR/$NAME-$VERSION.tar.gz"
if [[ -f "$DIST_DIR/$NAME-$VERSION.zip" ]]; then
  echo "  $DIST_DIR/$NAME-$VERSION.zip"
fi
