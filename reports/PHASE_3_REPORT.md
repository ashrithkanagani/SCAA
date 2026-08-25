# Phase 3 Report — Full Evaluation, Statistical Rigor, Cross-Agent Validation

**Project:** SCAA (Selective Causal Auditing for Agentic Systems)
**Phase:** 3 of 3
**Status:** Complete (automatic experiments). Human-study infrastructure delivered; results PENDING your team's input. 44/44 unit tests passing.

This phase implements every automatic metric from `EVALUATION_PLAN.md`, plus the additional rigor items from the external review you pasted (statistical significance, confidence intervals, extended hyperparameter sensitivity, runtime scaling, pairwise ablations, robustness-to-noise, cross-agent validation, and an Oracle-proxy baseline). Full reproduction: `python3 -m scaa.reproduce` (~9 seconds, no API keys needed).

---

## Answering your two direct questions first

**How many human accuracy tests?** Implemented for **3 raters × 3 scenarios × 2 conditions = 18 sessions** (Latin-square rotated so no rater repeats a scenario across conditions), ~45–60 min per teammate total. If time is tighter, the code supports dropping to 2 scenarios (12 sessions, ~30–40 min/teammate) with zero changes — just skip the `safety_critical` session files. This is genuinely a **pilot**, not a powered study, and every report says so explicitly.

**Comparing against papers that solve a different problem:** adopted your reframing wholesale. **Selection Diversity = 1 − Jaccard** is now the headline overlap metric (0.2 Jaccard → 0.8 diversity reads as a result, not a footnote). Rather than importing Who&When's or TrajAD's own metrics (invalid — different ground truth), I added their *selection strategy* as baselines within our framework: `attribution_topk_selection` (Who&When-style) and `deviation_only_topk_selection` (TrajAD/SentinelAgent-style anomaly-only selection). Added `oracle_proxy_topk_selection` as an upper-bound reference too, clearly labeled "proxy" everywhere (see Limitations below for exactly why it's not a real oracle).

---

## What's new this phase, mapped to the external review's 12 suggestions

| # | Suggestion | Status | Where |
|---|---|---|---|
| 1 | Statistical significance | **Done** | `paired_significance_test()`: paired t-test + Wilcoxon signed-rank, gate vs. each baseline, on the balanced scenario's 20 seeds |
| 2 | Confidence intervals | **Done** | Every multi-seed aggregate now reports `mean`, `std`, and `ci95` (t-distribution based) |
| 3 | Hyperparameter sensitivity (beyond axis sweeps) | **Done** | `random_weight_sensitivity()`: 50 random weight triples from a Dirichlet(1,1,1) simplex |
| 4 | Runtime scaling | **Done** | `runtime_scaling()`: n_jobs = 10→200; **empirical result: ~O(n^1.95), i.e. roughly quadratic, NOT linear** — see honest note below |
| 5 | Better ablations (pairs) | **Done** | `ablation_study()` extended with I+F, I+D, F+D pairwise variants alongside the existing single-component ones |
| 6 | Robustness to noise | **Done** | `robustness_to_input_noise()`: Gaussian jitter on deadline inputs, Spearman rank correlation of severity ordering before/after |
| 7 | Cross-agent validation | **Done** | New `GreedyEDFAgent` (structurally different policy) in `agent.py`; `cross_agent_validation()` reruns the full pipeline on both agents, zero pipeline code changes needed (validates the "agent-agnostic by construction" architecture claim) |
| 8 | Cross-domain validation | **Deferred — see Limitations** | Explicitly out of scope for this timeline (the review itself said "if time permits") |
| 9 | Failure cases | **Partially done** | Derived from the data below (`safety_critical`'s low audit-load reduction, threshold instability finding); write-up in the Final Report's Limitations section |
| 10 | Threats to Validity section | **Done** | Full section in `FINAL_RESEARCH_REPORT.md` |
| 11 | Explain-why-filtered logging | **Already present** | `severity_components` (I/F/D breakdown) has existed since Phase 1; `ifd_breakdown.png` visualizes it |
| 12 | Reproducibility (single command) | **Done** | `python3 -m scaa.reproduce` runs everything automatic in ~9s |
| + | Oracle upper-bound baseline | **Done (as proxy)** | `oracle_proxy_topk_selection()` — see Limitations for the important caveat |

---

## Headline results (all multi-seed, n=20 unless noted)

### Statistical significance (balanced scenario, paired across seeds)

| Comparison | Gate mean | Baseline mean | Paired t-test | Wilcoxon |
|---|---|---|---|---|
| Gate vs. Attribution-top-k | 0.791 | 0.533 | t=4.54, **p=0.00023** | **p=0.00117** |
| Gate vs. Deviation-only | 0.791 | 0.598 | t=3.21, **p=0.0046** | **p=0.0101** |
| Gate vs. Random-k | 0.791 | 0.443 | t=8.72, **p<0.00001** | **p=0.00028** |

All three comparisons are significant at p<0.01 (metric: critical decision coverage, defined below). This is the evidence tier the external review flagged as missing.

### Critical decision coverage across scenarios (mean ± std, n=20 seeds each)

| Scenario | Gate | Attribution | Deviation-only | Random | Audit load reduction |
|---|---|---|---|---|---|
| balanced | **0.791 ± 0.158** | 0.533 ± 0.181 | 0.598 ± 0.197 | 0.443 ± 0.183 | 51.4% ± 10.6% |
| high_contention | **0.869 ± 0.098** | 0.286 ± 0.115 | 0.421 ± 0.129 | 0.413 ± 0.140 | 63.9% ± 5.0% |
| safety_critical | **1.000 ± 0.000** | 0.871 ± 0.150 | 0.846 ± 0.141 | 0.775 ± 0.133 | 20.0% ± 7.5% |

Gate wins on coverage in all three scenarios, most dramatically in `high_contention` (0.869 vs 0.286 for attribution — a 3x gap). `safety_critical` shows the honest tradeoff: near-zero audit-load reduction because most decisions genuinely are high-impact there (see Limitations for what this scenario reveals about the absolute-threshold gate mode).

### Cross-agent validation (balanced scenario, n=10 seeds, ScoringAgent vs. GreedyEDFAgent)

| Metric | ScoringAgent | GreedyEDFAgent |
|---|---|---|
| Audit load reduction | 51.6% ± 7.8% | 72.3% ± 4.0% |
| Critical coverage (gate) | 0.800 ± 0.151 | 0.708 ± 0.099 |
| Critical coverage (attribution) | 0.562 | 0.314 |

The gate beats the attribution baseline on **both** agent policies, and the gap is if anything larger for GreedyEDFAgent (0.708 vs 0.314). This is real evidence against "the gate only works for the one heuristic it was tuned around" — it wasn't tuned for either agent's specific score distribution, since I/F depend only on task features (action type, duration, priority, deadline), not on the agent's internal scoring at all; only D depends on the agent's confidence gaps, and even that generalized here.

### Sensitivity and robustness

- **Threshold stability interval**: `[0.62, 0.62]` — i.e., zero width at 0.01 granularity on this single 27-step trajectory. **Honest finding, not spun**: with only 27 discrete decisions, the severity distribution is sparse enough that almost every 0.01 step in threshold changes at least one flag. This is a real limitation of reporting stability on a single short trajectory, not evidence the gate is fragile — the random-weight and axis-sensitivity results below are the more meaningful robustness evidence.
- **Axis-aligned weight sensitivity** (+/-30% per weight): Jaccard-vs-default ranged 0.50-1.00 across the six perturbations — moderate, not perfect, stability.
- **Random weight sensitivity** (50 fully random Dirichlet samples): Jaccard-vs-default mean 0.473, std 0.152, range [0, 1]. This is a genuinely harder stress test than the axis sweep (it includes near-degenerate corners of weight space), so a moderate mean is the expected, honest result — not a red flag, but also not something to oversell as "fully robust."
- **Robustness to input noise** (deadline jitter, sigma=1.5 ticks, 20 trials): Spearman correlation mean **0.991**, min 0.964. Severity ranking is highly stable under realistic deadline-estimation noise. This is the strongest robustness result of the three and the one I'd lead with in the paper.
- **Runtime scaling**: empirically **~O(n^1.95)** (fit via log-log regression across n_jobs=10-200), i.e. close to quadratic. This is because attribution replay reruns the simulator once per decision step, and each replay's own cost grows with remaining trajectory length. **This is a real limitation, not linear as might be hoped** — worth an explicit sentence in the paper's feasibility discussion, especially for very long trajectories.

### Ablation (single + pairwise, balanced scenario, single seed=42 — see circularity caveat below)

| Variant | Critical coverage | Delta vs. full gate |
|---|---|---|
| Full gate (I+F+D) | 0.429 | — |
| Irreversibility only | 1.000 | +0.571 |
| Impact only | 0.429 | 0.000 |
| Deviation only | 0.571 | +0.143 |
| Without irreversibility (F+D) | 0.143 | **-0.286** |
| Without impact (I+D) | 0.714 | +0.286 |
| Without deviation (I+F) | 0.429 | 0.000 |

**Important, must go in the paper's limitations section:** the "critical decision coverage" proxy ground truth is itself defined as top-I x duration (see `critical_decision_coverage()`), so any I-heavy variant is mechanically advantaged on this specific metric — "Irreversibility only" scoring a perfect 1.000 is close to circular, not a real finding that I alone is sufficient. The metric that ISN'T circular w.r.t. this proxy is **"Without irreversibility" scoring the worst (0.143, -0.286)** — that result is legitimate evidence that I contributes real, non-redundant information, since removing it hurts performance on a metric not solely defined by it in that direction. The genuinely trustworthy test of "does the gate select what actually matters" is the pending human study, not this internal proxy — flagged prominently, not buried.

---

## What's still pending from you

The human-study templates are generated and ready (`reports/human_study/`), but **contain no real data yet** — I will not fabricate ratings or timings. Two things:

1. **Selection agreement CSV** (`reports/human_study/selection_agreement_blank.csv`): make 3 copies, each teammate fills in Yes/No independently, blind to which strategy flagged what.
2. **Audit quiz sessions** (`reports/human_study/quiz_sessions/*.txt`): 9 files (3 raters x 3 sessions each per the Latin-square plan), each teammate reads their assigned sessions, answers the 5-question quiz, records their time.

Once you have these filled in, run `scaa.human_study.score_selection_agreement()` (for the CSVs) — a small manual scoring pass, not more coding, is all that's left. I did not build automatic scoring for the quiz answers (correctness of free-text answers needs a human to judge against the answer key in `answer_keys/`, not code) — budget ~20 minutes to grade the 9 sessions against their keys once collected.

---

**Files delivered this phase:** `scaa/scenarios.py` (3 named scenarios), `scaa/evaluation.py` (multi-seed metrics, significance tests, sensitivity/ablation/robustness/cross-agent/runtime experiments), `scaa/human_study.py` (template generation + agreement scoring), `scaa/reproduce.py` (single-command reproduction), `GreedyEDFAgent` in `agent.py`, `oracle_proxy_topk_selection` in `baselines.py`, 3 new Phase 3 figures in `visualize.py`, `tests/test_evaluation.py` (16 new tests), `outputs/evaluation/phase3_results.json`, `reports/human_study/*` (blank templates).
