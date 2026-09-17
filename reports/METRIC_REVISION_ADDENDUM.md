# Addendum — Critical Decision Coverage Metric Revision (ROC)

**This addendum supersedes the coverage numbers in `PHASE_3_REPORT.md` and `PHASE_4_REPORT.md`.** Read this first if there's any conflict between this document and earlier reports — this one reflects the corrected, regenerated results.

## What changed and why

The original `critical_decision_coverage` metric used **top-quartile by I × duration** as its ground truth for "high-stakes decision." This was flagged as partially circular: it's defined using Irreversibility (I), the same quantity the severity gate itself weights, mechanically advantaging any I-heavy selection regardless of whether I actually contributes useful signal. Concretely, this made Irreversibility-only ablation score a trivial ~1.0 and made Impact look comparatively useless — an artifact of the ground truth, not a real property of the gate.

**The fix**: ground truth is now **Realized Outcome Contribution (ROC)** — for each job, the penalty it *actually* contributed to the trajectory's outcome (realized lateness × penalty rate, plus realized reassignment penalty), computed entirely from what happened in the simulation. ROC never touches the I, F, or D formulas.

Implementation: `evaluation.py::compute_realized_outcome_contribution()` (Domain 1) and `domains/common.py::compute_realized_outcome_contribution_generic()` (Domains 2-4, which use different field names — `n_reroutes`, `n_migrations` — for the same underlying concept). `critical_decision_coverage()` now accepts an optional `roc_override` dict so each domain supplies its own correctly-computed ROC rather than assuming Domain 1's field names.

## Verification performed

- 64/64 existing tests pass unchanged (the `run_trajectory` signature change is opt-in via `return_env=False` default — zero risk to any existing caller).
- The ablation circularity is confirmed fixed: Irreversibility-only drops from ~1.0 to a value comparable to the other single-component variants (see table below).
- The delivery domain's previously-suspicious exact tie between gate and attribution coverage (0.684 = 0.684) is broken — they now diverge naturally per-seed and the aggregate favors the gate.

## An important, unplanned finding: ROC is not a fully neutral ground truth either

While regenerating Domain 1's primary results under ROC, the **balanced scenario flipped**: attribution now significantly *beats* the gate (0.750 vs. 0.541, paired t-test p=0.0075). This was not the expected direction and needed to be understood, not suppressed.

**The reason**: ROC is computed from the same penalty accounting as the environment's own outcome metric (`cumulative_sla_penalty`). Attribution's `influence_score` is computed by measuring, via counterfactual replay, how much that *same* metric changes under a different decision. ROC and attribution are therefore structurally related — both anchored to realized outcome — in a way the gate's I/F (upfront properties: commitment cost, priority, deadline, computed *before* any outcome is known) are not. This gives attribution a built-in advantage against ROC that has nothing to do with decision-selection quality.

**Conclusion, stated plainly**: neither ground truth tested so far is fully neutral. The old metric (I×duration) structurally favored the gate; ROC structurally favors attribution. This is now the paper's honest position — see the recommended limitations language below — and it strengthens rather than weakens the case for the pending human study as the real arbiter, since no internal proxy tried so far is bias-free.

## Corrected results (replace the corresponding tables in FINAL_RESEARCH_REPORT.md and Results 5.1-5.7)

### Domain 1 — critical decision coverage by scenario (n=20 seeds, ROC ground truth)

| Scenario | Gate | Attribution | Deviation-only | Random | Audit load reduction |
|---|---|---|---|---|---|
| Balanced | 0.541 ± 0.220 | **0.750 ± 0.150** | 0.584 ± 0.261 | 0.563 ± 0.157 | 51.4% ± 10.6% |
| High-contention | 0.460 ± 0.077 | 0.466 ± 0.132 | 0.412 ± 0.141 | 0.323 ± 0.129 | 63.9% ± 5.0% |
| Safety-critical | **0.928 ± 0.127** | 0.851 ± 0.153 | 0.853 ± 0.138 | 0.755 ± 0.158 | 20.0% ± 7.5% |

### Domain 1 — paired significance (balanced scenario, n=20)

| Comparison | Gate mean | Baseline mean | Paired t-test | Wilcoxon |
|---|---|---|---|---|
| Gate vs. Attribution | 0.541 | 0.750 | t=-2.94, **p=0.0075** (attribution wins) | p=0.0123 (attribution wins) |
| Gate vs. Deviation-only | 0.541 | 0.584 | p=0.539 (not significant) | p=0.459 (not significant) |
| Gate vs. Random | 0.541 | 0.563 | p=0.724 (not significant) | p=0.820 (not significant) |

**Only safety-critical now clearly favors the gate on Domain 1.** Balanced significantly favors attribution; high-contention is a near-tie. This is a materially different, more nuanced story than the previous "gate wins everywhere" narrative and should replace it in Results/Discussion — see the recommended rewrite below.

### Domain 1 — ablation, multi-seed (n=20, balanced scenario — replaces the single-seed=42 table)

| Variant | Coverage | Δ vs. full gate |
|---|---|---|
| Full gate (I+F+D) | 0.541 ± 0.220 | — |
| Irreversibility only | 0.635 ± 0.214 | +0.095 |
| Impact only | 0.446 ± 0.217 | -0.095 |
| Deviation only | 0.744 ± 0.264 | +0.203 |
| Without irreversibility | 0.506 ± 0.248 | -0.035 |
| Without impact | 0.608 ± 0.220 | +0.067 |
| Without deviation | 0.494 ± 0.204 | -0.046 |

Circularity is gone (no variant is trivially ~1.0), but the new honest finding is that **no single component or the full weighted combination clearly dominates under this ground truth** — Deviation-only actually scores highest of any variant (0.744), and several "without-X" variants slightly *exceed* the full gate. This is a legitimately different, more modest ablation story than before, and should be reported as such: the components are not strongly synergistic under ROC on this scenario, an honest finding worth a sentence in Discussion rather than a claim of clean complementarity.

### Cross-domain (Phase 4), ROC ground truth

| Domain | Audit load reduction | Gate coverage | Attribution coverage | Random coverage |
|---|---|---|---|---|
| Delivery (15 seeds) | 50.7% ± 11.0% | **0.757 ± 0.200** | 0.671 ± 0.151 | 0.418 ± 0.206 |
| Cloud (15 seeds) | 55.6% ± 11.2% | **0.739 ± 0.180** | 0.703 ± 0.193 | 0.495 ± 0.206 |
| Taillard/JSSP (5 real instances) | 33.0% ± 15.0% | 0.615 ± 0.180 | 0.527 ± 0.129 | 0.665 ± 0.150 |

**Good news**: the suspicious exact-tie in delivery is gone — gate now clearly and believably leads (0.757 vs. 0.671), and cloud shows a modest, believable gate lead too. **New honest caveat**: on Taillard, random now slightly *exceeds* the gate (0.665 vs. 0.615) — with only n=5 real instances, this is well within noise (stds of 0.15-0.18 on 5 samples), but should be reported as a non-significant, small-sample observation, not glossed over.

## Recommended changes to the paper text

1. **Results 5.1's Table 2 and surrounding prose**: replace with the corrected table above. The sentence "the severity gate achieves the highest coverage of consequential decisions in every scenario" is **no longer accurate** and must be rewritten — only safety-critical now supports that claim.
2. **Results 5.2's Table 3**: replace with the corrected significance table. The framing needs to shift from "gate beats all baselines significantly" to an honest scenario-by-scenario account: significantly worse than attribution on balanced, not significantly different from deviation-only/random on balanced, competitive on high-contention, clearly ahead only on safety-critical.
3. **Results 5.4's ablation table**: replace with the multi-seed table above; drop the single-seed circularity caveat language (no longer needed) and add the new honest caveat about weak component synergy instead.
4. **Results 5.7's cross-domain table**: replace with the corrected table; the delivery/cloud "attribution baseline degenerates" story from the original Phase 4 report **still holds** and gets *stronger* evidence now (gate clearly ahead, not tied) — keep that discussion, just update the numbers.
5. **Discussion 6.1-6.2 need a new subsection** (recommend 6.0 or a new opening paragraph) stating plainly: two internal ground truths were tried, one favored the gate structurally (old metric, via I), one favors attribution structurally (ROC, via shared outcome-grounding with the environment's own penalty accounting); neither is neutral; the paper's strongest evidence is therefore the *cross-domain and cross-agent* results (which don't depend on this choice the same way) plus the pending human study, not the single-scenario Domain-1 balanced comparison.
6. **Threats to Validity gets a new, important item**: "No internally-constructed ground truth for critical decision coverage tested so far is fully neutral between the gate and the attribution baseline; each has a structural bias toward one method. External validation (the human study) is therefore the load-bearing evidence, not either internal proxy."
7. **Abstract**: if it currently claims the gate "wins" broadly, soften to something like "achieves significantly higher coverage in safety-critical and cross-domain settings, with mixed results on lower-stakes scenarios" — do not overclaim uniform dominance.

## What this does NOT change

- Cross-agent validation (Section 5.6) did not depend on this metric in a way that flips its conclusion — worth re-verifying numerically but the mechanism (I/F depending only on task features, not agent internals) is unaffected.
- The noise-robustness result (Spearman ρ=0.991) and runtime scaling (~O(n^1.95)) are unaffected — neither depends on critical_decision_coverage at all.
- The core architectural claim (severity gate functions reused verbatim across domains) is unaffected — this is a code-structure fact, not a numeric result.
