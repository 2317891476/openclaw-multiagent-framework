#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports/lint
cat > reports/lint/summary.json <<'JSON'
{
  "status": "stub",
  "gate": "lint",
  "message": "Replace with your project-specific lint command."
}
JSON
echo "lint stub complete"
