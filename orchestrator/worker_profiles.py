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
    "spec": WorkerProfile(
        name="spec-worker",
        agent_type="spec",
        purpose="Produce specifications and acceptance criteria only.",
        allowed_paths=("spec/",),
        required_outputs=(
            "spec/module_spec.md",
            "spec/interface.md",
            "spec/timing_reset.md",
            "spec/corner_cases.md",
            "spec/acceptance.yaml",
        ),
        notes=("Do not edit rtl/, tb/, verif/, or build/.",),
    ),
    "rtl": WorkerProfile(
        name="rtl-worker",
        agent_type="rtl",
        purpose="Implement or fix RTL only.",
        allowed_paths=("rtl/",),
        notes=("Allowed file types: rtl/*.v, rtl/*.sv",),
    ),
    "rtl_fix": WorkerProfile(
        name="rtl-worker",
        agent_type="rtl",
        purpose="Fix RTL issues reported by a failed gate.",
        allowed_paths=("rtl/",),
        notes=("Focus only on RTL fixes needed to satisfy the failed gate.",),
    ),
    "tb": WorkerProfile(
        name="tb-worker",
        agent_type="tb",
        purpose="Implement or fix testbench code only.",
        allowed_paths=("tb/",),
    ),
    "tb_fix": WorkerProfile(
        name="tb-worker",
        agent_type="tb",
        purpose="Fix testbench issues reported by simulation or integration gates.",
        allowed_paths=("tb/",),
    ),
    "verification": WorkerProfile(
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
    return WORKER_PROFILES.get(stage, WORKER_PROFILES.get(stage.replace("_gate", ""), WORKER_PROFILES["spec"]))
