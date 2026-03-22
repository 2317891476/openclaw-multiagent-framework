# iFlow CLI Adapter

This is the first-step single-worker adapter for the OpenClaw multi-agent framework.

Goal: establish one minimal closed loop:

```text
Supervisor
 -> generate prompt.txt / meta.json
 -> sessions_spawn(runtime="subagent")
 -> iflow CLI executes
 -> stdout/stderr captured
 -> wrapper generates final_summary.json
 -> watcher marks completion
 -> Supervisor reads result
```

## Directory layout

Each task run should look like:

```text
runs/JOB-001/task-rtl-001/
  prompt.txt
  meta.json
  stdout.log
  stderr.log
  status.json
  final_summary.json
```

The most important file is `final_summary.json`.

## Files

- `run_v1.sh` — blocking wrapper, best entrypoint for orchestrators
- `runner.js` — launches `iflow -y -p <task>` with timeout + stall watchdog
- `watcher.js` — reads `status.json` and emits progress / terminal events
- `cleanup.sh` — cleanup helper for old run directories

## Wrapper usage

```bash
JOB_ID=JOB-001 AGENT_TYPE=rtl \
  bash adapters/iflow/run_v1.sh "Implement FIFO full/empty logic" task-rtl-001
```

Or with a prompt file (recommended for orchestrators):

```bash
JOB_ID=JOB-001 AGENT_TYPE=rtl \
  bash adapters/iflow/run_v1.sh --task-file jobs/JOB-001/prompts/task-rtl-001.txt task-rtl-001
```

## Direct runner usage

```bash
node adapters/iflow/runner.js \
  --job-id JOB-001 \
  --task-id task-rtl-001 \
  --agent-type rtl \
  --cwd "$PWD" \
  --task "Implement FIFO full/empty logic"
```

## `final_summary.json` schema (v1)

```json
{
  "job_id": "JOB-001",
  "task_id": "task-rtl-001",
  "agent_type": "rtl",
  "status": "completed",
  "changed_files": ["rtl/fifo.sv"],
  "summary": "Implemented pointer update and full/empty logic.",
  "next_hint": "run_lint"
}
```

Current implementation guarantees the schema shell and adapter metadata. `changed_files` and `next_hint` are placeholders for now and can be enriched by a later structured-output pass.

## Notes

- This adapter isolates the execution protocol from the upper orchestrator.
- The orchestrator should read `final_summary.json`, not raw iFlow prose.
- `IFLOW.md` in the project root is the right place for worker constraints.
