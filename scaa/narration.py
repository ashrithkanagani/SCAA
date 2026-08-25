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


def _reasons(components: dict) -> list:
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


class TemplateNarrator(Narrator):
    """Deterministic, rule-based. No network, no API key, no randomness."""

    def narrate(self, step: DecisionStep) -> str:
        chosen_desc = _describe_action(step.chosen_label)
        alt_desc = _describe_action(step.runner_up_label) if step.runner_up_label else None
        reasons = _reasons(step.severity_components) if step.severity_components else []

        sentence = f"Job {step.job_id} (priority {step.job_priority}, tick {step.tick}): {chosen_desc}"
        if alt_desc:
            sentence += f" instead of {alt_desc}"
        sentence += "."
        if reasons:
            sentence += " Flagged because " + " and ".join(reasons) + "."
        return sentence


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
        # Intentionally short: facts in, one plain-English audit sentence out.
        # No chain-of-thought requested; no multi-turn refinement.
        return (
            "Write ONE or TWO plain-English sentences for a non-technical auditor "
            "explaining this scheduling decision. State only the facts given; do not speculate.\n\n"
            f"Job: id={step.job_id}, priority={step.job_priority}/3, tick={step.tick}\n"
            f"Chosen action: {chosen_desc}\n"
            f"Alternative considered: {alt_desc}\n"
            f"Severity components: irreversibility={comps.get('I', 0):.2f}, "
            f"impact={comps.get('F', 0):.2f}, deviation={comps.get('D', 0):.2f}\n"
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
