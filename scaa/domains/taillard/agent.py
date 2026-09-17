"""
JSSP dispatching-rule agent, using Shortest-Processing-Time (SPT) as the
primary dispatch rule with priority-tier as a tie-break -- SPT is one of
the classic, widely-cited dispatching heuristics in the job-shop scheduling
literature (see e.g. Conway, Maxwell & Miller, 1967, *Theory of
Scheduling*), not an invented policy. Chosen specifically because it is a
well-known baseline in the SAME literature the Taillard/Lawrence benchmark
instances come from, making the "agent" side of this domain citable in the
same breath as the "environment/data" side.

At each decision point (a free machine with >=1 ready job competing for
it), candidates are the ready jobs, not machine choices -- the inverse of
Domains 1-3's structure, since in JSSP a job's machine is fixed by its
operation sequence, not chosen by the scheduler. See environment.py's
module docstring for why this makes Irreversibility (I) nearly constant in
this domain, an intentional and informative edge case.
"""

from __future__ import annotations

from typing import Optional

from ...agent import Candidate, Decision


class SPTDispatchAgent:
    """Shortest-Processing-Time dispatching rule, priority-tier tie-break."""

    def _first_machine_with_ready_job(self, env) -> Optional[int]:
        for m in env.machines:
            if m.is_free(env.tick):
                ready = env.ready_job_ids_for_machine(m.machine_id)
                if ready:
                    return m.machine_id
        return None

    def decide(self, env) -> Optional[Decision]:
        machine_id = self._first_machine_with_ready_job(env)
        if machine_id is None:
            return None

        ready_ids = env.ready_job_ids_for_machine(machine_id)
        candidates = []
        for jid in ready_ids:
            job = env.jobs[jid]
            # SPT: shorter operation duration scores higher (dispatched sooner);
            # priority tier is a secondary tie-break for equal-duration operations.
            score = (1.0 / (1.0 + job.duration)) * 2.5 + (job.priority / 3.0) * 0.5
            candidates.append(Candidate(
                action={"type": "assign", "job_id": jid, "machine_id": machine_id},
                score=score, label=f"assign_job_{jid}",
            ))

        candidates.sort(key=lambda c: c.score, reverse=True)
        chosen = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None
        chosen_job_id = chosen.action["job_id"]
        return Decision(job_id=chosen_job_id, candidates=candidates, chosen=chosen, runner_up=runner_up)
