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


if __name__ == "__main__":
    test_template_narrator_is_deterministic()
    test_template_narrator_mentions_job_and_action()
    test_narrate_steps_fills_narration_field()
    test_groq_narrator_falls_back_without_api_key()
    print("All narration tests passed.")
