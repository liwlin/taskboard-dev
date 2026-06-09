#!/usr/bin/env bash
set -euo pipefail

VERSION="${VERSION:-v4.3}"
NAME="taskboard-dev"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
STAGE_DIR="$DIST_DIR/$NAME"

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR/references" "$DIST_DIR"

cp "$ROOT_DIR/SKILL.md" "$STAGE_DIR/SKILL.md"
cp "$ROOT_DIR/USER-MANUAL.md" "$STAGE_DIR/USER-MANUAL.md"
cp "$ROOT_DIR/README.md" "$STAGE_DIR/README.md"
cp "$ROOT_DIR/references/taskboard-template.md" "$STAGE_DIR/references/taskboard-template.md"

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
