import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scaa.config import AttributionConfig, EnvironmentConfig, SeverityWeights
from scaa.agent import ScoringAgent
from scaa.simulate import run_trajectory
from scaa.attribution import compute_attribution
from scaa.severity import apply_severity_gate, calibrate_deviation
from scaa.baselines import (
    attribution_topk_selection,
    explain_everything_selection,
    random_k_selection,
    scaa_gate_selection,
    selection_summary,
)


def _full_trajectory(seed=6):
    cfg = EnvironmentConfig(seed=seed, n_jobs=15, sim_horizon=40)
    agent = ScoringAgent()
    traj = run_trajectory(cfg, agent)
    compute_attribution(traj, agent, cfg, job_schedule=None, attribution_config=AttributionConfig())
    calib = calibrate_deviation(cfg, agent, n_seeds=5)
    apply_severity_gate(traj, SeverityWeights(), calib)
    return traj


def test_explain_everything_returns_all_steps():
    traj = _full_trajectory()
    assert len(explain_everything_selection(traj)) == len(traj.steps)


def test_scaa_gate_matches_explanation_worthy_flags():
    traj = _full_trajectory()
    gate = scaa_gate_selection(traj)
    expected = [s for s in traj.steps if s.explanation_worthy]
    assert gate == expected


def test_attribution_topk_respects_k_and_is_sorted_by_magnitude():
    traj = _full_trajectory()
    k = 3
    top = attribution_topk_selection(traj, k)
    assert len(top) == min(k, len(traj.steps))
    mags = [abs(s.influence_score) for s in top]
    assert mags == sorted(mags, reverse=True)


def test_random_k_selection_is_seed_deterministic():
    traj = _full_trajectory()
    a = random_k_selection(traj, k=4, seed=1)
    b = random_k_selection(traj, k=4, seed=1)
    assert [s.step_id for s in a] == [s.step_id for s in b]


def test_selection_summary_matched_budget():
    traj = _full_trajectory()
    summary = selection_summary(traj)
    k = summary["k"]
    assert len(summary["scaa_gate"]) == k
    assert len(summary["attribution_topk"]) == min(k, summary["n_total"])
    assert len(summary["random_k"]) == min(k, summary["n_total"])
    assert len(summary["explain_everything"]) == summary["n_total"]


if __name__ == "__main__":
    test_explain_everything_returns_all_steps()
    test_scaa_gate_matches_explanation_worthy_flags()
    test_attribution_topk_respects_k_and_is_sorted_by_magnitude()
    test_random_k_selection_is_seed_deterministic()
    test_selection_summary_matched_budget()
    print("All baseline tests passed.")
