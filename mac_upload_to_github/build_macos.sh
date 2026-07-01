#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-}"

cd "$ROOT_DIR"

python3 -m venv .venv-oa-review
source .venv-oa-review/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements-oa-review.txt
python -m PyInstaller --clean --noconfirm OA_Review_macos.spec

if [[ -n "$TARGET_DIR" ]]; then
  TARGET_ABS="$(cd -- "$TARGET_DIR" && pwd)"
  rm -rf "$TARGET_ABS/OA_Review.app"
  cp -R "$ROOT_DIR/dist/OA_Review.app" "$TARGET_ABS/OA_Review.app"
  echo "Built $TARGET_ABS/OA_Review.app"
else
  echo "Built $ROOT_DIR/dist/OA_Review.app"
  echo "Copy OA_Review.app into a cluster folder before opening it."
fi
