from __future__ import annotations


def should_run_build_gate(stage: str, summary: dict) -> bool:
    # v1 policy: only run build gate after verif/build if caller opts in later.
    return False


def run_build_gate(stage: str, summary: dict, cwd: str) -> dict:
    return {
        "stage": stage,
        "status": "skipped",
        "reason": "build gate not enabled in orchestrator v1",
        "cwd": cwd,
    }
