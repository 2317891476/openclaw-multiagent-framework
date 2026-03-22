#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports/synth
cat > reports/synth/summary.json <<'JSON'
{
  "status": "stub",
  "gate": "synth",
  "message": "Replace with your project-specific synthesis command."
}
JSON
echo "synth stub complete"
