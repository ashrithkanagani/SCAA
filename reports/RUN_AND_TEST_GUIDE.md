# Run, Test, and Visualize — Setup Guide (Updated: Phase 4, all 4 domains)

Everything below runs locally, offline, in under 30 seconds total, with no API keys required.

---

## 0. One-time setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt`: `numpy`, `scipy`, `pytest`, `matplotlib`. That's it. The dashboard needs nothing installed locally (it's one HTML file; its one chart library loads from a CDN at runtime). Real benchmark data (`data/taillard/*.txt`) ships bundled — no download needed.

---

## 1. To-do checklist

- [ ] Step 1 — Run the test suite (64 tests, ~4 seconds)
- [ ] Step 2 — Run the full reproduction (~20-30 seconds: all 4 domains, every automatic result, dashboard data, human-study templates)
- [ ] Step 3 — Open the dashboard and explore all 4 domains
- [ ] Step 4 — Look at the static figures
- [ ] Step 5 — Distribute the human-study files (now 12 sessions across 4 domains) to your 2 teammates
- [ ] Step 6 — Score the results once they're done
- [ ] Step 7 (optional) — Try the Groq narrator with your own API key

---

## Step 1 — Run the test suite

```bash
python3 -m pytest tests/ -v
```

Expected: `64 passed` in a few seconds — 48 from Domain 1 (Phases 1-3) + 16 new from Phase 4 (`tests/test_domains.py`: environment determinism, full-pipeline gate validity, honest narration, real-benchmark parsing, the literal-code-reuse regression test, and the human-study rotation-plan tests).

---

## Step 2 — Run the full reproduction

```bash
python3 -m scaa.reproduce
```

Six steps, ~20-30 seconds total:
1. Domain 1 reference pipeline → `outputs/trajectory.json`, `outputs/summary.json`, `outputs/figures/*.png` (5 figures)
2. Domain 1 full Phase 3 evaluation (3 scenarios × 20 seeds, significance tests, sensitivity, ablation, cross-agent) → `outputs/evaluation/phase3_results.json`
3. Phase 3 figures → `outputs/evaluation/figures/*.png` (3 more figures)
4. **New**: cross-domain evaluation (delivery: 15 seeds, cloud: 15 seeds, Taillard/JSSP: all 5 real bundled instances) → `outputs/evaluation/cross_domain_results.json`
5. **New**: dashboard data (one narrated sample trajectory per domain + all aggregate results above) → `dashboard/dashboard_data.json`
6. Human-study templates (blank, now spanning 4 domains: 12 quiz sessions + 4 selection-agreement CSVs) → `reports/human_study/`

To run pieces individually:
```python
from scaa.domains.cross_domain_evaluation import run_cross_domain_evaluation
run_cross_domain_evaluation(n_seeds=15)          # just the 3 new domains

from scaa.domains.dashboard_data import build_dashboard_data
build_dashboard_data()                            # just the dashboard JSON
```

---

## Step 3 — Open the dashboard

```bash
# no server needed -- just open the file directly
open dashboard/index.html          # macOS
xdg-open dashboard/index.html      # Linux
start dashboard/index.html         # Windows
```

Click the file picker at the top right and select `dashboard/dashboard_data.json` (generated in Step 2). You'll see tabs for all four domains. Each tab shows:
- KPI cards: decisions total, flagged, audit-load reduction
- This run's outcome metrics
- A gate-vs-baselines coverage chart (multi-run data, where available)
- **The explanation log** — defaults to "worthy explanations only" (exactly what an auditor would actually want to read); toggle to "show full trajectory" to see the complete decision-by-decision working underneath

If your browser blocks the file picker's local file read (rare, some strict browser security settings), serve it locally instead:
```bash
cd dashboard && python3 -m http.server 8000
# then open http://localhost:8000 -- dashboard_data.json auto-loads via fetch()
```

---

## Step 4 — Look at the static figures

| File | What it shows |
|---|---|
| `outputs/figures/severity_timeline.png` | S(t) per decision, red = flagged |
| `outputs/figures/ifd_breakdown.png` | I/F/D stacked per flagged decision |
| `outputs/figures/threshold_sweep.png` | Gate rate vs. threshold |
| `outputs/figures/machine_gantt.png` | Domain 1's scheduling scenario visualized |
| `outputs/figures/baseline_comparison.png` | Narration budget across all 6 strategies |
| `outputs/evaluation/figures/scenario_coverage_comparison.png` | Domain 1's 3-scenario multi-seed comparison |
| `outputs/evaluation/figures/audit_load_reduction.png` | Per-scenario audit-load reduction |
| `outputs/evaluation/figures/ablation.png` | Component-contribution ablation |

(Cross-domain comparisons are in the dashboard, Step 3, rather than as static PNGs — the dashboard's per-domain charts cover this.)

---

## Step 5 — Distribute the human-study files (now 4 domains)

After Step 2, you have:
- `reports/human_study/selection_agreement_<domain>_blank.csv` — **4 files** (scheduling, delivery, cloud, taillard_jssp). Make 3 copies of EACH (12 files total), one per teammate per domain. Each teammate fills in Yes/No independently, blind to severity scores.
- `reports/human_study/quiz_sessions/*.txt` — **12 files** now (was 9), filenames like `rater_1__delivery__scaa.txt`. Each teammate has 4 sessions (one per domain — see the rotation table below).
- `reports/human_study/quiz_sessions/answer_keys/` — **do not send to raters.**

**Rotation plan** (who sees which domain under which condition):

| Rater | Scheduling | Delivery | Cloud | Taillard/JSSP |
|---|---|---|---|---|
| rater_1 | SCAA-gated | SCAA-gated | explain-all | SCAA-gated |
| rater_2 | SCAA-gated | explain-all | SCAA-gated | SCAA-gated |
| rater_3 | explain-all | SCAA-gated | SCAA-gated | explain-all |

Every domain is seen under both conditions across the team. Each rater does 4 sessions total (~30-40 min), similar total time to the original 3-scenario plan despite covering more domains.

Full protocol rationale: `EVALUATION_PLAN.md` Section 3, extended in `PHASE_4_REPORT.md`.

---

## Step 6 — Score the results

**Selection agreement** (automated once CSVs are filled in), per domain:
```python
from scaa.human_study import DOMAIN_REGISTRY, score_selection_agreement

domain = "delivery"  # or scheduling / cloud / taillard_jssp
traj = DOMAIN_REGISTRY[domain]["build"]()   # rebuilds the SAME trajectory the CSVs were built from
result = score_selection_agreement(traj, [
    "reports/human_study/rater1_delivery_filled.csv",
    "reports/human_study/rater2_delivery_filled.csv",
    "reports/human_study/rater3_delivery_filled.csv",
])
print(result)
```
Repeat for each domain. Results feed `FINAL_RESEARCH_REPORT.md` Section 7.

**Quiz grading** (manual, ~25-30 min for all 12 sessions): compare each rater's free-text answers against `reports/human_study/quiz_sessions/answer_keys/`. A reasonable bar: did they name the right driving factor (or, for Taillard, correctly describe the SPT dispatching rationale) and the right alternative? Record accuracy (X/5) and time per session.

---

## Step 7 (optional) — Try the Groq narrator

```bash
pip install requests
export GROQ_API_KEY="your-key-here"
python3 -m scaa.pipeline
```
Auto-detected; falls back silently to the deterministic template narrator if the key is missing or the call fails (tested).

---

## Troubleshooting

- **`ModuleNotFoundError: No module named 'scaa'`** — run from the project root, or use `python3 -m scaa.<module>` syntax, not `python3 scaa/<module>.py`.
- **Dashboard shows "no data loaded"** — you need to select `dashboard/dashboard_data.json` via the file picker (or serve the folder locally — see Step 3) after running Step 2; the dashboard has no data of its own.
- **`pip install` fails on a managed system** — add `--break-system-packages`, or use the venv from Step 0.
- **Different numbers than the reports** — expected for anything using randomness beyond the fixed seeds; the reference pipeline and all seeded scenarios/domains are deterministic and should reproduce exactly given the same seed.
- **Taillard/Lawrence files missing** — they ship in `data/taillard/`; if somehow absent, they're real public benchmark files, refetchable from `github.com/tamy0612/JSPLIB/tree/master/instances` (files `ta01`-`ta03`, `la01`-`la02`).
