import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scaa.config import SeverityWeights
from scaa.scenarios import SCENARIOS, get_scenario
from scaa.agent import GreedyEDFAgent, ScoringAgent
from scaa.evaluation import (
    ablation_study,
    critical_decision_coverage,
    cross_agent_validation,
    evaluate_scenario_multiseed,
    evaluate_single_trajectory,
    jaccard,
    paired_significance_test,
    random_weight_sensitivity,
    robustness_to_input_noise,
    runtime_scaling,
    selection_diversity,
    threshold_stability_interval,
    weight_sensitivity,
    _run_full_trajectory,
)


def test_jaccard_and_diversity_are_complements():
    a = {1, 2, 3}
    b = {2, 3, 4}
    j = jaccard(a, b)
    d = selection_diversity(a, b)
    assert abs((j + d) - 1.0) < 1e-9


def test_jaccard_identical_sets_is_one():
    a = {1, 2, 3}
    assert jaccard(a, a) == 1.0
    assert selection_diversity(a, a) == 0.0


def test_jaccard_disjoint_sets_is_zero():
    a = {1, 2}
    b = {3, 4}
    assert jaccard(a, b) == 0.0
    assert selection_diversity(a, b) == 1.0


def test_all_three_scenarios_are_defined_and_runnable():
    assert set(SCENARIOS.keys()) == {"balanced", "high_contention", "safety_critical"}
    for name in SCENARIOS:
        cfg = get_scenario(name, seed=1)
        result = evaluate_single_trajectory(cfg, SeverityWeights())
        assert result["n_total"] > 0
        assert 0.0 <= result["gate_rate"] <= 1.0


def test_critical_coverage_bounds():
    cfg = get_scenario("balanced", seed=2)
    traj = _run_full_trajectory(cfg, SeverityWeights())
    all_ids = set(s.step_id for s in traj.steps)
    cov_all = critical_decision_coverage(traj, all_ids)
    assert cov_all == 1.0  # selecting everything must catch 100% of the "critical" subset
    cov_none = critical_decision_coverage(traj, set())
    assert cov_none == 0.0


def test_multiseed_aggregate_has_expected_keys():
    result = evaluate_scenario_multiseed("balanced", n_seeds=3)
    assert result["n_seeds"] == 3
    assert len(result["per_seed"]) == 3
    assert "gate_rate" in result["aggregate"]
    assert "mean" in result["aggregate"]["gate_rate"]


def test_threshold_stability_interval_contains_default():
    cfg = get_scenario("balanced", seed=42)
    weights = SeverityWeights()
    result = threshold_stability_interval(cfg, weights)
    lo, hi = result["stability_interval"]
    assert lo <= result["default_threshold"] <= hi


def test_weight_sensitivity_returns_all_three_weights():
    cfg = get_scenario("balanced", seed=42)
    result = weight_sensitivity(cfg, SeverityWeights())
    assert set(result.keys()) == {"w_irrev", "w_impact", "w_deviation"}
    for w in result.values():
        assert "minus" in w and "plus" in w
        assert 0.0 <= w["minus"]["jaccard_vs_default"] <= 1.0


def test_ablation_study_runs_all_variants():
    cfg = get_scenario("balanced", seed=42)
    result = ablation_study(cfg, SeverityWeights())
    expected = {"full_gate", "irreversibility_only", "impact_only", "deviation_only",
                "without_irreversibility", "without_impact", "without_deviation",
                "irreversibility_plus_impact", "irreversibility_plus_deviation", "impact_plus_deviation"}
    assert set(result.keys()) == expected
    for name, d in result.items():
        if name != "full_gate":
            assert 0.0 <= d["jaccard_vs_full_gate"] <= 1.0


def test_paired_significance_test_runs_and_bounds_p_value():
    result = evaluate_scenario_multiseed("balanced", n_seeds=8)
    sig = paired_significance_test(result, "critical_coverage_gate", "critical_coverage_random")
    assert sig["n"] == 8
    if "p_value" in sig["paired_t_test"]:
        assert 0.0 <= sig["paired_t_test"]["p_value"] <= 1.0


def test_confidence_intervals_present_in_aggregate():
    result = evaluate_scenario_multiseed("balanced", n_seeds=5)
    for metric, stats_dict in result["aggregate"].items():
        assert "ci95" in stats_dict
        assert stats_dict["ci95"] >= 0.0


def test_greedy_edf_agent_produces_valid_trajectory():
    cfg = get_scenario("balanced", seed=1)
    weights = SeverityWeights()
    traj = _run_full_trajectory(cfg, weights, agent=GreedyEDFAgent())
    assert len(traj.steps) > 0
    for s in traj.steps:
        assert 0.0 <= s.severity_score <= 1.0


def test_cross_agent_validation_returns_both_agents():
    result = cross_agent_validation("balanced", n_seeds=3)
    assert "scoring_agent" in result and "greedy_edf_agent" in result
    assert result["scoring_agent"]["n_seeds"] == 3
    assert result["greedy_edf_agent"]["n_seeds"] == 3


def test_random_weight_sensitivity_bounds():
    cfg = get_scenario("balanced", seed=42)
    result = random_weight_sensitivity(cfg, SeverityWeights(), n_samples=10)
    assert result["n_samples"] == 10
    assert 0.0 <= result["jaccard_vs_default"]["mean"] <= 1.0
    assert 0.0 <= result["gate_rate"]["mean"] <= 1.0


def test_robustness_to_noise_returns_correlation_near_one():
    cfg = get_scenario("balanced", seed=42)
    result = robustness_to_input_noise(cfg, SeverityWeights(), noise_std_ticks=1.0, n_trials=5)
    corr = result["spearman_correlation"]["mean"]
    assert -1.0 <= corr <= 1.0
    # Small noise should not completely scramble the ranking.
    assert corr > 0.3


def test_runtime_scaling_returns_increasing_step_counts():
    result = runtime_scaling(job_counts=(5, 10))
    assert len(result["runs"]) == 2
    for run in result["runs"]:
        assert run["elapsed_seconds"] >= 0.0
        assert run["n_decision_steps"] > 0


if __name__ == "__main__":
    test_jaccard_and_diversity_are_complements()
    test_jaccard_identical_sets_is_one()
    test_jaccard_disjoint_sets_is_zero()
    test_all_three_scenarios_are_defined_and_runnable()
    test_critical_coverage_bounds()
    test_multiseed_aggregate_has_expected_keys()
    test_threshold_stability_interval_contains_default()
    test_weight_sensitivity_returns_all_three_weights()
    test_ablation_study_runs_all_variants()
    test_paired_significance_test_runs_and_bounds_p_value()
    test_confidence_intervals_present_in_aggregate()
    test_greedy_edf_agent_produces_valid_trajectory()
    test_cross_agent_validation_returns_both_agents()
    test_random_weight_sensitivity_bounds()
    test_robustness_to_noise_returns_correlation_near_one()
    test_runtime_scaling_returns_increasing_step_counts()
    print("All evaluation tests passed.")
