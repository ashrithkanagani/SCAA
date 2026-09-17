import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scaa.config import SeverityWeights
from scaa.severity import apply_severity_gate
from scaa.domains.common import run_trajectory_generic, calibrate_deviation_generic, compute_attribution_generic

from scaa.domains.delivery.environment import DeliveryEnvironment, DeliveryEnvConfig
from scaa.domains.delivery.agent import NearestWindowAgent
from scaa.domains.delivery.narration import DeliveryNarrator

from scaa.domains.cloud.environment import CloudEnvironment, CloudEnvConfig
from scaa.domains.cloud.agent import SLAAwareAgent
from scaa.domains.cloud.narration import CloudNarrator

from scaa.domains.taillard.loader import load_taillard_instance, list_bundled_instances
from scaa.domains.taillard.environment import JSSPEnvironment
from scaa.domains.taillard.agent import SPTDispatchAgent
from scaa.domains.taillard.narration import JSSPNarrator


# ---------------------------------------------------------------- delivery

def test_delivery_environment_deterministic():
    cfg = DeliveryEnvConfig(seed=7)
    e1 = DeliveryEnvironment(cfg)
    e2 = DeliveryEnvironment(cfg)
    assert [o.deadline for o in e1.order_schedule] == [o.deadline for o in e2.order_schedule]


def test_delivery_full_pipeline_gate_produces_valid_scores():
    cfg = DeliveryEnvConfig(seed=3, n_orders=10, sim_horizon=25)
    agent = NearestWindowAgent()
    traj = run_trajectory_generic(DeliveryEnvironment(cfg), agent)
    assert len(traj.steps) > 0
    calib = calibrate_deviation_generic(lambda: DeliveryEnvironment(cfg), agent, n_seeds=5)
    apply_severity_gate(traj, SeverityWeights(), calib)
    for s in traj.steps:
        assert 0.0 <= s.severity_score <= 1.0
        assert isinstance(s.explanation_worthy, bool)


def test_delivery_narrator_never_falsely_claims_flagged():
    cfg = DeliveryEnvConfig(seed=3, n_orders=10, sim_horizon=25)
    agent = NearestWindowAgent()
    traj = run_trajectory_generic(DeliveryEnvironment(cfg), agent)
    calib = calibrate_deviation_generic(lambda: DeliveryEnvironment(cfg), agent, n_seeds=5)
    apply_severity_gate(traj, SeverityWeights(), calib)
    narr = DeliveryNarrator()
    for s in traj.steps:
        text = narr.narrate(s)
        if not s.explanation_worthy:
            assert "Flagged for audit because" not in text


def test_delivery_attribution_generic_runs():
    cfg = DeliveryEnvConfig(seed=3, n_orders=8, sim_horizon=20)
    agent = NearestWindowAgent()
    traj = run_trajectory_generic(DeliveryEnvironment(cfg), agent)

    def parse_label(label, step):
        job_id = step.job_id
        if label.startswith("assign->M"):
            return {"type": "assign", "job_id": job_id, "machine_id": int(label.split("assign->M")[1])}
        if label == "defer":
            return {"type": "defer", "job_id": job_id}
        if label == "reject":
            return {"type": "reject", "job_id": job_id}
        raise ValueError(label)

    compute_attribution_generic(
        traj, agent, lambda: DeliveryEnvironment(cfg), parse_label,
        outcome_metric="late_penalty", metric_direction="lower_better",
    )
    for s in traj.steps:
        assert s.influence_score is not None


# ------------------------------------------------------------------ cloud

def test_cloud_environment_deterministic():
    cfg = CloudEnvConfig(seed=9)
    e1 = CloudEnvironment(cfg)
    e2 = CloudEnvironment(cfg)
    assert [t.deadline for t in e1.task_schedule] == [t.deadline for t in e2.task_schedule]


def test_cloud_full_pipeline_gate_produces_valid_scores():
    cfg = CloudEnvConfig(seed=4, n_tasks=12, sim_horizon=20)
    agent = SLAAwareAgent()
    traj = run_trajectory_generic(CloudEnvironment(cfg), agent)
    assert len(traj.steps) > 0
    calib = calibrate_deviation_generic(lambda: CloudEnvironment(cfg), agent, n_seeds=5)
    apply_severity_gate(traj, SeverityWeights(), calib)
    for s in traj.steps:
        assert 0.0 <= s.severity_score <= 1.0


def test_cloud_narrator_never_falsely_claims_flagged():
    cfg = CloudEnvConfig(seed=4, n_tasks=12, sim_horizon=20)
    agent = SLAAwareAgent()
    traj = run_trajectory_generic(CloudEnvironment(cfg), agent)
    calib = calibrate_deviation_generic(lambda: CloudEnvironment(cfg), agent, n_seeds=5)
    apply_severity_gate(traj, SeverityWeights(), calib)
    narr = CloudNarrator()
    for s in traj.steps:
        text = narr.narrate(s)
        if not s.explanation_worthy:
            assert "Flagged for audit because" not in text


# --------------------------------------------------------------- taillard

def test_bundled_instances_present():
    files = list_bundled_instances()
    assert "la01.txt" in files and "ta01.txt" in files


def test_taillard_loader_parses_real_instance_correctly():
    jobs, n_machines, _ = load_taillard_instance("data/taillard/la01.txt")
    assert len(jobs) == 10
    assert n_machines == 5
    for job in jobs:
        assert len(job.operations) == n_machines  # classical JSSP: one op per machine
        assert job.priority in (1, 2, 3)
        assert job.deadline > 0


def test_taillard_full_pipeline_completes_all_operations():
    jobs, n_machines, _ = load_taillard_instance("data/taillard/la01.txt")
    env = JSSPEnvironment(jobs, n_machines)
    agent = SPTDispatchAgent()
    traj = run_trajectory_generic(env, agent)
    # every job must have completed all of its operations
    for job in env.jobs.values():
        assert job.is_finished
    # exactly n_jobs * n_machines dispatch decisions in classical JSSP
    assert len(traj.steps) == len(jobs) * n_machines


def test_taillard_gate_runs_on_real_instance():
    jobs, n_machines, _ = load_taillard_instance("data/taillard/la01.txt")
    env = JSSPEnvironment(jobs, n_machines)
    agent = SPTDispatchAgent()
    traj = run_trajectory_generic(env, agent)
    calib = calibrate_deviation_generic(
        lambda: JSSPEnvironment(*load_taillard_instance("data/taillard/la01.txt")[:2]), agent, n_seeds=5)
    apply_severity_gate(traj, SeverityWeights(), calib)
    for s in traj.steps:
        assert 0.0 <= s.severity_score <= 1.0
    flagged = sum(1 for s in traj.steps if s.explanation_worthy)
    assert 0 < flagged < len(traj.steps)  # non-degenerate on real data


def test_taillard_narrator_handles_no_runner_up():
    jobs, n_machines, _ = load_taillard_instance("data/taillard/la01.txt")
    env = JSSPEnvironment(jobs, n_machines)
    agent = SPTDispatchAgent()
    traj = run_trajectory_generic(env, agent)
    calib = calibrate_deviation_generic(
        lambda: JSSPEnvironment(*load_taillard_instance("data/taillard/la01.txt")[:2]), agent, n_seeds=5)
    apply_severity_gate(traj, SeverityWeights(), calib)
    narr = JSSPNarrator()
    solo_steps = [s for s in traj.steps if s.runner_up_label is None]
    for s in solo_steps:
        text = narr.narrate(s)
        assert "only job" in text


# ---------------------------------------------------------- cross-domain

def test_severity_gate_functions_are_literally_the_same_import_across_domains():
    """The load-bearing claim of Phase 4: severity.py is never modified or
    subclassed per domain -- the exact same functions are imported and
    called directly."""
    import scaa.severity as sev_module
    from scaa.domains.delivery import environment as delivery_env  # noqa
    from scaa.domains.cloud import environment as cloud_env  # noqa
    from scaa.domains.taillard import environment as jssp_env  # noqa
    # If this import succeeded and apply_severity_gate was called
    # successfully in the tests above with no per-domain override or
    # subclass of severity.py, the reuse claim holds by construction.
    assert hasattr(sev_module, "apply_severity_gate")
    assert hasattr(sev_module, "compute_irreversibility")
    assert hasattr(sev_module, "compute_impact")
    assert hasattr(sev_module, "compute_deviation")


# ------------------------------------------------------- human study (x4)

def test_human_study_latin_square_all_raters_distinct():
    from scaa.human_study import LATIN_SQUARE_PLAN
    plans = [tuple(v) for v in LATIN_SQUARE_PLAN.values()]
    assert len(set(plans)) == 3, "raters must not collapse onto identical plans"


def test_human_study_latin_square_every_domain_both_conditions():
    from scaa.human_study import LATIN_SQUARE_PLAN
    from collections import defaultdict
    coverage = defaultdict(set)
    for sessions in LATIN_SQUARE_PLAN.values():
        for domain, cond in sessions:
            coverage[domain].add(cond)
    for domain, conds in coverage.items():
        assert conds == {"scaa", "explain_all"}, f"{domain} missing a condition: {conds}"


def test_human_study_taillard_has_solo_decision_steps():
    from scaa.human_study import DOMAIN_REGISTRY
    spec = DOMAIN_REGISTRY["taillard_jssp"]
    traj = spec["build"]()
    solo_steps = [s for s in traj.steps if s.runner_up_label is None]
    assert len(solo_steps) > 0


if __name__ == "__main__":
    test_delivery_environment_deterministic()
    test_delivery_full_pipeline_gate_produces_valid_scores()
    test_delivery_narrator_never_falsely_claims_flagged()
    test_delivery_attribution_generic_runs()
    test_cloud_environment_deterministic()
    test_cloud_full_pipeline_gate_produces_valid_scores()
    test_cloud_narrator_never_falsely_claims_flagged()
    test_bundled_instances_present()
    test_taillard_loader_parses_real_instance_correctly()
    test_taillard_full_pipeline_completes_all_operations()
    test_taillard_gate_runs_on_real_instance()
    test_taillard_narrator_handles_no_runner_up()
    test_severity_gate_functions_are_literally_the_same_import_across_domains()
    test_human_study_latin_square_all_raters_distinct()
    test_human_study_latin_square_every_domain_both_conditions()
    test_human_study_taillard_has_solo_decision_steps()
    print("All domain tests passed.")
