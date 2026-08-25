"""
Human study infrastructure: generate blinded rating templates, then score
them once your team fills them in.

THIS MODULE PRODUCES NO FAKE DATA. `generate_rating_templates()` writes CSVs
with empty rating columns for your teammates to fill in by hand (per the
protocol in reports/EVALUATION_PLAN.md, Section 3). `score_ratings()` only
works once those CSVs have real entries; run it after collecting them.

Design recap (see EVALUATION_PLAN.md for the full protocol):
  - 3 raters x 3 scenarios x 2 conditions (Explain-Everything vs SCAA-gated)
    = 18 sessions, Latin-square rotated so no rater sees the same trajectory
    in both conditions.
  - Each session: read the narrated decisions for ONE condition on ONE
    trajectory, then answer a 5-question factual quiz about *why* the agent
    made specific decisions, self-report completion time.
  - Separately, Experiment 1 (Selection Agreement): blind Yes/No "would you
    want this decision explained?" per step, across all steps of one
    trajectory, independent of which strategy flagged it.
"""

from __future__ import annotations

import csv
import os
import random

from .agent import ScoringAgent
from .attribution import compute_attribution
from .baselines import selection_summary
from .config import AttributionConfig, SeverityWeights
from .narration import TemplateNarrator, narrate_steps
from .scenarios import SCENARIOS, get_scenario
from .severity import apply_severity_gate, calibrate_deviation
from .simulate import run_trajectory

# Latin-square rotation: rater -> (scenario, condition) assignment plan.
# Each rater covers all 3 scenarios; condition alternates so every
# scenario x condition pair is covered by at least one rater, and no rater
# repeats a scenario across conditions.
LATIN_SQUARE_PLAN = {
    "rater_1": [("balanced", "scaa"), ("high_contention", "explain_all"), ("safety_critical", "scaa")],
    "rater_2": [("high_contention", "scaa"), ("safety_critical", "explain_all"), ("balanced", "explain_all")],
    "rater_3": [("safety_critical", "scaa"), ("balanced", "explain_all"), ("high_contention", "explain_all")],
}


def _build_trajectory(scenario_name: str, seed: int = 42):
    cfg = get_scenario(scenario_name, seed=seed)
    agent = ScoringAgent()
    traj = run_trajectory(cfg, agent)
    compute_attribution(traj, agent, cfg, job_schedule=None, attribution_config=AttributionConfig())
    calib = calibrate_deviation(cfg, agent, n_seeds=15)
    apply_severity_gate(traj, SeverityWeights(), calib)
    return traj


def generate_audit_quiz_sessions(output_dir: str = "reports/human_study/quiz_sessions"):
    """
    Experiments 2/5 (Information Compression + Time-to-Audit): for each
    (rater, scenario, condition) in the Latin-square plan, write a text
    file with the narrated decisions the rater should read, plus a 5
    question quiz with an ANSWER KEY kept separate (rater_answers/) so the
    quiz file itself stays blind.
    """
    os.makedirs(output_dir, exist_ok=True)
    answer_dir = os.path.join(output_dir, "answer_keys")
    os.makedirs(answer_dir, exist_ok=True)

    for rater, sessions in LATIN_SQUARE_PLAN.items():
        for scenario_name, condition in sessions:
            traj = _build_trajectory(scenario_name)
            selection = selection_summary(traj)
            steps = selection["explain_everything"] if condition == "explain_all" else selection["scaa_gate"]
            narrate_steps(steps, narrator=TemplateNarrator())

            fname = f"{rater}__{scenario_name}__{condition}.txt"
            with open(os.path.join(output_dir, fname), "w") as f:
                f.write(f"AUDIT SESSION: {rater} | scenario={scenario_name} | condition={condition}\n")
                f.write(f"Number of decisions shown: {len(steps)} (of {len(traj.steps)} total)\n")
                f.write("Start a timer now. Read the following, then answer the 5 questions below.\n")
                f.write("=" * 70 + "\n\n")
                for s in steps:
                    f.write(s.narration + "\n")
                f.write("\n" + "=" * 70 + "\n")
                f.write("QUIZ (answer briefly, then record your total time):\n")

                # Pick 5 quiz questions from steps *outside* explain_all's blind
                # spot is moot for explain_all (sees everything); for the SCAA
                # condition, questions are drawn only from steps the rater
                # actually saw, so the quiz measures comprehension of what was
                # shown, not recall of what was withheld.
                quiz_pool = steps if steps else traj.steps
                rng = random.Random(hash((rater, scenario_name, condition)) % (2**32))
                quiz_steps = rng.sample(quiz_pool, min(5, len(quiz_pool)))
                for i, qs in enumerate(quiz_steps, 1):
                    f.write(f"\n{i}. Why did the agent choose '{qs.chosen_label}' for job {qs.job_id} "
                            f"(tick {qs.tick})?\n   Your answer: ______________________\n")
                f.write("\nTotal time taken (mm:ss): ______\n")

            with open(os.path.join(answer_dir, fname.replace(".txt", "_KEY.txt")), "w") as f:
                for i, qs in enumerate(quiz_steps, 1):
                    comp = qs.severity_components or {}
                    driver = max(comp, key=comp.get) if comp else "n/a"
                    f.write(f"{i}. job={qs.job_id} chosen={qs.chosen_label} "
                            f"runner_up={qs.runner_up_label} driving_component={driver} "
                            f"I={comp.get('I')} F={comp.get('F')} D={comp.get('D')}\n")

    print(f"[human_study] {len(LATIN_SQUARE_PLAN) * 3} quiz sessions written to {output_dir}/")
    print(f"[human_study] answer keys (for scoring, not for the rater) in {answer_dir}/")


def generate_selection_agreement_csv(scenario_name: str = "balanced",
                                      output_path: str = "reports/human_study/selection_agreement_blank.csv"):
    """
    Experiment 1 (Selection Agreement): one row per decision, blind to which
    strategy flagged it. Each of the 3 teammates fills in their own copy's
    `rater_yes_no` column independently, then score_selection_agreement()
    compares each rater's answers to the gate/attribution/random flags.
    """
    traj = _build_trajectory(scenario_name)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["step_id", "tick", "job_id", "chosen_action", "runner_up_action",
                          "job_priority", "job_deadline", "job_duration",
                          "rater_yes_no (fill in: Yes/No -- would you want this explained?)"])
        for s in traj.steps:
            writer.writerow([s.step_id, s.tick, s.job_id, s.chosen_label,
                              s.runner_up_label, s.job_priority, s.job_deadline,
                              s.job_duration, ""])
    print(f"[human_study] blind selection-agreement template written to {output_path}")
    print("Make 3 copies (one per rater) before filling in, so raters stay independent.")
    return traj  # returned so callers can build the scoring ground truth alongside it


def score_selection_agreement(traj, filled_csv_paths: list) -> dict:
    """
    Once your 3 teammates have filled in their own copy of the CSV from
    generate_selection_agreement_csv(), pass their file paths here.
    Computes each rater's agreement with SCAA gate / attribution-topk /
    random-k, plus 3-rater consensus agreement.
    """
    selection = selection_summary(traj)
    gate_ids = set(s.step_id for s in selection["scaa_gate"])
    attr_ids = set(s.step_id for s in selection["attribution_topk"])
    rand_ids = set(s.step_id for s in selection["random_k"])

    all_rater_answers = []
    for path in filled_csv_paths:
        answers = {}
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                col = [k for k in row if k.startswith("rater_yes_no")][0]
                val = row[col].strip().lower()
                answers[int(row["step_id"])] = val.startswith("y")
        all_rater_answers.append(answers)

    def agreement(rater_answers, strategy_ids, n_total):
        agree = sum(1 for sid, said_yes in rater_answers.items()
                    if said_yes == (sid in strategy_ids))
        return agree / n_total if n_total else 0.0

    n_total = len(selection["scaa_gate"]) + 0  # placeholder, replaced below
    n_total = len(gate_ids | attr_ids | rand_ids) or len(all_rater_answers[0]) if all_rater_answers else 0

    per_rater = []
    for i, answers in enumerate(all_rater_answers, 1):
        n = len(answers)
        per_rater.append({
            "rater": f"rater_{i}",
            "agreement_with_gate": agreement(answers, gate_ids, n),
            "agreement_with_attribution": agreement(answers, attr_ids, n),
            "agreement_with_random": agreement(answers, rand_ids, n),
        })

    consensus = None
    if len(all_rater_answers) >= 2:
        common_steps = set(all_rater_answers[0])
        for a in all_rater_answers[1:]:
            common_steps &= set(a)
        agree_count = sum(
            1 for sid in common_steps
            if len({a[sid] for a in all_rater_answers}) == 1
        )
        consensus = agree_count / len(common_steps) if common_steps else None

    return {"per_rater": per_rater, "three_rater_consensus_rate": consensus}


if __name__ == "__main__":
    generate_audit_quiz_sessions()
    generate_selection_agreement_csv()
