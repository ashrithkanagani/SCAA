"""
Domain-agnostic simulation and attribution infrastructure, shared by every
Phase 4 domain (delivery, cloud, taillard).

Any environment implementing this minimal duck-typed interface can be
driven by `run_trajectory_generic`:
    env.observe()          -> object with .tick, .pending_job_ids, .machine_free_mask
    env.done()              -> bool
    env.jobs                 -> dict[int, object] with .priority, .deadline, .duration
    env.apply_action(action) -> None   (action: dict with "type" key)
    env.advance_tick()       -> None
    env.outcome_metrics()    -> dict

Any agent implementing `agent.decide(env) -> Decision | None` (the same
`Decision`/`Candidate` dataclasses from scaa.agent, used unmodified).

This is the literal code-level proof of the "the pipeline is agent- and
domain-agnostic by construction" claim made throughout this project: this
one function produces a Trajectory for the delivery-dispatch domain, the
cloud-scheduling domain, AND the Taillard/JSSP domain, and Domain 1's own
`simulate.py` implements the identical loop (kept separate there rather
than refactored to call this, to avoid any risk of regressing Phase 1-3's
already-validated 48 tests -- a deliberate, documented duplication, not an
oversight).
"""

from __future__ import annotations

from typing import Callable, Optional

from ..severity import DeviationCalibration
from ..trace import DecisionStep, Trajectory


def run_trajectory_generic(env, agent, override_step_id: Optional[int] = None,
                            override_action: Optional[dict] = None) -> Trajectory:
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
                step_id=step_id, tick=state.tick, job_id=decision.job_id,
                job_priority=job.priority, job_deadline=job.deadline, job_duration=job.duration,
                n_pending_jobs=len(state.pending_job_ids),
                n_free_machines=sum(state.machine_free_mask),
                candidate_labels=[c.label for c in decision.candidates],
                candidate_scores=[c.score for c in decision.candidates],
                chosen_label=chosen_label, chosen_score=chosen_score, chosen_action=chosen_action,
                runner_up_label=decision.runner_up.label if decision.runner_up else None,
                runner_up_score=decision.runner_up.score if decision.runner_up else None,
                runner_up_action=decision.runner_up.action if decision.runner_up else None,
                is_commit=chosen_action["type"] in ("assign", "reassign", "dispatch", "provision", "migrate"),
            )
            trajectory.add(step)
            env.apply_action(chosen_action)
            step_id += 1

        env.advance_tick()

    trajectory.final_outcome = env.outcome_metrics()
    return trajectory


def compute_attribution_generic(trajectory: Trajectory, agent, env_factory: Callable[[], object],
                                 parse_label_fn: Callable[[str, "DecisionStep"], dict],
                                 outcome_metric: str, metric_direction: str,
                                 n_counterfactuals: int = 1) -> Trajectory:
    """
    Domain-generic drop/hold-out counterfactual attribution -- identical
    algorithm to scaa/attribution.py's compute_attribution, generalized to
    accept an env_factory (so it can rebuild any domain's environment) and
    a domain-specific label parser. `parse_label_fn(label, step)` receives
    the FULL originating DecisionStep (not just its job_id), since some
    domains (Taillard/JSSP) need context beyond the label itself to
    reconstruct a valid action dict -- e.g. the machine a decision point
    was about, which JSSP labels don't encode (the machine is fixed by the
    decision point, not chosen, so it isn't part of the candidate label).
    """
    import numpy as np

    original_metric = trajectory.final_outcome[outcome_metric]

    for step in trajectory.steps:
        alt_labels = [l for l in step.candidate_labels if l != step.chosen_label]
        alt_labels = alt_labels[:n_counterfactuals]

        deltas = []
        for label in alt_labels:
            try:
                alt_action = parse_label_fn(label, step)
            except ValueError:
                continue

            cf_env = env_factory()
            cf_trajectory = run_trajectory_generic(
                cf_env, agent, override_step_id=step.step_id, override_action=alt_action,
            )
            cf_metric = cf_trajectory.final_outcome[outcome_metric]

            if metric_direction == "lower_better":
                delta = cf_metric - original_metric
            else:
                delta = original_metric - cf_metric
            deltas.append(delta)

        step.influence_score = float(np.mean(deltas)) if deltas else 0.0

    return trajectory


def calibrate_deviation_generic(env_factory: Callable[[], object], agent, n_seeds: int = 15) -> DeviationCalibration:
    """
    Domain-generic version of severity.calibrate_deviation: builds the same
    reference distribution of (chosen_score - runner_up_score) gaps by
    running the agent across several independent environment instances,
    generalized via env_factory instead of a hardcoded EnvironmentConfig.
    The statistic computed and the DeviationCalibration dataclass produced
    are IDENTICAL to Domain 1's -- only how the environment is constructed
    differs.
    """
    import math
    import numpy as np

    gaps = []
    for _ in range(n_seeds):
        env = env_factory()
        traj = run_trajectory_generic(env, agent)
        for step in traj.steps:
            if step.runner_up_score is not None and not math.isnan(step.chosen_score):
                gaps.append(step.chosen_score - step.runner_up_score)
    gaps_arr = np.array(gaps) if gaps else np.array([1.0])
    return DeviationCalibration(
        mean_gap=float(gaps_arr.mean()),
        std_gap=float(gaps_arr.std() + 1e-6),
        n_samples=len(gaps_arr),
    )


def compute_realized_outcome_contribution_generic(
    env, late_penalty_rate_attr: str, reassign_penalty_attr: str = None,
    reassign_count_attr: str = None,
) -> dict:
    """
    Domain-generic Realized Outcome Contribution (ROC): the same statistic
    as evaluation.py's compute_realized_outcome_contribution(), generalized
    via explicit attribute-name parameters since each domain's Job-like
    object uses different field names for the same underlying concept
    (e.g. delivery's Order.n_reroutes vs. scheduling's Job.n_reassignments;
    cloud's ComputeTask.n_migrations; JSSP has no reassignment concept at
    all, hence reassign_count_attr is optional).

    For each job: contribution = realized_lateness * late_penalty_rate,
    plus (reassignment_count * reassign_penalty_rate) if the domain has a
    reassignment-like action. Computed entirely from realized outcomes
    (job.finish_tick vs job.deadline, actual reassignment count), never
    from I, F, or D.
    """
    roc = {}
    rate_source = getattr(env, "config", env)  # JSSPEnvironment has no .config; rates live on env directly
    late_rate = getattr(rate_source, late_penalty_rate_attr)
    reassign_rate = getattr(rate_source, reassign_penalty_attr, 0.0) if reassign_penalty_attr else 0.0
    for job_id, job in env.jobs.items():
        contribution = 0.0
        finish = getattr(job, "finish_tick", None)
        deadline = getattr(job, "deadline", None)
        if finish is not None and deadline is not None and finish > deadline:
            contribution += (finish - deadline) * late_rate
        if reassign_count_attr is not None:
            contribution += getattr(job, reassign_count_attr, 0) * reassign_rate
        roc[job_id] = contribution
    return roc
