import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scaa.config import EnvironmentConfig, SeverityWeights
from scaa.agent import ScoringAgent
from scaa.simulate import run_trajectory
from scaa.severity import (
    apply_severity_gate,
    calibrate_deviation,
    compute_deviation,
    compute_impact,
    compute_irreversibility,
    DeviationCalibration,
)


def test_irreversibility_bounds():
    for action in ("assign", "reassign", "reject", "defer"):
        val = compute_irreversibility(action, duration=4, max_duration=6)
        assert 0.0 <= val <= 1.0


def test_irreversibility_scales_with_duration():
    short = compute_irreversibility("assign", duration=2, max_duration=6)
    long = compute_irreversibility("assign", duration=6, max_duration=6)
    assert long > short


def test_impact_bounds():
    val = compute_impact(job_priority=3, job_deadline=10, tick=9)
    assert 0.0 <= val <= 1.0
    val_low = compute_impact(job_priority=1, job_deadline=100, tick=0)
    val_high = compute_impact(job_priority=3, job_deadline=1, tick=0)
    assert val_high > val_low


def test_deviation_bounds_and_direction():
    calib = DeviationCalibration(mean_gap=1.0, std_gap=0.5, n_samples=100)
    close_call = compute_deviation(chosen_score=1.0, runner_up_score=0.99, calibration=calib)
    confident = compute_deviation(chosen_score=5.0, runner_up_score=0.1, calibration=calib)
    assert 0.0 <= close_call <= 1.0
    assert 0.0 <= confident <= 1.0
    assert close_call > confident  # close call should be flagged as MORE deviant


def test_severity_weights_normalize():
    w = SeverityWeights(w_irrev=2.0, w_impact=2.0, w_deviation=1.0)
    wn = w.normalized()
    assert abs((wn.w_irrev + wn.w_impact + wn.w_deviation) - 1.0) < 1e-9


def test_full_gate_pipeline_produces_valid_scores():
    cfg = EnvironmentConfig(seed=4, n_jobs=10, sim_horizon=30)
    agent = ScoringAgent()
    traj = run_trajectory(cfg, agent)
    calib = calibrate_deviation(cfg, agent, n_seeds=5)
    weights = SeverityWeights()
    apply_severity_gate(traj, weights, calib)
    for step in traj.steps:
        assert step.severity_score is not None
        assert 0.0 <= step.severity_score <= 1.0
        assert isinstance(step.explanation_worthy, bool)


def test_gate_is_selective_not_trivial():
    """The gate should not degenerate to flagging 0% or 100% on a normal run --
    that would defeat the point of a *selective* explanation mechanism."""
    cfg = EnvironmentConfig(seed=4, n_jobs=20, sim_horizon=50)
    agent = ScoringAgent()
    traj = run_trajectory(cfg, agent)
    calib = calibrate_deviation(cfg, agent, n_seeds=10)
    weights = SeverityWeights()  # uses default gate_threshold from config
    apply_severity_gate(traj, weights, calib)
    flagged = sum(1 for s in traj.steps if s.explanation_worthy)
    rate = flagged / len(traj.steps)
    assert 0.0 < rate < 1.0, f"gate degenerated: rate={rate}"


def test_percentile_gate_mode_selects_expected_fraction():
    cfg = EnvironmentConfig(seed=4, n_jobs=20, sim_horizon=50)
    agent = ScoringAgent()
    traj = run_trajectory(cfg, agent)
    calib = calibrate_deviation(cfg, agent, n_seeds=10)
    weights = SeverityWeights(gate_mode="percentile", gate_percentile=0.25)
    apply_severity_gate(traj, weights, calib)
    n = len(traj.steps)
    flagged = sum(1 for s in traj.steps if s.explanation_worthy)
    import math as _m
    expected = max(1, _m.ceil(0.25 * n))
    assert flagged == expected


if __name__ == "__main__":
    test_irreversibility_bounds()
    test_irreversibility_scales_with_duration()
    test_impact_bounds()
    test_deviation_bounds_and_direction()
    test_severity_weights_normalize()
    test_full_gate_pipeline_produces_valid_scores()
    test_gate_is_selective_not_trivial()
    test_percentile_gate_mode_selects_expected_fraction()
    print("All severity tests passed.")
