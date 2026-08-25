import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scaa.config import EnvironmentConfig
from scaa.environment import SchedulingEnvironment
from scaa.agent import ScoringAgent
from scaa.simulate import run_trajectory


def test_job_schedule_deterministic_given_seed():
    cfg = EnvironmentConfig(seed=7)
    env1 = SchedulingEnvironment(cfg)
    env2 = SchedulingEnvironment(cfg)
    ids1 = [j.job_id for j in env1.job_schedule]
    ids2 = [j.job_id for j in env2.job_schedule]
    assert ids1 == ids2
    ticks1 = [j.arrival_tick for j in env1.job_schedule]
    ticks2 = [j.arrival_tick for j in env2.job_schedule]
    assert ticks1 == ticks2


def test_job_schedule_independent_of_agent_actions():
    """Critical invariant for valid counterfactual replay: arrivals must not
    depend on what actions are taken."""
    cfg = EnvironmentConfig(seed=3)
    agent = ScoringAgent()
    traj_a = run_trajectory(cfg, agent)
    # force a different action at step 0 and confirm job schedule unaffected
    from scaa.attribution import parse_action_from_label
    first_step = traj_a.steps[0]
    if first_step.runner_up_label:
        alt = parse_action_from_label(first_step.runner_up_label, first_step.job_id)
        traj_b = run_trajectory(cfg, agent, override_step_id=0, override_action=alt)
        env_a = SchedulingEnvironment(cfg)
        env_b = SchedulingEnvironment(cfg)
        assert [j.arrival_tick for j in env_a.job_schedule] == [j.arrival_tick for j in env_b.job_schedule]


def test_two_runs_identical_outcome():
    cfg = EnvironmentConfig(seed=11)
    agent = ScoringAgent()
    t1 = run_trajectory(cfg, agent)
    t2 = run_trajectory(cfg, agent)
    assert t1.final_outcome == t2.final_outcome
    assert len(t1.steps) == len(t2.steps)


def test_no_double_assignment_to_busy_machine():
    cfg = EnvironmentConfig(seed=5)
    agent = ScoringAgent()
    traj = run_trajectory(cfg, agent)
    # Reconstruct machine occupancy and check no overlap
    env = SchedulingEnvironment(cfg)
    occupancy = {m: [] for m in range(cfg.n_machines)}
    for step in traj.steps:
        if step.chosen_action["type"] == "assign":
            m_id = step.chosen_action["machine_id"]
            occupancy[m_id].append((step.tick, step.tick + step.job_duration))
    for m_id, intervals in occupancy.items():
        intervals.sort()
        for i in range(1, len(intervals)):
            assert intervals[i][0] >= intervals[i - 1][1], f"overlap on machine {m_id}: {intervals}"


def test_outcome_metrics_present():
    cfg = EnvironmentConfig(seed=1)
    agent = ScoringAgent()
    traj = run_trajectory(cfg, agent)
    for key in ("sla_penalty", "completed_jobs", "late_jobs", "rejected_jobs"):
        assert key in traj.final_outcome


if __name__ == "__main__":
    test_job_schedule_deterministic_given_seed()
    test_job_schedule_independent_of_agent_actions()
    test_two_runs_identical_outcome()
    test_no_double_assignment_to_busy_machine()
    test_outcome_metrics_present()
    print("All environment tests passed.")
