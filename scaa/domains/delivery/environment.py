"""
Domain 2: Delivery / Logistics Dispatch.

A fleet of delivery vehicles must be dispatched to fulfill a stream of
incoming orders, each with a service tier (priority), a delivery-window
close time (deadline), and an estimated delivery duration. Once a vehicle
is dispatched to an order, the commitment is treated as irreversible in the
same sense as Domain 1's machine assignment: rerouting a vehicle mid-route
to a different order is possible but penalized (a real logistics cost --
wasted fuel/time, a broken delivery promise to the original customer).

Structurally analogous to Domain 1's SchedulingEnvironment (vehicles play
the role of machines, orders play the role of jobs) but NOT a renamed
copy: order arrival/priority/deadline distributions differ, the action
set's real-world semantics differ (dispatch/hold/cancel/reroute vs.
assign/defer/reject/reassign), and the agent (agent.py, this domain) uses a
distinct scoring policy. This is a deliberate, documented scope decision --
see PHASE_4_REPORT.md -- Domain 4 (Taillard/JSSP) provides the more
structurally distinct third domain.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

SERVICE_TIERS = (1, 2, 3)  # 1 = standard, 2 = express, 3 = perishable/urgent


class OrderStatus(Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"
    LATE = "late"
    CANCELLED = "cancelled"


@dataclass
class Order:
    job_id: int
    arrival_tick: int
    priority: int          # service tier
    deadline: int           # delivery window close (absolute tick)
    duration: int            # estimated delivery time (ticks)
    status: OrderStatus = OrderStatus.PENDING
    vehicle_id: Optional[int] = None
    start_tick: Optional[int] = None
    finish_tick: Optional[int] = None
    n_reroutes: int = 0


@dataclass
class Vehicle:
    vehicle_id: int
    busy_until: int = -1
    current_order: Optional[int] = None

    def is_free(self, tick: int) -> bool:
        return tick > self.busy_until


@dataclass
class DeliveryEnvConfig:
    n_vehicles: int = 5
    n_orders: int = 25
    sim_horizon: int = 55
    order_arrival_rate: float = 0.42
    reroute_penalty: float = 10.0     # cost of a mid-route reassignment
    late_penalty_per_tick: float = 6.0
    seed: int = 42


@dataclass
class DeliveryState:
    tick: int
    pending_job_ids: list
    machine_free_mask: list   # kept as "machine_free_mask" for interface compatibility with common.py
    n_delivered: int
    n_late: int
    n_cancelled: int
    cumulative_late_penalty: float


class DeliveryEnvironment:
    """Deterministic discrete-event delivery-dispatch simulator."""

    def __init__(self, config: DeliveryEnvConfig, order_schedule: Optional[list] = None):
        self.config = config
        self.order_schedule = order_schedule or self._generate_order_schedule()
        self.reset()

    def _generate_order_schedule(self) -> list:
        rng = random.Random(self.config.seed)
        schedule = []
        oid = 0
        for tick in range(self.config.sim_horizon):
            if rng.random() < self.config.order_arrival_rate:
                priority = rng.choice(SERVICE_TIERS)
                # perishable/urgent orders get tighter windows; standard gets looser ones
                jitter = {1: (5, 14), 2: (3, 9), 3: (2, 5)}[priority]
                deadline = tick + rng.randint(*jitter)
                duration = rng.randint(2, 5)
                schedule.append(Order(job_id=oid, arrival_tick=tick, priority=priority,
                                       deadline=deadline, duration=duration))
                oid += 1
            if oid >= self.config.n_orders:
                break
        return schedule

    def reset(self):
        self.tick = 0
        self.vehicles = [Vehicle(vehicle_id=i) for i in range(self.config.n_vehicles)]
        self.jobs = {
            o.job_id: Order(job_id=o.job_id, arrival_tick=o.arrival_tick, priority=o.priority,
                             deadline=o.deadline, duration=o.duration)
            for o in self.order_schedule
        }
        self.pending_queue: list = []
        self.cumulative_late_penalty = 0.0
        self.n_delivered = 0
        self.n_late = 0
        self.n_cancelled = 0
        self._admit_arrivals()

    def _admit_arrivals(self):
        for order in self.jobs.values():
            if order.arrival_tick == self.tick and order.status == OrderStatus.PENDING:
                if order.job_id not in self.pending_queue:
                    self.pending_queue.append(order.job_id)

    def observe(self) -> DeliveryState:
        return DeliveryState(
            tick=self.tick,
            pending_job_ids=list(self.pending_queue),
            machine_free_mask=[v.is_free(self.tick) for v in self.vehicles],
            n_delivered=self.n_delivered, n_late=self.n_late, n_cancelled=self.n_cancelled,
            cumulative_late_penalty=self.cumulative_late_penalty,
        )

    def done(self) -> bool:
        return self.tick >= self.config.sim_horizon and not self.pending_queue

    def apply_action(self, action: dict):
        """
        action = {"type": "dispatch", "job_id": int, "machine_id": int}
               | {"type": "defer",  "job_id": int}
               | {"type": "reject", "job_id": int}
               | {"type": "reassign", "job_id": int, "machine_id": int}
        (action "type" values kept aligned with Domain 1's vocabulary --
        assign/defer/reject/reassign -- purely so severity.py's
        `_IRREVERSIBILITY_BASE` action-type lookup table applies unmodified;
        the domain's OWN narration layer, domains/delivery/narration.py,
        translates these back into delivery language: "dispatch"/"hold"/
        "cancel"/"reroute".)
        """
        a_type = action["type"]
        job_id = action["job_id"]
        order = self.jobs[job_id]

        if a_type == "assign":
            vehicle = self.vehicles[action["machine_id"]]
            assert vehicle.is_free(self.tick)
            order.status = OrderStatus.DISPATCHED
            order.vehicle_id = vehicle.vehicle_id
            order.start_tick = self.tick
            order.finish_tick = self.tick + order.duration
            vehicle.busy_until = order.finish_tick
            vehicle.current_order = job_id
            if job_id in self.pending_queue:
                self.pending_queue.remove(job_id)

        elif a_type == "defer":
            pass

        elif a_type == "reject":
            order.status = OrderStatus.CANCELLED
            self.n_cancelled += 1
            if job_id in self.pending_queue:
                self.pending_queue.remove(job_id)

        elif a_type == "reassign":
            old_vehicle = self.vehicles[order.vehicle_id]
            old_vehicle.busy_until = self.tick - 1
            old_vehicle.current_order = None
            order.n_reroutes += 1
            new_vehicle = self.vehicles[action["machine_id"]]
            order.vehicle_id = new_vehicle.vehicle_id
            order.start_tick = self.tick
            order.finish_tick = self.tick + order.duration
            new_vehicle.busy_until = order.finish_tick
            new_vehicle.current_order = job_id
            self.cumulative_late_penalty += self.config.reroute_penalty
        else:
            raise ValueError(f"unknown action type {a_type}")

    def advance_tick(self):
        self.tick += 1
        for v in self.vehicles:
            if v.current_order is not None:
                order = self.jobs[v.current_order]
                if order.status == OrderStatus.DISPATCHED and order.finish_tick <= self.tick:
                    if order.finish_tick > order.deadline:
                        order.status = OrderStatus.LATE
                        lateness = order.finish_tick - order.deadline
                        self.cumulative_late_penalty += lateness * self.config.late_penalty_per_tick
                        self.n_late += 1
                    else:
                        order.status = OrderStatus.DELIVERED
                    self.n_delivered += 1
                    v.current_order = None
        self._admit_arrivals()

    def outcome_metrics(self) -> dict:
        return {
            "late_penalty": self.cumulative_late_penalty,
            "delivered_orders": self.n_delivered - self.n_late,
            "late_orders": self.n_late,
            "cancelled_orders": self.n_cancelled,
        }
