#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}/.."
python3 build/_write_summary.py sim passed "Stub simulation gate passed. Replace with your project-specific simulation command."
