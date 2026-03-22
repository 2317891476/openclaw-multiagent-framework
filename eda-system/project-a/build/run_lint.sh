#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}/.."
python3 build/_write_summary.py lint passed "Stub lint gate passed. Replace with your project-specific lint command."
