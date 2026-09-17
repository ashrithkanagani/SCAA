"""
Human study infrastructure: generate blinded rating templates, then score
them once your team fills them in.

THIS MODULE PRODUCES NO FAKE DATA. `generate_audit_quiz_sessions()` and
`generate_selection_agreement_csv()` write blank templates for your team to
fill in by hand (per the protocol in reports/EVALUATION_PLAN.md, Section 3,
and reports/PHASE_4_REPORT.md's cross-domain extension of that protocol).
Scoring functions only work once those templates have real entries.

Phase 4 extends the original single-domain (scheduling) study to all FOUR
domains via a small domain registry (`DOMAIN_REGISTRY`, below), so the
pilot study now also speaks to cross-domain generalization, not just
within-domain gate quality:

  - 3 raters x 4 domains x 1 condition each = 12 sessions (each rater
    covers every domain exactly once; condition -- SCAA-gated vs.
    explain-everything -- alternates by a fixed (rater, domain) formula so
    every domain is represented under both conditions across the team).
    This is a smaller per-rater burden than the original 3-scenario plan
    despite covering more ground (4 sessions/rater vs. the original's 3),
    because each domain is now seen once rather than each scenario twice.
  - Each session: read the narrated decisions for ONE condition on ONE
    domain's representative trajectory, then answer a 5-question factual
    quiz, self-report completion time.
  - Separately, Experiment 1 (Selection Agreement) is generated for EVERY
    domain (not just one), so agreement can be reported per-domain too.
"""

from __future__ import annotations

import csv
import os
import random

from .agent import ScoringAgent
from .attribution import compute_attribution
from .baselines import selection_summary
from .config import AttributionConfig, SeverityWeights
from .narration import TemplateNarrator, narrate_steps, _agent_rationale as _scheduling_rationale
from .scenarios import get_scenario
from .severity import apply_severity_gate, calibrate_deviation
from .simulate import run_trajectory

from .domains.common import run_trajectory_generic, calibrate_deviation_generic
from .domains.delivery.environment import DeliveryEnvironment, DeliveryEnvConfig
from .domains.delivery.agent import NearestWindowAgent
from .domains.delivery.narration import DeliveryNarrator
from .domains.cloud.environment import CloudEnvironment, CloudEnvConfig
from .domains.cloud.agent import SLAAwareAgent
from .domains.cloud.narration import CloudNarrator
from .domains.taillard.loader import load_taillard_instance
from .domains.taillard.environment import JSSPEnvironment
from .domains.taillard.agent import SPTDispatchAgent
from .domains.taillard.narration import JSSPNarrator


# ---------------------------------------------------------------- registry

def _build_scheduling_trajectory(seed: int = 42):
    cfg = get_scenario("balanced", seed=seed)
    agent = ScoringAgent()
    traj = run_trajectory(cfg, agent)
    compute_attribution(traj, agent, cfg, job_schedule=None, attribution_config=AttributionConfig())
    calib = calibrate_deviation(cfg, agent, n_seeds=15)
    apply_severity_gate(traj, SeverityWeights(), calib)
    return traj


def _build_delivery_trajectory(seed: int = 42):
    cfg = DeliveryEnvConfig(seed=seed)
    agent = NearestWindowAgent()
    traj = run_trajectory_generic(DeliveryEnvironment(cfg), agent)
    calib = calibrate_deviation_generic(lambda: DeliveryEnvironment(cfg), agent, n_seeds=10)
    apply_severity_gate(traj, SeverityWeights(), calib)
    return traj


def _build_cloud_trajectory(seed: int = 42):
    cfg = CloudEnvConfig(seed=seed)
    agent = SLAAwareAgent()
    traj = run_trajectory_generic(CloudEnvironment(cfg), agent)
    calib = calibrate_deviation_generic(lambda: CloudEnvironment(cfg), agent, n_seeds=10)
    apply_severity_gate(traj, SeverityWeights(), calib)
    return traj


def _build_taillard_trajectory(seed: int = 42, instance: str = "la01.txt"):
    path = os.path.join("data", "taillard", instance)
    jobs, n_machines, _ = load_taillard_instance(path)
    env = JSSPEnvironment(jobs, n_machines)
    agent = SPTDispatchAgent()
    traj = run_trajectory_generic(env, agent)
    calib = calibrate_deviation_generic(lambda: JSSPEnvironment(*load_taillard_instance(path)[:2]), agent, n_seeds=8)
    apply_severity_gate(traj, SeverityWeights(), calib)
    return traj


def _scheduling_category(step) -> str:
    chosen, runner = step.chosen_label, step.runner_up_label
    ct = "assign" if chosen.startswith("assign->M") else chosen
    rt = "assign" if (runner and runner.startswith("assign->M")) else runner
    if ct == "assign" and rt == "assign": return "tied_machines"
    if ct == "assign" and rt == "defer": return "assign_over_defer"
    if ct == "assign" and rt == "reject": return "assign_over_reject"
    if ct == "defer" and rt == "assign": return "defer_over_assign"
    if ct == "reject": return "reject"
    return "other"


def _taillard_category(step) -> str:
    return "solo_ready" if step.runner_up_label is None else "job_competition"


DOMAIN_REGISTRY = {
    "scheduling": {
        "build": _build_scheduling_trajectory,
        "narrator": TemplateNarrator,
        "category_fn": _scheduling_category,
        "rationale_fn": _scheduling_rationale,
        "question_template": "Why did the agent choose '{chosen}' for job {job_id} (tick {tick}) over '{runner_up}'?",
    },
    "delivery": {
        "build": _build_delivery_trajectory,
        "narrator": DeliveryNarrator,
        "category_fn": _scheduling_category,  # identical vocabulary (assign->Mx/defer/reject)
        "rationale_fn": lambda step: DeliveryNarrator()._agent_rationale(step),
        "question_template": "Why did the agent choose '{chosen}' for order {job_id} (tick {tick}) over '{runner_up}'?",
    },
    "cloud": {
        "build": _build_cloud_trajectory,
        "narrator": CloudNarrator,
        "category_fn": _scheduling_category,
        "rationale_fn": lambda step: CloudNarrator()._agent_rationale(step),
        "question_template": "Why did the agent choose '{chosen}' for task {job_id} (tick {tick}) over '{runner_up}'?",
    },
    "taillard_jssp": {
        "build": _build_taillard_trajectory,
        "narrator": JSSPNarrator,
        "category_fn": _taillard_category,
        "rationale_fn": lambda step: JSSPNarrator()._agent_rationale(step),
        "question_template": "Why was job {job_id}'s operation dispatched at tick {tick} ahead of '{runner_up}'?",
    },
}

# rater -> [(domain, condition), ...]. Each rater covers all 4 domains
# exactly once. Condition uses (rater_idx + domain_idx) % 3 (NOT % 2 --
# with only 2 conditions and 3 raters, mod-2 makes rater_1 and rater_3
# collapse onto the identical plan, which defeats the point of a rotation;
# mod-3 gives all 3 raters genuinely distinct plans while still ensuring
# every domain is represented under both conditions across the team, see
# the coverage table in this module's docstring/tests).
_DOMAINS_IN_ORDER = ["scheduling", "delivery", "cloud", "taillard_jssp"]
LATIN_SQUARE_PLAN = {}
for _rater_idx in range(3):
    _sessions = []
    for _domain_idx, _domain in enumerate(_DOMAINS_IN_ORDER):
        _condition = "explain_all" if (_rater_idx + _domain_idx) % 3 == 2 else "scaa"
        _sessions.append((_domain, _condition))
    LATIN_SQUARE_PLAN[f"rater_{_rater_idx + 1}"] = _sessions


def _select_diverse_quiz_steps(pool: list, category_fn, rng: random.Random, n: int = 5) -> list:
    by_category = {}
    for s in pool:
        by_category.setdefault(category_fn(s), []).append(s)
    for cat_steps in by_category.values():
        rng.shuffle(cat_steps)
    categories = list(by_category.keys())
    rng.shuffle(categories)

    selected = []
    idx = 0
    while len(selected) < n and any(by_category[c] for c in categories):
        cat = categories[idx % len(categories)]
        if by_category[cat]:
            selected.append(by_category[cat].pop())
        idx += 1
    return selected[:n]


def generate_audit_quiz_sessions(output_dir: str = "reports/human_study/quiz_sessions"):
    """
    For each (rater, domain, condition) in LATIN_SQUARE_PLAN, write a text
    file with the narrated decisions the rater should read, plus a
    5-question quiz with an ANSWER KEY kept separate (answer_keys/) so the
    quiz file itself stays blind. Covers all 4 domains (Phase 4).
    """
    os.makedirs(output_dir, exist_ok=True)
    answer_dir = os.path.join(output_dir, "answer_keys")
    os.makedirs(answer_dir, exist_ok=True)

    for rater, sessions in LATIN_SQUARE_PLAN.items():
        for domain_name, condition in sessions:
            spec = DOMAIN_REGISTRY[domain_name]
            traj = spec["build"]()
            selection = selection_summary(traj)
            steps = selection["explain_everything"] if condition == "explain_all" else selection["scaa_gate"]
            narrate_steps(steps, narrator=spec["narrator"]())

            fname = f"{rater}__{domain_name}__{condition}.txt"
            with open(os.path.join(output_dir, fname), "w") as f:
                f.write(f"AUDIT SESSION: {rater} | domain={domain_name} | condition={condition}\n")
                f.write(f"Number of decisions shown: {len(steps)} (of {len(traj.steps)} total)\n")
                f.write("Start a timer now. Read the following, then answer the 5 questions below.\n")
                f.write("=" * 70 + "\n\n")
                for s in steps:
                    f.write(s.narration + "\n")
                f.write("\n" + "=" * 70 + "\n")
                f.write("QUIZ (answer briefly, then record your total time):\n")

                quiz_pool = steps if steps else traj.steps
                rng = random.Random(hash((rater, domain_name, condition)) % (2**32))
                quiz_steps = _select_diverse_quiz_steps(quiz_pool, spec["category_fn"], rng, n=5)
                for i, qs in enumerate(quiz_steps, 1):
                    if qs.runner_up_label is None:
                        q = (f"Why was job {qs.job_id}'s decision at tick {qs.tick} "
                             f"the only option available at that moment?")
                    else:
                        q = spec["question_template"].format(
                            chosen=qs.chosen_label, job_id=qs.job_id, tick=qs.tick,
                            runner_up=qs.runner_up_label)
                    f.write(f"\n{i}. {q}\n   Your answer: ______________________\n")
                f.write("\nTotal time taken (mm:ss): ______\n")

            with open(os.path.join(answer_dir, fname.replace(".txt", "_KEY.txt")), "w") as f:
                for i, qs in enumerate(quiz_steps, 1):
                    comp = qs.severity_components or {}
                    driver = max(comp, key=comp.get) if comp else "n/a"
                    f.write(f"{i}. job={qs.job_id} category={spec['category_fn'](qs)}\n")
                    f.write(f"   expected answer (agent rationale): {spec['rationale_fn'](qs)}\n")
                    f.write(f"   gate status: {'FLAGGED' if qs.explanation_worthy else 'not flagged'}, "
                            f"driving_component={driver if qs.explanation_worthy else 'n/a'}, "
                            f"I={comp.get('I')} F={comp.get('F')} D={comp.get('D')}\n")

    total = sum(len(v) for v in LATIN_SQUARE_PLAN.values())
    print(f"[human_study] {total} quiz sessions written to {output_dir}/ (across {len(DOMAIN_REGISTRY)} domains)")
    print(f"[human_study] answer keys (for scoring, not for the rater) in {answer_dir}/")


def generate_selection_agreement_csv(domain_name: str = "scheduling",
                                      output_dir: str = "reports/human_study") -> object:
    """
    Experiment 1 (Selection Agreement), generated for ONE named domain
    (default: scheduling, matching the original Phase 3 protocol). Call
    once per domain if you want cross-domain agreement data -- see
    generate_all_selection_agreement_csvs() to do this for all 4 at once.
    """
    spec = DOMAIN_REGISTRY[domain_name]
    traj = spec["build"]()
    output_path = os.path.join(output_dir, f"selection_agreement_{domain_name}_blank.csv")
    os.makedirs(output_dir, exist_ok=True)

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
    return traj


def generate_all_selection_agreement_csvs(output_dir: str = "reports/human_study") -> dict:
    """Generates one blank selection-agreement CSV per domain (4 total)."""
    trajs = {}
    for domain_name in DOMAIN_REGISTRY:
        trajs[domain_name] = generate_selection_agreement_csv(domain_name, output_dir)
    print("Make 3 copies of EACH domain's CSV (one per rater) before filling in, so raters stay independent.")
    return trajs


def score_selection_agreement(traj, filled_csv_paths: list) -> dict:
    """
    Once your 3 teammates have filled in their own copy of a domain's CSV,
    pass their file paths here. Computes each rater's agreement with SCAA
    gate / attribution-topk / random-k, plus 3-rater consensus agreement.
    Works identically regardless of which domain the trajectory came from.
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
        agree_count = sum(1 for sid in common_steps if len({a[sid] for a in all_rater_answers}) == 1)
        consensus = agree_count / len(common_steps) if common_steps else None

    return {"per_rater": per_rater, "three_rater_consensus_rate": consensus}


if __name__ == "__main__":
    generate_audit_quiz_sessions()
    generate_all_selection_agreement_csvs()
