from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


DEFAULT_PIPELINE = ["spec", "rtl", "verif", "build"]
TERMINAL_STATUSES = {"completed", "failed"}


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
            return None
        if idx + 1 >= len(self.pipeline):
            return None
        return self.pipeline[idx + 1]

    def decide(self, current_stage: str, final_summary: dict) -> TransitionDecision:
        status = final_summary.get("status")
        if status != "completed":
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
