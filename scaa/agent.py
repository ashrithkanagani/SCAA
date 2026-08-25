"""
Decision-making agent for the scheduling environment.

Phase 1 uses a transparent, weighted scoring policy rather than an LLM call.
This is a deliberate reproducibility choice: the attribution engine needs to
replay counterfactual trajectories many times, and a deterministic scoring
policy makes those replays exact and fast. Phase 2 adds an LLM narration
layer on top of the decisions this agent already makes; the agent's
*decision logic* does not need to be an LLM for the severity-gate research
question to be valid -- SCAA is agnostic to what produces the trajectory,
it only consumes (state, candidate actions, chosen action, confidence).

Each tick, the agent looks at the single most urgent pending job and scores
three families of candidate actions for it:
    - assign to machine m  (for every currently free machine)
    - defer
    - reject
It commits to the highest-scoring candidate. The runner-up candidate is
retained explicitly -- this is the "alternative action" used later by the
drop/hold-out attribution engine (attribution.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .environment import EnvState, Job, SchedulingEnvironment


@dataclass
class Candidate:
    action: dict
    score: float
    label: str  # human-readable, e.g. "assign->M2", "defer", "reject"


@dataclass
class Decision:
    job_id: int
    candidates: list            # list[Candidate], sorted descending by score
    chosen: Candidate
    runner_up: Optional[Candidate]


class ScoringAgent:
    """Weighted-heuristic scheduling policy. Deterministic given environment state."""

    def __init__(self,
                 priority_weight: float = 2.0,
                 urgency_weight: float = 3.0,
                 lateness_weight: float = 0.3,
                 unsavable_slack: int = 5):
        self.priority_weight = priority_weight
        self.urgency_weight = urgency_weight
        self.lateness_weight = lateness_weight
        self.unsavable_slack = unsavable_slack

    def _select_focus_job(self, env: SchedulingEnvironment, state: EnvState) -> Optional[int]:
        """Pick the single most urgent pending job to decide on this tick."""
        if not state.pending_job_ids:
            return None

        def urgency_key(jid):
            job = env.jobs[jid]
            return (job.deadline - state.tick, -job.priority)

        return sorted(state.pending_job_ids, key=urgency_key)[0]

    def _score_assign(self, job: Job, machine_id: int, tick: int) -> float:
        finish = tick + job.duration
        slack = job.deadline - finish
        urgency = 1.0 / (1.0 + max(0, job.deadline - tick))
        priority_term = job.priority / 3.0
        lateness_penalty = self.lateness_weight * abs(slack) if slack < 0 else 0.0
        return self.priority_weight * priority_term + self.urgency_weight * urgency - lateness_penalty

    def _score_defer(self, job: Job, tick: int) -> float:
        urgency = 1.0 / (1.0 + max(0, job.deadline - tick))
        return 1.0 - urgency

    def _score_reject(self, job: Job, tick: int) -> float:
        best_possible_finish = tick + job.duration
        if best_possible_finish > job.deadline + self.unsavable_slack:
            return 2.5
        return 0.1

    def decide(self, env: SchedulingEnvironment) -> Optional[Decision]:
        """
        Produce a full Decision (all scored candidates + chosen + runner-up)
        for the current tick's focus job, or None if there is nothing pending.
        """
        state = env.observe()
        job_id = self._select_focus_job(env, state)
        if job_id is None:
            return None

        job = env.jobs[job_id]
        tick = state.tick
        candidates = []

        for m_id, is_free in enumerate(state.machine_free_mask):
            if is_free:
                score = self._score_assign(job, m_id, tick)
                candidates.append(Candidate(
                    action={"type": "assign", "job_id": job_id, "machine_id": m_id},
                    score=score,
                    label=f"assign->M{m_id}",
                ))

        candidates.append(Candidate(
            action={"type": "defer", "job_id": job_id},
            score=self._score_defer(job, tick),
            label="defer",
        ))
        candidates.append(Candidate(
            action={"type": "reject", "job_id": job_id},
            score=self._score_reject(job, tick),
            label="reject",
        ))

        candidates.sort(key=lambda c: c.score, reverse=True)
        chosen = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None

        return Decision(job_id=job_id, candidates=candidates, chosen=chosen, runner_up=runner_up)


class GreedyEDFAgent:
    """
    A structurally DIFFERENT second policy, used only for Phase 3's
    cross-agent validation experiment: does the severity gate's behavior
    generalize beyond ScoringAgent's specific weighted heuristic, or is it
    an artifact of that one policy's particular score distribution?

    Classic greedy Earliest-Deadline-First: always focus on the pending job
    with the nearest deadline (ties broken by priority), and score
    candidates purely by deadline slack -- no tunable priority/urgency
    blend like ScoringAgent uses. This produces a genuinely different
    confidence-gap distribution (relevant to D) and a different mix of
    assign/defer/reject decisions (relevant to I), which is exactly the
    kind of variation a reviewer would want to see the gate tested against.

    Implements the same Candidate/Decision interface as ScoringAgent, so it
    plugs into simulate.py, attribution.py, and severity.py with zero
    changes to any of them -- itself a small architecture validation point
    (the pipeline is agent-agnostic by construction, not just by claim).
    """

    def __init__(self, unsavable_slack: int = 5):
        self.unsavable_slack = unsavable_slack

    def _select_focus_job(self, env, state):
        if not state.pending_job_ids:
            return None
        # Pure EDF: earliest deadline first, ties broken by priority (desc).
        return sorted(state.pending_job_ids,
                      key=lambda jid: (env.jobs[jid].deadline, -env.jobs[jid].priority))[0]

    def decide(self, env):
        state = env.observe()
        job_id = self._select_focus_job(env, state)
        if job_id is None:
            return None

        job = env.jobs[job_id]
        tick = state.tick
        candidates = []

        for m_id, is_free in enumerate(state.machine_free_mask):
            if is_free:
                slack = job.deadline - (tick + job.duration)
                # Pure slack-based score: more slack remaining = safer choice.
                # No priority term at all -- this is the key structural
                # difference from ScoringAgent's blended heuristic.
                score = -slack if slack < 0 else 1.0 / (1.0 + slack)
                candidates.append(Candidate(
                    action={"type": "assign", "job_id": job_id, "machine_id": m_id},
                    score=score,
                    label=f"assign->M{m_id}",
                ))

        candidates.append(Candidate(
            action={"type": "defer", "job_id": job_id},
            score=0.3,  # fixed, low -- EDF greedily prefers assigning when possible
            label="defer",
        ))
        best_possible_finish = tick + job.duration
        reject_score = 2.0 if best_possible_finish > job.deadline + self.unsavable_slack else 0.05
        candidates.append(Candidate(
            action={"type": "reject", "job_id": job_id},
            score=reject_score,
            label="reject",
        ))

        candidates.sort(key=lambda c: c.score, reverse=True)
        chosen = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None
        return Decision(job_id=job_id, candidates=candidates, chosen=chosen, runner_up=runner_up)
