"""
Narration layer.

Deliberate scope limit (per explicit project guidance): the novelty of this
project is the severity gate, not the eloquence of the explanation text.
This module is intentionally the least sophisticated part of the codebase.

Two backends are provided behind one interface:

  - TemplateNarrator (default): a fully deterministic, rule-based sentence
    generator. No LLM call, no network dependency, fully unit-testable.
    This is what the pipeline uses unless an LLM backend is explicitly
    requested, and it is what Phase 3's evaluation should use for the
    primary results, precisely so results aren't confounded by LLM sampling
    variance or prompt-wording choices.

  - GroqNarrator (optional): a single-call, single-turn LLM wrapper for
    producing more natural prose on top of the SAME facts the template
    narrator uses. It is given the gate's already-decided output; it does
    not reason about severity, does not see the raw environment, and its
    prompt is intentionally short with no chain-of-thought requested. If
    GROQ_API_KEY is not set, or the network call fails for any reason, it
    transparently falls back to TemplateNarrator so the pipeline never
    breaks because of an external dependency.

Both backends implement the same one-method interface, `narrate(step) -> str`,
so Phase 3's evaluation can swap between them without touching anything else.

---
BUG FIX (found via an actual human-study pilot session, not a code review):
the original version conflated two different questions into one "Flagged
because..." sentence -- (1) why the AGENT chose this action, and (2) why
SCAA's severity gate flagged the decision for audit. Quiz questions asked
(1) but the narration only ever answered (2), so answers were unanswerable
as worded. Worse, because ScoringAgent's assign-scoring function does not
depend on which machine a job goes to, most assign-vs-assign comparisons
are genuinely tied, which pushed Irreversibility above threshold on nearly
every step and made every narration sentence look identical. Fixed by:
  (a) adding `_agent_rationale()`, a first sentence that always answers
      "why did the agent choose this," using the real scoring-policy logic,
      including the honest tied-machine-score case rather than inventing a
      machine-specific reason that doesn't exist in the policy;
  (b) making the gate-reasoning sentence conditional on `explanation_worthy`,
      so the explain-everything condition no longer claims "Flagged
      because..." for the 18/27 steps SCAA's gate never actually flagged.
---
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

from .trace import DecisionStep

_I_HIGH, _F_HIGH, _D_HIGH = 0.6, 0.6, 0.6


def _describe_action(label: str) -> str:
    if label.startswith("assign->M"):
        m = label.split("assign->M")[1]
        return f"assigning it to Machine {m}"
    if label == "defer":
        return "deferring it to the next cycle"
    if label == "reject":
        return "rejecting it"
    return label


def _action_type(label: str) -> str:
    return "assign" if label.startswith("assign->M") else label


def _agent_rationale(step: DecisionStep) -> str:
    """
    Explains WHY THE AGENT chose this action over its runner-up, in terms of
    the scheduling policy's own logic (urgency, priority, deadline slack) --
    this is a genuinely different question from "why did SCAA flag this for
    audit," and answers it using only facts already on the DecisionStep.

    Important, non-obvious case: ScoringAgent's assign-scoring function does
    not consider WHICH machine a job goes to, only WHETHER to assign it --
    so when two or more machines are free, every assign->Mx candidate is
    tied, and the tie is broken purely by machine index. This is a real
    property of the policy, not a narration limitation, and is stated
    honestly here rather than invented as a fake machine-specific reason.
    """
    chosen_type = _action_type(step.chosen_label)
    runner_type = _action_type(step.runner_up_label) if step.runner_up_label else None

    if chosen_type == "assign" and runner_type == "assign":
        chosen_m = step.chosen_label.split("assign->M")[1]
        runner_m = step.runner_up_label.split("assign->M")[1]
        return (f"Machines {chosen_m} and {runner_m} were both free and scored identically for this job "
                f"-- the scheduling policy does not distinguish between otherwise-idle machines -- "
                f"so Machine {chosen_m} was picked as the lower-indexed tied candidate.")

    if chosen_type == "assign" and runner_type == "defer":
        return ("The job's priority and closing deadline made assigning it now score higher than "
                "waiting a cycle, so the agent committed a machine immediately.")

    if chosen_type == "assign" and runner_type == "reject":
        return ("The job could still be completed within an acceptable margin of its deadline, "
                "so assigning it scored higher than turning it away.")

    if chosen_type == "defer" and runner_type == "assign":
        return ("The job's deadline was not yet close enough to justify committing a machine now, "
                "so the agent preferred to wait and re-evaluate next cycle.")

    if chosen_type == "defer" and runner_type == "reject":
        return "The job was not yet urgent, but also not clearly unsalvageable, so waiting scored higher than rejecting it outright."

    if chosen_type == "reject":
        return ("Even completed immediately, the job would finish too far past its deadline to be "
                "worth honoring, so the agent turned it away.")

    return "This was the highest-scoring option the agent considered at this step."


def _gate_reasons(components: dict) -> list:
    reasons = []
    if components["I"] >= _I_HIGH:
        reasons.append("the commitment would be hard to undo (high irreversibility)")
    if components["F"] >= _F_HIGH:
        reasons.append("the job was high priority and/or close to its deadline (high impact)")
    if components["D"] >= _D_HIGH:
        reasons.append("this was an unusually close call relative to the agent's typical decisions (high deviation)")
    if not reasons:
        reasons.append("its combined severity score crossed the configured threshold")
    return reasons


class Narrator(ABC):
    @abstractmethod
    def narrate(self, step: DecisionStep) -> str:
        ...


class BaseTemplateNarrator(Narrator):
    """
    Domain-agnostic two-sentence skeleton, extracted for Phase 4 so new
    domains (delivery, cloud, taillard) can reuse this exact logic --
    including the conditional gate-reasoning sentence and the honest
    non-gated disclosure -- while only overriding the action vocabulary
    (`_describe_action`, `_agent_rationale`). Domain 1's `TemplateNarrator`
    below is refactored to be a thin subclass of this with IDENTICAL
    output to before this refactor (verified by the existing narration
    test suite, unchanged).
    """

    def _describe_action(self, label: str) -> str:
        raise NotImplementedError

    def _agent_rationale(self, step: DecisionStep) -> str:
        raise NotImplementedError

    def narrate(self, step: DecisionStep) -> str:
        chosen_desc = self._describe_action(step.chosen_label)
        alt_desc = self._describe_action(step.runner_up_label) if step.runner_up_label else None

        sentence = f"Job {step.job_id} (priority {step.job_priority}, tick {step.tick}): {chosen_desc}"
        if alt_desc:
            sentence += f" instead of {alt_desc}"
        sentence += ". "

        sentence += self._agent_rationale(step)

        if step.explanation_worthy and step.severity_components:
            reasons = _gate_reasons(step.severity_components)
            sentence += " Flagged for audit because " + " and ".join(reasons) + "."
        elif step.severity_components:
            sentence += (" (Not flagged by SCAA's severity gate -- shown here only because this "
                         "condition displays every decision.)")

        return sentence


class TemplateNarrator(BaseTemplateNarrator):
    """Deterministic, rule-based. No network, no API key, no randomness."""

    def _describe_action(self, label: str) -> str:
        return _describe_action(label)

    def _agent_rationale(self, step: DecisionStep) -> str:
        return _agent_rationale(step)


class GroqNarrator(Narrator):
    """
    Thin wrapper around Groq's chat completion endpoint. Single call, single
    turn, short prompt, low temperature. Falls back to TemplateNarrator on
    any failure (missing key, network error, malformed response) so the
    pipeline is never blocked by this optional dependency.
    """

    def __init__(self, model: str = "llama-3.1-8b-instant", temperature: float = 0.2):
        self.model = model
        self.temperature = temperature
        self._fallback = TemplateNarrator()
        self._api_key = os.environ.get("GROQ_API_KEY")

    def _build_prompt(self, step: DecisionStep) -> str:
        chosen_desc = _describe_action(step.chosen_label)
        alt_desc = _describe_action(step.runner_up_label) if step.runner_up_label else "no viable alternative"
        comps = step.severity_components or {}
        rationale = _agent_rationale(step)
        gate_note = (
            "This step WAS flagged by SCAA's severity gate for the reasons implied by the scores below."
            if step.explanation_worthy else
            "This step was NOT flagged by SCAA's severity gate; only mention that if asked, don't invent a reason it was."
        )
        # Intentionally short: facts in, one plain-English audit sentence out.
        # No chain-of-thought requested; no multi-turn refinement. The prompt
        # explicitly separates "why the agent acted" from "why the gate
        # flagged it" so the model doesn't collapse them into one, which was
        # the exact bug found in the template version of this narrator.
        return (
            "Write ONE or TWO plain-English sentences for a non-technical auditor "
            "explaining this scheduling decision. State only the facts given; do not speculate.\n\n"
            f"Job: id={step.job_id}, priority={step.job_priority}/3, tick={step.tick}\n"
            f"Chosen action: {chosen_desc}\n"
            f"Alternative considered: {alt_desc}\n"
            f"Why the agent chose this over the alternative: {rationale}\n"
            f"Severity components: irreversibility={comps.get('I', 0):.2f}, "
            f"impact={comps.get('F', 0):.2f}, deviation={comps.get('D', 0):.2f}\n"
            f"{gate_note}\n"
        )

    def narrate(self, step: DecisionStep) -> str:
        if not self._api_key:
            return self._fallback.narrate(step)
        try:
            import requests
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self.model,
                    "temperature": self.temperature,
                    "max_tokens": 120,
                    "messages": [{"role": "user", "content": self._build_prompt(step)}],
                },
                timeout=15,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            return text if text else self._fallback.narrate(step)
        except Exception:
            return self._fallback.narrate(step)


def narrate_steps(steps: list, narrator: Narrator = None) -> None:
    """Mutates each step's `.narration` field in place."""
    narrator = narrator or TemplateNarrator()
    for step in steps:
        step.narration = narrator.narrate(step)
