"""
Attribution engine: adapted drop/hold-out counterfactual influence scoring.

Method (documented explicitly for the paper's Related Work / Methods section):

    For each decision step i in the real trajectory, we replay the simulation
    from scratch with EVERY step identical to the original EXCEPT step i,
    where we force the agent's runner-up candidate action instead of its
    actual choice. From step i+1 onward the agent resumes normal decision-
    making against the now-different environment state (this is a policy
    intervention, not a static hold-out of a single prediction -- sequential
    decisions require this because the environment state itself branches).

    influence(i) = sign(metric) * (counterfactual_outcome - original_outcome)

    where sign(metric) flips depending on whether the outcome metric is
    "lower is better" (e.g. SLA penalty) or "higher is better" (e.g.
    completed jobs), so that influence > 0 always means "the agent's actual
    choice at step i was better than the alternative it passed over."

This is the same family of technique as Zhang et al.'s Who&When benchmark
(ICML 2025) and the drop/hold-out sentence attribution used in "The Why
Behind the Action" (agentic attribution via context ablation) -- we adapt it
to a resource-scheduling MDP rather than a single-turn LLM context window.
It is NOT itself the novel contribution of this project; it is the
attribution primitive that severity.py's gate consumes and re-purposes.
"""

from __future__ import annotations

import numpy as np

from .agent import ScoringAgent
from .config import AttributionConfig, EnvironmentConfig
from .simulate import run_trajectory
from .trace import Trajectory

_METRIC_DIRECTION = {
    "sla_penalty": "lower_better",
    "completed_jobs": "higher_better",
    "late_jobs": "lower_better",
    "rejected_jobs": "lower_better",
}


def parse_action_from_label(label: str, job_id: int) -> dict:
    """Reconstruct an action dict from a candidate's human-readable label."""
    if label.startswith("assign->M"):
        machine_id = int(label.split("assign->M")[1])
        return {"type": "assign", "job_id": job_id, "machine_id": machine_id}
    if label == "defer":
        return {"type": "defer", "job_id": job_id}
    if label == "reject":
        return {"type": "reject", "job_id": job_id}
    raise ValueError(f"cannot parse candidate label: {label}")


def compute_attribution(
    trajectory: Trajectory,
    agent: ScoringAgent,
    env_config: EnvironmentConfig,
    job_schedule: list,
    attribution_config: AttributionConfig,
) -> Trajectory:
    """
    Mutates `trajectory` in place, filling in `influence_score` for every step.
    Returns the same trajectory for convenience/chaining.
    """
    metric = attribution_config.outcome_metric
    direction = _METRIC_DIRECTION[metric]
    original_metric = trajectory.final_outcome[metric]

    for step in trajectory.steps:
        alt_labels = [l for l in step.candidate_labels if l != step.chosen_label]
        alt_labels = alt_labels[: attribution_config.n_counterfactuals]

        deltas = []
        for label in alt_labels:
            try:
                alt_action = parse_action_from_label(label, step.job_id)
            except ValueError:
                continue

            cf_trajectory = run_trajectory(
                env_config,
                agent,
                job_schedule=job_schedule,
                override_step_id=step.step_id,
                override_action=alt_action,
            )
            cf_metric = cf_trajectory.final_outcome[metric]

            if direction == "lower_better":
                delta = cf_metric - original_metric
            else:
                delta = original_metric - cf_metric
            deltas.append(delta)

        step.influence_score = float(np.mean(deltas)) if deltas else 0.0

    return trajectory
