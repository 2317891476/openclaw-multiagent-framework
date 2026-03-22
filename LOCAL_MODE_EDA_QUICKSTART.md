# Local Mode EDA Quickstart

This is the recommended first path for using the framework with iFlow CLI.

## 1. Enter the repo

```bash
cd /home/illya/.openclaw/workspace/repos/openclaw-multiagent-framework
```

## 2. Use the scaffolded EDA project

```bash
cd eda-system/project-a
```

Project layout includes:
- `spec/`
- `rtl/`
- `tb/`
- `verif/assertions/`
- `verif/cover/`
- `verif/formal/`
- `build/run_lint.sh`
- `build/run_sim.sh`
- `build/run_formal.sh`
- `build/run_synth.sh`
- `reports/`

## 3. Run a single local orchestrator stage

```bash
cd /home/illya/.openclaw/workspace/repos/openclaw-multiagent-framework
python3 orchestrator/main.py \
  --job-id JOB-EDA-001 \
  --goal "Implement a parameterized FIFO" \
  --workspace "$PWD/eda-system/project-a" \
  --max-stages 1 \
  --dispatch-mode local
```

## 4. Continue the next stage

```bash
python3 orchestrator/main.py \
  --job-id JOB-EDA-001 \
  --workspace "$PWD/eda-system/project-a" \
  --max-stages 1 \
  --dispatch-mode local
```

## 5. Inspect outputs

Job state:

```bash
cat jobs/JOB-EDA-001/job_state.json
```

Run outputs:

```bash
find runs/JOB-EDA-001 -maxdepth 2 -type f | sort
cat runs/JOB-EDA-001/task-spec-001/final_summary.json
```

Build gate summaries:

```bash
cat eda-system/project-a/reports/summary.json
cat eda-system/project-a/reports/lint/summary.json
cat eda-system/project-a/reports/sim/summary.json
cat eda-system/project-a/reports/formal/summary.json
cat eda-system/project-a/reports/synth/summary.json
```

## Notes

- This mode is the current stable path.
- Gate scripts are fixed entrypoints and currently stubs.
- Replace the stub scripts with your real EDA toolchain commands later.
