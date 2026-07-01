#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$ROOT_DIR/oa_review_gui.py" ]]; then
  export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
elif [[ -f "$SCRIPT_DIR/oa_review_gui.py" ]]; then
  export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
else
  echo "oa_review_gui.py was not found."
  echo "Copy the full Astronaut_OA folder to this Mac, or put oa_review_gui.py next to this command file."
  read -r -p "Press Enter to close..."
  exit 1
fi

if [[ -x "$ROOT_DIR/.venv-oa-review/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv-oa-review/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 was not found. Install Python 3 for macOS first."
  read -r -p "Press Enter to close..."
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import tkinter
from PIL import Image
PY
then
  echo "Python dependencies are missing."
  echo "Run these commands from the Astronaut_OA folder:"
  echo "  python3 -m venv .venv-oa-review"
  echo "  source .venv-oa-review/bin/activate"
  echo "  python -m pip install -r requirements-oa-review.txt"
  read -r -p "Press Enter to close..."
  exit 1
fi

cd "$SCRIPT_DIR"
exec "$PYTHON_BIN" "$SCRIPT_DIR/visualisation.py"
