"""
THE CORE NOVEL MODULE.

This is the "severity gate": the mechanism that decides which decisions in
an agent's trajectory deserve a full causal explanation, based on
consequence-based criteria rather than on attribution magnitude or error
signals alone. This is what distinguishes SCAA from prior work:

  - Failure-attribution methods (e.g. Who&When, ICML 2025) ask "which step
    caused the bad outcome?" -- they require an outcome to already be bad.
  - Anomaly/drift detectors (e.g. TrajAD, Trajectory Guard) ask "is this
    trajectory unusual?" -- they flag statistical outliers, not consequence.
  - SCAA asks a third, different question: "regardless of whether this
    decision turns out well or badly, was it consequential enough, right
    now, that a human auditor should be shown a plain-language explanation
    of it?" That is a stakes-based question, not an error-based one.

Formulation (hybrid, as specified in the project design):

    S = w_irrev * I  +  w_impact * F  +  w_deviation * D

    I (Irreversibility)  - rule-based, derived directly from the action type
                            taken (assign/reassign/reject/defer). Transparent
                            and auditable by design -- a CPS reviewer can
                            read the rule table directly.

    F (Impact / Safety)  - rule-based, derived from task-defined severity
                            inputs (job priority, deadline urgency). This is
                            the "business/safety cost function" a deploying
                            organization would define for its own domain;
                            here it is instantiated for scheduling.

    D (Deviation)         - statistically computed, NOT rule-based. It is
                            the z-scored confidence gap between the agent's
                            chosen action and its runner-up, calibrated
                            against a reference distribution of gaps
                            collected from multiple independent simulation
                            runs (see `calibrate`). A decision with an
                            unusually small gap (a "close call" relative to
                            the agent's typical behavior) scores high on D.
                            This is the learned/statistical component that
                            gives the gate its algorithmic (not purely
                            heuristic) character, in the same spirit as
                            drift-detection signals (TrajAD, Trajectory
                            Guard) -- but consumed here as one gate INPUT
                            rather than as a standalone anomaly output.

I and F are individually bounded to [0, 1] by construction. D is mapped to
[0, 1] via a sigmoid of its z-score. S is therefore always in [0, 1] given
normalized weights, and `gate_threshold` is directly interpretable as a
percentage of maximum possible severity.

----------------------------------------------------------------------
Mathematical justification (why this specific form, for the paper)
----------------------------------------------------------------------

1. WHY A LINEAR WEIGHTED SUM, NOT SOMETHING MORE EXOTIC.

   S = w1*I + w2*F + w3*D is an instance of the Weighted Sum Model (WSM),
   also called Simple Additive Weighting -- the most established
   aggregation method in multi-criteria decision analysis (Fishburn, 1967;
   Triantaphyllou, 2000). WSM is the right tool here, not a compromise,
   for three reasons specific to this application:
     - Auditability: a linear model's contribution of each criterion is
       readable directly off the weight (a CPS safety reviewer can verify
       "irreversibility counts for 40% of the decision to explain" without
       needing to interpret a nonlinear surrogate).
     - Monotonicity: WSM guarantees that increasing any one criterion
       (holding others fixed) never decreases S. This is a hard requirement
       for a severity gate -- a nonlinear or interaction-heavy aggregator
       could not guarantee that a strictly-more-irreversible decision is
       never scored as strictly-less-severe, which would be difficult to
       justify to a safety auditor.
     - WSM's known weakness -- compensability, i.e. a very low criterion
       can be offset by a very high one -- is explicitly ACCEPTABLE here:
       it is reasonable that an extremely high-impact decision (F near 1)
       should be explained even if it is trivially reversible (I near 0),
       and vice versa. The gate is intentionally compensatory.

2. WHY A SIGMOID FOR D, SPECIFICALLY.

   D is defined on a z-score z = (gap - mean_gap) / std_gap, which is
   unbounded in principle. The logistic sigmoid is the standard, smooth,
   monotonic map from an unbounded real-valued statistic onto [0, 1] that
   preserves rank order (a strictly smaller gap always yields a strictly
   larger D) while compressing extreme outliers instead of letting them
   dominate the weighted sum -- the same justification used for calibrated
   probability outputs from unbounded scores in logistic regression.

3. WHY TWO THRESHOLD MODES ARE PROVIDED (`gate_mode` below), NOT JUST ONE.

   A fixed absolute threshold (`gate_mode="absolute"`) is simple and
   auditable but is not scenario-invariant: Phase 1's cross-seed check
   showed gate rate swinging from 33% to 68% at a *fixed* threshold of
   0.62 purely because of scenario difficulty (job load, machine scarcity)
   changing the S distribution's shape, not because the underlying
   decisions became more or less consequential in a way that should be
   compared 1:1 across scenarios.

   `gate_mode="percentile"` instead flags the top-p% of S scores WITHIN
   each trajectory (an order-statistic threshold: the k-th order statistic
   of S, k = ceil(p * n)). This is the standard technique used for
   scenario-adaptive cutoffs in outlier/anomaly detection when the
   underlying score distribution's scale is not comparable across runs,
   and it lets Phase 3's evaluation hold "selectivity" (e.g. always the
   top 30% most severe decisions) constant while comparing across
   scenarios of very different difficulty -- which the fixed-threshold
   mode cannot do.

   Both modes are kept (not just percentile) because CPS deployments
   typically want an absolute, pre-committed threshold for regulatory
   auditability ("any decision scoring above 0.62 by policy must be
   explained") rather than a moving relative bar -- this tension itself
   is worth a sentence in the paper's limitations section.

4. THRESHOLD / WEIGHT SENSITIVITY.

   Following the MCDA literature on weight stability intervals
   (Triantaphyllou & Sanchez, 1997; O'Shea et al., 2025) -- the range of
   weight values for which a ranking/decision does not change -- Phase 3's
   ablation sweeps w_irrev/w_impact/w_deviation and gate_threshold and
   reports the stability interval within which the SET of flagged
   decisions is invariant, rather than reporting a single point estimate.
   This is the paper's answer to "why these weights:" not "we picked them,"
   but "here is the interval over which the conclusion is robust."
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from .agent import ScoringAgent
from .config import EnvironmentConfig, SeverityWeights
from .simulate import run_trajectory
from .trace import Trajectory

# ----------------------------------------------------------------------
# I: Irreversibility (rule-based, transparent)
# ----------------------------------------------------------------------

_IRREVERSIBILITY_BASE = {
    "assign": 0.55,    # commits a machine's physical time; scaled further by how long it holds it
    "reassign": 0.7,   # actively undoing a prior commitment; also scaled by new commitment length
    "reject": 0.6,     # the job opportunity is permanently lost, though no machine time is spent
    "defer": 0.1,      # trivially revisited next tick; nothing physically committed
}


def compute_irreversibility(action_type: str, duration: int = None, max_duration: int = 6) -> float:
    """
    Irreversibility is not just a function of *category* of action -- committing
    a machine for 6 ticks is harder to walk back than committing it for 2.
    For assign/reassign we scale the base rate by how much of the machine's
    time is being locked in, so I actually varies across decisions instead
    of collapsing to a near-constant whenever the agent chooses to commit.
    """
    base = _IRREVERSIBILITY_BASE.get(action_type, 0.5)
    if action_type in ("assign", "reassign") and duration is not None:
        duration_scale = min(1.0, duration / max_duration)
        return float(min(1.0, base + 0.45 * duration_scale))
    return base


# ----------------------------------------------------------------------
# F: Impact / Safety (rule-based, task-defined cost function)
# ----------------------------------------------------------------------

def compute_impact(job_priority: int, job_deadline: int, tick: int,
                    max_priority: int = 3,
                    priority_weight: float = 0.6,
                    urgency_weight: float = 0.4) -> float:
    priority_term = job_priority / max_priority
    urgency_term = 1.0 / (1.0 + max(0, job_deadline - tick))
    raw = priority_weight * priority_term + urgency_weight * urgency_term
    return float(min(1.0, max(0.0, raw)))


# ----------------------------------------------------------------------
# D: Deviation (statistical, calibrated against reference behavior)
# ----------------------------------------------------------------------

@dataclass
class DeviationCalibration:
    mean_gap: float
    std_gap: float
    n_samples: int


def calibrate_deviation(env_config: EnvironmentConfig, agent: ScoringAgent,
                         n_seeds: int = 15) -> DeviationCalibration:
    """
    Build a reference distribution of (chosen_score - runner_up_score) gaps
    by running the agent across several independent seeds. This is the
    agent's "typical confidence gap" -- decisions far below this typical
    gap (i.e. unusually close calls) are the ones D should flag.
    """
    gaps = []
    for seed in range(n_seeds):
        cfg = replace(env_config, seed=seed)
        traj = run_trajectory(cfg, agent)
        for step in traj.steps:
            if step.runner_up_score is not None and not math.isnan(step.chosen_score):
                gaps.append(step.chosen_score - step.runner_up_score)
    gaps_arr = np.array(gaps) if gaps else np.array([1.0])
    return DeviationCalibration(
        mean_gap=float(gaps_arr.mean()),
        std_gap=float(gaps_arr.std() + 1e-6),
        n_samples=len(gaps_arr),
    )


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def compute_deviation(chosen_score: float, runner_up_score, calibration: DeviationCalibration) -> float:
    if runner_up_score is None or math.isnan(chosen_score):
        return 0.0  # no alternative existed; nothing to deviate from
    gap = chosen_score - runner_up_score
    z = (gap - calibration.mean_gap) / calibration.std_gap
    # Large positive z (unusually confident) -> D near 0.
    # Large negative z (unusually close call) -> D near 1.
    return float(1.0 - _sigmoid(z))


# ----------------------------------------------------------------------
# S: The combined severity gate
# ----------------------------------------------------------------------

def apply_severity_gate(
    trajectory: Trajectory,
    weights: SeverityWeights,
    calibration: DeviationCalibration,
) -> Trajectory:
    """
    Mutates `trajectory` in place: fills severity_components, severity_score,
    and explanation_worthy for every step. Returns the same trajectory.

    Two gate modes (see the module docstring, section 3, for the rationale):
      - "absolute":   explanation_worthy = (S >= gate_threshold)
      - "percentile": explanation_worthy = S is among the top
                       `gate_percentile` fraction of this trajectory's scores
                       (order-statistic threshold, scenario-adaptive).
    """
    w = weights.normalized()

    for step in trajectory.steps:
        action_type = step.chosen_action["type"]
        I = compute_irreversibility(action_type, duration=step.job_duration)
        F = compute_impact(step.job_priority, step.job_deadline, step.tick)
        D = compute_deviation(step.chosen_score, step.runner_up_score, calibration)

        S = w.w_irrev * I + w.w_impact * F + w.w_deviation * D

        step.severity_components = {"I": I, "F": F, "D": D}
        step.severity_score = float(S)

    if w.gate_mode == "percentile":
        scores = sorted((s.severity_score for s in trajectory.steps), reverse=True)
        n_flag = max(1, math.ceil(w.gate_percentile * len(scores)))
        # order-statistic cutoff: the n_flag-th highest score, ties included
        cutoff = scores[n_flag - 1]
        for step in trajectory.steps:
            step.explanation_worthy = bool(step.severity_score >= cutoff)
    else:  # "absolute"
        for step in trajectory.steps:
            step.explanation_worthy = bool(step.severity_score >= w.gate_threshold)

    return trajectory
