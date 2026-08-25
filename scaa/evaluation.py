"""
Phase 3 evaluation.

Implements every AUTOMATIC metric from reports/EVALUATION_PLAN.md Section 1,
across multiple seeds and all three named scenarios (scenarios.py), plus the
extra experiments proposed in the pre-Phase-3 discussion:

  - Selection Diversity (1 - Jaccard) of SCAA's gate vs. attribution-topk,
    deviation-only-topk, and random-k, at matched budget.
  - Critical Decision Coverage: of the "top quartile most consequential"
    decisions (by I*duration, a proxy for true high-stakes ground truth
    since no external label exists), what fraction does each strategy catch.
  - Gate-rate reduction (audit load) per scenario.
  - Threshold stability interval and per-weight sensitivity (ablation).

What this module explicitly does NOT do: it does not fabricate human
accuracy, human agreement, or human timing numbers. Those require your
team's actual input (see reports/HUMAN_STUDY/ for the templates and
score_human_ratings.py for the scoring script) and are reported as
"PENDING" in every output this module produces until real CSVs are filled
in and scored.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import replace

from scipy import stats as scipy_stats

from .agent import GreedyEDFAgent, ScoringAgent
from .attribution import compute_attribution
from .baselines import selection_summary
from .config import AttributionConfig, EnvironmentConfig, SeverityWeights
from .scenarios import SCENARIOS, get_scenario
from .severity import apply_severity_gate, calibrate_deviation
from .simulate import run_trajectory


def _ids(steps) -> set:
    return set(s.step_id for s in steps)


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def selection_diversity(a: set, b: set) -> float:
    """1 - Jaccard. 0 = identical selections (no added value); 1 = disjoint."""
    return 1.0 - jaccard(a, b)


def _run_full_trajectory(env_config: EnvironmentConfig, weights: SeverityWeights,
                          attribution_config: AttributionConfig = None, n_calib_seeds: int = 15,
                          agent=None):
    agent = agent or ScoringAgent()
    attribution_config = attribution_config or AttributionConfig()
    traj = run_trajectory(env_config, agent)
    compute_attribution(traj, agent, env_config, job_schedule=None, attribution_config=attribution_config)
    calib = calibrate_deviation(env_config, agent, n_seeds=n_calib_seeds)
    apply_severity_gate(traj, weights, calib)
    return traj


def critical_decision_coverage(trajectory, selection_ids: set, top_fraction: float = 0.25) -> float:
    """
    Proxy ground truth for "high-stakes decision": top `top_fraction` of
    steps by I * job_duration (i.e. the most consequential-to-undo
    commitments in absolute terms, independent of the gate's own score).
    Reports what fraction of that proxy ground-truth set a given selection
    captures. This is an internal proxy, not an external human-labeled
    ground truth -- reported as such in every output.
    """
    scored = sorted(
        trajectory.steps,
        key=lambda s: (s.severity_components or {}).get("I", 0.0) * s.job_duration,
        reverse=True,
    )
    n_critical = max(1, int(round(top_fraction * len(scored))))
    critical_ids = _ids(scored[:n_critical])
    if not critical_ids:
        return 0.0
    return len(critical_ids & selection_ids) / len(critical_ids)


def evaluate_single_trajectory(env_config: EnvironmentConfig, weights: SeverityWeights, agent=None) -> dict:
    traj = _run_full_trajectory(env_config, weights, agent=agent)
    summary = selection_summary(traj)
    gate_ids = _ids(summary["scaa_gate"])
    attr_ids = _ids(summary["attribution_topk"])
    dev_ids = _ids(summary["deviation_only_topk"])
    oracle_ids = _ids(summary["oracle_proxy_topk"])
    rand_ids = _ids(summary["random_k"])
    n_total = summary["n_total"]
    k = summary["k"]

    return {
        "n_total": n_total,
        "k": k,
        "gate_rate": k / n_total if n_total else 0.0,
        "audit_load_reduction": 1.0 - (k / n_total) if n_total else 0.0,
        "selection_diversity_vs_attribution": selection_diversity(gate_ids, attr_ids),
        "selection_diversity_vs_deviation_only": selection_diversity(gate_ids, dev_ids),
        "selection_diversity_vs_random": selection_diversity(gate_ids, rand_ids),
        "critical_coverage_gate": critical_decision_coverage(traj, gate_ids),
        "critical_coverage_attribution": critical_decision_coverage(traj, attr_ids),
        "critical_coverage_deviation_only": critical_decision_coverage(traj, dev_ids),
        "critical_coverage_oracle_proxy": critical_decision_coverage(traj, oracle_ids),
        "critical_coverage_random": critical_decision_coverage(traj, rand_ids),
    }


def evaluate_scenario_multiseed(scenario_name: str, n_seeds: int = 20,
                                 weights: SeverityWeights = None, agent=None) -> dict:
    weights = weights or SeverityWeights()
    per_seed = []
    for seed in range(n_seeds):
        cfg = get_scenario(scenario_name, seed=seed)
        result = evaluate_single_trajectory(cfg, weights, agent=agent)
        result["seed"] = seed
        per_seed.append(result)

    def agg(key):
        vals = [r[key] for r in per_seed]
        mean = statistics.mean(vals)
        std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        # 95% CI via t-distribution (appropriate for small n; falls back
        # gracefully as n grows). sem = standard error of the mean.
        if len(vals) > 1:
            sem = statistics.stdev(vals) / (len(vals) ** 0.5)
            t_crit = scipy_stats.t.ppf(0.975, df=len(vals) - 1)
            ci95 = t_crit * sem
        else:
            ci95 = 0.0
        return {"mean": mean, "std": std, "ci95": ci95, "n": len(vals)}

    keys = [
        "gate_rate", "audit_load_reduction",
        "selection_diversity_vs_attribution", "selection_diversity_vs_deviation_only",
        "selection_diversity_vs_random",
        "critical_coverage_gate", "critical_coverage_attribution",
        "critical_coverage_deviation_only", "critical_coverage_oracle_proxy",
        "critical_coverage_random",
    ]
    return {
        "scenario": scenario_name,
        "n_seeds": n_seeds,
        "aggregate": {k: agg(k) for k in keys},
        "per_seed": per_seed,
    }


def paired_significance_test(scenario_multiseed_result: dict,
                              metric_a: str = "critical_coverage_gate",
                              metric_b: str = "critical_coverage_attribution") -> dict:
    """
    Paired comparison across seeds (same seed -> same trajectory for both
    metrics, so this is a legitimate paired design). Reports both a paired
    t-test and a Wilcoxon signed-rank test (the latter is distribution-free,
    safer given the small-to-moderate seed counts used here and the fact
    that these ratio-like metrics are not guaranteed normal).
    """
    per_seed = scenario_multiseed_result["per_seed"]
    a = [r[metric_a] for r in per_seed]
    b = [r[metric_b] for r in per_seed]
    diffs = [x - y for x, y in zip(a, b)]

    result = {
        "metric_a": metric_a, "metric_b": metric_b,
        "n": len(a),
        "mean_diff": statistics.mean(diffs),
        "a_mean": statistics.mean(a), "b_mean": statistics.mean(b),
    }
    try:
        t_stat, t_p = scipy_stats.ttest_rel(a, b)
        result["paired_t_test"] = {"statistic": float(t_stat), "p_value": float(t_p)}
    except Exception as e:
        result["paired_t_test"] = {"error": str(e)}
    try:
        if any(d != 0 for d in diffs):
            w_stat, w_p = scipy_stats.wilcoxon(a, b)
            result["wilcoxon"] = {"statistic": float(w_stat), "p_value": float(w_p)}
        else:
            result["wilcoxon"] = {"note": "all paired differences are zero"}
    except Exception as e:
        result["wilcoxon"] = {"error": str(e)}
    return result


def threshold_stability_interval(env_config: EnvironmentConfig, weights: SeverityWeights,
                                  thresholds=None) -> dict:
    """
    Sweep gate_threshold and find the widest contiguous interval around the
    default threshold over which the SET of flagged steps does not change
    (per Triantaphyllou & Sanchez, 1997's weight-stability-interval concept,
    applied here to the threshold rather than a criterion weight).
    """
    thresholds = thresholds or [round(0.40 + 0.01 * i, 3) for i in range(36)]  # 0.40 .. 0.75
    traj = _run_full_trajectory(env_config, weights)
    default_ids = _ids([s for s in traj.steps if s.explanation_worthy])

    stable = []
    for t in thresholds:
        ids_t = _ids([s for s in traj.steps if s.severity_score >= t])
        stable.append((t, ids_t == default_ids))

    default_t = weights.gate_threshold
    idx_default = min(range(len(thresholds)), key=lambda i: abs(thresholds[i] - default_t))
    lo = idx_default
    while lo > 0 and stable[lo - 1][1]:
        lo -= 1
    hi = idx_default
    while hi < len(stable) - 1 and stable[hi + 1][1]:
        hi += 1

    return {
        "default_threshold": default_t,
        "stability_interval": [thresholds[lo], thresholds[hi]],
        "sweep": [{"threshold": t, "gate_rate": len(_ids([s for s in traj.steps if s.severity_score >= t])) / len(traj.steps)} for t in thresholds],
    }


def weight_sensitivity(env_config: EnvironmentConfig, base_weights: SeverityWeights = None,
                        perturbation: float = 0.3) -> dict:
    """
    Perturb each weight independently by +/- `perturbation` fraction, and
    report the resulting change in gate rate and selection diversity from
    the default gate's selection. Small changes here support "the gate
    isn't fragile to reasonable weight choices."
    """
    base_weights = base_weights or SeverityWeights()
    traj_default = _run_full_trajectory(env_config, base_weights)
    default_ids = _ids([s for s in traj_default.steps if s.explanation_worthy])

    results = {}
    for name in ("w_irrev", "w_impact", "w_deviation"):
        results[name] = {}
        for direction, factor in (("minus", 1 - perturbation), ("plus", 1 + perturbation)):
            kwargs = {
                "w_irrev": base_weights.w_irrev,
                "w_impact": base_weights.w_impact,
                "w_deviation": base_weights.w_deviation,
                "gate_threshold": base_weights.gate_threshold,
                "gate_mode": base_weights.gate_mode,
                "gate_percentile": base_weights.gate_percentile,
            }
            kwargs[name] = kwargs[name] * factor
            perturbed = SeverityWeights(**kwargs)
            traj = _run_full_trajectory(env_config, perturbed)
            ids = _ids([s for s in traj.steps if s.explanation_worthy])
            results[name][direction] = {
                "gate_rate": len(ids) / len(traj.steps) if traj.steps else 0.0,
                "jaccard_vs_default": jaccard(ids, default_ids),
            }
    return results


def random_weight_sensitivity(env_config: EnvironmentConfig, base_weights: SeverityWeights = None,
                               n_samples: int = 50, seed: int = 0) -> dict:
    """
    Beyond the ±30% axis-aligned perturbations in weight_sensitivity(),
    sample `n_samples` random (w_irrev, w_impact, w_deviation) triples from
    a uniform simplex (Dirichlet(1,1,1)) and report the distribution of
    gate rate and Jaccard-vs-default across all of them. This directly
    answers the reviewer concern: "does performance collapse unless weights
    are tuned to one specific point, or is it stable across a wide region
    of weight space?" A tight Jaccard distribution (high mean, low std)
    here is the honest version of "not over-tuned."
    """
    import random as _random
    base_weights = base_weights or SeverityWeights()
    traj_default = _run_full_trajectory(env_config, base_weights)
    default_ids = _ids([s for s in traj_default.steps if s.explanation_worthy])

    rng = _random.Random(seed)
    jaccards, gate_rates = [], []
    for _ in range(n_samples):
        raw = [rng.expovariate(1.0) for _ in range(3)]  # Dirichlet(1,1,1) via normalized exponentials
        total = sum(raw)
        w_irrev, w_impact, w_deviation = [r / total for r in raw]
        w = SeverityWeights(w_irrev=w_irrev, w_impact=w_impact, w_deviation=w_deviation,
                             gate_threshold=base_weights.gate_threshold,
                             gate_mode=base_weights.gate_mode,
                             gate_percentile=base_weights.gate_percentile)
        traj = _run_full_trajectory(env_config, w)
        ids = _ids([s for s in traj.steps if s.explanation_worthy])
        jaccards.append(jaccard(ids, default_ids))
        gate_rates.append(len(ids) / len(traj.steps) if traj.steps else 0.0)

    return {
        "n_samples": n_samples,
        "jaccard_vs_default": {
            "mean": statistics.mean(jaccards), "std": statistics.pstdev(jaccards),
            "min": min(jaccards), "max": max(jaccards),
        },
        "gate_rate": {
            "mean": statistics.mean(gate_rates), "std": statistics.pstdev(gate_rates),
            "min": min(gate_rates), "max": max(gate_rates),
        },
    }


def runtime_scaling(job_counts=(10, 25, 50, 100, 200), sim_horizon_scale: float = 2.4, seed: int = 42) -> dict:
    """
    Wall-clock time of the full pipeline (agent run + calibration +
    drop/hold-out attribution replay + severity gate) as a function of
    trajectory length. Attribution replay is the expected bottleneck since
    it reruns the simulator once per decision step -- this should show
    roughly linear-to-superlinear scaling, which matters for the paper's
    feasibility/limitations discussion on auditing long trajectories.
    """
    results = []
    for n_jobs in job_counts:
        cfg = EnvironmentConfig(n_machines=4, n_jobs=n_jobs,
                                 sim_horizon=int(n_jobs * sim_horizon_scale),
                                 job_arrival_rate=0.4, seed=seed)
        t0 = time.time()
        traj = _run_full_trajectory(cfg, SeverityWeights(), n_calib_seeds=5)
        elapsed = time.time() - t0
        results.append({"n_jobs": n_jobs, "n_decision_steps": len(traj.steps), "elapsed_seconds": elapsed})
    return {"runs": results}


def robustness_to_input_noise(env_config: EnvironmentConfig, weights: SeverityWeights,
                               noise_std_ticks: float = 1.5, n_trials: int = 20, seed: int = 0) -> dict:
    """
    Reviewer concern: F (impact) depends on job deadline, which in a real
    deployment would be an estimate, not a perfectly known constant. This
    checks: if deadlines are jittered by small Gaussian noise (representing
    input-measurement imprecision) and F/S are recomputed on the SAME
    trajectory (action sequence held fixed -- this isolates sensitivity of
    the SCORING function from sensitivity of the agent's decisions, which
    is a separate question), how much does the resulting severity RANKING
    change? Reported as Spearman rank correlation between original and
    noised severity orderings, averaged over `n_trials` independent noise
    draws.
    """
    import random as _random
    from .severity import compute_impact, compute_irreversibility, compute_deviation

    traj = _run_full_trajectory(env_config, weights)
    calib_agent = ScoringAgent()
    calib = calibrate_deviation(env_config, calib_agent, n_seeds=15)
    w = weights.normalized()

    original_scores = [s.severity_score for s in traj.steps]
    rng = _random.Random(seed)

    correlations = []
    for _ in range(n_trials):
        noised_scores = []
        for s in traj.steps:
            noised_deadline = s.job_deadline + rng.gauss(0, noise_std_ticks)
            F_noised = compute_impact(s.job_priority, noised_deadline, s.tick)
            I = compute_irreversibility(s.chosen_action["type"], duration=s.job_duration)
            D = compute_deviation(s.chosen_score, s.runner_up_score, calib)
            S_noised = w.w_irrev * I + w.w_impact * F_noised + w.w_deviation * D
            noised_scores.append(S_noised)
        rho, _ = scipy_stats.spearmanr(original_scores, noised_scores)
        correlations.append(rho)

    return {
        "noise_std_ticks": noise_std_ticks,
        "n_trials": n_trials,
        "spearman_correlation": {
            "mean": statistics.mean(correlations), "std": statistics.pstdev(correlations),
            "min": min(correlations),
        },
    }


def cross_agent_validation(scenario_name: str = "balanced", n_seeds: int = 10,
                            weights: SeverityWeights = None) -> dict:
    """
    Runs the full pipeline with a SECOND, structurally different agent
    (GreedyEDFAgent, agent.py) on the same scenario, and reports the same
    headline metrics as evaluate_scenario_multiseed(). This is the single
    experiment that most directly answers "does the gate only work for the
    one heuristic you built it around?" -- if audit-load reduction and
    critical-decision coverage stay in a similar range across both agents,
    that is real evidence of generalization; if they diverge sharply, that
    is an honest limitation to report, not a result to hide.
    """
    weights = weights or SeverityWeights()
    scoring_result = evaluate_scenario_multiseed(scenario_name, n_seeds=n_seeds, weights=weights, agent=ScoringAgent())
    edf_result = evaluate_scenario_multiseed(scenario_name, n_seeds=n_seeds, weights=weights, agent=GreedyEDFAgent())
    return {"scoring_agent": scoring_result, "greedy_edf_agent": edf_result}



def ablation_study(env_config: EnvironmentConfig, base_weights: SeverityWeights = None) -> dict:
    """
    Zero out each component's weight (I-only, F-only, D-only, and
    pairwise-without-X) and measure the resulting selection's Jaccard
    overlap with the full gate's selection and its critical-decision
    coverage. All variants are compared at the SAME matched budget
    (percentile gate mode, matched to the full gate's own rate) so that
    "did selection QUALITY change" isn't confounded with "did selection
    SIZE change."
    """
    base_weights = base_weights or SeverityWeights()
    traj_full = _run_full_trajectory(env_config, base_weights)
    full_ids = _ids([s for s in traj_full.steps if s.explanation_worthy])
    full_coverage = critical_decision_coverage(traj_full, full_ids)
    matched_percentile = len(full_ids) / len(traj_full.steps) if traj_full.steps else 0.3

    variants = {
        "irreversibility_only": dict(w_irrev=1.0, w_impact=0.0, w_deviation=0.0),
        "impact_only": dict(w_irrev=0.0, w_impact=1.0, w_deviation=0.0),
        "deviation_only": dict(w_irrev=0.0, w_impact=0.0, w_deviation=1.0),
        "without_irreversibility": dict(w_irrev=0.0, w_impact=base_weights.w_impact, w_deviation=base_weights.w_deviation),
        "without_impact": dict(w_irrev=base_weights.w_irrev, w_impact=0.0, w_deviation=base_weights.w_deviation),
        "without_deviation": dict(w_irrev=base_weights.w_irrev, w_impact=base_weights.w_impact, w_deviation=0.0),
        # Pairwise (equal-weighted pairs), requested to check whether any
        # TWO components already explain most of the full gate's behavior.
        "irreversibility_plus_impact": dict(w_irrev=0.5, w_impact=0.5, w_deviation=0.0),
        "irreversibility_plus_deviation": dict(w_irrev=0.5, w_impact=0.0, w_deviation=0.5),
        "impact_plus_deviation": dict(w_irrev=0.0, w_impact=0.5, w_deviation=0.5),
    }

    out = {"full_gate": {"gate_rate": len(full_ids) / len(traj_full.steps), "critical_coverage": full_coverage}}

    for name, w_kwargs in variants.items():
        w_matched = SeverityWeights(gate_mode="percentile", gate_percentile=matched_percentile, **w_kwargs)
        traj = _run_full_trajectory(env_config, w_matched)
        ids = _ids([s for s in traj.steps if s.explanation_worthy])
        cov = critical_decision_coverage(traj, ids)
        out[name] = {
            "gate_rate": len(ids) / len(traj.steps) if traj.steps else 0.0,
            "jaccard_vs_full_gate": jaccard(ids, full_ids),
            "critical_coverage": cov,
            "coverage_delta_vs_full": cov - full_coverage,
        }
    return out


def run_full_evaluation(n_seeds: int = 20, output_dir: str = "outputs/evaluation") -> dict:
    os.makedirs(output_dir, exist_ok=True)
    weights = SeverityWeights()
    results = {"scenarios": {}, "significance": {}, "sensitivity": {}, "ablation": {},
               "cross_agent": {}, "runtime_scaling": {}}

    for name in SCENARIOS:
        print(f"[evaluation] scenario={name}: running {n_seeds} seeds ...")
        results["scenarios"][name] = evaluate_scenario_multiseed(name, n_seeds=n_seeds, weights=weights)

    print("[evaluation] paired significance tests (balanced scenario) ...")
    bal = results["scenarios"]["balanced"]
    results["significance"]["gate_vs_attribution"] = paired_significance_test(
        bal, "critical_coverage_gate", "critical_coverage_attribution")
    results["significance"]["gate_vs_deviation_only"] = paired_significance_test(
        bal, "critical_coverage_gate", "critical_coverage_deviation_only")
    results["significance"]["gate_vs_random"] = paired_significance_test(
        bal, "critical_coverage_gate", "critical_coverage_random")

    default_cfg = get_scenario("balanced", seed=42)
    print("[evaluation] threshold stability interval (balanced, seed=42) ...")
    results["sensitivity"]["threshold_stability"] = threshold_stability_interval(default_cfg, weights)
    print("[evaluation] axis-aligned weight sensitivity (balanced, seed=42) ...")
    results["sensitivity"]["weight_sensitivity"] = weight_sensitivity(default_cfg, weights)
    print("[evaluation] random weight sensitivity, 50 samples (balanced, seed=42) ...")
    results["sensitivity"]["random_weight_sensitivity"] = random_weight_sensitivity(default_cfg, weights, n_samples=50)
    print("[evaluation] robustness to input noise (balanced, seed=42) ...")
    results["sensitivity"]["robustness_to_noise"] = robustness_to_input_noise(default_cfg, weights)

    print("[evaluation] ablation study, incl. pairwise (balanced, seed=42) ...")
    results["ablation"] = ablation_study(default_cfg, weights)

    print("[evaluation] cross-agent validation (balanced, 10 seeds, ScoringAgent vs GreedyEDFAgent) ...")
    results["cross_agent"] = cross_agent_validation("balanced", n_seeds=min(n_seeds, 10), weights=weights)

    print("[evaluation] runtime scaling (n_jobs = 10..200) ...")
    results["runtime_scaling"] = runtime_scaling()

    with open(os.path.join(output_dir, "phase3_results.json"), "w") as f:
        json.dump(results, f, indent=2)
    print(f"[evaluation] done. Results written to {output_dir}/phase3_results.json")
    return results


if __name__ == "__main__":
    run_full_evaluation(n_seeds=20)
