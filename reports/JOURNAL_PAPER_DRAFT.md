# Selective Causal Auditing: A Severity-Gated Framework for Explaining Consequential Decisions in Agentic Systems

**[Author names], [Institution], [Department]**

> **How to use this document:** This is a full draft with real structure, real numbers, and real citations, meant to be rewritten in your own voice — not submitted as-is. Sentences in `[brackets]` are placeholders you must fill in or decide on. Paragraphs marked **[EXPAND]** are intentionally thin and need your own explanation added. Every number in this draft comes from `PHASE_3_REPORT.md` / `FINAL_RESEARCH_REPORT.md` — if you rerun the evaluation and get different numbers, update them here, don't leave stale numbers in your final paper. Citations marked **[VERIFY]** were found via search and must be independently confirmed against the live paper before submission.

---

## Abstract

*(150–250 words — write this LAST, after every other section is final. Draft below to structure it, not to keep verbatim.)*

Autonomous agents increasingly make long sequences of interdependent decisions in resource-constrained, safety-relevant settings, yet existing explainability tools either explain every decision indiscriminately or explain only the single step responsible for a failure after the fact. We introduce **Selective Causal Auditing (SCAA)**, a severity-gated framework that decides, prospectively, *which* decisions in an agent's trajectory warrant a causal, human-readable explanation — using irreversibility, task impact, and behavioral deviation as consequence-based gating criteria, rather than post-hoc error attribution or statistical anomaly detection. We formulate the severity score as a weighted-sum multi-criteria model and evaluate it on an industrial/IoT scheduling task across three scenarios and two structurally different agent policies. SCAA reduces audit load by [51–72]% relative to explaining every decision while achieving significantly higher critical-decision coverage than attribution-magnitude and anomaly-based baselines (p < 0.01, paired tests, n=20 seeds), and its severity ranking remains stable under realistic input noise (Spearman ρ = 0.99). We report a pilot human inter-rater study [n=3, PENDING/COMPLETE — fill in], full sensitivity and ablation analyses, and discuss the framework's limitations for real-world, LLM-driven deployment.

---

## 1. Introduction

**[EXPAND — 4–6 paragraphs. Structure below.]**

**Paragraph 1 — the problem.** Open with the motivating scenario: agentic systems (LLM-driven or otherwise) are increasingly deployed to make sequences of decisions with real consequences — resource allocation, scheduling, industrial control. When an agent's behavior needs to be audited (by a regulator, an engineer, or after an incident), a human cannot feasibly review every decision in a long trajectory, but also cannot know in advance which decisions matter without reading all of them — a circular bottleneck.

**Paragraph 2 — how existing work falls short.** Two adjacent literatures exist. Failure-attribution methods (Zhang et al., 2025 — *Who&When*, ICML 2025 Spotlight [1]) identify which step in a trajectory caused an already-observed failure — a retrospective, forensic question that presupposes labeled failure. Trajectory anomaly/drift-detection methods (TrajAD [6], Trajectory Guard [7], SentinelAgent [8]) flag statistically unusual behavior, independent of consequence. Neither answers the question an auditor actually has *before* anything has gone wrong: which of these decisions, if any, are consequential enough that I should understand *why* the agent made them?

**Paragraph 3 — our reframing.** State the core reframing explicitly: SCAA treats "worth explaining" as a *prospective, consequence-based gating decision*, not an error-attribution or anomaly-detection decision. Introduce the three criteria — Irreversibility (I), Impact (F), Deviation (D) — at a high level here (formal definitions in Section 4).

**Paragraph 4 — contributions.** State as a numbered list:
1. A severity-gating formulation (SCAA) that combines irreversibility, task impact, and calibrated behavioral deviation into a single, interpretable, auditable severity score, using a Weighted Sum Model with an explicit theoretical justification for that choice (Section 4).
2. An empirical demonstration, across three scenarios and two structurally different agent policies, that SCAA selects a substantially different and more consequence-aligned set of decisions than attribution-magnitude or anomaly-only baselines (Section 6), with statistical significance.
3. A full sensitivity, ablation, and robustness analysis, including a pilot human inter-rater study, reported with explicit honesty about scale and internal-proxy limitations (Sections 7–8).
4. An open, fully reproducible implementation (single-command reproduction, `[repository URL]`).

**Paragraph 5 (optional) — roadmap.** One sentence per remaining section.

---

## 2. Related Work

**[EXPAND — this should be ~600–900 words of prose organized under the four subheadings below. Use the citation list in Section 10 of `FINAL_RESEARCH_REPORT.md` as your source; do not invent claims about papers you have not read the abstract of.]**

### 2.1 Failure attribution in multi-agent and LLM-agent systems
Cover: Zhang et al.'s *Who&When* benchmark and its Agent-as-a-Judge / step-level attribution methods [1]; Shapley-value-based responsibility allocation for multi-agent failures [2]; AgentDebug / AgentErrorTaxonomy's decomposition of trajectories into memory/reflection/planning/action failure modes [3]; intention-behavior consistency-based attribution [5]. **Framing sentence to include:** these methods answer "which step caused the failure," which presupposes an already-labeled failure — SCAA's question is prospective and does not require a failure to have occurred.

### 2.2 Trajectory anomaly and drift detection
Cover: TrajAD [6], Trajectory Guard [7], SentinelAgent's graph-based multi-agent anomaly detection [8], and silent-failure/drift taxonomies [9]. **Framing sentence:** these methods flag statistical unusualness relative to typical behavior, independent of consequence — a trajectory can be highly unusual but low-stakes, or highly typical but high-stakes; SCAA's Deviation (D) component draws on this family as one *input* to a gate rather than treating anomaly as the verdict itself.

### 2.3 Provenance and execution tracking
Cover: PROV-AGENT's unified provenance tracking for agent workflows [10]. **Framing sentence:** provenance systems answer "what happened," a necessary but not sufficient condition for "what should a human look at" — SCAA assumes a provenance/trace layer exists (Section 3) and builds the selection layer on top of it.

### 2.4 Static explainable AI (XAI)
Cover: SHAP [14] and LIME [15] as the dominant feature-attribution methods for single, static predictions. **Framing sentence:** these methods have no native notion of a decision *sequence* where each step's meaning depends on prior steps — the original motivating gap for this entire project line (this sentence can also anchor your Introduction).

### 2.5 Explanation design and regulatory grounding
Cover: Rudin (2019) on the case for interpretable models over post-hoc explanation in high-stakes decisions [11] — this is the closest existing theoretical argument for *stakes-based* explanation policy, though Rudin's argument is about model choice, not about selecting which of many sequential decisions to explain; *Beyond Technocratic XAI*'s stakeholder-calibrated explanation depth [12]; the EU AI Act's high-risk-system explainability requirements as regulatory motivation [13].

**Closing paragraph of Related Work — the gap statement (can reuse near-verbatim from `FINAL_RESEARCH_REPORT.md` Section 2):** "SCAA asks a fourth, different question: independent of whether an outcome turns out well or badly, and independent of whether a decision is statistically unusual, is this decision consequential enough — by irreversibility and impact — that a human auditor should see a causal explanation of it, before any failure has occurred?"

---

## 3. System Architecture

**[EXPAND — 2–3 paragraphs of prose, then Figure 1 = your pipeline diagram.]**

Describe the five-stage pipeline in prose:

> The system operates as a five-stage pipeline (Figure 1). An **agent** — any policy implementing a common decision interface — acts within a discrete-event **environment**. Every decision is recorded by a **trace capture** layer into a structured, JSON-serializable record containing the chosen action, all alternatives considered, and the environment state at decision time. A **drop/hold-out attribution engine** then estimates each decision's counterfactual influence on the trajectory's final outcome by replaying the simulation with the runner-up alternative substituted at each step in turn. The **severity gate** — this paper's central contribution — combines three consequence-based criteria into a single interpretable score and decides which decisions warrant explanation. Finally, a deliberately minimal **narration layer** converts gated decisions into plain-language audit text.

**Point not to miss:** state explicitly that the pipeline is agent-agnostic *by construction*, not merely by design intent — demonstrated empirically in Section 6.3 by running the identical downstream pipeline against two structurally different agent policies with zero code changes.

**Point not to miss:** be explicit that the attribution engine (Section 3, stage 3) is **not** the paper's novel contribution — it is infrastructure, adapted from the same technical family as prior drop/hold-out and context-ablation attribution methods [4], used here to construct one of the paper's baselines and to supply the Deviation calibration signal.

---

## 4. Method: The Severity Gate

**[This section can be adapted heavily from `severity.py`'s docstring and `PHASE_1_REPORT.md` Section 5 / `PHASE_2_REPORT.md` Action Item 1 — that text was written to become this section. Do not just paste it though; convert code-comment register into paper register.]**

### 4.1 Formulation

The severity score for decision step *i* is a weighted sum:

$$S_i = w_I \cdot I_i + w_F \cdot F_i + w_D \cdot D_i, \qquad w_I + w_F + w_D = 1, \qquad S_i \in [0,1]$$

A decision is flagged explanation-worthy under one of two gating modes:
- **Absolute mode**: $S_i \geq \tau$ for a fixed, pre-committed threshold $\tau$.
- **Percentile mode**: $S_i$ is among the top $p\%$ of scores within the trajectory (an order-statistic threshold).

### 4.2 Why a linear weighted sum

State the Weighted Sum Model (WSM / Simple Additive Weighting) justification explicitly, citing Fishburn (1967) [16] and Triantaphyllou (2000) [17]:
1. **Auditability** — each criterion's contribution to the flag decision is readable directly from its weight.
2. **Monotonicity** — WSM guarantees a strictly more irreversible (or impactful, or deviant) decision is never scored as less severe, a property a nonlinear aggregator cannot generally guarantee and that a safety auditor would reasonably require.
3. **Deliberate compensability** — WSM's well-known weakness (a low score on one criterion can be offset by a high score on another) is explicitly *desired* here: an extremely high-impact decision should be flagged even if trivially reversible, and vice versa.

### 4.3 Irreversibility (I) — rule-based

Define the action-type base rates and the duration-scaling correction (Section 5 of `PHASE_1_REPORT.md`). **Point not to miss:** include the iterative-validation story — an early flat-constant formulation caused I to collapse to a near-constant value for the majority action type, degenerately flagging ~93% of decisions; scaling by committed duration restored meaningful spread. This is good methods-section material demonstrating empirical validation, not just an armchair formula.

### 4.4 Impact / Safety (F) — rule-based, task-defined

Present the priority + deadline-proximity formula, and state explicitly that F is intentionally domain-specific — a different deployment (e.g., drone mission planning, industrial process control) would substitute a different F while the gating *mechanism* remains unchanged. This distinction (domain-agnostic mechanism vs. domain-specific instantiation) is worth a full sentence, since reviewers will ask whether the contribution generalizes.

### 4.5 Deviation (D) — statistical, calibrated

Present the z-scored confidence-gap formulation and the sigmoid mapping. Justify the sigmoid choice: the standard smooth, monotonic, rank-preserving map from an unbounded statistic onto [0,1], the same justification used for calibrated probability outputs in logistic regression. Note the calibration procedure (multi-seed reference distribution of confidence gaps) and its conceptual relationship to drift-detection methods [6,7,8] — but state clearly that D is consumed here as *one gate input*, not a standalone anomaly verdict, which is part of the paper's reframing argument.

### 4.6 Threshold and weight sensitivity — reported as intervals, not point estimates

Cite Triantaphyllou & Sánchez (1997) [18] and, if verified, O'Shea et al. (2025) [19, **VERIFY**] for the weight-stability-interval concept. State the paper's position plainly: rather than defending a single threshold value, Section 7.4 reports the empirical stability and sensitivity of the gate's output to both threshold and weight choices.

---

## 5. Experimental Setup

### 5.1 Task environment

Describe the industrial/IoT scheduling environment: machines, jobs (priority, deadline, duration), action space (assign / defer / reject / reassign), and the irreversibility semantics of committing a job to a machine. **Point not to miss:** state the determinism guarantee explicitly — the job arrival schedule is generated independently of agent actions, which is the property that makes counterfactual replay in Section 3 valid (a common validity threat for counterfactual methods that a reviewer may probe).

### 5.2 Scenarios

Present the three scenarios as a table:

| Scenario | Machines | Jobs | Arrival rate | Priority skew | Deadline tightness | Designed to stress |
|---|---|---|---|---|---|---|
| Balanced | 4 | 25 | 0.4 | uniform (1–3) | moderate | reference case |
| High-contention | 2 | 25 | 0.55 | uniform (1–3) | moderate | Irreversibility (I) |
| Safety-critical | 4 | 25 | 0.4 | skewed toward 3 | tight | Impact (F) |

**Point not to miss:** state that these are parameterizations of one simulator rather than three independent environments, and justify this as a deliberate scope decision keeping the evaluation focused on the gate rather than on environment diversity — pre-empt the "why not three real domains" question directly rather than let a reviewer raise it first.

### 5.3 Agents

Two structurally different policies:
- **ScoringAgent**: a weighted-heuristic policy blending priority and deadline urgency.
- **GreedyEDFAgent**: a classic greedy earliest-deadline-first policy with no priority term at all.

State explicitly that both are deterministic, non-learned policies — a reproducibility choice, not an attempt to claim these represent realistic LLM-agent behavior (this caveat belongs here **and** in Limitations).

### 5.4 Baselines

Present as a table:

| Baseline | Selection rule | Represents |
|---|---|---|
| Explain-everything | All decisions | Naive upper-bound audit load |
| Attribution-top-k | Top-k by \|counterfactual influence\| | Who&When-style attribution-only selection [1] |
| Deviation-only-top-k | Top-k by D alone | TrajAD/SentinelAgent-style anomaly-only selection [6,8] |
| Random-k | Random k decisions | Sanity floor |
| Oracle-proxy-top-k | Top-k by I×duration | Upper-bound reference on the internal coverage proxy (see 6.2 caveat) |

All baselines are evaluated at **matched budget** (k = the SCAA gate's own flag count for that trajectory), so comparisons are of selection *quality*, not selection *size*.

### 5.5 Metrics

- **Audit load reduction** = $1 - k/n$.
- **Selection Diversity** = $1 - \text{Jaccard}(\text{gate selection}, \text{baseline selection})$ — 0 means identical selections (no added value), 1 means fully disjoint.
- **Critical decision coverage** — fraction of the top quartile by I×duration (an internal proxy for "high-stakes decision," see 6.2 caveat) captured by a given selection.
- **Statistical tests** — paired t-test and Wilcoxon signed-rank test across seeds, since seeds pair naturally (same seed → same trajectory for every method).

---

## 6. Results

### 6.1 Selection Diversity — is the gate just relabeling attribution?

Report: Jaccard(gate, attribution-top-k) = 0.2 → Selection Diversity = 0.8 on the reference trajectory. **State plainly what this number is and isn't**: it demonstrates the gate is not a relabeling of attribution magnitude on this trajectory; it is a single-trajectory sanity check, with the scenario-level coverage results below providing the multi-seed evidence.

### 6.2 Critical decision coverage across scenarios

| Scenario | SCAA Gate | Attribution | Deviation-only | Random |
|---|---|---|---|---|
| Balanced | **0.791 ± 0.158** | 0.533 ± 0.181 | 0.598 ± 0.197 | 0.443 ± 0.183 |
| High-contention | **0.869 ± 0.098** | 0.286 ± 0.115 | 0.421 ± 0.129 | 0.413 ± 0.140 |
| Safety-critical | **1.000 ± 0.000** | 0.871 ± 0.150 | 0.846 ± 0.141 | 0.775 ± 0.133 |

*n = 20 seeds per scenario, mean ± std.*

**Statistical significance** (balanced scenario, paired across seeds):

| Comparison | Paired t-test | Wilcoxon |
|---|---|---|
| Gate vs. Attribution | t = 4.54, **p = 0.00023** | **p = 0.00117** |
| Gate vs. Deviation-only | t = 3.21, **p = 0.0046** | **p = 0.0101** |
| Gate vs. Random | t = 8.72, **p < 0.00001** | **p = 0.00028** |

**Caveat that MUST appear directly under this table, not deferred to a limitations section paragraphs later:** the critical-decision-coverage metric is defined using I×duration — the same quantity the severity gate itself weights. This makes the metric an internally consistent proxy rather than independent ground truth. Present these results as internal-consistency evidence and explicitly point the reader to the (pending/completed) human study in 6.5 as the independent validation.

### 6.3 Cross-agent generalization

| Metric | ScoringAgent | GreedyEDFAgent |
|---|---|---|
| Audit load reduction | 51.6% ± 7.8% | 72.3% ± 4.0% |
| Critical coverage (gate) | 0.800 ± 0.151 | 0.708 ± 0.099 |
| Critical coverage (attribution) | 0.562 | 0.314 |

*n = 10 seeds, balanced scenario.* The gate outperforms the attribution baseline on both structurally different policies, evidence against the concern that the gate's advantage is an artifact of one agent's particular score distribution.

### 6.4 Sensitivity and robustness

- **Input-noise robustness**: Gaussian jitter (σ = 1.5 ticks) applied to job deadlines, severity ranking recomputed, Spearman correlation to the unperturbed ranking = **0.991 ± 0.009** (n = 20 trials). This is the strongest and most reviewer-convincing robustness result — lead with it.
- **Random weight sensitivity**: 50 weight triples sampled uniformly from the simplex; Jaccard-vs-default selection = 0.473 ± 0.152. Report honestly as moderate, not perfect, stability — this is a harder stress test than axis-aligned perturbation and a moderate result here is expected, not alarming.
- **Runtime scaling**: empirically **O(n^1.95)** in trajectory length (log-log regression, n_jobs = 10–200) — approximately quadratic. **Do not claim linear scaling**; this is a genuine feasibility limitation for long trajectories, driven by attribution replay cost, and belongs explicitly in Section 8.

### 6.5 Human study

**[FILL IN ONCE COLLECTED.]** Report protocol (n = 3 raters, Latin-square rotated across 3 scenarios × 2 conditions, 18 sessions; separately, a blind Yes/No selection-agreement protocol on one trajectory), then: per-rater agreement with SCAA gate vs. attribution-top-k vs. random-k; 3-rater consensus rate; audit-quiz accuracy and completion time under the SCAA-gated condition vs. the explain-everything condition (this is your Information Compression / Explanation Efficiency result if the numbers support it — compute $EE = \text{quiz accuracy} / \text{number of explanations shown}$ per condition and report the ratio). **State the sample size honestly in the same sentence as any result from this section**: "a pilot inter-rater study (n=3)," not "a user study validated our approach."

---

## 7. Ablation Study

| Variant | Critical coverage | Δ vs. full gate |
|---|---|---|
| Full gate (I+F+D) | 0.429 | — |
| Irreversibility only | 1.000 | +0.571 |
| Impact only | 0.429 | 0.000 |
| Deviation only | 0.571 | +0.143 |
| Without irreversibility (F+D) | 0.143 | **−0.286** |
| Without impact (I+D) | 0.714 | +0.286 |
| Without deviation (I+F) | 0.429 | 0.000 |

**Critical framing point, must not be omitted or the ablation becomes misleading:** because the coverage metric is defined using I, single-component and pairwise variants that *include* I are mechanically advantaged on this specific metric — "Irreversibility only" scoring a perfect 1.000 should **not** be reported as "I alone is sufficient." The methodologically sound reading of this table is the **removal** direction: "Without irreversibility" produces the single largest coverage drop (−0.286) among the three "without-X" variants, which is legitimate (non-circular in that direction) evidence that I contributes real, non-redundant signal to the gate.

---

## 8. Threats to Validity

Write this as a numbered list in the paper, not folded into prose — reviewers scan for this section specifically:

1. **Simulated, not real-world, environment.** External validity to deployed industrial/IoT scheduling agents is untested.
2. **Human study is a pilot (n=3), not a powered validation study.**
3. **F (impact) is domain-specific**, though the gating mechanism itself is domain-agnostic by design.
4. **Attribution assumes a deterministic, replayable environment**; does not transfer directly to non-deterministic or non-replayable real systems without modification.
5. **The critical-decision-coverage metric is partially circular** with respect to I (Section 6.2, 7).
6. **Runtime scales approximately quadratically**, not linearly, with trajectory length.
7. **Threshold stability was evaluated on a single short trajectory** and found unstable at fine (0.01) granularity — a small-sample artifact, not evidence of gate fragility; the random-weight and noise-robustness results are the more meaningful stability evidence.
8. **No cross-domain validation** — one task family (scheduling) only; explicitly deferred as future work given project scope.
9. **Cross-agent validation used two heuristic, non-learned policies**, not an LLM-driven agent — generalization to LLM agents is untested and is arguably the single most important open question for this line of work.

---

## 9. Limitations and Future Work

Draw from Section 8 plus:
- **Failure case**: in the safety-critical scenario, audit-load reduction shrinks toward zero (20.0% vs. 51–64% elsewhere) because most decisions genuinely are high-stakes there — state this as expected, correct gate behavior in a degenerate case, not a bug, but note that `gate_mode="percentile"` rather than the absolute threshold should be used in such regimes to preserve selectivity.
- **Future work**: validate against an actual LLM-driven agent; extend to a second domain; scale the human study beyond a pilot; address the quadratic attribution-replay cost (e.g., incremental/cached replay); replace the internal coverage proxy with an externally-labeled ground truth.

---

## 10. Conclusion

**[EXPAND — 1 paragraph.]** Restate the contribution (a consequence-based, prospective severity gate, distinct from failure attribution and anomaly detection), the strongest evidence (statistically significant coverage advantage across scenarios and two agent policies, high robustness to input noise), and end on the honest note that the largest remaining validation gap — real LLM agents and a fully powered human study — is squarely future work, not a hidden flaw.

---

## References

*(Format to your target venue's citation style; IEEE numeric used here as a placeholder.)*

[1] Zhang, S. et al. "Which Agent Causes Task Failures and When? On Automated Failure Attribution of LLM Multi-Agent Systems." *ICML 2025 (Spotlight)*.

[2] "Automatic Failure Attribution and Critical Step Prediction Method for Multi-Agent Systems." arXiv:2509.08682. **[VERIFY]**

[3] "Where LLM Agents Fail and How They Can Learn from Failures" (AgentDebug / AgentErrorTaxonomy). arXiv:2503.xxxxx. **[VERIFY exact ID]**

[4] "The Why Behind the Action: Unveiling Internal Drivers via Agentic Attribution." arXiv:2601.15075. **[VERIFY]**

[5] "Intention-Behavior Consistency-Based Automated Failure Attribution for LLM-Driven Multi-Agent Systems." *ScienceDirect*, 2026. **[VERIFY]**

[6] "TrajAD: Trajectory Anomaly Detection for Trustworthy LLM Agents." arXiv:2602.06443. **[VERIFY]**

[7] "Trajectory Guard: A Lightweight, Sequence-Aware Model for Real-Time Anomaly Detection in Agentic AI." arXiv:2601.00516. **[VERIFY]**

[8] He, X. et al. "SentinelAgent: Graph-based Anomaly Detection in Multi-Agent Systems." arXiv:2505.24201. **[VERIFY]**

[9] "Detecting Silent Failures in Multi-Agentic AI Trajectories." arXiv:2511.04032. **[VERIFY]**

[10] Souza, R. et al. "PROV-AGENT: Unified Provenance for Tracking AI Agent Interactions in Agentic Workflows." *IEEE e-Science 2025*.

[11] Rudin, C. "Stop Explaining Black Box Machine Learning Models for High Stakes Decisions and Use Interpretable Models Instead." *Nature Machine Intelligence*, 2019.

[12] "Beyond Technocratic XAI: The Who, What & How in Explanation Design." arXiv:2508.09231. **[VERIFY]**

[13] "Bridging the Transparency Gap: What Can Explainable AI Learn From the AI Act?" arXiv. **[VERIFY exact ID]**

[14] Lundberg, S. & Lee, S-I. "A Unified Approach to Interpreting Model Predictions." *NeurIPS 2017*.

[15] Ribeiro, M.T., Singh, S., Guestrin, C. "'Why Should I Trust You?': Explaining the Predictions of Any Classifier." *KDD 2016*.

[16] Fishburn, P.C. "Additive Utilities with Incomplete Product Set." *Operations Research*, 1967.

[17] Triantaphyllou, E. *Multi-Criteria Decision Making: A Comparative Study*. Kluwer Academic Publishers, 2000.

[18] Triantaphyllou, E. & Sánchez, A. "A Sensitivity Analysis Approach for Some Deterministic Multi-Criteria Decision-Making Methods." *Decision Sciences*, 1997.

[19] O'Shea et al. "Weight stability intervals for multi-criteria decision analysis using the weighted sum model." *Expert Systems With Applications*, 2025. **[VERIFY — this citation was surfaced via search and is the least certain of the list; confirm it exists with this exact title/venue before use, or drop it and lean on [18] alone.]**

---

## Checklist before you submit — do not skip any of these

- [ ] Every `[bracketed placeholder]` above is filled in or deliberately removed.
- [ ] Every `[VERIFY]` reference has been checked against the live paper (title, authors, venue, year all match).
- [ ] Human study results (Section 6.5) are either filled in with real data or the section is honestly reframed as future work if you run out of time — never leave it silently blank.
- [ ] Every number in Sections 6–7 matches your latest `outputs/evaluation/phase3_results.json` — if you reran the evaluation after this draft was written, regenerate the numbers.
- [ ] The Abstract is written last and matches the final Results section, not this draft's placeholder text.
- [ ] Author names, affiliation, and acknowledgments are added.
- [ ] Figures referenced in the text (pipeline diagram, scenario comparison, ablation) are actually inserted, not just described.
- [ ] Formatted to your target venue's template (margins, citation style, page limit).
