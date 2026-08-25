import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scaa.config import AttributionConfig, EnvironmentConfig
from scaa.agent import ScoringAgent
from scaa.simulate import run_trajectory
from scaa.attribution import compute_attribution, parse_action_from_label


def test_parse_action_from_label():
    a = parse_action_from_label("assign->M2", job_id=5)
    assert a == {"type": "assign", "job_id": 5, "machine_id": 2}
    d = parse_action_from_label("defer", job_id=5)
    assert d == {"type": "defer", "job_id": 5}
    r = parse_action_from_label("reject", job_id=5)
    assert r == {"type": "reject", "job_id": 5}


def test_attribution_fills_every_step():
    cfg = EnvironmentConfig(seed=2, n_jobs=10, sim_horizon=30)
    agent = ScoringAgent()
    traj = run_trajectory(cfg, agent)
    attr_cfg = AttributionConfig()
    compute_attribution(traj, agent, cfg, job_schedule=None, attribution_config=attr_cfg)
    for step in traj.steps:
        assert step.influence_score is not None


def test_attribution_zero_when_no_alternative():
    """If a step had no candidates other than the chosen one, influence should be 0."""
    cfg = EnvironmentConfig(seed=2, n_jobs=10, sim_horizon=30)
    agent = ScoringAgent()
    traj = run_trajectory(cfg, agent)
    attr_cfg = AttributionConfig()
    compute_attribution(traj, agent, cfg, job_schedule=None, attribution_config=attr_cfg)
    for step in traj.steps:
        if len(step.candidate_labels) <= 1:
            assert step.influence_score == 0.0


if __name__ == "__main__":
    test_parse_action_from_label()
    test_attribution_fills_every_step()
    test_attribution_zero_when_no_alternative()
    print("All attribution tests passed.")
