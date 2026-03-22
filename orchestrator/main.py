#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
    shared_context: Path
    task_registry: Path
    job_status_dir: Path


def infer_paths() -> OrchestratorPaths:
    repo_root = Path(__file__).resolve().parents[1]
    shared_context = Path.home() / ".openclaw" / "shared-context"
    return OrchestratorPaths(
        repo_root=repo_root,
        adapter_dir=repo_root / "adapters" / "iflow",
        jobs_root=repo_root / "jobs",
        shared_context=shared_context,
        task_registry=shared_context / "monitor-tasks" / "subagent-task-registry.json",
        job_status_dir=shared_context / "job-status",
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


def write_prompt_artifact(job_dir: Path, task_id: str, prompt: str) -> Path:
    prompts_dir = job_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    path = prompts_dir / f"{task_id}.txt"
    path.write_text(prompt + "\n", encoding="utf-8")
    return path


def parse_runner_kv(stdout: str) -> dict:
    result: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def try_read_json(path: Path) -> Optional[dict]:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_framework_task_record(paths: OrchestratorPaths, job_id: str, task_id: str) -> tuple[Optional[str], Optional[dict]]:
    payload = try_read_json(paths.task_registry)
    if not isinstance(payload, dict):
        return None, None
    for framework_task_id, record in payload.items():
        evidence = record.get("evidence") or {}
        task_text = str(evidence.get("task") or "")
        if job_id in task_text and task_id in task_text:
            return framework_task_id, record
    return None, None


def wait_for_framework_task_terminal(paths: OrchestratorPaths, job_id: str, task_id: str, timeout_s: int) -> tuple[Optional[str], Optional[dict], Optional[dict]]:
    deadline = time.time() + timeout_s
    found_task_id = None
    while time.time() < deadline:
        framework_task_id, record = find_framework_task_record(paths, job_id, task_id)
        if framework_task_id:
            found_task_id = framework_task_id
            job_status = try_read_json(paths.job_status_dir / f"{framework_task_id}.json")
            callback_status = str(record.get("callback_status") or "")
            registry_state = str(record.get("state") or "")
            job_state = str((job_status or {}).get("state") or "")
            if callback_status in {"acked", "received"} or registry_state in {"completed", "failed", "timeout"} or job_state in {"callback_received", "failed", "timeout"}:
                return framework_task_id, record, job_status
        time.sleep(2)
    return found_task_id, None, None


def run_adapter_local(paths: OrchestratorPaths, job_state: dict, stage: str, task_id: str, prompt_file: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["JOB_ID"] = job_state["job_id"]
    env["AGENT_TYPE"] = stage
    cmd = ["bash", str(paths.adapter_dir / "run_v1.sh"), "--task-file", str(prompt_file), task_id]
    return subprocess.run(
        cmd,
        cwd=job_state.get("workspace") or str(paths.repo_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def build_subagent_dispatch_message(paths: OrchestratorPaths, job_state: dict, stage: str, task_id: str, prompt_file: Path) -> str:
    workspace = job_state.get("workspace") or str(paths.repo_root)
    command = (
        f"cd {shlex.quote(workspace)} && "
        f"JOB_ID={shlex.quote(job_state['job_id'])} "
        f"AGENT_TYPE={shlex.quote(stage)} "
        f"bash {shlex.quote(str(paths.adapter_dir / 'run_v1.sh'))} "
        f"--task-file {shlex.quote(str(prompt_file))} {shlex.quote(task_id)}"
    )
    return (
        "Use sessions_spawn right now to start exactly one subagent run.\n"
        "Parameters: runtime='subagent', mode='run', cleanup='delete', cwd set to the workspace below.\n"
        f"Workspace: {workspace}\n"
        "The child subagent task is: run exactly this shell command and then stop.\n"
        f"{command}\n"
        "Do not do the work yourself. Only spawn the subagent. After spawning, reply briefly with the child session key or run id if available."
    )


def run_adapter_via_agent_subagent(
    paths: OrchestratorPaths,
    job_state: dict,
    stage: str,
    task_id: str,
    prompt_file: Path,
    dispatcher_session_id: str | None,
    dispatcher_agent: str,
    wait_timeout_s: int,
    state_bridge_timeout_s: int,
) -> subprocess.CompletedProcess:
    workspace = job_state.get("workspace") or str(paths.repo_root)
    message = build_subagent_dispatch_message(paths, job_state, stage, task_id, prompt_file)
    cmd = ["openclaw", "agent", "--json", "--message", message]
    if dispatcher_session_id:
        cmd.extend(["--session-id", dispatcher_session_id])
    else:
        cmd.extend(["--agent", dispatcher_agent])

    dispatch = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, check=False)
    run_dir = Path(workspace) / "runs" / job_state["job_id"] / task_id
    summary_path = run_dir / "final_summary.json"
    deadline = time.time() + wait_timeout_s
    while time.time() < deadline:
        if summary_path.exists():
            framework_task_id, registry_record, job_status = wait_for_framework_task_terminal(
                paths,
                job_state["job_id"],
                task_id,
                state_bridge_timeout_s,
            )
            stdout = f"RUN_DIR={run_dir}\nFINAL_SUMMARY_PATH={summary_path}\n"
            if framework_task_id:
                stdout += f"FRAMEWORK_TASK_ID={framework_task_id}\n"
            if registry_record:
                stdout += f"FRAMEWORK_CALLBACK_STATUS={registry_record.get('callback_status')}\n"
            if job_status:
                stdout += f"FRAMEWORK_JOB_STATE={job_status.get('state')}\n"
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr=(dispatch.stdout or "") + (dispatch.stderr or ""))
        time.sleep(2)

    return subprocess.CompletedProcess(
        cmd,
        1,
        stdout=dispatch.stdout,
        stderr=(dispatch.stderr or "") + f"\nTimed out waiting for {summary_path}",
    )


def run_one_stage(
    paths: OrchestratorPaths,
    machine: StageMachine,
    job_state_path: Path,
    job_state: dict,
    dispatch_mode: str,
    dispatcher_session_id: str | None,
    dispatcher_agent: str,
    subagent_wait_timeout_s: int,
    state_bridge_timeout_s: int,
) -> dict:
    stage = job_state["current_stage"]
    next_index = len(job_state.get("history", [])) + 1
    task_id = make_task_id(stage, next_index)
    prompt = build_stage_prompt(job_state, stage)
    prompt_file = write_prompt_artifact(job_state_path.parent, task_id, prompt)

    job_state["status"] = "running"
    job_state["current_task_id"] = task_id
    job_state["updated_at"] = now_iso()
    write_json(job_state_path, job_state)

    if dispatch_mode == "local":
        completed = run_adapter_local(paths, job_state, stage, task_id, prompt_file)
    elif dispatch_mode == "agent-subagent":
        completed = run_adapter_via_agent_subagent(
            paths,
            job_state,
            stage,
            task_id,
            prompt_file,
            dispatcher_session_id,
            dispatcher_agent,
            subagent_wait_timeout_s,
            state_bridge_timeout_s,
        )
    else:
        raise RuntimeError(f"unknown dispatch mode: {dispatch_mode}")

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
    framework_task_id = kv.get("FRAMEWORK_TASK_ID")
    framework_callback_status = kv.get("FRAMEWORK_CALLBACK_STATUS")
    framework_job_state = kv.get("FRAMEWORK_JOB_STATE")
    if framework_task_id:
        history_entry["framework_task_id"] = framework_task_id
    if framework_callback_status:
        history_entry["framework_callback_status"] = framework_callback_status
    if framework_job_state:
        history_entry["framework_job_state"] = framework_job_state

    job_state.setdefault("history", []).append(history_entry)
    job_state["current_run_dir"] = run_dir

    if should_run_build_gate(stage, final_summary):
        history_entry["build_gate"] = run_build_gate(
            stage,
            final_summary,
            job_state.get("workspace") or str(paths.repo_root),
        )

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
    parser.add_argument("--dispatch-mode", choices=["local", "agent-subagent"], default="local")
    parser.add_argument("--dispatcher-session-id", help="Existing OpenClaw session id used to issue sessions_spawn via openclaw agent")
    parser.add_argument("--dispatcher-agent", default="main", help="Agent id to use when dispatcher session id is not provided")
    parser.add_argument("--subagent-wait-timeout-s", type=int, default=1800, help="How long to wait for adapter final_summary.json when dispatching via sessions_spawn")
    parser.add_argument("--state-bridge-timeout-s", type=int, default=120, help="Extra time to wait for framework registry/job-status to move from pending to terminal after final_summary.json exists")
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
        job_state = run_one_stage(
            paths,
            machine,
            job_state_path,
            job_state,
            dispatch_mode=args.dispatch_mode,
            dispatcher_session_id=args.dispatcher_session_id,
            dispatcher_agent=args.dispatcher_agent,
            subagent_wait_timeout_s=args.subagent_wait_timeout_s,
            state_bridge_timeout_s=args.state_bridge_timeout_s,
        )
        executed += 1
        if args.once:
            break
        if args.max_stages and executed >= args.max_stages:
            break

    print(json.dumps(job_state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
