"""
Domain 4: Job-Shop Scheduling on real Taillard/Lawrence benchmark instances.

The most structurally distinct of the four domains. Unlike Domains 1-3
(where a job needs exactly one resource commitment), a JSSP job is a fixed
SEQUENCE of operations, each requiring a SPECIFIC machine (not a free
choice of machine), and operation k+1 cannot start until operation k
finishes. The scheduling decision at each point is therefore a DISPATCHING
decision: when a machine frees up and more than one job's next operation is
ready for it, which job goes first.

Consequence for the severity gate: every decision here is a genuine
irreversible commitment (no analog of "defer" or "reject" exists in
classical JSSP -- all operations must eventually run), so Irreversibility
(I) is high and nearly uniform across every decision in this domain by
construction. This is a deliberate, informative edge case for the paper's
discussion section: it demonstrates what the gate degenerates to when I
carries little discriminative signal, throwing the analytical weight onto
Impact (F) and Deviation (D) instead -- see PHASE_4_REPORT.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class JSSPMachine:
    machine_id: int
    busy_until: int = -1
    current_job: Optional[int] = None

    def is_free(self, tick: int) -> bool:
        return tick > self.busy_until


@dataclass
class JSSPRuntimeJob:
    job_id: int
    operations: list       # list[JSSPOperation] (loader.py), fixed order
    priority: int
    deadline: int
    op_index: int = 0        # index of the NEXT operation to run
    finish_tick: Optional[int] = None  # when the CURRENT/last-dispatched op finishes
    status: str = "pending"   # pending | running | completed | breached

    @property
    def duration(self) -> int:
        """Duration of the CURRENT (next-to-dispatch) operation -- this is
        what feeds severity.py's Irreversibility scaling, consistent with
        every other domain's convention of 'duration = how long this
        specific commitment holds the resource'."""
        if self.op_index < len(self.operations):
            return self.operations[self.op_index].duration
        return 0

    @property
    def current_machine(self) -> Optional[int]:
        if self.op_index < len(self.operations):
            return self.operations[self.op_index].machine_id
        return None

    @property
    def is_finished(self) -> bool:
        return self.op_index >= len(self.operations)


@dataclass
class JSSPState:
    tick: int
    pending_job_ids: list
    machine_free_mask: list
    n_completed: int
    n_breached: int
    cumulative_breach_penalty: float


class JSSPEnvironment:
    """
    Deterministic discrete-event JSSP simulator driven by a real (or
    synthetically-augmented-with-priority/deadline) benchmark instance.
    """

    def __init__(self, jobs, n_machines: int, breach_penalty_per_tick: float = 3.0,
                 sim_horizon_padding: int = 50):
        self.n_machines = n_machines
        self.breach_penalty_per_tick = breach_penalty_per_tick
        self._job_specs = jobs
        # generous horizon: sum of all processing time is a safe upper bound on makespan
        self.sim_horizon = sum(j.total_processing_time for j in jobs) + sim_horizon_padding
        self.reset()

    def reset(self):
        self.tick = 0
        self.machines = [JSSPMachine(machine_id=i) for i in range(self.n_machines)]
        self.jobs = {
            j.job_id: JSSPRuntimeJob(job_id=j.job_id, operations=j.operations,
                                      priority=j.priority, deadline=j.deadline)
            for j in self._job_specs
        }
        self.n_completed = 0
        self.n_breached = 0
        self.cumulative_breach_penalty = 0.0

    def ready_job_ids_for_machine(self, machine_id: int) -> list:
        ready = []
        for job in self.jobs.values():
            if job.status in ("pending",) and not job.is_finished and job.current_machine == machine_id:
                ready.append(job.job_id)
        return ready

    def observe(self) -> JSSPState:
        # "pending_job_ids" here means: jobs with at least one ready operation
        # on SOME currently-free machine (a decision point exists).
        pending = []
        for m in self.machines:
            if m.is_free(self.tick):
                pending.extend(self.ready_job_ids_for_machine(m.machine_id))
        return JSSPState(
            tick=self.tick,
            pending_job_ids=sorted(set(pending)),
            machine_free_mask=[m.is_free(self.tick) for m in self.machines],
            n_completed=self.n_completed, n_breached=self.n_breached,
            cumulative_breach_penalty=self.cumulative_breach_penalty,
        )

    def done(self) -> bool:
        all_finished = all(j.is_finished for j in self.jobs.values())
        return all_finished or self.tick >= self.sim_horizon

    def apply_action(self, action: dict):
        """action = {"type": "assign", "job_id": int, "machine_id": int}. This
        is the ONLY action type in this domain -- see module docstring."""
        assert action["type"] == "assign"
        job_id, machine_id = action["job_id"], action["machine_id"]
        job = self.jobs[job_id]
        machine = self.machines[machine_id]
        assert machine.is_free(self.tick) and job.current_machine == machine_id

        duration = job.duration
        job.status = "running"
        job.finish_tick = self.tick + duration
        machine.busy_until = job.finish_tick
        machine.current_job = job_id

    def advance_tick(self):
        self.tick += 1
        for m in self.machines:
            if m.current_job is not None:
                job = self.jobs[m.current_job]
                if job.status == "running" and job.finish_tick is not None and job.finish_tick <= self.tick:
                    job.op_index += 1
                    m.current_job = None
                    if job.is_finished:
                        if job.finish_tick > job.deadline:
                            job.status = "breached"
                            lateness = job.finish_tick - job.deadline
                            self.cumulative_breach_penalty += lateness * self.breach_penalty_per_tick
                            self.n_breached += 1
                        else:
                            job.status = "completed"
                        self.n_completed += 1
                    else:
                        job.status = "pending"  # ready for its NEXT operation

    def outcome_metrics(self) -> dict:
        makespan = max((j.finish_tick or 0 for j in self.jobs.values()), default=0)
        return {
            "breach_penalty": self.cumulative_breach_penalty,
            "completed_jobs": self.n_completed - self.n_breached,
            "breached_jobs": self.n_breached,
            "makespan": makespan,
        }
