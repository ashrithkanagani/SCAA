# SCAA: Final Research Report

**Selective Causal Auditing for Agentic Systems**
A severity-gated explanation framework for sequential agent decisions in safety-critical settings

This is the consolidated reference for writing the journal paper. It does not repeat everything already written in the three phase reports in full — where a topic is already covered in depth there, this report says so explicitly and gives a short pointer rather than duplicating text. Use this document as the paper's skeleton; use the phase reports as the appendix-level detail underneath each section.

**Document map:**
- Deep implementation detail on the attribution engine -> `PHASE_1_REPORT.md` Section 4
- Deep implementation detail on the environment/scenario -> `PHASE_1_REPORT.md` Section 3
- Full mathematical justification text (long-form) -> `severity.py` module docstring, summarized in `PHASE_2_REPORT.md` Action Item 1
- Narration layer design rationale -> `PHASE_2_REPORT.md` Action Item 4
- Full evaluation protocol design (why these metrics) -> `EVALUATION_PLAN.md`
- All numeric results with context -> `PHASE_3_REPORT.md`
- How to run everything -> `RUN_AND_TEST_GUIDE.md`

---

## 1. Title and framing

**Suggested title:** *Selective Causal Auditing: A Severity-Gated Framework for Explaining Consequential Decisions in Agentic Systems*

**One-line pitch:** AI agents make chains of interdependent decisions; when something goes wrong, nobody can efficiently audit which decisions mattered. SCAA doesn't explain every decision or only the one that caused a failure — it flags, in advance, which decisions are consequential enough (by irreversibility, impact, and behavioral deviation) to warrant a human-readable causal explanation, cutting audit load by roughly half while catching the decisions that matter more reliably than existing attribution or anomaly-detection approaches.

---

## 2. The research gap (for the Introduction / Related Work)

Three existing literatures address adjacent but distinct questions:

1. **Failure attribution** (Zhang et al., *Who&When*, ICML 2025 Spotlight; AgentDebug/AgentErrorTaxonomy; Shapley-value responsibility allocation) asks: *given a failure, which step caused it?* This presupposes a labeled failure and answers a forensic, after-the-fact question.
2. **Trajectory anomaly/drift detection** (TrajAD; Trajectory Guard; SentinelAgent) asks: *is this trajectory statistically unusual?* This flags outliers relative to typical behavior, without reference to consequence.
3. **Static XAI** (SHAP, LIME) explains a single prediction; neither addresses sequential, interdependent decisions at all.

**SCAA asks a fourth, different question**: independent of whether an outcome turns out well or badly, and independent of whether a decision is statistically unusual, *is this decision consequential enough — by irreversibility and impact — that a human auditor should see a causal explanation of it, before any failure has occurred?* This is a **prospective, consequence-based gating question**, not a retrospective forensic one and not a pure outlier-detection one. The empirical evidence that this is a genuinely different question (not a relabeling of attribution magnitude) is the Selection Diversity result in Section 6.

---

## 3. System architecture

Five-stage pipeline, all in `scaa/`:

```
Agent (pluggable) --> Environment (industrial/IoT scheduling)
        |
        v
Trace Capture (trace.py: DecisionStep / Trajectory)
        |
        v
Attribution Engine (attribution.py: drop/hold-out counterfactual)
        |
        v
Severity Gate (severity.py: I, F, D -> S -> explanation_worthy)  <-- NOVEL CONTRIBUTION
        |
        v
Narration Layer (narration.py: deliberately simple, template-first)
```

**Full detail on each module already exists in `PHASE_1_REPORT.md` Section 2 (module table) and Sections 4-5 (attribution and severity mechanics) — do not re-derive it, adapt those sections' text directly into the paper's Methods section.**

**Architecture validation point worth stating explicitly in the paper**: the pipeline is agent-agnostic by construction, not just by claim — `GreedyEDFAgent` (Phase 3) plugs into the identical `simulate.py`/`attribution.py`/`severity.py` code with zero modifications, because every downstream stage consumes only the `Candidate`/`Decision` interface, never the agent's internal logic.

---

## 4. The task environment (for Methods)

Industrial/IoT scheduling: a fleet of machines processes a stochastic stream of jobs (priority, deadline, duration), with genuine irreversibility semantics (committing a job to a machine costs a real penalty to undo). Full detail, including why this satisfies the CPS-justifiability requirement for your programme, is in `PHASE_1_REPORT.md` Section 3 — use that text directly, it was written for exactly this purpose.

**Three named scenarios** (Phase 3, `scenarios.py`), instantiated as parameterizations of the same simulator rather than three independent environments (a deliberate scope decision, defensible in the paper as keeping the evaluation surface focused on the gate rather than on environment diversity):

- **`balanced`**: the default/reference scenario.
- **`high_contention`**: fewer machines relative to job load, higher arrival rate — stresses irreversibility (scarce, costly commitments).
- **`safety_critical`**: heavily skewed toward priority-3 ("critical") jobs with tight deadlines — stresses impact.

The fact that gate behavior shifts in the *predicted* direction across these three (see Section 6) is itself a validity check on the I/F/D design, not just a robustness footnote — say this explicitly in Results.

---

## 5. The severity gate — mathematical formulation (for Methods)

```
S = w_irrev * I + w_impact * F + w_deviation * D,   S in [0,1] given normalized weights
explanation_worthy = (S >= gate_threshold)                          [absolute mode]
                    = (S in top gate_percentile of this trajectory)  [percentile mode]
```

- **I (Irreversibility)**: rule-based, `_IRREVERSIBILITY_BASE` table scaled by committed job duration. Exact formula and the empirical correction story (why duration-scaling was needed) is in `PHASE_1_REPORT.md` Section 5 — that correction narrative ("a flat constant collapsed I to near-0.9 for the majority action, fixed by scaling with duration") is good methods-section material showing iterative validation, worth including in the paper almost verbatim.
- **F (Impact/Safety)**: rule-based, priority + deadline-proximity. Same section for the formula.
- **D (Deviation)**: statistical, calibrated z-score of confidence gap via sigmoid. Formula and calibration procedure in the same section.

**Full mathematical justification — WHY this specific form** (linear weighted sum / WSM, sigmoid choice, two gate modes, stability-interval framing) is written at length in `severity.py`'s module docstring and summarized in `PHASE_2_REPORT.md` Action Item 1. **This is close to paper-ready prose already** — the WSM justification (auditability, monotonicity, deliberate compensability) and the sigmoid justification can likely be adapted into the Methods section with light editing rather than rewritten.

**Citations for this section:**
- Fishburn, P.C. (1967). *Additive Utilities with Incomplete Product Set*. Operations Research.
- Triantaphyllou, E. (2000). *Multi-Criteria Decision Making: A Comparative Study*. Kluwer.
- Triantaphyllou, E. & Sanchez, A. (1997). *A Sensitivity Analysis Approach for Some Deterministic Multi-Criteria Decision-Making Methods*. Decision Sciences.
- O'Shea et al. (2025). *Weight stability intervals for multi-criteria decision analysis using the weighted sum model*. Expert Systems With Applications. **Verify this exact citation (title/venue/year) against the actual paper before submission**; it was surfaced via search during Phase 2 and should be independently confirmed, not taken on faith.

---

## 6. Results (for the paper's Results section)

All numbers below are reproduced by `python3 -m scaa.reproduce`; full context and additional numbers are in `PHASE_3_REPORT.md` — this section is the distilled, paper-ready subset.

### 6.1 Selection Diversity (the core novelty evidence)

Single-seed sanity check (Phase 2): **Jaccard(gate, attribution-top-k) = 0.2 -> Selection Diversity = 0.8**. This is the number that argues SCAA is not a relabeling of attribution magnitude.

### 6.2 Critical decision coverage across scenarios (multi-seed, n=20)

| Scenario | Gate | Attribution | Deviation-only | Random |
|---|---|---|---|---|
| balanced | **0.791 +/- 0.158** | 0.533 +/- 0.181 | 0.598 +/- 0.197 | 0.443 +/- 0.183 |
| high_contention | **0.869 +/- 0.098** | 0.286 +/- 0.115 | 0.421 +/- 0.129 | 0.413 +/- 0.140 |
| safety_critical | **1.000 +/- 0.000** | 0.871 +/- 0.150 | 0.846 +/- 0.141 | 0.775 +/- 0.133 |

Statistically significant (balanced scenario, paired across 20 seeds): gate vs. attribution p=0.00023 (t-test), p=0.00117 (Wilcoxon); gate vs. deviation-only p=0.0046/0.0101; gate vs. random p<0.00001/0.00028.

**Caveat that must appear alongside this table, not omitted**: the coverage proxy is defined using I x duration, so this metric is not fully independent ground truth (see Section 8, Threats to Validity, point 5). Present it as internal-consistency evidence, and let the pending human study (Section 7) be the independent validation.

### 6.3 Cross-agent generalization (balanced scenario, n=10 seeds each)

| Metric | ScoringAgent | GreedyEDFAgent |
|---|---|---|
| Audit load reduction | 51.6% +/- 7.8% | 72.3% +/- 4.0% |
| Critical coverage (gate) | 0.800 +/- 0.151 | 0.708 +/- 0.099 |
| Critical coverage (attribution) | 0.562 | 0.314 |

Gate beats attribution on both structurally different policies — evidence against "tuned to one heuristic."

### 6.4 Robustness

- Input-noise robustness (deadline jitter, sigma=1.5 ticks): Spearman rho = 0.991 +/- 0.009 (n=20 trials). **Strongest robustness result — lead with this one.**
- Random weight sensitivity (50 Dirichlet samples): Jaccard-vs-default 0.473 +/- 0.152. Moderate, honestly reported.
- Runtime scaling: **~O(n^1.95)**, i.e. approximately quadratic, not linear. State this plainly in Limitations/Feasibility, do not claim linear scaling.

### 6.5 Ablation (ties to Section 8's circularity caveat — read that before writing this up)

Single most defensible ablation finding: removing I (irreversibility) alone produces the *largest* coverage drop among the "without-X" variants (-0.286) — legitimate evidence I contributes genuine, non-redundant signal. Full table in `PHASE_3_REPORT.md`.

---

## 7. Human study status (for Results, marked pending)

Protocol, sample-size justification, and full design already written in `EVALUATION_PLAN.md` Section 3 — cite that reasoning directly ("a pilot inter-rater study, n=3, not a validation study"). **As of this report, no human data has been collected** — templates are generated (`reports/human_study/`) but blank. When your team completes them:
1. Score the selection-agreement CSVs with `scaa.human_study.score_selection_agreement()`.
2. Manually grade the 9 quiz sessions against their answer keys (~20 min, human judgment required, not automatable).
3. Slot the resulting agreement rates and quiz accuracy/time numbers into Section 6 above before submission — this is the one piece of the Results section that cannot be finished without your team's ~1 hour of input.

---

## 8. Threats to Validity (write this as its own section — reviewers expect it, and its presence pre-empts most "gotcha" reviews)

1. **Simulated, not real-world environment.** The scheduling task is a discrete-event simulation, not a deployed system. External validity to real industrial/IoT scheduling agents is untested.
2. **Human study is a pilot (n=3), not a validation study.** State this in the same sentence as any human-study result, every time, per `EVALUATION_PLAN.md`'s own framing.
3. **F (impact) is domain-specific.** The severity gate mechanism is domain-agnostic by design, but the specific impact function (priority + deadline-proximity) is scheduling-specific; a different CPS deployment needs a different F.
4. **Attribution assumes a deterministic, replayable environment.** The drop/hold-out counterfactual method depends on being able to exactly replay the simulator; this does not transfer directly to non-deterministic or non-replayable real-world systems without modification.
5. **The critical-decision-coverage proxy metric is partially circular.** It is defined using I x duration, the same quantity the gate itself weights — see Section 6.5 and the Phase 3 report's explicit callout. This is why the human study, not this proxy, is positioned as the real validation.
6. **Runtime scales ~quadratically**, not linearly, with trajectory length (Section 6.4) — a real feasibility limitation for auditing very long agent trajectories, not yet addressed by an optimization (e.g., caching partial replays).
7. **Threshold stability was evaluated on a single 27-step trajectory** and found unstable at fine (0.01) granularity — a small-sample artifact worth naming rather than hiding; the random-weight and noise-robustness results are the more meaningful stability evidence.
8. **No cross-domain validation.** Everything here is one task family (scheduling); a second, structurally different domain (e.g., warehouse routing, or a genuinely different CPS task) was explicitly deferred given the project timeline — name this as future work, not as an oversight.
9. **Cross-agent validation used two heuristic policies, not an LLM-based agent.** Both `ScoringAgent` and `GreedyEDFAgent` are deterministic non-LLM policies (a deliberate Phase 1 reproducibility choice). Generalization to an actual LLM-driven agent is untested.

Writing this section yourself, in the paper, using this exact list (trimmed/expanded as fits) pre-empts the "reviewer catches you" failure mode.

---

## 9. Failure cases (pairs with Threats to Validity)

Derived from the scenario data: SCAA's audit-load reduction shrinks toward zero in the `safety_critical` scenario (20.0% vs. 51-64% elsewhere) — the gate still outperforms baselines on coverage there, but stops being "selective" in the audit-load sense once most decisions genuinely are high-stakes. State this honestly as the expected, correct behavior in a degenerate case (if everything matters, a consequence-based gate should flag most things), not as a bug — but note it as a scenario where the *absolute* threshold mode is the wrong choice and `gate_mode="percentile"` should be used instead to preserve selectivity.

---

## 10. Full reference list (consolidated, with roles)

| Ref | Role in paper |
|---|---|
| Zhang et al., *Who&When*, ICML 2025 Spotlight | Primary attribution baseline comparison point |
| Shapley-value failure attribution, arXiv 2509.08682 | Related work, Category A |
| AgentDebug/AgentErrorTaxonomy, arXiv 2503.xxxxx | Related work, Category A |
| *The Why Behind the Action*, arXiv 2601.15075 | Attribution engine's methodological basis |
| Intention-Behavior Consistency attribution, ScienceDirect 2026 | Related work, Category A |
| TrajAD, arXiv 2602.06443 | Deviation-only baseline's methodological analog |
| Trajectory Guard, arXiv 2601.00516 | Related work, Category B |
| SentinelAgent, arXiv 2505.24201 | Related work, Category B |
| *Detecting Silent Failures*, arXiv 2511.04032 | Related work, Category B |
| PROV-AGENT, IEEE e-Science 2025 | Related work, Category C (provenance) |
| Rudin (2019), *Stop Explaining Black Box Models* | Theoretical basis for consequence-based gating |
| *Beyond Technocratic XAI*, arXiv 2508.09231 | Stakeholder-calibrated explanation depth |
| *Bridging the Transparency Gap* (EU AI Act), arXiv | Regulatory grounding for high-risk explainability |
| Lundberg & Lee (SHAP) | Static XAI contrast |
| Ribeiro et al. (LIME) | Static XAI contrast |
| Fishburn (1967) | WSM justification |
| Triantaphyllou (2000) | WSM justification |
| Triantaphyllou & Sanchez (1997) | Stability-interval framing |
| O'Shea et al. (2025) — **verify before citing** | Stability-interval framing |

**Action needed from you before submission**: every arXiv ID above was surfaced via web search during earlier conversation turns, not verified against the live arXiv listing in this session. Re-verify each ID resolves to the claimed paper immediately before you cite it — arXiv IDs from search results can occasionally be mistyped or the paper's title can drift between preprint versions.

---

## 11. Suggested paper structure

1. Introduction — the one-line pitch (Section 1), the research gap (Section 2)
2. Related Work — four categories (Section 2), full citation table (Section 10)
3. Method — architecture (Section 3), environment (Section 4), severity gate formulation (Section 5)
4. Experimental Setup — three scenarios, baselines, metrics (`EVALUATION_PLAN.md` + `PHASE_3_REPORT.md`)
5. Results — Section 6, with the pending human study (Section 7) added once available
6. Ablation and Sensitivity — Section 6.4-6.5
7. Threats to Validity — Section 8 (use nearly verbatim)
8. Limitations and Future Work — Section 9, cross-domain deferral, human study scale-up
9. Conclusion

---

## 12. What's genuinely novel vs. what's honestly borrowed (say this explicitly to your guide/reviewers)

**Novel**: the severity-gate mechanism itself — consequence-based (not error-based, not anomaly-based) selective explanation for sequential agent decisions, the specific I/F/D formulation, and the empirical demonstration (Selection Diversity, cross-agent, cross-scenario) that this selects a materially different and more consequence-aligned set of decisions than existing attribution/anomaly approaches.

**Not novel, explicitly borrowed and cited as such**: the drop/hold-out counterfactual attribution technique (adapted from prior agentic-attribution work), the WSM aggregation form (standard MCDA), the sigmoid calibration technique (standard). None of this needs to be — and should not be — presented as original; the paper's contribution is the gate, not these supporting mechanisms.
