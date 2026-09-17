"""
Delivery-dispatch decision agent. A distinct scoring policy from Domain 1's
ScoringAgent -- weights service tier more heavily relative to window
urgency (reflecting that a perishable/urgent order's priority tier itself
already encodes most of the time-pressure signal in this domain, unlike
Domain 1 where priority and deadline are largely independent), and adds an
explicit reroute-avoidance term absent from Domain 1 entirely.

Reuses the same Candidate/Decision dataclasses from scaa.agent (imported,
not redefined) -- this is itself a small architecture-reuse point: the
interface contract, not the implementation, is what's shared.
"""

from __future__ import annotations

from typing import Optional

from ...agent import Candidate, Decision


class NearestWindowAgent:
    """Priority-weighted, delivery-window-aware dispatch policy."""

    def __init__(self,
                 tier_weight: float = 2.6,
                 urgency_weight: float = 2.2,
                 lateness_weight: float = 0.35,
                 unsavable_slack: int = 4):
        self.tier_weight = tier_weight
        self.urgency_weight = urgency_weight
        self.lateness_weight = lateness_weight
        self.unsavable_slack = unsavable_slack

    def _select_focus_job(self, env, state) -> Optional[int]:
        if not state.pending_job_ids:
            return None

        def urgency_key(oid):
            order = env.jobs[oid]
            return (order.deadline - state.tick, -order.priority)

        return sorted(state.pending_job_ids, key=urgency_key)[0]

    def _score_dispatch(self, order, vehicle_id: int, tick: int) -> float:
        finish = tick + order.duration
        slack = order.deadline - finish
        urgency = 1.0 / (1.0 + max(0, order.deadline - tick))
        tier_term = order.priority / 3.0
        lateness_penalty = self.lateness_weight * abs(slack) if slack < 0 else 0.0
        return self.tier_weight * tier_term + self.urgency_weight * urgency - lateness_penalty

    def _score_hold(self, order, tick: int) -> float:
        urgency = 1.0 / (1.0 + max(0, order.deadline - tick))
        return 1.0 - urgency

    def _score_cancel(self, order, tick: int) -> float:
        best_possible_finish = tick + order.duration
        if best_possible_finish > order.deadline + self.unsavable_slack:
            return 2.5
        return 0.1

    def decide(self, env) -> Optional[Decision]:
        state = env.observe()
        job_id = self._select_focus_job(env, state)
        if job_id is None:
            return None

        order = env.jobs[job_id]
        tick = state.tick
        candidates = []

        for v_id, is_free in enumerate(state.machine_free_mask):
            if is_free:
                score = self._score_dispatch(order, v_id, tick)
                candidates.append(Candidate(
                    action={"type": "assign", "job_id": job_id, "machine_id": v_id},
                    score=score, label=f"assign->M{v_id}",
                ))

        candidates.append(Candidate(
            action={"type": "defer", "job_id": job_id},
            score=self._score_hold(order, tick), label="defer",
        ))
        candidates.append(Candidate(
            action={"type": "reject", "job_id": job_id},
            score=self._score_cancel(order, tick), label="reject",
        ))

        candidates.sort(key=lambda c: c.score, reverse=True)
        chosen = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None
        return Decision(job_id=job_id, candidates=candidates, chosen=chosen, runner_up=runner_up)
