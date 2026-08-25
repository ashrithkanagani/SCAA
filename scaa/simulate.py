"""
Core run loop: drives the environment + agent together to produce a Trajectory.

This function is the single source of truth for "what happens when the agent
runs." It is used twice:
  1. Once, unmodified, to produce the real trajectory (pipeline.py).
  2. Many times, with a single decision forcibly overridden, to produce
     counterfactual trajectories for drop/hold-out attribution (attribution.py).

Keeping this in one place guarantees the counterfactual replays are faithful
to the real run except at the single overridden step, which is exactly the
hold-out assumption the attribution method depends on.
"""

from __future__ import annotations

from typing import Optional

from .agent import ScoringAgent
from .config import EnvironmentConfig
from .environment import SchedulingEnvironment
from .trace import DecisionStep, Trajectory


def run_trajectory(
    env_config: EnvironmentConfig,
    agent: ScoringAgent,
    job_schedule: Optional[list] = None,
    override_step_id: Optional[int] = None,
    override_action: Optional[dict] = None,
) -> Trajectory:
    """
    Run the agent in a fresh environment until completion.

    If override_step_id is given, the decision at that step index (0-indexed,
    counting only ticks where a decision was actually made) is replaced with
    override_action instead of the agent's own chosen action. All other steps
    proceed exactly as the agent would normally choose -- this is the
    drop/hold-out counterfactual used by attribution.py.
    """
    env = SchedulingEnvironment(env_config, job_schedule=job_schedule)
    trajectory = Trajectory()
    step_id = 0

    while not env.done():
        decision = agent.decide(env)
        if decision is not None:
            if override_step_id is not None and step_id == override_step_id and override_action is not None:
                chosen_action = override_action
                chosen_label = "OVERRIDE:" + override_action["type"]
                chosen_score = float("nan")
            else:
                chosen_action = decision.chosen.action
                chosen_label = decision.chosen.label
                chosen_score = decision.chosen.score

            state = env.observe()
            job = env.jobs[decision.job_id]

            step = DecisionStep(
                step_id=step_id,
                tick=state.tick,
                job_id=decision.job_id,
                job_priority=job.priority,
                job_deadline=job.deadline,
                job_duration=job.duration,
                n_pending_jobs=len(state.pending_job_ids),
                n_free_machines=sum(state.machine_free_mask),
                candidate_labels=[c.label for c in decision.candidates],
                candidate_scores=[c.score for c in decision.candidates],
                chosen_label=chosen_label,
                chosen_score=chosen_score,
                chosen_action=chosen_action,
                runner_up_label=decision.runner_up.label if decision.runner_up else None,
                runner_up_score=decision.runner_up.score if decision.runner_up else None,
                runner_up_action=decision.runner_up.action if decision.runner_up else None,
                is_commit=chosen_action["type"] in ("assign", "reassign"),
            )
            trajectory.add(step)
            env.apply_action(chosen_action)
            step_id += 1

        env.advance_tick()

    trajectory.final_outcome = env.outcome_metrics()
    return trajectory
