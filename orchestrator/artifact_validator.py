from __future__ import annotations

from pathlib import Path


class ArtifactValidationError(RuntimeError):
    pass


REQUIRED_RUN_FILES = [
    "prompt.txt",
    "meta.json",
    "stdout.log",
    "stderr.log",
    "status.json",
    "final_summary.json",
]


def validate_run_dir(run_dir: str | Path) -> None:
    run_path = Path(run_dir)
    if not run_path.exists():
        raise ArtifactValidationError(f"run directory does not exist: {run_path}")

    missing = [name for name in REQUIRED_RUN_FILES if not (run_path / name).exists()]
    if missing:
        raise ArtifactValidationError(
            f"run directory missing required files: {', '.join(missing)}"
        )


def validate_final_summary(summary: dict) -> None:
    required = [
        "job_id",
        "task_id",
        "agent_type",
        "status",
        "changed_files",
        "summary",
        "next_hint",
    ]
    missing = [key for key in required if key not in summary]
    if missing:
        raise ArtifactValidationError(
            f"final_summary missing required keys: {', '.join(missing)}"
        )
