"""
Industrial / IoT scheduling environment.

Scenario: a fleet of machines (e.g. CNC cells, robotic arms, edge-compute
workers) must be allocated to a stream of incoming jobs. Each job has a
priority level, a deadline, and a processing duration. Once a job is
DISPATCHED (assigned + started on a machine) the commitment is treated as
irreversible: undoing it later (REASSIGN) incurs a real penalty, mirroring
real industrial constraints (a robot mid-weld cannot costlessly switch tasks).

This environment is fully deterministic given a seed: the job arrival
schedule is pre-generated independently of agent actions, which is what
makes counterfactual replay (attribution.py) valid -- upstream arrivals
never depend on what the agent chooses to do.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .config import EnvironmentConfig


class JobStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"      # committed to a machine, irreversible under normal cost
    COMPLETED = "completed"
    LATE = "late"
    REJECTED = "rejected"


@dataclass
class Job:
    job_id: int
    arrival_tick: int
    priority: int              # 1 (low) .. 3 (critical, e.g. safety interlock)
    deadline: int              # absolute tick by which it should complete
    duration: int              # ticks required on a machine
    status: JobStatus = JobStatus.PENDING
    machine_id: Optional[int] = None
    start_tick: Optional[int] = None
    finish_tick: Optional[int] = None
    n_reassignments: int = 0


@dataclass
class Machine:
    machine_id: int
    busy_until: int = -1
    current_job: Optional[int] = None

    def is_free(self, tick: int) -> bool:
        return tick > self.busy_until


@dataclass
class EnvState:
    """A lightweight, serializable snapshot of the world at a given tick."""
    tick: int
    pending_job_ids: list
    machine_free_mask: list          # bool per machine
    n_completed: int
    n_late: int
    n_rejected: int
    cumulative_sla_penalty: float


class SchedulingEnvironment:
    """
    Deterministic discrete-event scheduling simulator.

    Usage:
        env = SchedulingEnvironment(config)
        env.reset()
        while not env.done():
            obs = env.observe()
            ...agent picks an action...
            env.apply_action(action)
            env.advance_tick()
    """

    def __init__(self, config: EnvironmentConfig, job_schedule: Optional[list] = None):
        self.config = config
        self._rng = random.Random(config.seed)
        self.job_schedule = job_schedule or self._generate_job_schedule()
        self.reset()

    # ------------------------------------------------------------------
    # Setup / determinism
    # ------------------------------------------------------------------

    def _generate_job_schedule(self) -> list:
        """
        Pre-generate all job arrivals independent of any agent action.
        This independence is what makes hold-out counterfactual replay valid:
        replaying with a different action at step i never changes which jobs
        arrive later.
        """
        rng = random.Random(self.config.seed)
        schedule = []
        job_id = 0
        for tick in range(self.config.sim_horizon):
            if rng.random() < self.config.job_arrival_rate:
                priority = rng.choice(self.config.priority_levels)
                jitter_lo, jitter_hi = self.config.deadline_jitter
                deadline = tick + rng.randint(jitter_lo, jitter_hi)
                duration = rng.randint(2, 6)
                schedule.append(
                    Job(
                        job_id=job_id,
                        arrival_tick=tick,
                        priority=priority,
                        deadline=deadline,
                        duration=duration,
                    )
                )
                job_id += 1
            if job_id >= self.config.n_jobs:
                break
        return schedule

    def reset(self):
        self.tick = 0
        self.machines = [Machine(machine_id=i) for i in range(self.config.n_machines)]
        # deep-ish copy of jobs so repeated resets/replays don't share mutable state
        self.jobs = {
            j.job_id: Job(
                job_id=j.job_id,
                arrival_tick=j.arrival_tick,
                priority=j.priority,
                deadline=j.deadline,
                duration=j.duration,
            )
            for j in self.job_schedule
        }
        self.pending_queue: list = []
        self.cumulative_sla_penalty = 0.0
        self.n_completed = 0
        self.n_late = 0
        self.n_rejected = 0
        self._admit_arrivals()

    def clone_from(self, other: "SchedulingEnvironment"):
        """Deep-copy world state from another environment instance (used for replay branching)."""
        import copy
        self.tick = other.tick
        self.machines = copy.deepcopy(other.machines)
        self.jobs = copy.deepcopy(other.jobs)
        self.pending_queue = list(other.pending_queue)
        self.cumulative_sla_penalty = other.cumulative_sla_penalty
        self.n_completed = other.n_completed
        self.n_late = other.n_late
        self.n_rejected = other.n_rejected

    def _admit_arrivals(self):
        for job in self.jobs.values():
            if job.arrival_tick == self.tick and job.status == JobStatus.PENDING:
                if job.job_id not in self.pending_queue:
                    self.pending_queue.append(job.job_id)

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def observe(self) -> EnvState:
        return EnvState(
            tick=self.tick,
            pending_job_ids=list(self.pending_queue),
            machine_free_mask=[m.is_free(self.tick) for m in self.machines],
            n_completed=self.n_completed,
            n_late=self.n_late,
            n_rejected=self.n_rejected,
            cumulative_sla_penalty=self.cumulative_sla_penalty,
        )

    def done(self) -> bool:
        return self.tick >= self.config.sim_horizon and not self.pending_queue

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def apply_action(self, action: dict):
        """
        action = {"type": "assign", "job_id": int, "machine_id": int}
               | {"type": "defer",  "job_id": int}
               | {"type": "reject", "job_id": int}
               | {"type": "reassign", "job_id": int, "machine_id": int}   # penalized, rare
        """
        a_type = action["type"]
        job_id = action["job_id"]
        job = self.jobs[job_id]

        if a_type == "assign":
            machine = self.machines[action["machine_id"]]
            assert machine.is_free(self.tick), "attempted to assign to a busy machine"
            job.status = JobStatus.ASSIGNED
            job.machine_id = machine.machine_id
            job.start_tick = self.tick
            job.finish_tick = self.tick + job.duration
            machine.busy_until = job.finish_tick
            machine.current_job = job_id
            if job_id in self.pending_queue:
                self.pending_queue.remove(job_id)

        elif a_type == "defer":
            pass  # stays in pending_queue, re-evaluated next tick

        elif a_type == "reject":
            job.status = JobStatus.REJECTED
            self.n_rejected += 1
            if job_id in self.pending_queue:
                self.pending_queue.remove(job_id)

        elif a_type == "reassign":
            # Irreversibility violation: costly to undo a committed assignment.
            old_machine = self.machines[job.machine_id]
            old_machine.busy_until = self.tick - 1
            old_machine.current_job = None
            job.n_reassignments += 1
            new_machine = self.machines[action["machine_id"]]
            job.machine_id = new_machine.machine_id
            job.start_tick = self.tick
            job.finish_tick = self.tick + job.duration
            new_machine.busy_until = job.finish_tick
            new_machine.current_job = job_id
            self.cumulative_sla_penalty += self.config.reassignment_penalty
        else:
            raise ValueError(f"unknown action type {a_type}")

    def advance_tick(self):
        self.tick += 1
        # complete jobs whose machine has finished processing by this tick
        for m in self.machines:
            if m.current_job is not None:
                job = self.jobs[m.current_job]
                if job.status == JobStatus.ASSIGNED and job.finish_tick <= self.tick:
                    if job.finish_tick > job.deadline:
                        job.status = JobStatus.LATE
                        lateness = job.finish_tick - job.deadline
                        self.cumulative_sla_penalty += lateness * self.config.sla_violation_penalty
                        self.n_late += 1
                    else:
                        job.status = JobStatus.COMPLETED
                    self.n_completed += 1
                    m.current_job = None
        self._admit_arrivals()

    # ------------------------------------------------------------------
    # Outcome metrics (used by the attribution engine)
    # ------------------------------------------------------------------

    def outcome_metrics(self) -> dict:
        return {
            "sla_penalty": self.cumulative_sla_penalty,
            "completed_jobs": self.n_completed - self.n_late,
            "late_jobs": self.n_late,
            "rejected_jobs": self.n_rejected,
        }
