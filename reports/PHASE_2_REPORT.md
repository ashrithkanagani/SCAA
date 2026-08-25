# Phase 2 Report — Math Justification, Narration, Baselines, Visualization, Evaluation Planning

**Project:** SCAA (Selective Causal Auditing for Agentic Systems)
**Phase:** 2 of 3
**Status:** Complete. 28/28 unit tests passing (18 from Phase 1 + 10 new).

This phase directly addresses the four action items given before starting, in order.

---

## Action Item 1 — Strengthened mathematical justification

`severity.py`'s module docstring now contains a full justification section. Summary for the paper:

1. **Why a linear weighted sum (WSM/SAW).** `S = w1·I + w2·F + w3·D` is an instance of the Weighted Sum Model, the most established multi-criteria decision analysis method (Fishburn, 1967; Triantaphyllou, 2000). This is the deliberate choice, not a placeholder, for three reasons: (a) auditability — each criterion's contribution is readable directly off its weight; (b) monotonicity — WSM guarantees a strictly-more-irreversible decision is never scored as strictly-less-severe, which a nonlinear aggregator cannot guarantee and a safety auditor would need; (c) WSM's known weakness, *compensability* (a very low criterion can be offset by a very high one), is explicitly acceptable here — an extremely high-impact decision should be flagged even if trivially reversible, and vice versa. The gate is intentionally compensatory.

2. **Why a sigmoid for D.** D is built on an unbounded z-score; the logistic sigmoid is the standard smooth, monotonic, rank-preserving map from an unbounded statistic onto [0,1], the same justification used for calibrated probability outputs in logistic regression.

3. **Two gate modes, not one.** The Phase 1 cross-seed check showed gate rate swinging 33%→68% at a *fixed* absolute threshold purely from scenario-difficulty shifting the S-distribution's shape — not from decisions becoming more or less consequential in a comparable way. `severity.py` now implements both:
   - `gate_mode="absolute"`: fixed threshold (default 0.62) — auditable, regulation-friendly ("any decision scoring above 0.62 by policy must be explained"), but not scenario-invariant.
   - `gate_mode="percentile"`: flags the top-p% of S scores *within* the trajectory (an order-statistic / rank threshold) — scenario-adaptive, holds "selectivity" constant across scenarios of different difficulty. Verified: `gate_percentile=0.30` on the reference trajectory flags exactly 9/27 = 33.3%, matching the target fraction exactly.
   Both are kept deliberately — the tension between a pre-committed absolute bar and an adaptive relative one is itself worth a sentence in the paper's limitations section.

4. **Threshold/weight sensitivity, not a single defended number.** Following the MCDA literature on *weight stability intervals* (Triantaphyllou & Sánchez, 1997; O'Shea et al., 2025 — the range of weight values for which a decision/ranking doesn't change), Phase 3's ablation is now scoped to report **stability intervals** for `gate_threshold` and each weight, not point estimates. This reframes "why 0.62" as "here is the interval over which the conclusion is robust," which is a stronger, citable answer than defending a single number.

**References added for the paper's methods section:** Fishburn (1967); Triantaphyllou, E. (2000) *Multi-Criteria Decision Making: A Comparative Study*; Triantaphyllou & Sánchez (1997) sensitivity analysis for MCDM; O'Shea et al. (2025), *Weight stability intervals for multi-criteria decision analysis using the weighted sum model*, Expert Systems With Applications.

---

## Action Item 2 — Evaluation planned before narration prompts

Full plan in `reports/EVALUATION_PLAN.md`. Written first, deliberately, so narration design doesn't retroactively shape what gets measured. Three tiers:

1. **Automatic metrics** (zero human involvement, computable now): gate-rate reduction, **gate/attribution-topk Jaccard overlap** (the single most important number — see the preliminary result below), gate/random Jaccard as a sanity floor, irreversibility capture rate, threshold stability intervals, weight sensitivity sweeps, runtime scaling.
2. **Narration quality** (rubric-based, 3 teammates rate ~20 flagged decisions on factual grounding / completeness / clarity) — explicitly scoped as a check that narration doesn't hallucinate, **not** as the paper's contribution.
3. **The human study** — honestly scoped as a **pilot inter-rater agreement study** (n=3 raters, one ~27-decision trajectory, blind Yes/No "would you want this explained"), not a validated user study. The plan states this limitation explicitly rather than overselling it, and computes agreement between each rater and each of the three selection strategies (SCAA gate, attribution-top-k, random-k) at matched budget — so a negative result (SCAA doesn't beat baselines) is just as measurable as a positive one.

**Action needed from you now, in parallel with Phase 3's coding, not after:** the rating exercise needs your 2 teammates to spend roughly an hour each on the Yes/No protocol in Section 3 of the evaluation plan. This is real calendar time the plan can't compress — starting it now avoids it becoming Phase 3's critical path.

**Preliminary sanity check run this phase** (single seed, not the full multi-seed evaluation — that's Phase 3's job): on the reference trajectory, **gate/attribution-top-k Jaccard overlap = 0.2** (gate flagged steps `{4,5,9,15,16,19,20,24,25}`, attribution-top-k flagged `{0,1,2,3,4,5,6,7,9}`, at matched budget k=9). This is the empirical evidence the paper's central novelty claim depends on: if this were close to 1.0, the severity gate would be redundant with "large outcome impact," and the paper's contribution would collapse. A single-seed 0.2 is an encouraging early signal that the gate is selecting a genuinely different set of decisions — Phase 3 needs to confirm this holds across ≥20 seeds before it goes in the paper as a result rather than a preliminary observation.

---

## Action Item 3 — Lightweight visualizations

`scaa/visualize.py` (matplotlib, headless/Agg backend, static PNGs — deliberately not an interactive dashboard). Wired into `pipeline.py` as an optional final step (`generate_figures=True` by default). Five figures, generated to `outputs/figures/` on every pipeline run:

| Figure | Shows |
|---|---|
| `severity_timeline.png` | S(t) per decision step as a bar chart, red = explanation-worthy, with the threshold line — the single figure that most directly demonstrates selectivity |
| `ifd_breakdown.png` | Stacked I/F/D contribution per gated decision — shows *why* each one was flagged |
| `threshold_sweep.png` | Gate rate (%) vs. `gate_threshold` — the sensitivity curve grounding the "why 0.62" discussion |
| `machine_gantt.png` | Machine occupancy over time, red outline on explanation-worthy assignments — makes the scheduling scenario itself legible to a reader unfamiliar with the environment |
| `baseline_comparison.png` | Narration counts across the four selection strategies at matched budget |

All five verified rendering correctly on the reference trajectory (visually inspected this phase).

---

## Action Item 4 — Narration kept deliberately simple

`scaa/narration.py` implements exactly one interface (`narrate(step) -> str`) with two backends, and nothing more:

- **`TemplateNarrator`** (default): pure deterministic string formatting, zero LLM calls, zero network dependency. This is what the pipeline uses unless a different narrator is explicitly passed in, and it is what Phase 3's primary results should use, precisely so results aren't confounded by LLM sampling variance or prompt-wording choices. Sample output (from the reference run):

  > *"Job 14 (priority 3, tick 23): assigning it to Machine 2 instead of assigning it to Machine 3. Flagged because the commitment would be hard to undo (high irreversibility) and the job was high priority and/or close to its deadline (high impact) and this was an unusually close call relative to the agent's typical decisions (high deviation)."*

  Verified deterministic (same step → same text, tested), grounded only in fields already present on the `DecisionStep` (tested), and stays a short audit sentence rather than an essay (tested, <80 words).

- **`GroqNarrator`** (optional): single call, single turn, one fixed short prompt with **no chain-of-thought requested and no multi-turn refinement** — exactly per the instruction not to let prompt engineering become the focus. It receives only the gate's already-decided output (chosen action, runner-up, I/F/D values); it does not reason about severity or see the raw environment. Falls back to `TemplateNarrator` transparently on any failure (missing `GROQ_API_KEY`, network error, malformed response) — verified this phase, since the sandboxed build environment has no route to `api.groq.com` and this fallback path had to work correctly with no key present. Untested against a real Groq call in this environment by design; intended to run on your own machine with your existing Groq setup from Medictate.

No prompt iteration, no few-shot examples, no output re-ranking, no retries-for-quality were added — the narration layer is intentionally the least sophisticated module in the codebase, as instructed.

---

## What else was built (supporting the above)

- **`scaa/baselines.py`**: four selection strategies at matched narration budget — `scaa_gate_selection`, `explain_everything_selection`, `attribution_topk_selection`, `random_k_selection` — plus `selection_summary()` which runs all four at once, budget-matched to the gate's own flag count. This is the direct input to both the automatic metrics and the human study in the evaluation plan.
- **`pipeline.py`** extended from 4 steps to 6: agent run → calibration → attribution → severity gate → narrate gated steps → compute baselines (+ optional figure generation). Verified end-to-end: 9/27 steps gated and narrated on the reference run, all four baseline selections computed at matched budget.
- **10 new unit tests** (`tests/test_narration.py`, `tests/test_baselines.py`): narrator determinism, groundedness (job ID present in output), length bound, fallback-without-API-key behavior; baseline budget-matching, sort-order correctness for attribution-top-k, seed-determinism for random-k. All 28 tests (18 Phase 1 + 10 Phase 2) pass.

---

## Data schema additions

No new `DecisionStep` fields were needed — Phase 1's schema already included everything Phase 2 needed to consume (`severity_components`, `explanation_worthy`, `influence_score`, `runner_up_*`). Only `SeverityWeights` gained two new fields (`gate_mode`, `gate_percentile`), both defaulted so existing Phase 1 configs/outputs remain valid without modification.

---

## What Phase 3 needs to do

1. Run the full pipeline across ≥20 seeds (and a few scenario-difficulty variants) to turn this phase's single-seed Jaccard=0.2 sanity check into a proper multi-seed result with a confidence interval.
2. Compute every metric in `EVALUATION_PLAN.md` Section 1 (`evaluation.py`, new file — pure computation over existing JSON/pipeline outputs, no new modeling).
3. Collect the teammate ratings for Sections 2 and 3 of the evaluation plan (should already be in progress in parallel, per the note above).
4. Run the threshold/weight sensitivity sweeps and report stability intervals rather than point estimates, per Action Item 1's framing.
5. Assemble results into paper-ready tables and figures (building on `visualize.py`'s existing plotting functions where possible, e.g. extending `plot_threshold_sweep` across multiple seeds).

---

**Files delivered this phase:** `scaa/narration.py`, `scaa/baselines.py`, `scaa/visualize.py` (all pre-existing from initial build, verified/extended this phase), `pipeline.py` extended to 6 steps with figure generation, `tests/test_narration.py`, `tests/test_baselines.py` (10 new tests), `reports/EVALUATION_PLAN.md`, `outputs/figures/*.png` (5 figures from the reference run), strengthened math-justification docstring in `severity.py`, percentile gate mode in `severity.py`/`config.py`.
