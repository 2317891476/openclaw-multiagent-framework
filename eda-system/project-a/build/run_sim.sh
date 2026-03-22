#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
cd "$PROJECT_ROOT"

mkdir -p reports/sim build

if ! command -v iverilog >/dev/null 2>&1; then
  python3 build/_write_summary.py sim failed "iverilog not found in PATH"
  exit 1
fi
if ! command -v vvp >/dev/null 2>&1; then
  python3 build/_write_summary.py sim failed "vvp not found in PATH"
  exit 1
fi

FILELIST="build/filelist.f"
if [ ! -f "$FILELIST" ]; then
  cat > "$FILELIST" <<'EOF'
# Add one Verilog/SystemVerilog source file per line.
# Example:
# rtl/top.sv
# tb/top_tb.sv
EOF
  python3 build/_write_summary.py sim failed "build/filelist.f missing; template created"
  exit 1
fi

SIM_OUT="build/sim.out"
LOG_PATH="reports/sim/run.log"
VCD_PATH="reports/sim/wave.vcd"

set +e
iverilog -g2012 -o "$SIM_OUT" -c "$FILELIST" >"$LOG_PATH" 2>&1
compile_rc=$?
if [ $compile_rc -eq 0 ]; then
  VVP_OUT="$VCD_PATH" vvp "$SIM_OUT" >>"$LOG_PATH" 2>&1
  run_rc=$?
else
  run_rc=$compile_rc
fi
set -e

if [ $run_rc -eq 0 ]; then
  python3 build/_write_summary.py sim passed "iverilog/vvp simulation passed; open reports/sim/wave.vcd with gtkwave if needed"
else
  python3 build/_write_summary.py sim failed "iverilog/vvp simulation failed; inspect reports/sim/run.log"
  exit $run_rc
fi
