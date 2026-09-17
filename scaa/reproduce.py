"""
Single-command reproduction of every automatic (non-human) result reported
in the paper, across all 4 domains (Phase 1-4). Run:

    python3 -m scaa.reproduce

This runs, in order:
  1. The reference pipeline run (Domain 1: agent -> trace -> attribution ->
     gate -> narration -> baselines -> figures) -> outputs/trajectory.json,
     outputs/summary.json, outputs/figures/*.png
  2. The full Phase 3 evaluation (Domain 1: 3 scenarios x 20 seeds,
     significance tests, sensitivity/ablation studies, cross-agent
     validation, runtime scaling) -> outputs/evaluation/phase3_results.json
  3. Phase 3 figures -> outputs/evaluation/figures/*.png
  4. Phase 4 cross-domain evaluation (delivery, cloud, real Taillard/
     Lawrence JSSP benchmark instances) -> outputs/evaluation/cross_domain_results.json
  5. Dashboard data (one narrated sample trajectory per domain + all
     aggregate results above) -> dashboard/dashboard_data.json
  6. The human-study templates (blank, for your team to fill in, now
     spanning all 4 domains) -> reports/human_study/

Total runtime: under 30 seconds on a normal laptop (no GPU, no network,
no API keys needed for any of the above -- narration defaults to the
deterministic TemplateNarrator; Taillard/Lawrence benchmark data ships
bundled in data/taillard/, no download required).
"""

import time

from .evaluation import run_full_evaluation
from .human_study import generate_audit_quiz_sessions, generate_all_selection_agreement_csvs
from .pipeline import run_pipeline
from .config import PipelineConfig
from .visualize import generate_phase3_figures

from .domains.cross_domain_evaluation import run_cross_domain_evaluation
from .domains.dashboard_data import build_dashboard_data


def main():
    t0 = time.time()

    print("=" * 70)
    print("STEP 1/6: Reference pipeline run (Domain 1: scheduling)")
    print("=" * 70)
    run_pipeline(PipelineConfig())

    print()
    print("=" * 70)
    print("STEP 2/6: Full Phase 3 evaluation (Domain 1: 3 scenarios x 20 seeds + extras)")
    print("=" * 70)
    results = run_full_evaluation(n_seeds=20)

    print()
    print("=" * 70)
    print("STEP 3/6: Phase 3 figures")
    print("=" * 70)
    fig_dir = generate_phase3_figures(results)
    print(f"Figures written to {fig_dir}/")

    print()
    print("=" * 70)
    print("STEP 4/6: Phase 4 cross-domain evaluation (delivery, cloud, real Taillard/JSSP)")
    print("=" * 70)
    run_cross_domain_evaluation(n_seeds=15)

    print()
    print("=" * 70)
    print("STEP 5/6: Dashboard data (one narrated sample per domain + aggregates)")
    print("=" * 70)
    build_dashboard_data()

    print()
    print("=" * 70)
    print("STEP 6/6: Human-study templates (blank -- your team fills these in, 4 domains)")
    print("=" * 70)
    generate_audit_quiz_sessions()
    generate_all_selection_agreement_csvs()

    elapsed = time.time() - t0
    print()
    print("=" * 70)
    print(f"DONE in {elapsed:.1f}s. See reports/RUN_AND_TEST_GUIDE.md for what to do next.")
    print(f"Open dashboard/index.html and load dashboard/dashboard_data.json to explore results.")
    print("=" * 70)


if __name__ == "__main__":
    main()
