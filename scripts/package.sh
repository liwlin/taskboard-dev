#!/usr/bin/env bash
set -euo pipefail

VERSION="${VERSION:-v4.2}"
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
  else
    echo "zip not found; skipped $NAME-$VERSION.zip" >&2
  fi
)

echo "Packaged:"
echo "  $DIST_DIR/$NAME-$VERSION.tar.gz"
if [[ -f "$DIST_DIR/$NAME-$VERSION.zip" ]]; then
  echo "  $DIST_DIR/$NAME-$VERSION.zip"
fi
