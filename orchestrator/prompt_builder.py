from __future__ import annotations

from textwrap import dedent


def build_stage_prompt(job_state: dict, stage: str) -> str:
    goal = job_state["goal"]
    workspace = job_state.get("workspace", "the current workspace")
    agent_type = stage
    history = job_state.get("history", [])
    history_lines = []
    for item in history[-5:]:
        history_lines.append(
            f"- stage={item.get('stage')} task_id={item.get('task_id')} result={item.get('result')}"
        )
    history_block = "\n".join(history_lines) if history_lines else "- (none yet)"

    return dedent(
        f"""
        You are the {agent_type} worker for job {job_state['job_id']}.

        Goal:
        {goal}

        Workspace:
        {workspace}

        Current stage:
        {stage}

        Prior history:
        {history_block}

        Output requirements:
        - Keep the final answer concise.
        - Make concrete file edits only when needed.
        - Respect project IFLOW.md constraints if present.
        - The adapter will capture stdout/stderr and produce final_summary.json.
        """
    ).strip()
