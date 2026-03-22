from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


DEFAULT_PIPELINE = [
    "spec",
    "rtl",
    "lint_gate",
    "tb",
    "sim_gate",
    "verification",
    "formal_gate",
    "synth_gate",
]

FAILURE_ROUTES = {
    "lint_gate": "rtl_fix",
    "sim_gate": "tb_fix",
    "formal_gate": "verification_fix",
    "synth_gate": "build_fix",
    "rtl_fix": "lint_gate",
    "tb_fix": "sim_gate",
    "verification_fix": "formal_gate",
    "build_fix": "synth_gate",
}

GATE_STAGES = {"lint_gate", "sim_gate", "formal_gate", "synth_gate"}


@dataclass
class TransitionDecision:
    next_stage: Optional[str]
    job_status: str
    reason: str


class StageMachine:
    def __init__(self, pipeline: list[str] | None = None):
        self.pipeline = pipeline or list(DEFAULT_PIPELINE)

    def first_stage(self) -> str:
        return self.pipeline[0]

    def next_stage_after(self, stage: str) -> Optional[str]:
        try:
            idx = self.pipeline.index(stage)
        except ValueError:
            return FAILURE_ROUTES.get(stage)
        if idx + 1 >= len(self.pipeline):
            return None
        return self.pipeline[idx + 1]

    def decide(self, current_stage: str, final_summary: dict) -> TransitionDecision:
        status = final_summary.get("status")
        if status != "completed":
            fallback = FAILURE_ROUTES.get(current_stage)
            if fallback:
                return TransitionDecision(
                    next_stage=fallback,
                    job_status="running",
                    reason=f"stage {current_stage} failed -> route to {fallback}",
                )
            return TransitionDecision(
                next_stage=None,
                job_status="failed",
                reason=f"stage {current_stage} returned status={status!r}",
            )

        next_stage = self.next_stage_after(current_stage)
        if next_stage is None:
            return TransitionDecision(
                next_stage=None,
                job_status="completed",
                reason="pipeline exhausted",
            )

        return TransitionDecision(
            next_stage=next_stage,
            job_status="running",
            reason=f"advance to {next_stage}",
        )
