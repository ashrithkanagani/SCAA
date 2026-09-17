"""
JSSP narrator. Structurally different from the other three domains' agent
rationale (since candidates here are competing JOBS for one machine, not
competing actions for one job) -- but still inherits the exact same
two-sentence skeleton and conditional gate-reasoning sentence from
BaseTemplateNarrator, unchanged.
"""

from __future__ import annotations

from ...narration import BaseTemplateNarrator
from ...trace import DecisionStep


class JSSPNarrator(BaseTemplateNarrator):
    def _describe_action(self, label: str) -> str:
        if label.startswith("assign_job_"):
            jid = label.split("assign_job_")[1]
            return f"dispatching Job {jid}'s next operation"
        return label

    def _agent_rationale(self, step: DecisionStep) -> str:
        if step.runner_up_label is None:
            return "It was the only job with a ready operation for this machine at this moment."

        chosen_jid = step.chosen_label.split("assign_job_")[1]
        runner_jid = step.runner_up_label.split("assign_job_")[1]
        return (f"Job {chosen_jid} and Job {runner_jid} both had operations ready for this machine; "
                f"Job {chosen_jid} was dispatched first under the shortest-processing-time rule "
                f"(with job priority tier as the tie-break for near-equal operation durations).")
