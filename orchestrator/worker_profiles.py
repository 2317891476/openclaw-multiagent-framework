from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerProfile:
    name: str
    agent_type: str
    purpose: str
    allowed_paths: tuple[str, ...]
    required_outputs: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


WORKER_PROFILES: dict[str, WorkerProfile] = {
    "project_import": WorkerProfile(
        name="project-import-worker",
        agent_type="project_import",
        purpose="Decompose an upstream/open-source project into the EDA project skeleton without implementing new design intent.",
        allowed_paths=("spec/", "rtl/", "tb/", "verif/", "build/", "reports/"),
        required_outputs=(
            "spec/import_manifest.md",
            "spec/source_map.md",
            "build/filelist.f",
        ),
        notes=(
            "Focus on mapping/importing existing project structure into the local EDA layout.",
            "Do not invent missing functionality beyond what is needed for a faithful decomposition.",
        ),
    ),
    "spec_clarify": WorkerProfile(
        name="spec-worker",
        agent_type="spec",
        purpose="Clarify system goals, constraints, and acceptance criteria for the upgraded CPU.",
        allowed_paths=("spec/",),
        required_outputs=(
            "spec/module_spec.md",
            "spec/acceptance.yaml",
        ),
    ),
    "top_partition": WorkerProfile(
        name="spec-worker",
        agent_type="spec",
        purpose="Partition the CPU into top-level architectural blocks and data/control domains.",
        allowed_paths=("spec/",),
        required_outputs=(
            "spec/top_partition.md",
            "spec/pipeline_overview.md",
        ),
    ),
    "interface_define": WorkerProfile(
        name="spec-worker",
        agent_type="spec",
        purpose="Define precise module interfaces and architectural contracts before implementation.",
        allowed_paths=("spec/",),
        required_outputs=(
            "spec/interface.md",
            "spec/timing_reset.md",
            "spec/corner_cases.md",
        ),
    ),
    "rtl_core": WorkerProfile(
        name="rtl-worker",
        agent_type="rtl",
        purpose="Implement or refactor core execution pipeline RTL (issue/execute/writeback/control).",
        allowed_paths=("rtl/",),
        notes=("Allowed file types: rtl/*.v, rtl/*.sv",),
    ),
    "rtl_memsys": WorkerProfile(
        name="rtl-worker",
        agent_type="rtl",
        purpose="Implement or refactor memory-system RTL (MMU/TLB/PTW/cache/MSHR/AXI side).",
        allowed_paths=("rtl/",),
    ),
    "rtl_fix": WorkerProfile(
        name="rtl-worker",
        agent_type="rtl",
        purpose="Fix RTL issues reported by a failed gate.",
        allowed_paths=("rtl/",),
        notes=("Focus only on RTL fixes needed to satisfy the failed gate.",),
    ),
    "tb_smoke": WorkerProfile(
        name="tb-worker",
        agent_type="tb",
        purpose="Create or refine smoke-level testbench collateral for bring-up and regression entry.",
        allowed_paths=("tb/",),
    ),
    "tb_fix": WorkerProfile(
        name="tb-worker",
        agent_type="tb",
        purpose="Fix testbench issues reported by simulation or integration gates.",
        allowed_paths=("tb/",),
    ),
    "verification_collateral": WorkerProfile(
        name="verification-worker",
        agent_type="verification",
        purpose="Implement assertions, coverage, and formal collateral only.",
        allowed_paths=("verif/assertions/", "verif/cover/", "verif/formal/"),
    ),
    "verification_fix": WorkerProfile(
        name="verification-worker",
        agent_type="verification",
        purpose="Fix verification collateral in response to formal or verification failures.",
        allowed_paths=("verif/assertions/", "verif/cover/", "verif/formal/"),
    ),
    "convergence": WorkerProfile(
        name="build-worker",
        agent_type="build",
        purpose="Summarize gate results, residual risks, and the minimal next fix target.",
        allowed_paths=("reports/", "spec/"),
        required_outputs=("reports/summary.json",),
    ),
    "final_report": WorkerProfile(
        name="spec-worker",
        agent_type="spec",
        purpose="Produce the final architecture/refactor report and roadmap summary.",
        allowed_paths=("spec/", "reports/"),
        required_outputs=("reports/summary.json",),
    ),
    "build": WorkerProfile(
        name="build-worker",
        agent_type="build",
        purpose="Execute fixed build/lint/sim/formal/synth scripts and summarize results.",
        allowed_paths=("build/", "reports/"),
        required_outputs=("reports/summary.json",),
        notes=("Prefer fixed scripts over free-form shell decisions.",),
    ),
    "build_fix": WorkerProfile(
        name="build-worker",
        agent_type="build",
        purpose="Repair build-script or report issues without touching design files unless explicitly allowed.",
        allowed_paths=("build/", "reports/"),
    ),
}


def get_worker_profile(stage: str) -> WorkerProfile:
    if stage in {"lint_gate", "sim_gate", "formal_gate", "synth_gate"}:
        return WORKER_PROFILES["build"]
    return WORKER_PROFILES.get(stage, WORKER_PROFILES["spec_clarify"])
