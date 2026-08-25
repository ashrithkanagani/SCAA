# Run, Test, and Visualize — Setup Guide

Everything below runs locally, offline, with no API keys required (narration defaults to a deterministic template; the optional Groq narrator only activates if you set `GROQ_API_KEY` yourself).

---

## 0. One-time setup

```bash
# from the project root (the folder containing scaa/, tests/, reports/)
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` contains: `numpy`, `scipy`, `pytest`, `matplotlib`. That's the entire dependency footprint — no LangGraph, no Groq SDK required unless you opt into the optional LLM narrator.

---

## 1. To-do checklist (do these in order)

- [ ] **Step 1** — Run the test suite (2-3 seconds, confirms your environment is set up correctly)
- [ ] **Step 2** — Run the single reference pipeline (confirms the core flow works end-to-end)
- [ ] **Step 3** — Run the full reproduction script (~9 seconds, generates every automatic result and figure)
- [ ] **Step 4** — Look at the generated figures
- [ ] **Step 5** — Distribute the human-study files to your 2 teammates
- [ ] **Step 6** — Once they're done, score the results
- [ ] **Step 7** (optional) — Try the Groq narrator with your own API key

---

## Step 1 — Run the test suite

```bash
python3 -m pytest tests/ -v
```

Expected: `44 passed` in under 3 seconds. If anything fails, stop here and check your Python version (`python3 --version` — this was built and tested on 3.12, should work on any 3.9+).

---

## Step 2 — Run the reference pipeline

```bash
python3 -m scaa.pipeline
```

This runs one full scenario end-to-end and prints a 6-step log ending in something like `9/27 steps (33.3%) flagged explanation-worthy`. Outputs land in `outputs/`:
- `outputs/trajectory.json` — every decision, fully annotated (severity scores, narration, attribution)
- `outputs/summary.json` — the run's headline numbers
- `outputs/figures/*.png` — 5 figures (severity timeline, I/F/D breakdown, threshold sweep, machine Gantt chart, baseline comparison)

---

## Step 3 — Run the full reproduction (this is the big one)

```bash
python3 -m scaa.reproduce
```

Runs, in order: the reference pipeline (Step 2 again), the full Phase 3 evaluation (3 scenarios x 20 seeds, statistical significance tests, sensitivity/ablation/robustness/cross-agent/runtime experiments), Phase 3 figures, and the blank human-study templates. Takes about 9 seconds total. This is the single command that reproduces every automatic number in `FINAL_RESEARCH_REPORT.md` and `PHASE_3_REPORT.md`.

New outputs after this step:
- `outputs/evaluation/phase3_results.json` — every multi-seed/sensitivity/ablation/cross-agent/runtime number
- `outputs/evaluation/figures/*.png` — 3 more figures (scenario coverage comparison, audit load reduction, ablation)
- `reports/human_study/` — blank templates (see Step 5)

**To change the number of seeds** (e.g. for a quicker check or a more thorough run):
```python
from scaa.evaluation import run_full_evaluation
run_full_evaluation(n_seeds=5)   # faster, less statistical power
run_full_evaluation(n_seeds=50)  # slower (~20s), tighter confidence intervals
```

---

## Step 4 — Look at the figures

Open these directly (any image viewer, or drag into your paper draft to check they render at a reasonable size):

| File | What it shows |
|---|---|
| `outputs/figures/severity_timeline.png` | S(t) per decision, red = flagged — the clearest single "selectivity" figure |
| `outputs/figures/ifd_breakdown.png` | I/F/D stacked per flagged decision |
| `outputs/figures/threshold_sweep.png` | Gate rate vs. threshold, single trajectory |
| `outputs/figures/machine_gantt.png` | Makes the scheduling scenario itself legible |
| `outputs/figures/baseline_comparison.png` | Narration budget across all 6 strategies |
| `outputs/evaluation/figures/scenario_coverage_comparison.png` | The main multi-seed results figure — use this as your Results section's Figure 1 |
| `outputs/evaluation/figures/audit_load_reduction.png` | Per-scenario audit-load reduction bars |
| `outputs/evaluation/figures/ablation.png` | Component-contribution ablation (remember the circularity caveat when captioning this one — see `FINAL_RESEARCH_REPORT.md` Section 8) |

---

## Step 5 — Distribute the human-study files

After Step 3, you have:
- `reports/human_study/selection_agreement_blank.csv` — **make 3 copies** (`rater1.csv`, `rater2.csv`, `rater3.csv`), send one to each teammate. Each fills in the last column (`Yes`/`No`) independently, without seeing the others' answers or any severity scores.
- `reports/human_study/quiz_sessions/*.txt` — 9 files, pre-assigned per rater (filenames start with `rater_1__`, `rater_2__`, `rater_3__`). Each teammate reads their 3 files and fills in the quiz answers + timer at the bottom of each.
- `reports/human_study/quiz_sessions/answer_keys/` — **do not send these to raters.** Keep for your own grading in Step 6.

Full protocol/rationale if anyone asks why the study is designed this way: `EVALUATION_PLAN.md` Section 3, and the Latin-square explanation at the top of `scaa/human_study.py`.

---

## Step 6 — Score the results

**Selection agreement** (fully automated once the 3 CSVs are filled in):
```python
from scaa.human_study import generate_selection_agreement_csv, score_selection_agreement

# regenerate the SAME trajectory the CSVs were built from (same scenario/seed = same trajectory)
traj = generate_selection_agreement_csv(scenario_name="balanced", output_path="/tmp/unused.csv")

result = score_selection_agreement(traj, [
    "reports/human_study/rater1_filled.csv",
    "reports/human_study/rater2_filled.csv",
    "reports/human_study/rater3_filled.csv",
])
print(result)
```
This prints each rater's agreement rate with the SCAA gate, attribution-top-k, and random-k, plus the 3-rater consensus rate. These numbers go directly into `FINAL_RESEARCH_REPORT.md` Section 7.

**Quiz grading** (manual — needs a human to judge free-text answers against the key):
1. Open each `reports/human_study/quiz_sessions/rater_N__scenario__condition.txt`.
2. Compare the rater's 5 answers against the matching file in `answer_keys/`.
3. Score each answer correct/incorrect (a reasonable bar: did they name the right driving factor — irreversibility, impact, or deviation — and the right alternative action?).
4. Record: quiz accuracy (X/5) and total time, per session.
5. Average across the 3 "SCAA condition" sessions and the 3 "explain-everything condition" sessions per rater, then across raters, for the compression/efficiency numbers in Section 6 of the final report.

Budget about 20-30 minutes total for grading 9 sessions.

---

## Step 7 (optional) — Try the Groq narrator

Only if you want LLM-generated narration instead of the default deterministic template (not required for any result in the paper — see `PHASE_2_REPORT.md` Action Item 4 for why the template is the primary narrator):

```bash
pip install groq
export GROQ_API_KEY="your-key-here"
python3 -m scaa.pipeline
```

The pipeline auto-detects the key and switches narrators; everything else is unchanged. If the key is invalid or missing, it silently falls back to the template narrator (tested, see `tests/test_narration.py::test_groq_narrator_falls_back_without_api_key`).

---

## Troubleshooting

- **`ModuleNotFoundError: No module named 'scaa'`** — run commands from the project root (the folder containing `scaa/`, not from inside `scaa/`), or use `python3 -m scaa.pipeline` (module syntax) rather than `python3 scaa/pipeline.py`.
- **`pip install` fails on a managed system** — add `--break-system-packages` to the pip command, or just use the venv from Step 0.
- **Different numbers than the report** — expected for anything using randomness beyond the fixed seeds (e.g. if you change `n_seeds`); the reference pipeline (Step 2) and the seeded scenarios in `scenarios.py` are fully deterministic and should always reproduce exactly.
- **Figures look empty/blank** — matplotlib uses the headless `Agg` backend by design (no display needed); this doesn't affect file output, only interactive display, which isn't used anywhere in this project.
