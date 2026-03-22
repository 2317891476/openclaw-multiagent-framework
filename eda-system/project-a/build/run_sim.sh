#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports/sim
cat > reports/sim/summary.json <<'JSON'
{
  "status": "stub",
  "gate": "sim",
  "message": "Replace with your project-specific simulation command."
}
JSON
echo "sim stub complete"
