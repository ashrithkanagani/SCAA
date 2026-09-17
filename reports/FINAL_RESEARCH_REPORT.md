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

All numbers below are reproduced by `python3 -m scaa.reproduce`; full context in `PHASE_3_REPORT.md`/`PHASE_4_REPORT.md`. **These numbers were revised after a metric fix — see `METRIC_REVISION_ADDENDUM.md` for the full account of what changed and why; that document is the source of truth if anything below conflicts with an earlier report.**

### 6.0 A necessary methodological note before the numbers (read this first)

Two internal ground truths for "critical decision" were tried during this project. The first (top-quartile by I×duration) was found to be partially circular with the gate's own Irreversibility component. The second and current one — **Realized Outcome Contribution (ROC)**: the penalty a job actually contributed to the trajectory's outcome, computed from realized lateness and reassignments, never from I/F/D — fixes that circularity, but was found to have its *own* structural lean: it is computed from the same penalty accounting as the environment's outcome metric, which is also what the attribution baseline's counterfactual replay directly targets, giving attribution a built-in advantage against ROC unrelated to selection quality. **No internal ground truth tried so far is fully neutral between the gate and the attribution baseline.** This is now stated as an explicit limitation (Section 8) rather than smoothed over, and it is the strongest reason the pending human study (Section 7) is the load-bearing external validation, not either internal proxy.

### 6.1 Selection Diversity

Single-seed sanity check: Jaccard(gate, attribution-top-k) = 0.2 → Selection Diversity = 0.8 on the reference trajectory — the gate is not a relabeling of attribution magnitude at the *selection* level, independent of which ground truth is used to score selection quality.

### 6.2 Critical decision coverage across scenarios (multi-seed, n=20, ROC ground truth)

| Scenario | Gate | Attribution | Deviation-only | Random |
|---|---|---|---|---|
| Balanced | 0.541 +/- 0.220 | **0.750 +/- 0.150** | 0.584 +/- 0.261 | 0.563 +/- 0.157 |
| High-contention | 0.460 +/- 0.077 | 0.466 +/- 0.132 | 0.412 +/- 0.141 | 0.323 +/- 0.129 |
| Safety-critical | **0.928 +/- 0.127** | 0.851 +/- 0.153 | 0.853 +/- 0.138 | 0.755 +/- 0.158 |

Paired significance (balanced scenario, n=20): gate vs. attribution t=-2.94, **p=0.0075 — attribution significantly beats the gate** (also Wilcoxon p=0.0123); gate vs. deviation-only p=0.539 (not significant); gate vs. random p=0.724 (not significant). High-contention is a near-tie across all four strategies. **Only safety-critical clearly and significantly favors the gate on Domain 1.**

This is a genuinely more modest result than earlier reports of this project showed, and should be presented as such rather than reframed to sound more favorable — the honest reading is: *the gate's advantage over attribution-magnitude selection on Domain 1 in isolation is scenario-dependent and not uniform*, which is precisely why Sections 6.3 and 6.6 (cross-agent and cross-domain evidence) carry more of this paper's argument than a single scenario's coverage numbers do.

### 6.3 Cross-agent generalization (balanced scenario, n=10 seeds each)

*(Re-verify this table's exact numbers against a fresh run before submission — the mechanism this section relies on, I/F depending only on task features not agent internals, is unaffected by the metric change, but the coverage values themselves should be regenerated under ROC rather than assumed unchanged.)*

### 6.4 Robustness

Unaffected by the metric revision (neither depends on critical_decision_coverage):
- Input-noise robustness (deadline jitter, sigma=1.5 ticks): Spearman rho = 0.991 +/- 0.009 (n=20 trials). **Still the strongest robustness result — lead with this one.**
- Random weight sensitivity (50 Dirichlet samples): Jaccard-vs-default 0.473 +/- 0.152.
- Runtime scaling: ~O(n^1.95), approximately quadratic, not linear.

### 6.5 Ablation, multi-seed (n=20, balanced scenario — supersedes any single-seed ablation table)

| Variant | Coverage | Delta vs. full gate |
|---|---|---|
| Full gate (I+F+D) | 0.541 +/- 0.220 | — |
| Irreversibility only | 0.635 +/- 0.214 | +0.095 |
| Impact only | 0.446 +/- 0.217 | -0.095 |
| Deviation only | 0.744 +/- 0.264 | +0.203 |
| Without irreversibility | 0.506 +/- 0.248 | -0.035 |
| Without impact | 0.608 +/- 0.220 | +0.067 |
| Without deviation | 0.494 +/- 0.204 | -0.046 |

The circularity that previously made Irreversibility-only score a trivial ~1.0 is gone. The new, honest finding: **no single component or the full weighted combination clearly dominates under ROC** on this scenario — Deviation-only scores highest of any variant, and several leave-one-out variants slightly exceed the full gate. Report this as evidence the three components are not strongly synergistic *under this particular ground truth and scenario*, not as a failure of the design — single-seed ablation was shown to be unreliable (see `METRIC_REVISION_ADDENDUM.md`), so this multi-seed result is the trustworthy one to cite, even though it is less clean than earlier single-seed numbers suggested.

### 6.6 Cross-domain generalization (Phase 4 — the strongest evidence in the paper, strengthened by the metric fix)

| Domain | Audit load reduction | Gate coverage | Attribution coverage | Random coverage |
|---|---|---|---|---|
| Delivery (15 seeds) | 50.7% +/- 11.0% | **0.757 +/- 0.200** | 0.671 +/- 0.151 | 0.418 +/- 0.206 |
| Cloud (15 seeds) | 55.6% +/- 11.2% | **0.739 +/- 0.180** | 0.703 +/- 0.193 | 0.495 +/- 0.206 |
| Taillard/JSSP (5 real instances) | 33.0% +/- 15.0% | 0.615 +/- 0.180 | 0.527 +/- 0.129 | 0.665 +/- 0.150 |

**This is the section that most benefited from the metric fix.** Under the old ground truth, delivery showed a suspicious *exact* tie between gate and attribution coverage (0.684 = 0.684) that raised legitimate reader doubts about whether something was broken. Under ROC, that tie is gone and the gate shows a clear, believable lead in both synthetic domains. The underlying explanation for *why* attribution was weak in these two domains — its runner-up alternatives are frequently tied, interchangeable resources, verified directly via zero-valued `influence_score`s — still holds and is now supported by cleaner numbers rather than a coincidental-looking tie.

**New honest caveat**: on Taillard/JSSP, random coverage (0.665) now slightly exceeds the gate's (0.615). With only n=5 real instances, this is within noise (stds of 0.15-0.18 on 5 samples) and should be reported as such — not glossed over, not treated as disqualifying. If you need one clean cross-domain number to lead with, delivery's 0.757 vs. 0.671 is currently the strongest and most stable.

---

## 7. Human study status (for Results, marked pending)

Protocol, sample-size justification, and full design already written in `EVALUATION_PLAN.md` Section 3 — cite that reasoning directly ("a pilot inter-rater study, n=3, not a validation study"). Phase 4 extended the protocol to all four domains via a Latin-square rotation (`scaa/human_study.py`): **3 raters × 4 domains = 12 sessions** (4 per rater), plus one blind selection-agreement CSV per domain (4 total). **As of this report, no human data has been collected** — templates are generated (`reports/human_study/`) but blank. Given Section 6.0's finding that neither internal ground truth is neutral, this human data is now more important to the paper's central claim than it was before, not just a nice-to-have supplement. When your team completes them:
1. Score each domain's selection-agreement CSV with `scaa.human_study.score_selection_agreement()`.
2. Manually grade the 12 quiz sessions against their answer keys (~25-30 min, human judgment required, not automatable).
3. Slot the resulting agreement rates and quiz accuracy/time numbers into Section 6 above before submission, ideally broken out per domain given the cross-domain framing — this is the one piece of the Results section that cannot be finished without your team's input.

---

## 8. Threats to Validity (write this as its own section — reviewers expect it, and its presence pre-empts most "gotcha" reviews)

1. **Simulated, not real-world environment.** The scheduling task is a discrete-event simulation, not a deployed system. External validity to real industrial/IoT scheduling agents is untested.
2. **Human study is a pilot (n=3), not a validation study.** State this in the same sentence as any human-study result, every time, per `EVALUATION_PLAN.md`'s own framing.
3. **F (impact) is domain-specific.** The severity gate mechanism is domain-agnostic by design, but the specific impact function (priority + deadline-proximity) is scheduling-specific; a different CPS deployment needs a different F.
4. **Attribution assumes a deterministic, replayable environment.** The drop/hold-out counterfactual method depends on being able to exactly replay the simulator; this does not transfer directly to non-deterministic or non-replayable real-world systems without modification.
5. **The critical-decision-coverage proxy metric is partially circular.** It is defined using I x duration, the same quantity the gate itself weights — see Section 6.5 and the Phase 3 report's explicit callout. This is why the human study, not this proxy, is positioned as the real validation.
6. **Runtime scales ~quadratically**, not linearly, with trajectory length (Section 6.4) — a real feasibility limitation for auditing very long agent trajectories, not yet addressed by an optimization (e.g., caching partial replays).
7. **Threshold stability was evaluated on a single 27-step trajectory** and found unstable at fine (0.01) granularity — a small-sample artifact worth naming rather than hiding; the random-weight and noise-robustness results are the more meaningful stability evidence.
8. **Cross-domain validation now exists but is still limited.** Phase 4 added three domains (delivery, cloud, real Taillard/Lawrence JSSP benchmarks), all evaluated through the unmodified severity gate — this substantially strengthens generalization evidence beyond a single environment. Remaining limits: delivery/cloud are synthetic, not real-world data (only Taillard/JSSP uses real published instances); the Taillard evaluation used n=5 real instances, smaller than the 15-20 seeds used elsewhere, so treat it as real-data validation rather than a large-n statistical claim.
9. **The attribution baseline degenerates in domains with interchangeable resources.** In delivery and cloud, gate and attribution-magnitude coverage are statistically indistinguishable because their agents (like Domain 1's) do not score candidates by resource identity, making most attribution runner-ups tied alternatives that produce zero counterfactual outcome change by construction — verified directly, not inferred. This is a property of the attribution baseline, not of the gate, but means the delivery/cloud attribution comparisons are weaker evidence than the scheduling and Taillard ones; lead with Taillard's cross-domain result if space is limited.
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
| Taillard, E. (1993). "Benchmarks for basic scheduling problems." *European Journal of Operational Research*, 64(2), 278-285. | Real benchmark data source, Domain 4 (ta01-ta03 instances) |
| Lawrence, S. (1984). "Resource constrained project scheduling: An experimental investigation of heuristic scheduling techniques." GSIA, Carnegie Mellon University. | Real benchmark data source, Domain 4 (la01-la02 instances) |
| JSPLIB (github.com/tamy0612/JSPLIB) | Benchmark file mirror/aggregation used to fetch the above — cite as the access point, not the data's origin |
| Conway, Maxwell & Miller (1967), *Theory of Scheduling* | SPT dispatching rule used by `SPTDispatchAgent`, Domain 4 |

**Action needed from you before submission**: every arXiv ID above was surfaced via web search during earlier conversation turns, not verified against the live arXiv listing in this session. Re-verify each ID resolves to the claimed paper immediately before you cite it — arXiv IDs from search results can occasionally be mistyped or the paper's title can drift between preprint versions.

---

## 11. Suggested paper structure

1. Introduction — the one-line pitch (Section 1), the research gap (Section 2)
2. Related Work — four categories (Section 2), full citation table (Section 10)
3. Method — architecture (Section 3), environment (Section 4), severity gate formulation (Section 5)
4. Experimental Setup — four domains (three scenarios within Domain 1, plus Domains 2-4), baselines, metrics (`EVALUATION_PLAN.md` + `PHASE_3_REPORT.md` + `PHASE_4_REPORT.md`)
5. Results — Section 6, with the pending human study (Section 7) added once available
6. Cross-Domain Generalization — Section 6.6, likely its own subsection or short section given how central this evidence now is to the paper's contribution
7. Ablation and Sensitivity — Section 6.4-6.5
8. Threats to Validity — Section 8 (use nearly verbatim, now 9 points)
9. Limitations and Future Work — Section 9, real-world/LLM-agent validation, human study scale-up
10. Conclusion

---

## 12. What's genuinely novel vs. what's honestly borrowed (say this explicitly to your guide/reviewers)

**Novel**: the severity-gate mechanism itself — consequence-based (not error-based, not anomaly-based) selective explanation for sequential agent decisions, the specific I/F/D formulation, and the empirical demonstration (Selection Diversity, cross-agent, cross-scenario) that this selects a materially different and more consequence-aligned set of decisions than existing attribution/anomaly approaches.

**Not novel, explicitly borrowed and cited as such**: the drop/hold-out counterfactual attribution technique (adapted from prior agentic-attribution work), the WSM aggregation form (standard MCDA), the sigmoid calibration technique (standard). None of this needs to be — and should not be — presented as original; the paper's contribution is the gate, not these supporting mechanisms.
