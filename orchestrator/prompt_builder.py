from __future__ import annotations

from textwrap import dedent

from worker_profiles import get_worker_profile


STAGE_HINTS = {
    "project_import": "Decompose or import an existing open-source/project structure into the local EDA skeleton. Create mapping/spec artifacts first; do not jump straight into redesign.",
    "spec": "Produce specification artifacts only. Do not implement RTL yet.",
    "rtl": "Implement or refine RTL according to the spec artifacts.",
    "lint_gate": "Run the fixed lint script and summarize the result, do not improvise commands.",
    "tb": "Implement or refine testbench collateral only.",
    "sim_gate": "Run the fixed simulation script and summarize the result, do not improvise commands. Prefer iverilog + vvp; wave viewing should be prepared for gtkwave but not block CI-style execution.",
    "verification": "Implement assertions/coverage/formal collateral only.",
    "formal_gate": "Run the fixed formal script and summarize the result, do not improvise commands.",
    "synth_gate": "Run the fixed synthesis script and summarize the result, do not improvise commands.",
    "rtl_fix": "Apply the smallest RTL change required to address the failed gate.",
    "tb_fix": "Apply the smallest TB change required to address the failed gate.",
    "verification_fix": "Apply the smallest verification collateral change required to address the failed gate.",
    "build_fix": "Only fix build/report automation issues unless the prompt explicitly allows broader changes.",
}


def build_stage_prompt(job_state: dict, stage: str) -> str:
    goal = job_state["goal"]
    workspace = job_state.get("workspace", "the current workspace")
    history = job_state.get("history", [])
    profile = get_worker_profile(stage)
    history_lines = []
    for item in history[-5:]:
        history_lines.append(
            f"- stage={item.get('stage')} task_id={item.get('task_id')} result={item.get('result')}"
        )
    history_block = "\n".join(history_lines) if history_lines else "- (none yet)"
    allowed_paths = "\n".join(f"- {p}" for p in profile.allowed_paths) if profile.allowed_paths else "- (none)"
    required_outputs = "\n".join(f"- {p}" for p in profile.required_outputs) if profile.required_outputs else "- (none required)"
    extra_notes = "\n".join(f"- {n}" for n in profile.notes) if profile.notes else "- (none)"
    stage_hint = STAGE_HINTS.get(stage, "Perform only the work appropriate for this stage.")

    return dedent(
        f"""
        You are the {profile.name} for job {job_state['job_id']}.

        Goal:
        {goal}

        Workspace:
        {workspace}

        Current stage:
        {stage}

        Worker purpose:
        {profile.purpose}

        Stage directive:
        {stage_hint}

        Allowed paths:
        {allowed_paths}

        Required outputs for this stage:
        {required_outputs}

        Additional notes:
        {extra_notes}

        Prior history:
        {history_block}

        Output requirements:
        - Keep the final answer concise.
        - Respect project IFLOW.md constraints if present.
        - Do not modify files outside the allowed paths.
        - If this is a gate stage, prefer fixed scripts under build/ instead of ad-hoc commands.
        - If simulation is involved, keep execution non-interactive; write wave artifacts that can later be opened in gtkwave.
        - The adapter will capture stdout/stderr and produce final_summary.json.
        """
    ).strip()
