"""
Cross-domain evaluation: the actual empirical test of Phase 4's central
claim -- that SCAA's severity gate generalizes across sequential decision
domains, not just across scenarios of one domain.

Reuses, UNCHANGED:
  - scaa.baselines.selection_summary / attribution_topk_selection / etc.
    (operate only on trajectory.steps; no domain-specific fields touched)
  - scaa.evaluation.critical_decision_coverage (same: only reads
    severity_components and job_duration, both present on every domain's
    DecisionStep records via the shared trace.py schema)
  - scaa.severity.apply_severity_gate / calibrate_deviation_generic
    (domains/common.py)

Domain 4 (Taillard/JSSP) has no natural "seed" axis -- it is driven by
fixed, real, published benchmark instance files. Its "multi-seed" analog is
evaluating across the 5 bundled real instances (ta01-ta03, la01-la02)
instead of across random seeds -- arguably a STRONGER validation than
synthetic seeds, since these are literally different published problem
instances from the OR-Library / JSPLIB benchmark suite.
"""

from __future__ import annotations

import json
import os
import statistics

from ..baselines import selection_summary
from ..config import SeverityWeights
from ..evaluation import critical_decision_coverage, jaccard, selection_diversity
from .common import (run_trajectory_generic, calibrate_deviation_generic, compute_attribution_generic,
                      compute_realized_outcome_contribution_generic)

from .delivery.environment import DeliveryEnvironment, DeliveryEnvConfig
from .delivery.agent import NearestWindowAgent

from .cloud.environment import CloudEnvironment, CloudEnvConfig
from .cloud.agent import SLAAwareAgent

from .taillard.loader import load_taillard_instance, list_bundled_instances
from .taillard.environment import JSSPEnvironment
from .taillard.agent import SPTDispatchAgent


def _parse_label_scheduling_like(label: str, step) -> dict:
    """Shared label parser for delivery and cloud (both use the assign->Mx/
    defer/reject vocabulary internally -- see their environment.py docstrings).
    job_id is always the step's own job_id for these two domains, since a
    candidate label there represents an alternative ACTION for the SAME job."""
    job_id = step.job_id
    if label.startswith("assign->M"):
        return {"type": "assign", "job_id": job_id, "machine_id": int(label.split("assign->M")[1])}
    if label == "defer":
        return {"type": "defer", "job_id": job_id}
    if label == "reject":
        return {"type": "reject", "job_id": job_id}
    raise ValueError(f"cannot parse label: {label}")


def _parse_label_jssp(label: str, step) -> dict:
    """JSSP labels encode the competing JOB directly (the machine is fixed
    by the decision point, not chosen, so it isn't part of the label) --
    the machine_id is instead recovered from the originating step's own
    chosen_action, which all candidates at that decision point share."""
    if label.startswith("assign_job_"):
        alt_job_id = int(label.split("assign_job_")[1])
        machine_id = step.chosen_action["machine_id"]
        return {"type": "assign", "job_id": alt_job_id, "machine_id": machine_id}
    raise ValueError(f"cannot parse label: {label}")


def _summarize_trajectory(traj, roc: dict) -> dict:
    summary = selection_summary(traj)
    gate_ids = set(s.step_id for s in summary["scaa_gate"])
    attr_ids = set(s.step_id for s in summary["attribution_topk"])
    dev_ids = set(s.step_id for s in summary["deviation_only_topk"])
    rand_ids = set(s.step_id for s in summary["random_k"])
    n_total, k = summary["n_total"], summary["k"]

    return {
        "n_total": n_total, "k": k,
        "audit_load_reduction": 1.0 - (k / n_total) if n_total else 0.0,
        "selection_diversity_vs_attribution": selection_diversity(gate_ids, attr_ids),
        "critical_coverage_gate": critical_decision_coverage(traj, gate_ids, roc_override=roc),
        "critical_coverage_attribution": critical_decision_coverage(traj, attr_ids, roc_override=roc),
        "critical_coverage_deviation_only": critical_decision_coverage(traj, dev_ids, roc_override=roc),
        "critical_coverage_random": critical_decision_coverage(traj, rand_ids, roc_override=roc),
    }


def evaluate_delivery_domain(n_seeds: int = 15, weights: SeverityWeights = None) -> dict:
    weights = weights or SeverityWeights()
    agent = NearestWindowAgent()
    per_seed = []
    for seed in range(n_seeds):
        cfg = DeliveryEnvConfig(seed=seed)
        env = DeliveryEnvironment(cfg)
        traj = run_trajectory_generic(env, agent)
        compute_attribution_generic(traj, agent, lambda cfg=cfg: DeliveryEnvironment(cfg),
                                     _parse_label_scheduling_like, "late_penalty", "lower_better")
        calib = calibrate_deviation_generic(lambda cfg=cfg: DeliveryEnvironment(cfg), agent, n_seeds=10)
        from ..severity import apply_severity_gate
        apply_severity_gate(traj, weights, calib)
        roc = compute_realized_outcome_contribution_generic(
            env, "late_penalty_per_tick", "reroute_penalty", "n_reroutes")
        per_seed.append(_summarize_trajectory(traj, roc))
    return {"domain": "delivery", "n_runs": n_seeds, "per_run": per_seed, "aggregate": _aggregate(per_seed)}


def evaluate_cloud_domain(n_seeds: int = 15, weights: SeverityWeights = None) -> dict:
    weights = weights or SeverityWeights()
    agent = SLAAwareAgent()
    per_seed = []
    for seed in range(n_seeds):
        cfg = CloudEnvConfig(seed=seed)
        env = CloudEnvironment(cfg)
        traj = run_trajectory_generic(env, agent)
        compute_attribution_generic(traj, agent, lambda cfg=cfg: CloudEnvironment(cfg),
                                     _parse_label_scheduling_like, "breach_penalty", "lower_better")
        calib = calibrate_deviation_generic(lambda cfg=cfg: CloudEnvironment(cfg), agent, n_seeds=10)
        from ..severity import apply_severity_gate
        apply_severity_gate(traj, weights, calib)
        roc = compute_realized_outcome_contribution_generic(
            env, "breach_penalty_per_tick", "migration_penalty", "n_migrations")
        per_seed.append(_summarize_trajectory(traj, roc))
    return {"domain": "cloud", "n_runs": n_seeds, "per_run": per_seed, "aggregate": _aggregate(per_seed)}


def evaluate_taillard_domain(weights: SeverityWeights = None) -> dict:
    """Evaluates across all bundled REAL benchmark instances (not seeds)."""
    weights = weights or SeverityWeights()
    agent = SPTDispatchAgent()
    per_instance = []
    for fname in list_bundled_instances():
        path = os.path.join("data", "taillard", fname)
        jobs, n_machines, _ = load_taillard_instance(path)
        env = JSSPEnvironment(jobs, n_machines)
        traj = run_trajectory_generic(env, agent)
        compute_attribution_generic(
            traj, agent, lambda p=path: JSSPEnvironment(*load_taillard_instance(p)[:2]),
            _parse_label_jssp, "breach_penalty", "lower_better",
        )
        calib = calibrate_deviation_generic(
            lambda p=path: JSSPEnvironment(*load_taillard_instance(p)[:2]), agent, n_seeds=5)
        from ..severity import apply_severity_gate
        apply_severity_gate(traj, weights, calib)
        # JSSP has no reassignment-like action -- reassign_penalty_attr/reassign_count_attr
        # left as None, ROC here is realized-lateness-only.
        roc = compute_realized_outcome_contribution_generic(env, "breach_penalty_per_tick")
        result = _summarize_trajectory(traj, roc)
        result["instance"] = fname
        per_instance.append(result)
    return {"domain": "taillard_jssp", "n_runs": len(per_instance), "per_run": per_instance,
            "aggregate": _aggregate(per_instance)}


def _aggregate(per_run: list) -> dict:
    keys = ["audit_load_reduction", "selection_diversity_vs_attribution",
            "critical_coverage_gate", "critical_coverage_attribution",
            "critical_coverage_deviation_only", "critical_coverage_random"]
    out = {}
    for k in keys:
        vals = [r[k] for r in per_run]
        out[k] = {"mean": statistics.mean(vals), "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0}
    return out


def run_cross_domain_evaluation(n_seeds: int = 15, output_dir: str = "outputs/evaluation") -> dict:
    os.makedirs(output_dir, exist_ok=True)
    print("[cross-domain] evaluating delivery domain ...")
    delivery = evaluate_delivery_domain(n_seeds=n_seeds)
    print("[cross-domain] evaluating cloud domain ...")
    cloud = evaluate_cloud_domain(n_seeds=n_seeds)
    print("[cross-domain] evaluating taillard/JSSP domain (real benchmark instances) ...")
    taillard = evaluate_taillard_domain()

    results = {"delivery": delivery, "cloud": cloud, "taillard_jssp": taillard}
    with open(os.path.join(output_dir, "cross_domain_results.json"), "w") as f:
        json.dump(results, f, indent=2)
    print(f"[cross-domain] done. Results written to {output_dir}/cross_domain_results.json")
    return results


if __name__ == "__main__":
    run_cross_domain_evaluation(n_seeds=15)
