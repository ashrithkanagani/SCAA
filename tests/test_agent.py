import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scaa.config import EnvironmentConfig
from scaa.environment import SchedulingEnvironment
from scaa.agent import ScoringAgent


def test_agent_returns_none_when_no_pending_jobs():
    cfg = EnvironmentConfig(seed=1, n_jobs=5, sim_horizon=10, job_arrival_rate=0.0)
    env = SchedulingEnvironment(cfg)
    agent = ScoringAgent()
    decision = agent.decide(env)
    assert decision is None


def test_agent_candidates_include_all_free_machines_plus_defer_reject():
    cfg = EnvironmentConfig(seed=2, n_jobs=10, sim_horizon=30, n_machines=3)
    env = SchedulingEnvironment(cfg)
    agent = ScoringAgent()
    decision = agent.decide(env)
    if decision is not None:
        n_free = sum(env.observe().machine_free_mask)
        # candidates = one per free machine + defer + reject
        assert len(decision.candidates) == n_free + 2


def test_agent_chosen_has_highest_score():
    cfg = EnvironmentConfig(seed=3, n_jobs=10, sim_horizon=30)
    env = SchedulingEnvironment(cfg)
    agent = ScoringAgent()
    decision = agent.decide(env)
    if decision is not None:
        assert decision.chosen.score == max(c.score for c in decision.candidates)


if __name__ == "__main__":
    test_agent_returns_none_when_no_pending_jobs()
    test_agent_candidates_include_all_free_machines_plus_defer_reject()
    test_agent_chosen_has_highest_score()
    print("All agent tests passed.")
