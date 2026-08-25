"""
Pipeline orchestrator.

Runs the full flow:
    1. Simulate the agent in the scheduling environment -> Trajectory
    2. Calibrate the deviation reference distribution (multi-seed)
    3. Run drop/hold-out attribution over every step
    4. Apply the severity gate (I, F, D -> S -> explanation_worthy)
    5. [Phase 2] Narrate the SCAA-gated steps (TemplateNarrator by default)
    6. [Phase 2] Compute the three comparison baselines at matched budget
    7. Save the annotated trajectory + a summary report as JSON
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict

from .agent import ScoringAgent
from .attribution import compute_attribution
from .baselines import selection_summary
from .config import PipelineConfig
from .narration import TemplateNarrator, narrate_steps
from .severity import apply_severity_gate, calibrate_deviation
from .simulate import run_trajectory
from .trace import Trajectory
from .visualize import generate_all_figures


def run_pipeline(config: PipelineConfig, agent: ScoringAgent = None,
                  narrator=None, verbose: bool = True, generate_figures: bool = True) -> dict:
    agent = agent or ScoringAgent()
    narrator = narrator or TemplateNarrator()
    t0 = time.time()

    if verbose:
        print("[1/6] Running agent in environment ...")
    trajectory = run_trajectory(config.env, agent)
    n_steps = len(trajectory.steps)

    if verbose:
        print(f"      -> {n_steps} decision steps captured. "
              f"final_outcome={trajectory.final_outcome}")
        print("[2/6] Calibrating deviation reference distribution ...")
    calibration = calibrate_deviation(config.env, agent, n_seeds=15)
    if verbose:
        print(f"      -> mean_gap={calibration.mean_gap:.3f}, std_gap={calibration.std_gap:.3f}, "
              f"n_samples={calibration.n_samples}")

    if verbose:
        print(f"[3/6] Running drop/hold-out attribution over {n_steps} steps "
              f"(this replays the simulator once per step) ...")
    compute_attribution(trajectory, agent, config.env,
                         job_schedule=None, attribution_config=config.attribution)
    # NOTE: job_schedule=None here is intentional -- attribution.py's
    # run_trajectory calls regenerate the SAME deterministic schedule from
    # config.env.seed, so counterfactual replays stay consistent with the
    # original run without needing to pass the schedule object around.

    if verbose:
        print("[4/6] Applying severity gate ...")
    apply_severity_gate(trajectory, config.weights, calibration)

    n_gated = sum(1 for s in trajectory.steps if s.explanation_worthy)

    if verbose:
        print(f"[5/6] Narrating {n_gated} gated steps with {type(narrator).__name__} ...")
    gated_steps = [s for s in trajectory.steps if s.explanation_worthy]
    narrate_steps(gated_steps, narrator=narrator)

    if verbose:
        print("[6/6] Computing comparison baselines at matched budget ...")
    baselines = selection_summary(trajectory)
    baseline_sizes = {
        "scaa_gate": len(baselines["scaa_gate"]),
        "explain_everything": len(baselines["explain_everything"]),
        "attribution_topk": len(baselines["attribution_topk"]),
        "deviation_only_topk": len(baselines["deviation_only_topk"]),
        "oracle_proxy_topk": len(baselines["oracle_proxy_topk"]),
        "random_k": len(baselines["random_k"]),
        "k": baselines["k"],
        "n_total": baselines["n_total"],
    }

    elapsed = time.time() - t0

    summary = {
        "n_decision_steps": n_steps,
        "n_explanation_worthy": n_gated,
        "gate_rate": n_gated / n_steps if n_steps else 0.0,
        "final_outcome": trajectory.final_outcome,
        "calibration": asdict(calibration),
        "weights": asdict(config.weights.normalized()),
        "baseline_sizes": baseline_sizes,
        "narrator": type(narrator).__name__,
        "elapsed_seconds": round(elapsed, 2),
    }

    if verbose:
        print(f"      -> {n_gated}/{n_steps} steps ({summary['gate_rate']:.1%}) "
              f"flagged explanation-worthy. Done in {elapsed:.1f}s.")

    os.makedirs(config.output_dir, exist_ok=True)
    trajectory.save_json(os.path.join(config.output_dir, "trajectory.json"))
    with open(os.path.join(config.output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    if generate_figures:
        if verbose:
            print("[+]    Generating figures ...")
        fig_dir = generate_all_figures(
            trajectory, config.weights, config.env, baseline_sizes,
            out_dir=os.path.join(config.output_dir, "figures"),
        )
        if verbose:
            print(f"      -> figures saved to {fig_dir}/")

    return {"trajectory": trajectory, "summary": summary, "baselines": baselines}


if __name__ == "__main__":
    cfg = PipelineConfig()
    run_pipeline(cfg)
