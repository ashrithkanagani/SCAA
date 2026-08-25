"""
Single-command reproduction of every automatic (non-human) result reported
in the paper. Run:

    python3 -m scaa.reproduce

This runs, in order:
  1. The reference pipeline run (agent -> trace -> attribution -> gate ->
     narration -> baselines -> figures) -> outputs/trajectory.json,
     outputs/summary.json, outputs/figures/*.png
  2. The full Phase 3 evaluation (3 scenarios x 20 seeds, significance
     tests, sensitivity/ablation studies, cross-agent validation, runtime
     scaling) -> outputs/evaluation/phase3_results.json
  3. Phase 3 figures -> outputs/evaluation/figures/*.png
  4. The human-study templates (blank, for your team to fill in)
     -> reports/human_study/

Total runtime: under 15 seconds on a normal laptop (no GPU, no network,
no API keys needed for any of the above -- narration defaults to the
deterministic TemplateNarrator).
"""

import json
import time

from .evaluation import run_full_evaluation
from .human_study import generate_audit_quiz_sessions, generate_selection_agreement_csv
from .pipeline import run_pipeline
from .config import PipelineConfig
from .visualize import generate_phase3_figures


def main():
    t0 = time.time()

    print("=" * 70)
    print("STEP 1/4: Reference pipeline run")
    print("=" * 70)
    run_pipeline(PipelineConfig())

    print()
    print("=" * 70)
    print("STEP 2/4: Full Phase 3 evaluation (3 scenarios x 20 seeds + extras)")
    print("=" * 70)
    results = run_full_evaluation(n_seeds=20)

    print()
    print("=" * 70)
    print("STEP 3/4: Phase 3 figures")
    print("=" * 70)
    fig_dir = generate_phase3_figures(results)
    print(f"Figures written to {fig_dir}/")

    print()
    print("=" * 70)
    print("STEP 4/4: Human-study templates (blank -- your team fills these in)")
    print("=" * 70)
    generate_audit_quiz_sessions()
    generate_selection_agreement_csv()

    elapsed = time.time() - t0
    print()
    print("=" * 70)
    print(f"DONE in {elapsed:.1f}s. See reports/RUN_AND_TEST_GUIDE.md for what to do next.")
    print("=" * 70)


if __name__ == "__main__":
    main()
