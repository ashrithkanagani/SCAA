"""Cloud task-scheduling narrator. Subclasses BaseTemplateNarrator, same pattern as domains/delivery/narration.py."""

from __future__ import annotations

from ...narration import BaseTemplateNarrator
from ...trace import DecisionStep


class CloudNarrator(BaseTemplateNarrator):
    def _describe_action(self, label: str) -> str:
        if label.startswith("assign->M"):
            srv = label.split("assign->M")[1]
            return f"provisioning Server {srv}"
        if label == "defer":
            return "queueing the task for the next cycle"
        if label == "reject":
            return "denying the task"
        return label

    def _action_type(self, label: str) -> str:
        return "assign" if label.startswith("assign->M") else label

    def _agent_rationale(self, step: DecisionStep) -> str:
        chosen_type = self._action_type(step.chosen_label)
        runner_type = self._action_type(step.runner_up_label) if step.runner_up_label else None

        if chosen_type == "assign" and runner_type == "assign":
            chosen_s = step.chosen_label.split("assign->M")[1]
            runner_s = step.runner_up_label.split("assign->M")[1]
            return (f"Servers {chosen_s} and {runner_s} were both free and scored identically for "
                    f"this task -- the scheduling policy does not distinguish between otherwise-idle "
                    f"servers -- so Server {chosen_s} was picked as the lower-indexed tied candidate.")

        if chosen_type == "assign" and runner_type == "defer":
            return ("The task's SLA tier made provisioning it now score higher than queueing it, "
                    "reflecting this policy's strong preference for immediate provisioning of "
                    "higher-tier tasks.")

        if chosen_type == "assign" and runner_type == "reject":
            return ("The task could still plausibly complete within a tolerable margin of its "
                    "deadline, so provisioning it scored higher than denying it outright.")

        if chosen_type == "defer" and runner_type == "assign":
            return ("The task's SLA tier and deadline were not yet pressing enough to outscore "
                    "queueing it for the next cycle.")

        if chosen_type == "defer" and runner_type == "reject":
            return "The task was not yet urgent, but also not clearly unrunnable in time, so queueing scored higher than denying it outright."

        if chosen_type == "reject":
            return ("Even provisioned immediately, the task would breach its deadline by more than "
                    "this policy tolerates, so it was denied.")

        return "This was the highest-scoring option the agent considered at this step."
