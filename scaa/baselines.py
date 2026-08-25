"""
Baseline decision-selection strategies.

These exist purely so Phase 3 can answer "is the severity gate actually
better than the obvious alternatives?" Each function takes a Trajectory
(already run through attribution.py and severity.py) and returns the subset
of steps that strategy would narrate. All four return `list[DecisionStep]`
so they can be fed directly into `narration.narrate_steps()`.

  - scaa_gate_selection        : the project's actual contribution
  - explain_everything_selection: the "no gate" baseline -- narrate every
                                   decision. Upper bound on completeness,
                                   upper bound on audit fatigue.
  - attribution_topk_selection : narrate only the k steps with the largest
                                   |influence_score| (ties to Who&When-style
                                   attribution-only methods). Tests whether
                                   "consequential to the outcome" and
                                   "worth a human's attention" are the same
                                   thing (SCAA's thesis is that they are not).
  - deviation_only_topk_selection: narrate only the k steps with the largest
                                   D (deviation) alone, proxying the
                                   anomaly/drift-detection literature
                                   (TrajAD, Trajectory Guard, SentinelAgent)
                                   AS A SELECTION STRATEGY, not as a
                                   reproduction of their labeled benchmarks.
  - random_k_selection         : narrate a random k steps. The sanity floor
                                   -- if SCAA and attribution-top-k don't
                                   both clearly beat this, something is wrong.

For a fair comparison, Phase 3 should call attribution_topk_selection and
random_k_selection with k = the number of steps SCAA's gate actually
flagged for that trajectory (`n_explanation_worthy` in the pipeline summary),
so all three strategies are compared at equal narration "budget."
"""

from __future__ import annotations

import random

from .trace import Trajectory


def scaa_gate_selection(trajectory: Trajectory) -> list:
    return [s for s in trajectory.steps if s.explanation_worthy]


def explain_everything_selection(trajectory: Trajectory) -> list:
    return list(trajectory.steps)


def attribution_topk_selection(trajectory: Trajectory, k: int) -> list:
    ranked = sorted(
        trajectory.steps,
        key=lambda s: abs(s.influence_score) if s.influence_score is not None else 0.0,
        reverse=True,
    )
    return ranked[:k]


def deviation_only_topk_selection(trajectory: Trajectory, k: int) -> list:
    """
    Proxy baseline for the anomaly/drift-detection literature (TrajAD,
    Trajectory Guard, SentinelAgent): select the k steps with the largest
    deviation (D) alone, ignoring irreversibility and impact entirely.
    This is NOT a reproduction of any of those papers' actual benchmarks
    (different data, no labeled anomalies here) -- it exists so the paper
    can compare SCAA against "the same STRATEGY that family of work uses"
    within our own evaluation, rather than invalidly importing their
    reported metrics, which are computed against a different ground truth
    (labeled anomalies vs. our consequence-based question).
    """
    ranked = sorted(
        trajectory.steps,
        key=lambda s: (s.severity_components or {}).get("D", 0.0),
        reverse=True,
    )
    return ranked[:k]


def oracle_proxy_topk_selection(trajectory: Trajectory, k: int) -> list:
    """
    An UPPER-BOUND proxy baseline, not a real oracle: selects exactly the k
    steps with the highest I * job_duration (the same internal proxy used
    by evaluation.py's `critical_decision_coverage` as its ground truth).
    By construction this baseline achieves ~100% coverage against that
    specific proxy metric -- it exists to show what "perfect performance on
    the proxy" looks like as a ceiling reference, NOT as evidence SCAA is
    close to a true oracle. The real oracle -- what a human auditor would
    actually pick -- can only come from the pilot human study
    (reports/EVALUATION_PLAN.md Section 3); this is clearly labeled
    "oracle_proxy" everywhere it is reported, never plain "oracle", to keep
    that distinction unambiguous in the paper.
    """
    ranked = sorted(
        trajectory.steps,
        key=lambda s: (s.severity_components or {}).get("I", 0.0) * s.job_duration,
        reverse=True,
    )
    return ranked[:k]


def random_k_selection(trajectory: Trajectory, k: int, seed: int = 0) -> list:
    rng = random.Random(seed)
    pool = list(trajectory.steps)
    rng.shuffle(pool)
    return pool[:k]


def selection_summary(trajectory: Trajectory) -> dict:
    """Convenience: run all strategies at a matched budget and report sizes."""
    gate = scaa_gate_selection(trajectory)
    k = len(gate)
    return {
        "scaa_gate": gate,
        "explain_everything": explain_everything_selection(trajectory),
        "attribution_topk": attribution_topk_selection(trajectory, k),
        "deviation_only_topk": deviation_only_topk_selection(trajectory, k),
        "oracle_proxy_topk": oracle_proxy_topk_selection(trajectory, k),
        "random_k": random_k_selection(trajectory, k),
        "k": k,
        "n_total": len(trajectory.steps),
    }
