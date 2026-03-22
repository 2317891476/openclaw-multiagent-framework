#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from artifact_validator import validate_final_summary, validate_run_dir
from build_router import run_build_gate, should_run_build_gate
from prompt_builder import build_stage_prompt
from state_machine import StageMachine


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass
class OrchestratorPaths:
    repo_root: Path
    adapter_dir: Path
    jobs_root: Path


def infer_paths() -> OrchestratorPaths:
    repo_root = Path(__file__).resolve().parents[1]
    return OrchestratorPaths(
        repo_root=repo_root,
        adapter_dir=repo_root / "adapters" / "iflow",
        jobs_root=repo_root / "jobs",
    )


def ensure_default_job_state(job_id: str, goal: str, workspace: str | None, pipeline: list[str]) -> dict:
    return {
        "job_id": job_id,
        "goal": goal,
        "workspace": workspace,
        "current_stage": pipeline[0],
        "status": "pending",
        "current_task_id": None,
        "current_run_dir": None,
        "updated_at": now_iso(),
        "history": [],
    }


def make_task_id(stage: str, index: int) -> str:
    return f"task-{stage}-{index:03d}"


def run_adapter(paths: OrchestratorPaths, job_state: dict, stage: str, task_id: str, prompt: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["JOB_ID"] = job_state["job_id"]
    env["AGENT_TYPE"] = stage
    cmd = ["bash", str(paths.adapter_dir / "run_v1.sh"), prompt, task_id]
    return subprocess.run(
        cmd,
        cwd=job_state.get("workspace") or str(paths.repo_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def parse_runner_kv(stdout: str) -> dict:
    result: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def run_one_stage(paths: OrchestratorPaths, machine: StageMachine, job_state_path: Path, job_state: dict) -> dict:
    stage = job_state["current_stage"]
    next_index = len(job_state.get("history", [])) + 1
    task_id = make_task_id(stage, next_index)
    prompt = build_stage_prompt(job_state, stage)

    job_state["status"] = "running"
    job_state["current_task_id"] = task_id
    job_state["updated_at"] = now_iso()
    write_json(job_state_path, job_state)

    completed = run_adapter(paths, job_state, stage, task_id, prompt)
    kv = parse_runner_kv(completed.stdout)
    run_dir = kv.get("RUN_DIR")
    final_summary_path = kv.get("FINAL_SUMMARY_PATH")
    if not run_dir or not final_summary_path:
        raise RuntimeError(
            "adapter output missing RUN_DIR or FINAL_SUMMARY_PATH\n"
            f"stdout:\n{completed.stdout}\n\n"
            f"stderr:\n{completed.stderr}"
        )

    run_path = Path(run_dir)
    summary_path = Path(final_summary_path)
    validate_run_dir(run_path)
    final_summary = read_json(summary_path)
    validate_final_summary(final_summary)

    history_entry = {
        "stage": stage,
        "task_id": task_id,
        "result": final_summary.get("status"),
        "summary": final_summary.get("summary"),
        "run_dir": run_dir,
    }
    job_state.setdefault("history", []).append(history_entry)
    job_state["current_run_dir"] = run_dir

    if should_run_build_gate(stage, final_summary):
        history_entry["build_gate"] = run_build_gate(stage, final_summary, job_state.get("workspace") or str(paths.repo_root))

    decision = machine.decide(stage, final_summary)
    job_state["status"] = decision.job_status
    job_state["updated_at"] = now_iso()
    if decision.next_stage is not None:
        job_state["current_stage"] = decision.next_stage
    job_state["last_transition_reason"] = decision.reason
    write_json(job_state_path, job_state)
    return job_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Job Orchestrator v1 for iFlow adapter")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--goal", help="Create a new job if job_state.json does not exist")
    parser.add_argument("--workspace", help="Working directory for adapter execution")
    parser.add_argument("--once", action="store_true", help="Run at most one stage and exit")
    parser.add_argument("--max-stages", type=int, default=0, help="Optional cap on number of stages to execute in this invocation (0 = no cap)")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    paths = infer_paths()
    machine = StageMachine()

    job_dir = paths.jobs_root / args.job_id
    job_state_path = job_dir / "job_state.json"

    if job_state_path.exists():
        job_state = read_json(job_state_path)
    else:
        if not args.goal:
            raise SystemExit("job_state.json not found; provide --goal to create a new job")
        job_state = ensure_default_job_state(args.job_id, args.goal, args.workspace, machine.pipeline)
        write_json(job_state_path, job_state)

    executed = 0
    while job_state.get("status") not in {"completed", "failed"}:
        job_state = run_one_stage(paths, machine, job_state_path, job_state)
        executed += 1
        if args.once:
            break
        if args.max_stages and executed >= args.max_stages:
            break

    print(json.dumps(job_state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
