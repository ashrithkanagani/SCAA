import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scaa.config import EnvironmentConfig, SeverityWeights
from scaa.agent import ScoringAgent
from scaa.simulate import run_trajectory
from scaa.severity import apply_severity_gate, calibrate_deviation
from scaa.narration import TemplateNarrator, GroqNarrator, narrate_steps


def _gated_trajectory(seed=4):
    cfg = EnvironmentConfig(seed=seed, n_jobs=15, sim_horizon=40)
    agent = ScoringAgent()
    traj = run_trajectory(cfg, agent)
    calib = calibrate_deviation(cfg, agent, n_seeds=5)
    apply_severity_gate(traj, SeverityWeights(), calib)
    return traj


def test_template_narrator_is_deterministic():
    traj = _gated_trajectory()
    narrator = TemplateNarrator()
    gated = [s for s in traj.steps if s.explanation_worthy]
    assert len(gated) > 0, "need at least one gated step to test narration"
    text1 = narrator.narrate(gated[0])
    text2 = narrator.narrate(gated[0])
    assert text1 == text2


def test_template_narrator_mentions_job_and_action():
    traj = _gated_trajectory()
    narrator = TemplateNarrator()
    gated = [s for s in traj.steps if s.explanation_worthy]
    for step in gated[:3]:
        text = narrator.narrate(step)
        assert str(step.job_id) in text
        assert len(text.split()) < 80  # stays a short audit sentence, not an essay


def test_narrate_steps_fills_narration_field():
    traj = _gated_trajectory()
    gated = [s for s in traj.steps if s.explanation_worthy]
    narrate_steps(gated, narrator=TemplateNarrator())
    for step in gated:
        assert step.narration is not None
        assert len(step.narration) > 0


def test_groq_narrator_falls_back_without_api_key():
    """Without GROQ_API_KEY set, GroqNarrator must transparently fall back
    to TemplateNarrator rather than raising or blocking the pipeline."""
    os.environ.pop("GROQ_API_KEY", None)
    traj = _gated_trajectory()
    gated = [s for s in traj.steps if s.explanation_worthy]
    narrator = GroqNarrator()
    text = narrator.narrate(gated[0])
    assert isinstance(text, str) and len(text) > 0


def test_narration_answers_why_the_agent_chose_this():
    """Regression test for the bug found in the human-study pilot: the
    narration must contain agent-rationale language, not just severity-gate
    language, so 'why did the agent choose X' is actually answerable."""
    traj = _gated_trajectory()
    for step in traj.steps[:10]:
        text = TemplateNarrator().narrate(step)
        # Agent-rationale sentences always contain one of these signal phrases;
        # gate-only text (the old, broken behavior) never did.
        rationale_markers = ["scored", "deadline", "priority", "tied", "urgent", "highest-scoring"]
        assert any(m in text for m in rationale_markers), f"no agent rationale found in: {text}"


def test_tied_machine_assignment_is_explained_honestly():
    """When chosen and runner-up are both assign->Mx (a real tie in
    ScoringAgent's scoring function, which ignores machine identity), the
    narration must say so honestly rather than inventing a machine-specific
    reason that doesn't exist in the policy."""
    from scaa.narration import _agent_rationale
    from scaa.trace import DecisionStep

    step = DecisionStep(
        step_id=0, tick=1, job_id=0, job_priority=2, job_deadline=10, job_duration=3,
        n_pending_jobs=1, n_free_machines=2,
        candidate_labels=["assign->M0", "assign->M1", "defer", "reject"],
        candidate_scores=[3.0, 3.0, 1.0, 0.1],
        chosen_label="assign->M0", chosen_score=3.0, chosen_action={"type": "assign", "job_id": 0, "machine_id": 0},
        runner_up_label="assign->M1", runner_up_score=3.0, runner_up_action={"type": "assign", "job_id": 0, "machine_id": 1},
        is_commit=True,
    )
    text = _agent_rationale(step)
    assert "tied" in text or "identically" in text
    assert "Machine 0" in text and "1" in text


def test_non_gated_step_does_not_falsely_claim_flagged():
    """Regression test for the explain-everything bug: a step with
    explanation_worthy=False must NOT contain 'Flagged for audit because'."""
    traj = _gated_trajectory()
    non_gated = [s for s in traj.steps if not s.explanation_worthy]
    assert len(non_gated) > 0, "need at least one non-gated step to test this"
    for step in non_gated[:5]:
        text = TemplateNarrator().narrate(step)
        assert "Flagged for audit because" not in text
        assert "Not flagged by SCAA" in text


def test_gated_step_does_claim_flagged():
    traj = _gated_trajectory()
    gated = [s for s in traj.steps if s.explanation_worthy]
    for step in gated[:5]:
        text = TemplateNarrator().narrate(step)
        assert "Flagged for audit because" in text


if __name__ == "__main__":
    test_template_narrator_is_deterministic()
    test_template_narrator_mentions_job_and_action()
    test_narrate_steps_fills_narration_field()
    test_groq_narrator_falls_back_without_api_key()
    test_narration_answers_why_the_agent_chose_this()
    test_tied_machine_assignment_is_explained_honestly()
    test_non_gated_step_does_not_falsely_claim_flagged()
    test_gated_step_does_claim_flagged()
    print("All narration tests passed.")
