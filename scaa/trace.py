"""
Trace capture: the data schema shared by every downstream module
(attribution.py, severity.py, and Phase 2's narration layer).

A Trajectory is an ordered list of DecisionStep records. Each record is
intentionally flat and JSON-serializable so it can be logged, replayed,
and later handed to an LLM narrator without any custom object graph.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class DecisionStep:
    """
    One agent decision, fully self-contained for downstream analysis.

    Fields map directly onto the SCAA pipeline stages:
      - step_id, tick, job_id, state_snapshot   -> captured by trace.py at decision time
      - candidate_labels/candidate_scores        -> captured by agent.py
      - chosen_label/chosen_score, runner_up_*   -> captured by agent.py
      - is_commit (irreversibility flag)         -> captured by trace.py
      - influence_score                          -> filled in later by attribution.py
      - severity / severity_components           -> filled in later by severity.py
      - explanation_worthy                       -> filled in later by severity.py (the gate)
    """

    step_id: int
    tick: int
    job_id: int
    job_priority: int
    job_deadline: int
    job_duration: int
    n_pending_jobs: int
    n_free_machines: int

    candidate_labels: list
    candidate_scores: list

    chosen_label: str
    chosen_score: float
    chosen_action: dict
    runner_up_label: Optional[str]
    runner_up_score: Optional[float]
    runner_up_action: Optional[dict]

    is_commit: bool  # True if the chosen action is "assign" or "reassign" (irreversible-ish)

    # Populated by later pipeline stages; left as None at capture time.
    influence_score: Optional[float] = None
    severity_components: Optional[dict] = None
    severity_score: Optional[float] = None
    explanation_worthy: Optional[bool] = None
    narration: Optional[str] = None  # filled in Phase 2

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Trajectory:
    steps: list = field(default_factory=list)   # list[DecisionStep]
    final_outcome: Optional[dict] = None         # filled in once the run completes

    def add(self, step: DecisionStep):
        self.steps.append(step)

    def to_dict(self) -> dict:
        return {
            "final_outcome": self.final_outcome,
            "steps": [s.to_dict() for s in self.steps],
        }

    def save_json(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_json(cls, path: str) -> "Trajectory":
        with open(path) as f:
            data = json.load(f)
        traj = cls(final_outcome=data.get("final_outcome"))
        for s in data["steps"]:
            traj.steps.append(DecisionStep(**s))
        return traj
