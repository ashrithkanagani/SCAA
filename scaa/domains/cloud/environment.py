"""
Domain 3: Cloud / Datacenter Compute Task Scheduling.

A fleet of servers must be provisioned to run a stream of incoming compute
tasks, each with an SLA tier (priority), a completion deadline, and an
estimated runtime. Provisioning a server to a task is treated as
irreversible in the sense that migrating a running task to another server
mid-execution is possible but costly (checkpoint/restore overhead, network
transfer of task state) -- a real cloud-operations cost, not a scheduling
abstraction invented for this project.

Distinct from Domain 1 and Domain 2 in its arrival/priority/deadline
distribution (SLA-tier-heavy, tighter completion windows than Domain 1's
scheduling task, looser than Domain 2's perishable-order windows) and in
its own agent policy (agent.py, this domain: an SLA-aware greedy policy
distinct from both ScoringAgent and NearestWindowAgent).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional

SLA_TIERS = (1, 2, 3)  # 1 = best-effort, 2 = standard, 3 = premium/latency-sensitive


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SLA_BREACHED = "sla_breached"
    DENIED = "denied"


@dataclass
class ComputeTask:
    job_id: int
    arrival_tick: int
    priority: int            # SLA tier
    deadline: int             # completion deadline (absolute tick)
    duration: int              # estimated runtime (ticks)
    status: TaskStatus = TaskStatus.PENDING
    server_id: Optional[int] = None
    start_tick: Optional[int] = None
    finish_tick: Optional[int] = None
    n_migrations: int = 0


@dataclass
class Server:
    server_id: int
    busy_until: int = -1
    current_task: Optional[int] = None

    def is_free(self, tick: int) -> bool:
        return tick > self.busy_until


@dataclass
class CloudEnvConfig:
    n_servers: int = 6
    n_tasks: int = 30
    sim_horizon: int = 50
    task_arrival_rate: float = 0.5
    migration_penalty: float = 12.0     # checkpoint/restore + network transfer cost
    breach_penalty_per_tick: float = 4.0
    seed: int = 42


@dataclass
class CloudState:
    tick: int
    pending_job_ids: list
    machine_free_mask: list
    n_completed: int
    n_breached: int
    n_denied: int
    cumulative_breach_penalty: float


class CloudEnvironment:
    """Deterministic discrete-event compute-task-scheduling simulator."""

    def __init__(self, config: CloudEnvConfig, task_schedule: Optional[list] = None):
        self.config = config
        self.task_schedule = task_schedule or self._generate_task_schedule()
        self.reset()

    def _generate_task_schedule(self) -> list:
        rng = random.Random(self.config.seed)
        schedule = []
        tid = 0
        for tick in range(self.config.sim_horizon):
            if rng.random() < self.config.task_arrival_rate:
                priority = rng.choice(SLA_TIERS)
                # premium/latency-sensitive tasks get the tightest SLA windows
                jitter = {1: (4, 12), 2: (3, 8), 3: (1, 4)}[priority]
                deadline = tick + rng.randint(*jitter)
                duration = rng.randint(1, 4)
                schedule.append(ComputeTask(job_id=tid, arrival_tick=tick, priority=priority,
                                             deadline=deadline, duration=duration))
                tid += 1
            if tid >= self.config.n_tasks:
                break
        return schedule

    def reset(self):
        self.tick = 0
        self.servers = [Server(server_id=i) for i in range(self.config.n_servers)]
        self.jobs = {
            t.job_id: ComputeTask(job_id=t.job_id, arrival_tick=t.arrival_tick, priority=t.priority,
                                   deadline=t.deadline, duration=t.duration)
            for t in self.task_schedule
        }
        self.pending_queue: list = []
        self.cumulative_breach_penalty = 0.0
        self.n_completed = 0
        self.n_breached = 0
        self.n_denied = 0
        self._admit_arrivals()

    def _admit_arrivals(self):
        for task in self.jobs.values():
            if task.arrival_tick == self.tick and task.status == TaskStatus.PENDING:
                if task.job_id not in self.pending_queue:
                    self.pending_queue.append(task.job_id)

    def observe(self) -> CloudState:
        return CloudState(
            tick=self.tick,
            pending_job_ids=list(self.pending_queue),
            machine_free_mask=[s.is_free(self.tick) for s in self.servers],
            n_completed=self.n_completed, n_breached=self.n_breached, n_denied=self.n_denied,
            cumulative_breach_penalty=self.cumulative_breach_penalty,
        )

    def done(self) -> bool:
        return self.tick >= self.config.sim_horizon and not self.pending_queue

    def apply_action(self, action: dict):
        """
        Action "type" values kept aligned with Domain 1's vocabulary
        (assign/defer/reject/reassign) for severity.py compatibility;
        domains/cloud/narration.py translates these into cloud-operations
        language: provision/queue/deny/migrate.
        """
        a_type = action["type"]
        job_id = action["job_id"]
        task = self.jobs[job_id]

        if a_type == "assign":
            server = self.servers[action["machine_id"]]
            assert server.is_free(self.tick)
            task.status = TaskStatus.RUNNING
            task.server_id = server.server_id
            task.start_tick = self.tick
            task.finish_tick = self.tick + task.duration
            server.busy_until = task.finish_tick
            server.current_task = job_id
            if job_id in self.pending_queue:
                self.pending_queue.remove(job_id)

        elif a_type == "defer":
            pass

        elif a_type == "reject":
            task.status = TaskStatus.DENIED
            self.n_denied += 1
            if job_id in self.pending_queue:
                self.pending_queue.remove(job_id)

        elif a_type == "reassign":
            old_server = self.servers[task.server_id]
            old_server.busy_until = self.tick - 1
            old_server.current_task = None
            task.n_migrations += 1
            new_server = self.servers[action["machine_id"]]
            task.server_id = new_server.server_id
            task.start_tick = self.tick
            task.finish_tick = self.tick + task.duration
            new_server.busy_until = task.finish_tick
            new_server.current_task = job_id
            self.cumulative_breach_penalty += self.config.migration_penalty
        else:
            raise ValueError(f"unknown action type {a_type}")

    def advance_tick(self):
        self.tick += 1
        for s in self.servers:
            if s.current_task is not None:
                task = self.jobs[s.current_task]
                if task.status == TaskStatus.RUNNING and task.finish_tick <= self.tick:
                    if task.finish_tick > task.deadline:
                        task.status = TaskStatus.SLA_BREACHED
                        lateness = task.finish_tick - task.deadline
                        self.cumulative_breach_penalty += lateness * self.config.breach_penalty_per_tick
                        self.n_breached += 1
                    else:
                        task.status = TaskStatus.COMPLETED
                    self.n_completed += 1
                    s.current_task = None
        self._admit_arrivals()

    def outcome_metrics(self) -> dict:
        return {
            "breach_penalty": self.cumulative_breach_penalty,
            "completed_tasks": self.n_completed - self.n_breached,
            "breached_tasks": self.n_breached,
            "denied_tasks": self.n_denied,
        }
