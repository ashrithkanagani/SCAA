"""
Aggregates a single dashboard_data.json from a representative run of each
of the four domains (narrated, gated) plus each domain's multi-run
aggregate metrics, for dashboard/index.html to load via its file picker.

No new experiments are run here beyond what evaluation.py /
cross_domain_evaluation.py already computed -- this module only aggregates
and narrates ONE representative trajectory per domain for the dashboard's
"worthy explanation log" view, and reuses the JSON files those modules
already wrote for the aggregate charts.
"""

from __future__ import annotations

import json
import os

from ..config import SeverityWeights
from ..severity import apply_severity_gate

from .common import run_trajectory_generic, calibrate_deviation_generic

from .delivery.environment import DeliveryEnvironment, DeliveryEnvConfig
from .delivery.agent import NearestWindowAgent
from .delivery.narration import DeliveryNarrator

from .cloud.environment import CloudEnvironment, CloudEnvConfig
from .cloud.agent import SLAAwareAgent
from .cloud.narration import CloudNarrator

from .taillard.loader import load_taillard_instance
from .taillard.environment import JSSPEnvironment
from .taillard.agent import SPTDispatchAgent
from .taillard.narration import JSSPNarrator


def _step_record(s, narrator) -> dict:
    return {
        "step_id": s.step_id, "tick": s.tick, "job_id": s.job_id,
        "priority": s.job_priority, "chosen": s.chosen_label, "runner_up": s.runner_up_label,
        "severity_score": round(s.severity_score, 3) if s.severity_score is not None else None,
        "severity_components": {k: round(v, 3) for k, v in (s.severity_components or {}).items()},
        "explanation_worthy": bool(s.explanation_worthy),
        "narration": narrator.narrate(s),
    }


def build_domain1_record() -> dict:
    from ..agent import ScoringAgent
    from ..scenarios import get_scenario
    from ..simulate import run_trajectory
    from ..attribution import compute_attribution
    from ..config import AttributionConfig
    from ..narration import TemplateNarrator

    cfg = get_scenario("balanced", seed=42)
    agent = ScoringAgent()
    traj = run_trajectory(cfg, agent)
    compute_attribution(traj, agent, cfg, job_schedule=None, attribution_config=AttributionConfig())
    from ..severity import calibrate_deviation
    calib = calibrate_deviation(cfg, agent, n_seeds=15)
    apply_severity_gate(traj, SeverityWeights(), calib)
    narr = TemplateNarrator()

    n_gated = sum(1 for s in traj.steps if s.explanation_worthy)
    return {
        "display_name": "Industrial / IoT Scheduling",
        "description": "Machines process a stream of jobs with priority, deadline, and duration; "
                        "assignment commits a machine for the job's duration.",
        "n_total": len(traj.steps), "n_gated": n_gated,
        "outcome_metrics": traj.final_outcome,
        "steps": [_step_record(s, narr) for s in traj.steps],
    }


def build_domain2_record() -> dict:
    cfg = DeliveryEnvConfig(seed=42)
    agent = NearestWindowAgent()
    traj = run_trajectory_generic(DeliveryEnvironment(cfg), agent)
    calib = calibrate_deviation_generic(lambda: DeliveryEnvironment(cfg), agent, n_seeds=10)
    apply_severity_gate(traj, SeverityWeights(), calib)
    narr = DeliveryNarrator()

    n_gated = sum(1 for s in traj.steps if s.explanation_worthy)
    return {
        "display_name": "Delivery / Logistics Dispatch",
        "description": "Vehicles are dispatched to orders with a service tier and delivery-window "
                        "deadline; dispatch commits a vehicle for the delivery duration.",
        "n_total": len(traj.steps), "n_gated": n_gated,
        "outcome_metrics": traj.final_outcome,
        "steps": [_step_record(s, narr) for s in traj.steps],
    }


def build_domain3_record() -> dict:
    cfg = CloudEnvConfig(seed=42)
    agent = SLAAwareAgent()
    traj = run_trajectory_generic(CloudEnvironment(cfg), agent)
    calib = calibrate_deviation_generic(lambda: CloudEnvironment(cfg), agent, n_seeds=10)
    apply_severity_gate(traj, SeverityWeights(), calib)
    narr = CloudNarrator()

    n_gated = sum(1 for s in traj.steps if s.explanation_worthy)
    return {
        "display_name": "Cloud / Datacenter Task Scheduling",
        "description": "Servers are provisioned to compute tasks with an SLA tier and completion "
                        "deadline; provisioning commits a server for the task's runtime.",
        "n_total": len(traj.steps), "n_gated": n_gated,
        "outcome_metrics": traj.final_outcome,
        "steps": [_step_record(s, narr) for s in traj.steps],
    }


def build_domain4_record(instance_file: str = "la01.txt") -> dict:
    path = os.path.join("data", "taillard", instance_file)
    jobs, n_machines, _ = load_taillard_instance(path)
    env = JSSPEnvironment(jobs, n_machines)
    agent = SPTDispatchAgent()
    traj = run_trajectory_generic(env, agent)
    calib = calibrate_deviation_generic(
        lambda: JSSPEnvironment(*load_taillard_instance(path)[:2]), agent, n_seeds=8)
    apply_severity_gate(traj, SeverityWeights(), calib)
    narr = JSSPNarrator()

    n_gated = sum(1 for s in traj.steps if s.explanation_worthy)
    return {
        "display_name": f"Job-Shop Scheduling (real benchmark: {instance_file})",
        "description": "Real published Taillard/Lawrence job-shop-scheduling benchmark instance "
                        "(JSPLIB). Each job is a fixed sequence of operations on specific machines; "
                        "dispatching a job's operation commits that machine for its duration.",
        "n_total": len(traj.steps), "n_gated": n_gated,
        "outcome_metrics": traj.final_outcome,
        "steps": [_step_record(s, narr) for s in traj.steps],
    }


def build_dashboard_data(output_path: str = "dashboard/dashboard_data.json") -> dict:
    print("[dashboard_data] building Domain 1 (scheduling) sample ...")
    d1 = build_domain1_record()
    print("[dashboard_data] building Domain 2 (delivery) sample ...")
    d2 = build_domain2_record()
    print("[dashboard_data] building Domain 3 (cloud) sample ...")
    d3 = build_domain3_record()
    print("[dashboard_data] building Domain 4 (taillard/JSSP) sample ...")
    d4 = build_domain4_record()

    data = {"domains": {
        "scheduling": d1, "delivery": d2, "cloud": d3, "taillard_jssp": d4,
    }}

    # attach whatever aggregate result files already exist (from evaluation.py /
    # cross_domain_evaluation.py) so the dashboard can chart multi-run results
    # alongside the single narrated sample above -- no new experiments run here.
    p3_path = "outputs/evaluation/phase3_results.json"
    cd_path = "outputs/evaluation/cross_domain_results.json"
    if os.path.exists(p3_path):
        with open(p3_path) as f:
            data["phase3_scenarios"] = json.load(f)["scenarios"]
    if os.path.exists(cd_path):
        with open(cd_path) as f:
            data["cross_domain"] = json.load(f)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[dashboard_data] written to {output_path}")
    return data


if __name__ == "__main__":
    build_dashboard_data()
