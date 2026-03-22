from __future__ import annotations

import subprocess
from pathlib import Path


GATE_TO_SCRIPT = {
    "lint_gate": "build/run_lint.sh",
    "sim_gate": "build/run_sim.sh",
    "formal_gate": "build/run_formal.sh",
    "synth_gate": "build/run_synth.sh",
}


def should_run_build_gate(stage: str, summary: dict) -> bool:
    return stage in GATE_TO_SCRIPT


def run_build_gate(stage: str, summary: dict, cwd: str) -> dict:
    rel = GATE_TO_SCRIPT.get(stage)
    if not rel:
        return {
            "stage": stage,
            "status": "skipped",
            "reason": "no gate script mapped",
            "cwd": cwd,
        }

    script = Path(cwd) / rel
    if not script.exists():
        return {
            "stage": stage,
            "status": "missing",
            "reason": f"gate script not found: {script}",
            "cwd": cwd,
            "script": str(script),
        }

    result = subprocess.run(["bash", str(script)], cwd=cwd, capture_output=True, text=True, check=False)
    return {
        "stage": stage,
        "status": "completed" if result.returncode == 0 else "failed",
        "cwd": cwd,
        "script": str(script),
        "returncode": result.returncode,
        "stdout_tail": (result.stdout or "")[-2000:],
        "stderr_tail": (result.stderr or "")[-2000:],
    }
