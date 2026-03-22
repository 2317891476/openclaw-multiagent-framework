#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
cd "$PROJECT_ROOT"
VCD_PATH="reports/sim/wave.vcd"
if [ ! -f "$VCD_PATH" ]; then
  echo "wave file not found: $VCD_PATH" >&2
  exit 1
fi
if ! command -v gtkwave >/dev/null 2>&1; then
  echo "gtkwave not found in PATH" >&2
  exit 1
fi
exec gtkwave "$VCD_PATH"
