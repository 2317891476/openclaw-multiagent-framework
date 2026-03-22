# CPU Macro State Machine Quickstart

This quickstart is for the large RISC-V CPU upgrade workflow in local mode.

## Macro stages

```text
project_import
-> spec_clarify
-> top_partition
-> interface_define
-> rtl_core
-> rtl_memsys
-> lint_gate
-> tb_smoke
-> sim_gate
-> verification_collateral
-> formal_gate
-> synth_gate
-> convergence
-> final_report
```

## Recommended first run

```bash
cd /home/illya/.openclaw/workspace/repos/openclaw-multiagent-framework
python3 orchestrator/main.py \
  --job-id JOB-RISCV-OOO-001 \
  --goal "Import and decompose the SMT-risc-v_core repository into the local EDA workspace. Identify the existing SMT-related pipeline modules, execution pipeline boundaries, memory-system modules, and integration points that must be refactored for a future industrial-grade upgrade toward scoreboard-based out-of-order dual-issue execution, MMU/TLB/PTW support, non-blocking cache with MSHR and AXI4, and an AI coprocessor interface. Focus on repository decomposition, source mapping, and refactor target identification rather than immediate RTL redesign." \
  --workspace "$PWD/eda-system/project-a" \
  --max-stages 1 \
  --dispatch-mode local
```

## Continue the next stage

```bash
python3 orchestrator/main.py \
  --job-id JOB-RISCV-OOO-001 \
  --workspace "$PWD/eda-system/project-a" \
  --max-stages 1 \
  --dispatch-mode local
```

## What to inspect after each stage

```bash
cat jobs/JOB-RISCV-OOO-001/job_state.json
find runs/JOB-RISCV-OOO-001 -maxdepth 2 -type f | sort
cat runs/JOB-RISCV-OOO-001/task-project_import-001/final_summary.json
```

## Worker intent by stage

- `project_import`: import/decompose upstream open-source project into local EDA layout
- `spec_clarify`: clarify the architectural target and acceptance criteria
- `top_partition`: identify top-level subsystem boundaries
- `interface_define`: define architectural module interfaces
- `rtl_core`: modify execution-pipeline/control-side RTL
- `rtl_memsys`: modify MMU/cache/AXI/memory-side RTL
- `tb_smoke`: build a smoke-level bring-up testbench
- gate stages: run fixed scripts under `build/`
- `verification_collateral`: add assertions/coverage/formal collateral
- `convergence`: summarize unresolved blockers and route the next fix
- `final_report`: emit the final architecture/refactor summary
