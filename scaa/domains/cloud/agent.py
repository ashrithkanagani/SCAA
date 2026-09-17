"""
Cloud task-scheduling decision agent. A third, distinct scoring policy:
SLA-tier-dominant (premium/latency-sensitive tasks are strongly preferred
for immediate provisioning almost regardless of slack), with a much softer
lateness penalty than Domain 1/2's agents -- reflecting that in cloud
scheduling, a task running slightly over deadline on a busy server is
often preferable to denying it outright (unlike a physical delivery, which
becomes genuinely undeliverable once its window closes).
"""

from __future__ import annotations

from typing import Optional

from ...agent import Candidate, Decision


class SLAAwareAgent:
    """SLA-tier-dominant compute task scheduling policy."""

    def __init__(self,
                 sla_weight: float = 3.2,
                 urgency_weight: float = 1.4,
                 lateness_weight: float = 0.15,
                 unsavable_slack: int = 6):
        self.sla_weight = sla_weight
        self.urgency_weight = urgency_weight
        self.lateness_weight = lateness_weight
        self.unsavable_slack = unsavable_slack

    def _select_focus_job(self, env, state) -> Optional[int]:
        if not state.pending_job_ids:
            return None

        def priority_key(tid):
            task = env.jobs[tid]
            return (-task.priority, task.deadline - state.tick)

        return sorted(state.pending_job_ids, key=priority_key)[0]

    def _score_provision(self, task, tick: int) -> float:
        finish = tick + task.duration
        slack = task.deadline - finish
        urgency = 1.0 / (1.0 + max(0, task.deadline - tick))
        sla_term = task.priority / 3.0
        lateness_penalty = self.lateness_weight * abs(slack) if slack < 0 else 0.0
        return self.sla_weight * sla_term + self.urgency_weight * urgency - lateness_penalty

    def _score_queue(self, task, tick: int) -> float:
        urgency = 1.0 / (1.0 + max(0, task.deadline - tick))
        return 1.0 - urgency

    def _score_deny(self, task, tick: int) -> float:
        best_possible_finish = tick + task.duration
        if best_possible_finish > task.deadline + self.unsavable_slack:
            return 2.0
        return 0.05

    def decide(self, env) -> Optional[Decision]:
        state = env.observe()
        job_id = self._select_focus_job(env, state)
        if job_id is None:
            return None

        task = env.jobs[job_id]
        tick = state.tick
        candidates = []

        for s_id, is_free in enumerate(state.machine_free_mask):
            if is_free:
                score = self._score_provision(task, tick)
                candidates.append(Candidate(
                    action={"type": "assign", "job_id": job_id, "machine_id": s_id},
                    score=score, label=f"assign->M{s_id}",
                ))

        candidates.append(Candidate(
            action={"type": "defer", "job_id": job_id},
            score=self._score_queue(task, tick), label="defer",
        ))
        candidates.append(Candidate(
            action={"type": "reject", "job_id": job_id},
            score=self._score_deny(task, tick), label="reject",
        ))

        candidates.sort(key=lambda c: c.score, reverse=True)
        chosen = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None
        return Decision(job_id=job_id, candidates=candidates, chosen=chosen, runner_up=runner_up)
