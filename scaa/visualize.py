"""
Lightweight visualization module.

Produces the figures a paper/presentation actually needs from this project:
  1. Severity timeline  - S(t) across decision steps, threshold line, gated
                           steps highlighted -- the single figure that most
                           directly demonstrates "the gate is selective."
  2. I/F/D breakdown     - stacked bar of the three components per gated
                           decision -- shows WHY each one was flagged.
  3. Threshold sweep     - gate rate vs. gate_threshold -- the sensitivity
                           curve that grounds the "why 0.62" discussion.
  4. Machine Gantt chart - occupancy of each machine over time -- makes the
                           scheduling scenario itself legible to a reader
                           who has never seen the environment.
  5. Baseline comparison - bar chart of narration counts across the four
                           selection strategies at matched budget.

Kept deliberately simple (matplotlib, static PNGs, no interactivity) -- these
are demonstration/paper figures, not a dashboard product.
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")  # headless, no display available
import matplotlib.pyplot as plt

from .config import EnvironmentConfig, SeverityWeights
from .severity import DeviationCalibration, apply_severity_gate
from .trace import Trajectory


def plot_severity_timeline(trajectory: Trajectory, weights: SeverityWeights, out_path: str):
    steps = trajectory.steps
    ticks = [s.tick for s in steps]
    scores = [s.severity_score for s in steps]
    flagged = [s.explanation_worthy for s in steps]

    fig, ax = plt.subplots(figsize=(9, 4))
    colors = ["#d64550" if f else "#8fa6c2" for f in flagged]
    ax.bar(ticks, scores, color=colors, width=0.8)
    threshold = weights.normalized().gate_threshold
    if weights.gate_mode == "absolute":
        ax.axhline(threshold, color="black", linestyle="--", linewidth=1,
                   label=f"gate_threshold = {threshold:.2f}")
    ax.set_xlabel("Tick")
    ax.set_ylabel("Severity score S")
    ax.set_title("Severity score per decision (red = explanation-worthy)")
    ax.set_ylim(0, 1.0)
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_ifd_breakdown(trajectory: Trajectory, out_path: str, max_steps: int = 15):
    gated = [s for s in trajectory.steps if s.explanation_worthy][:max_steps]
    if not gated:
        gated = trajectory.steps[:max_steps]

    labels = [f"J{s.job_id}\n(t{s.tick})" for s in gated]
    I = [s.severity_components["I"] for s in gated]
    F = [s.severity_components["F"] for s in gated]
    D = [s.severity_components["D"] for s in gated]

    fig, ax = plt.subplots(figsize=(max(8, len(gated) * 0.6), 4.5))
    x = range(len(gated))
    ax.bar(x, I, label="I (irreversibility)", color="#3b6ea5")
    ax.bar(x, F, bottom=I, label="F (impact)", color="#e0a458")
    bottom_if = [i + f for i, f in zip(I, F)]
    ax.bar(x, D, bottom=bottom_if, label="D (deviation)", color="#8c6bb1")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("Weighted contribution to S")
    ax.set_title("I / F / D breakdown for gated decisions")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_threshold_sweep(trajectory: Trajectory, out_path: str,
                          thresholds=None):
    thresholds = thresholds or [round(0.45 + 0.025 * i, 3) for i in range(15)]
    scores = sorted((s.severity_score for s in trajectory.steps), reverse=True)
    n = len(scores)
    rates = [sum(1 for s in scores if s >= t) / n for t in thresholds]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(thresholds, [r * 100 for r in rates], marker="o", color="#d64550")
    ax.set_xlabel("gate_threshold")
    ax.set_ylabel("% of decisions flagged explanation-worthy")
    ax.set_title("Gate-rate sensitivity to threshold (this trajectory)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_machine_gantt(trajectory: Trajectory, env_config: EnvironmentConfig, out_path: str):
    fig, ax = plt.subplots(figsize=(9, 2 + 0.4 * env_config.n_machines))
    cmap = plt.get_cmap("tab20")

    for step in trajectory.steps:
        if step.chosen_action["type"] == "assign":
            m_id = step.chosen_action["machine_id"]
            start = step.tick
            dur = step.job_duration
            severity = step.severity_score or 0.0
            edge = "red" if step.explanation_worthy else "none"
            ax.barh(m_id, dur, left=start, height=0.6,
                    color=cmap(step.job_id % 20), edgecolor=edge, linewidth=2)
            ax.text(start + dur / 2, m_id, f"J{step.job_id}",
                    ha="center", va="center", fontsize=7, color="black")

    ax.set_yticks(range(env_config.n_machines))
    ax.set_yticklabels([f"Machine {i}" for i in range(env_config.n_machines)])
    ax.set_xlabel("Tick")
    ax.set_title("Machine occupancy Gantt chart (red outline = explanation-worthy assignment)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_baseline_comparison(baseline_sizes: dict, out_path: str):
    labels = ["scaa_gate", "attribution_topk", "deviation_only_topk", "oracle_proxy_topk", "random_k", "explain_everything"]
    values = [baseline_sizes[l] for l in labels]

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(labels, values, color=["#d64550", "#3b6ea5", "#4caf7d", "#f2b134", "#8c6bb1", "#8fa6c2"])
    ax.set_ylabel("# decisions narrated")
    ax.set_title(f"Narration budget by strategy (n_total={baseline_sizes['n_total']})")
    ax.tick_params(axis="x", labelrotation=20)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.3, str(v), ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_scenario_comparison(scenario_results: dict, out_path: str):
    """
    scenario_results: {scenario_name: {"aggregate": {metric: {"mean","std"}}}}
    Grouped bar chart of critical-coverage across strategies, per scenario.
    """
    scenarios = list(scenario_results.keys())
    strategies = ["gate", "attribution", "deviation_only", "random"]
    colors = {"gate": "#d64550", "attribution": "#3b6ea5", "deviation_only": "#4caf7d", "random": "#8c6bb1"}

    fig, ax = plt.subplots(figsize=(9, 4.5))
    width = 0.2
    x = range(len(scenarios))
    for i, strat in enumerate(strategies):
        means = [scenario_results[s]["aggregate"][f"critical_coverage_{strat}"]["mean"] for s in scenarios]
        stds = [scenario_results[s]["aggregate"][f"critical_coverage_{strat}"]["std"] for s in scenarios]
        offset = (i - 1.5) * width
        ax.bar([xi + offset for xi in x], means, width=width, yerr=stds,
               label=strat, color=colors[strat], capsize=3)
    ax.set_xticks(list(x))
    ax.set_xticklabels(scenarios)
    ax.set_ylabel("Critical decision coverage")
    ax.set_title("Critical-decision coverage by strategy across scenarios (mean ± std, multi-seed)")
    ax.legend(fontsize=8)
    ax.set_ylim(0, 1.05)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_audit_load_reduction(scenario_results: dict, out_path: str):
    scenarios = list(scenario_results.keys())
    means = [scenario_results[s]["aggregate"]["audit_load_reduction"]["mean"] * 100 for s in scenarios]
    stds = [scenario_results[s]["aggregate"]["audit_load_reduction"]["std"] * 100 for s in scenarios]

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(scenarios, means, yerr=stds, color="#d64550", capsize=4)
    ax.set_ylabel("Audit load reduction (%)")
    ax.set_title("SCAA gate's audit-load reduction vs. explain-everything")
    for b, v in zip(bars, means):
        ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}%", ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_ablation(ablation_results: dict, out_path: str):
    names = [n for n in ablation_results if n != "full_gate"]
    coverage = [ablation_results[n]["critical_coverage"] for n in names]
    jaccard = [ablation_results[n]["jaccard_vs_full_gate"] for n in names]

    fig, ax1 = plt.subplots(figsize=(9, 4.5))
    x = range(len(names))
    ax1.bar([xi - 0.2 for xi in x], coverage, width=0.4, color="#3b6ea5", label="critical coverage")
    ax1.axhline(ablation_results["full_gate"]["critical_coverage"], color="#3b6ea5",
                linestyle="--", linewidth=1, label="full gate coverage")
    ax1.set_ylabel("Critical coverage", color="#3b6ea5")
    ax1.set_ylim(0, 1.05)

    ax2 = ax1.twinx()
    ax2.bar([xi + 0.2 for xi in x], jaccard, width=0.4, color="#d64550", alpha=0.7, label="Jaccard vs full gate")
    ax2.set_ylabel("Jaccard vs. full gate selection", color="#d64550")
    ax2.set_ylim(0, 1.05)

    ax1.set_xticks(list(x))
    ax1.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    ax1.set_title("Ablation: component contribution to selection & coverage\n"
                  "(NOTE: coverage proxy is I-based, so I-containing variants are advantaged -- see report)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def generate_phase3_figures(phase3_results: dict, out_dir: str = "outputs/evaluation/figures"):
    os.makedirs(out_dir, exist_ok=True)
    plot_scenario_comparison(phase3_results["scenarios"], os.path.join(out_dir, "scenario_coverage_comparison.png"))
    plot_audit_load_reduction(phase3_results["scenarios"], os.path.join(out_dir, "audit_load_reduction.png"))
    plot_ablation(phase3_results["ablation"], os.path.join(out_dir, "ablation.png"))
    return out_dir


def generate_all_figures(trajectory: Trajectory, weights: SeverityWeights,
                          env_config: EnvironmentConfig, baseline_sizes: dict,
                          out_dir: str = "outputs/figures"):
    os.makedirs(out_dir, exist_ok=True)
    plot_severity_timeline(trajectory, weights, os.path.join(out_dir, "severity_timeline.png"))
    plot_ifd_breakdown(trajectory, os.path.join(out_dir, "ifd_breakdown.png"))
    plot_threshold_sweep(trajectory, os.path.join(out_dir, "threshold_sweep.png"))
    plot_machine_gantt(trajectory, env_config, os.path.join(out_dir, "machine_gantt.png"))
    plot_baseline_comparison(baseline_sizes, os.path.join(out_dir, "baseline_comparison.png"))
    return out_dir
