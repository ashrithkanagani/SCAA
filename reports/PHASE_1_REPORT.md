# Phase 1 Report — Core Infrastructure

**Project:** SCAA (Selective Causal Auditing for Agentic Systems)
**Phase:** 1 of 3 — Agent + Trace Capture + Attribution Engine + Severity Gate
**Status:** Complete. 18/18 unit tests passing.

---

## 1. What was built

A fully working, dependency-light Python pipeline that:

1. Simulates a deterministic **industrial/IoT scheduling agent** (jobs competing for limited machines, with irreversible commitment once a job is dispatched).
2. Captures a **complete decision trace** for every choice the agent makes.
3. Runs **drop/hold-out counterfactual attribution** over every step to measure how much each decision influenced the final outcome.
4. Applies the **severity gate** — the project's core novel contribution — which combines Irreversibility (I), Impact (F), and Deviation (D) into a single score S, and flags which decisions are "explanation-worthy."

No LLM calls are made anywhere in Phase 1. This is intentional: the attribution engine needs to replay the simulation many times (once per decision step, per counterfactual), and a deterministic scoring-policy agent makes those replays exact, fast, and free to run — critical for the ablation studies planned in Phase 3. The LLM only enters in Phase 2, purely as a narration layer sitting *on top of* the already-decided severity scores; it does not participate in decision-making or scoring.

---

## 2. Module-by-module summary

| Module | Purpose | Key exports |
|---|---|---|
| `config.py` | All tunable parameters in one place | `EnvironmentConfig`, `SeverityWeights`, `AttributionConfig`, `PipelineConfig` |
| `environment.py` | Deterministic discrete-event scheduling simulator | `SchedulingEnvironment`, `Job`, `Machine`, `JobStatus`, `EnvState` |
| `agent.py` | Transparent weighted-scoring decision policy | `ScoringAgent`, `Decision`, `Candidate` |
| `trace.py` | Data schema shared by every downstream module | `DecisionStep`, `Trajectory` |
| `simulate.py` | Shared run loop for real + counterfactual runs | `run_trajectory()` |
| `attribution.py` | Drop/hold-out counterfactual influence scoring | `compute_attribution()`, `parse_action_from_label()` |
| `severity.py` | **The novel severity gate** | `compute_irreversibility()`, `compute_impact()`, `compute_deviation()`, `calibrate_deviation()`, `apply_severity_gate()` |
| `pipeline.py` | End-to-end orchestration | `run_pipeline()` |

---

## 3. The scenario (industrial/IoT scheduling)

- A fleet of `n_machines` (default 4) must process a stream of `n_jobs` (default 25) arriving stochastically over `sim_horizon` ticks (default 60).
- Each job has a **priority** (1–3, where 3 represents something like a safety-interlock or critical-path job), a **deadline**, and a **processing duration**.
- The agent's available actions per decision: `assign` (commit a job to a free machine — irreversible in the sense that undoing it costs a penalty), `defer` (revisit next tick — fully reversible), `reject` (permanently drop the job), `reassign` (undo a prior commitment — penalized).
- **Why this scenario satisfies the CPS-justifiability requirement:** it is a safety/resource-constrained sequential decision problem with real irreversibility semantics, which is the CPS framing agreed on earlier (CPS-as-lens, not CPS-as-hardware).
- **Determinism guarantee:** the full job arrival schedule is pre-generated from the seed *before* any agent action is taken, and is provably independent of the agent's choices (see `test_job_schedule_independent_of_agent_actions` in `tests/test_environment.py`). This is what makes counterfactual replay in `attribution.py` valid — replaying with a different action at step *i* can only change what happens to machines and jobs *after* step *i*, never what jobs arrive.

---

## 4. Attribution engine — method actually implemented

For each decision step *i*:
1. Take the agent's **runner-up candidate action** at step *i* (the second-highest-scored alternative it considered but didn't take).
2. Replay the simulation from scratch, identical to the real run at every step *except* step *i*, where the runner-up action is forced instead.
3. From step *i*+1 onward, the agent resumes normal decision-making against the now-different (branched) environment state.
4. Compare the final outcome metric (default: cumulative SLA penalty) between the real run and the counterfactual run.
5. `influence(i) = sign(metric) × (counterfactual_outcome − original_outcome)`, where the sign flips depending on whether the metric is "lower is better" (SLA penalty) or "higher is better" (completed jobs) — so `influence > 0` always means "the agent's actual choice was better than the alternative."

This is a **policy-intervention counterfactual**, not a static single-prediction hold-out — sequential decisions require this because the environment branches after the intervention point. This is the same technical family as the drop/hold-out sentence-ablation approach in *"The Why Behind the Action"* and conceptually adjacent to the ICML 2025 Who&When failure-attribution benchmark, adapted here to a resource-scheduling MDP rather than a single-turn LLM context window. **This attribution mechanism is explicitly not the paper's novel contribution** — it is documented in detail here because Phase 3's evaluation will benchmark the severity gate's selections against this attribution signal as one baseline.

`AttributionConfig.n_counterfactuals` is exposed for future extension (averaging over more than one alternative candidate); Phase 1 uses `n_counterfactuals=1` (runner-up only) for tractable runtime.

---

## 5. The severity gate — core novel module, concrete formulation

```
S = w_irrev · I  +  w_impact · F  +  w_deviation · D
```

Weights are normalized to sum to 1 (`SeverityWeights.normalized()`), so `S ∈ [0, 1]` and `gate_threshold` is directly interpretable as a fraction of maximum possible severity. A decision is flagged `explanation_worthy = True` iff `S ≥ gate_threshold`.

### I — Irreversibility (rule-based, transparent)
```python
_IRREVERSIBILITY_BASE = {"assign": 0.55, "reassign": 0.7, "reject": 0.6, "defer": 0.1}
# for assign/reassign, scaled further by how long the commitment holds a machine:
I = base + 0.45 * min(1.0, duration / max_duration)   # for assign/reassign
I = base                                                # for reject/defer
```
Deliberately rule-based and fully auditable — a CPS reviewer can read this table directly and verify it against the task's actual physical constraints. Scaling by committed duration (rather than a flat per-action-type constant) was an empirical correction made during Phase 1 testing: an earlier flat-constant version caused I to collapse to a near-constant 0.9 whenever the agent chose to assign (the majority action), which made the gate degenerate toward flagging almost everything. Scaling by duration restored meaningful spread (see Section 7).

### F — Impact / Safety (rule-based, task-defined cost function)
```python
F = clip(0.6 * (priority / max_priority) + 0.4 * (1 / (1 + max(0, deadline - tick))), 0, 1)
```
This is the "business/safety cost function" a deploying organization defines for its own domain; here it's instantiated as priority + deadline-proximity for scheduling. In a different CPS deployment (e.g. drone mission planning, industrial process control) this function would be swapped for a domain-specific one — the *severity-gate mechanism* is domain-agnostic even though this particular F is not.

### D — Deviation (statistical, calibrated — this is the algorithmic, non-rule-based component)
```python
gap = chosen_score - runner_up_score
z = (gap - mean_gap) / std_gap             # calibrated from 15 independent seeded runs
D = 1 - sigmoid(z)
```
`mean_gap` and `std_gap` are computed once per scenario by `calibrate_deviation()`, which runs the agent across 15 independent seeds and collects the distribution of confidence gaps (chosen score minus runner-up score) it typically produces. A decision with an unusually small gap — a "close call" relative to the agent's own typical behavior — scores high on D. This is deliberately the same statistical family as drift-detection signals (TrajAD, Trajectory Guard) but is consumed here as **one input to a gate**, not as a standalone anomaly output — that reframing (severity input, not verdict) is part of the paper's novelty argument.

---

## 6. Data schema (what Phase 2 will consume)

Every decision is a `DecisionStep` (see `trace.py`), fully JSON-serializable. Fields Phase 2's narration layer needs are:

| Field | Type | Meaning |
|---|---|---|
| `step_id`, `tick`, `job_id` | int | identifiers |
| `job_priority`, `job_deadline`, `job_duration` | int | task context for narration |
| `n_pending_jobs`, `n_free_machines` | int | environment context at decision time |
| `candidate_labels`, `candidate_scores` | list | all options the agent considered |
| `chosen_label`, `chosen_action` | str, dict | what it did |
| `runner_up_label`, `runner_up_action` | str, dict | the road not taken (needed for "why not X" narration) |
| `is_commit` | bool | whether this was an irreversible-type action |
| `influence_score` | float | from attribution.py |
| `severity_components` | dict `{I, F, D}` | the three gate inputs, for transparent narration ("flagged because irreversibility was high") |
| `severity_score` | float `[0,1]` | S |
| **`explanation_worthy`** | bool | **the gate decision — Phase 2 only narrates steps where this is True** |
| `narration` | str, currently `None` | Phase 2 fills this in |

A full `Trajectory` is `{final_outcome: {...}, steps: [DecisionStep, ...]}`. Load via `Trajectory.load_json("outputs/trajectory.json")`.

---

## 7. Validation performed this phase

- **18/18 unit tests passing** (`tests/test_environment.py`, `test_agent.py`, `test_attribution.py`, `test_severity.py`), covering: schedule determinism, schedule-independence-from-actions (the critical counterfactual-validity invariant), no double-booking of machines, bounds-checking on I/F/D, and — importantly — a non-degeneracy test (`test_gate_is_selective_not_trivial`) asserting the gate doesn't collapse to flagging 0% or 100% of decisions.
- **Bug found and fixed during this phase:** the original job-completion detection logic in `environment.py::advance_tick()` had an off-by-one condition that never triggered, so no job was ever marked complete (0 completions in every run). Fixed and now verified against completion counts summing correctly with `n_completed = n_late + n_on_time`.
- **Calibration correction:** the initial severity gate flagged 92.6% of decisions as explanation-worthy on the default scenario — not a bug, but an empirically poor default (I was collapsing to a near-constant for the majority action type). Fixed by making I scale with committed job duration; default `gate_threshold` retuned from 0.55 to 0.62 based on the resulting score distribution.
- **Cross-seed robustness check** (5 seeds, default config): gate rate ranged from 33.3% to 68.4% (mean ~51%) — confirms the gate is genuinely selective and scenario-sensitive rather than a fixed pass-through, and gives an honest sense of variance for Phase 3's evaluation section rather than a single cherry-picked number.

---

## 8. Open parameters (Phase 3's ablation study surface)

All exposed in `config.py`, none hard-coded elsewhere:

- `SeverityWeights.w_irrev / w_impact / w_deviation` — relative weighting of the three gate inputs.
- `SeverityWeights.gate_threshold` — currently 0.62; the full sweep (0.5–0.7) already shows gate rate moving from 85% down to 4%, so this is a rich ablation axis.
- `AttributionConfig.n_counterfactuals` — currently 1 (runner-up only); could be extended to average over more alternatives.
- `EnvironmentConfig` — machine count, job count, arrival rate, penalty weights — useful for testing generalization across scenario difficulty.

---

## 9. What Phase 2 needs to do

1. Take `Trajectory.load_json(...)`, filter to `step.explanation_worthy == True`.
2. For each flagged step, call the narration LLM (Groq, consistent with your existing stack) with the step's context (`job_priority`, `candidate_labels/scores`, `chosen` vs `runner_up`, `severity_components`) and produce a plain-language audit sentence — e.g. *"Assigned Job 14 (priority: critical) to Machine 2 over deferring, because its deadline was imminent (Impact: high) and committing the machine for 5 ticks was hard to undo (Irreversibility: high)."*
3. Implement the **two baselines** required for the paper's evaluation section: (a) explain-everything (narrate every step, no gate), (b) attribution-only top-k (narrate only the top-k steps by `influence_score`, ignoring I/F/D) — so Phase 3 can compare SCAA's selection against both.
4. Write `step.narration` back into the trajectory and re-save.

---

**Files delivered this phase:** full `scaa/` package (8 modules), `tests/` (4 files, 18 tests), `config.py` defaults tuned and documented, `outputs/trajectory.json` + `outputs/summary.json` from a reference run, `README.md`.
