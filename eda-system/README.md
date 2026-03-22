# EDA System Template

Recommended top-level layout for a local EDA automation workspace:

```text
eda-system/
  orchestrator/
  adapters/
  iflow/
  workspace/
    project-a/
      IFLOW.md
      spec/
      rtl/
      tb/
      verif/
        assertions/
        cover/
        formal/
      build/
        run_lint.sh
        run_sim.sh
        run_formal.sh
        run_synth.sh
      reports/
        lint/
        sim/
        formal/
        synth/
  runs/
  state/
```

Separation of concerns:
- `workspace/project-a/` — business/design project
- `runs/` — execution traces and task outputs
- `state/` — orchestrator state machine files

Do not mix project source files with orchestration state or run artifacts.
