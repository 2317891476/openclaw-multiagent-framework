# Job Orchestrator v1

This is the first-pass orchestrator for the iFlow CLI adapter.

## Goal

Turn the single-task adapter into a stage-driven job loop:

```text
read job_state.json
-> decide current_stage
-> build prompt
-> run adapters/iflow/run_v1.sh
-> read final_summary.json
-> validate artifacts
-> advance stage / fail / complete
```

## Files

- `main.py` — orchestrator entrypoint
- `state_machine.py` — stage transition policy
- `prompt_builder.py` — per-stage prompt builder
- `artifact_validator.py` — validates run directory + final summary shape
- `build_router.py` — build gate stub for later expansion
- `schemas/job_state.schema.json` — job-state schema reference

## Create and run a job

```bash
cd /home/illya/.openclaw/workspace/repos/openclaw-multiagent-framework
python3 orchestrator/main.py \
  --job-id JOB-DEMO-001 \
  --goal "Implement a parameterized FIFO" \
  --workspace "$PWD" \
  --max-stages 1
```

This creates:

```text
jobs/JOB-DEMO-001/job_state.json
```

and one adapter run under:

```text
runs/JOB-DEMO-001/task-<stage>-001/
```

## Continue a job

```bash
python3 orchestrator/main.py --job-id JOB-DEMO-001 --workspace "$PWD" --max-stages 1
```

## Current scope

- stage pipeline v3: `project_import -> spec_clarify -> top_partition -> interface_define -> rtl_core -> rtl_memsys -> lint_gate -> tb_smoke -> sim_gate -> verification_collateral -> formal_gate -> synth_gate -> convergence -> final_report`
- worker-profile model instead of long-lived personas:
  - `project-import-worker`
  - `spec-worker`
  - `rtl-worker`
  - `tb-worker`
  - `verification-worker`
  - `build-worker`
- verified local execution via `adapters/iflow/run_v1.sh`
- experimental dispatch mode: `agent-subagent` (uses `openclaw agent` to request a `sessions_spawn(runtime="subagent")` turn)
- build/integration gates prefer fixed scripts under `build/`
- no parallelism yet

## Dispatch modes

### `--dispatch-mode local`

The orchestrator directly runs the adapter wrapper locally. This path is verified.

### `--dispatch-mode agent-subagent`

The orchestrator writes a prompt file, then asks an OpenClaw agent turn to spawn a subagent that runs the adapter wrapper.

Example:

```bash
python3 orchestrator/main.py \
  --job-id JOB-DEMO-002 \
  --goal "Implement a parameterized FIFO" \
  --workspace "$PWD" \
  --max-stages 1 \
  --dispatch-mode agent-subagent \
  --dispatcher-agent main
```

Current note: this mode is asynchronous in two phases: (1) wait for `final_summary.json`, then (2) wait a bit longer for framework state (`subagent-task-registry.json` / `job-status/*.json`) to move from pending to terminal. Use `--state-bridge-timeout-s` to control the second wait window.

## Next planned steps

- stabilize the `sessions_spawn(runtime="subagent")` bridge with a pinned dispatcher session
- enrich `final_summary.json` with `changed_files`
- add artifact validators per stage
- add build/lint/test gates
