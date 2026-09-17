"""
Delivery-dispatch narrator. Subclasses BaseTemplateNarrator (scaa/narration.py)
and overrides only the action vocabulary -- the two-sentence skeleton (agent
rationale, then conditional gate reasoning) and the non-gated honesty
behavior are inherited UNCHANGED from Domain 1's narration logic.
"""

from __future__ import annotations

from ...narration import BaseTemplateNarrator
from ...trace import DecisionStep


class DeliveryNarrator(BaseTemplateNarrator):
    def _describe_action(self, label: str) -> str:
        if label.startswith("assign->M"):
            v = label.split("assign->M")[1]
            return f"dispatching Vehicle {v}"
        if label == "defer":
            return "holding the order for the next cycle"
        if label == "reject":
            return "cancelling the order"
        return label

    def _action_type(self, label: str) -> str:
        return "assign" if label.startswith("assign->M") else label

    def _agent_rationale(self, step: DecisionStep) -> str:
        chosen_type = self._action_type(step.chosen_label)
        runner_type = self._action_type(step.runner_up_label) if step.runner_up_label else None

        if chosen_type == "assign" and runner_type == "assign":
            chosen_v = step.chosen_label.split("assign->M")[1]
            runner_v = step.runner_up_label.split("assign->M")[1]
            return (f"Vehicles {chosen_v} and {runner_v} were both free and scored identically for "
                    f"this order -- the dispatch policy does not distinguish between otherwise-idle "
                    f"vehicles -- so Vehicle {chosen_v} was picked as the lower-indexed tied candidate.")

        if chosen_type == "assign" and runner_type == "defer":
            return ("The order's service tier and closing delivery window made dispatching now score "
                    "higher than holding it for the next cycle.")

        if chosen_type == "assign" and runner_type == "reject":
            return ("The order could still be delivered within an acceptable margin of its window, "
                    "so dispatching it scored higher than cancelling it.")

        if chosen_type == "defer" and runner_type == "assign":
            return ("The order's delivery window was not yet close enough to justify committing a "
                    "vehicle now, so the agent preferred to hold and re-evaluate next cycle.")

        if chosen_type == "defer" and runner_type == "reject":
            return "The order was not yet urgent, but also not clearly undeliverable, so holding scored higher than cancelling it outright."

        if chosen_type == "reject":
            return ("Even dispatched immediately, the order would arrive too far past its delivery "
                    "window to honor, so the agent cancelled it.")

        return "This was the highest-scoring option the agent considered at this step."
