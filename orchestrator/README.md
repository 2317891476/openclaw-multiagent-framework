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

- fixed stage pipeline: `spec -> rtl -> verif -> build`
- verified local execution via `adapters/iflow/run_v1.sh`
- experimental dispatch mode: `agent-subagent` (uses `openclaw agent` to request a `sessions_spawn(runtime="subagent")` turn)
- no parallelism yet
- no real build gate yet

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

Current note: the bridge code is present, but in this machine's shell environment `openclaw agent ...` behaved as a blocking CLI and did not yet complete a verified end-to-end smoke test. Treat this mode as experimental until a stable requester session / CLI path is pinned.

## Next planned steps

- stabilize the `sessions_spawn(runtime="subagent")` bridge with a pinned dispatcher session
- enrich `final_summary.json` with `changed_files`
- add artifact validators per stage
- add build/lint/test gates
