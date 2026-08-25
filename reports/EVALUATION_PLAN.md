# SCAA Evaluation Plan

Written before narration prompts, as instructed — the metrics and human
study design should shape what Phase 3 measures, not be reverse-engineered
from whatever the narration happens to produce.

This plan covers three categories of evaluation, all of which Phase 3 will
execute using the artifacts Phase 1/2 already produce: `outputs/trajectory.json`
(per-step severity, influence, narration) and `baselines.py`'s four matched-
budget selections.

---

## 1. Automatic metrics (no human involved, computable right now)

These can be computed the moment Phase 3 starts, on any number of seeds/scenarios,
with zero manual labor — run them across many seeds for statistical power.

| Metric | Definition | What it argues |
|---|---|---|
| **Gate-rate reduction** | `1 - (n_gated / n_total)` | How much audit load SCAA removes vs. explain-everything. Report mean ± std across ≥20 seeds, not one number. |
| **Gate/attribution overlap (Jaccard)** | `\|gate ∩ attribution_topk\| / \|gate ∪ attribution_topk\|` at matched budget k | Tests SCAA's central thesis: if this is close to 1, the gate is redundant with attribution magnitude and the paper's contribution collapses. If it's meaningfully < 1, the gate is finding a *different* set of decisions than "large impact on outcome" — that gap is the paper's evidence for novelty. |
| **Gate/random overlap** | Same Jaccard, vs. `random_k_selection` | Sanity floor — if gate/random overlap ≈ gate/attribution overlap, the gate isn't doing anything structured. |
| **Irreversibility capture rate** | Fraction of all `is_commit=True` steps with `duration` in the top quartile that the gate flags | A domain-specific sanity check: the gate should disproportionately catch the most consequential-to-undo commitments. |
| **Threshold stability interval** | Range of `gate_threshold` over which the *set* of flagged steps stays identical (per Triantaphyllou & Sanchez, 1997) | Answers "why 0.62" with an interval, not a single defended number — see Section 7 below. |
| **Weight sensitivity** | Sweep each of w_irrev/w_impact/w_deviation ±30% independently, holding others fixed; report % change in gate rate and Jaccard overlap with the default gate's selection | Shows the gate's output isn't fragile to small weight perturbations, which matters for reviewer confidence in the hybrid formulation. |
| **Runtime/scalability** | Wall-clock time of the full pipeline vs. `n_jobs` (e.g. 10, 25, 50, 100) | Needed for the feasibility/limitations section — attribution replay cost grows with trajectory length. |

All of the above are pure computation over already-generated JSON — no new code beyond a small `evaluation.py` script that loads `trajectory.json` (or runs the pipeline across seeds) and prints/plots these numbers. Budget: 2-3 days, not weeks.

---

## 2. Narration quality metrics (rubric-based, small human involvement)

This is NOT where the paper's novelty lives (per the explicit instruction to
keep narration simple) — this section exists only to demonstrate the
narration layer doesn't hallucinate or mislead, which a reviewer will ask
about regardless of whether narration is the contribution.

**Protocol:** for a sample of ~20 gated decisions, each of the 3 teammates
independently rates the TemplateNarrator output on a 1-5 scale for:
- **Factual grounding** — does it only state facts present in the `DecisionStep`, with nothing invented? (This should score at ceiling for TemplateNarrator by construction — it's a useful control.)
- **Completeness** — does it mention what was chosen, the alternative, and the driving severity component?
- **Clarity** — would a non-technical stakeholder understand it without further explanation?

Report inter-rater agreement (simple % agreement or Cohen's kappa given 3 raters) and mean scores. If a GroqNarrator variant is also run (optional, needs your own `GROQ_API_KEY`), repeat the same rubric on its output for a one-paragraph comparison — but this is optional polish, not required for the paper's core claim.

---

## 3. The human study — what "worth explaining" actually measures

This is the part that needs the most honesty about scale: with a 3-person
team and no budget for a real user study, this cannot be a statistically
powered study — it is a **pilot inter-rater agreement study**, and the
paper should describe it as exactly that, not oversell it as "a user study
validated our approach."

**Protocol:**
1. Take one full trajectory (~25-30 decisions).
2. Strip severity scores/gate labels from a copy shown to raters (blind to which strategy flagged what).
3. Each of the 3 teammates independently answers, for every decision: *"If you were auditing this agent after the fact, would you want this decision explained to you? (Yes/No)"* — framed exactly as the gate's underlying question, not as "was this a good decision."
4. Compute, for each teammate: agreement rate between their Yes/No and (a) SCAA's gate flag, (b) attribution-top-k's flag, (c) random-k's flag, at matched budget.
5. Report all three agreement rates side by side. The paper's claim is supported if SCAA's agreement rate is meaningfully higher than both baselines'; if it isn't, that is also a valid (and still publishable, reframed) finding — this plan is written so the negative result is just as measurable as the positive one.
6. Report simple 3-rater agreement (fraction of decisions where all 3 teammates gave the same Yes/No) as a measure of how well-defined "worth explaining" even is as a question — low agreement here is itself a finding worth discussing in limitations.

**Sample size honesty:** n=3 raters, 1 trajectory (~25-30 items) is a pilot, not a validation study. The paper should say so explicitly — e.g. "a pilot inter-rater study (n=3, 27 decisions)" — rather than implying a larger validation. If time permits, repeating this on 2-3 trajectories from different seeds strengthens it cheaply (raters already know the protocol).

---

## 4. What Phase 3 will actually deliver against this plan

- `evaluation.py`: computes every metric in Section 1 across a configurable number of seeds, saves a results table + the ablation/sensitivity plots.
- A rating spreadsheet/CSV template for Section 2 and 3 (teammates fill it in — this is the one piece of "human" work that has to happen outside the code, and should start as soon as Phase 3 begins, since it doesn't block on anything else).
- A results section draft assembling all of the above into paper-ready tables/figures.

**Honest scope note:** Sections 2 and 3 depend on your 3 teammates actually spending an hour or two rating decisions. That is real calendar time this plan cannot compress — start that rating exercise in parallel with Phase 3's coding, not after it, or it becomes the critical path.
