"""
Loader for real, published job-shop-scheduling benchmark instances in the
standard Taillard/JSPLIB text format (used by both Taillard's 1993 instances
and the Lawrence 1984 instances), fetched from the JSPLIB mirror
(github.com/tamy0612/JSPLIB), the standard open aggregation of these
classic OR-Library benchmark instance files.

Format (both ta*.txt and la*.txt files, after stripping comment lines
starting with '#'): first non-comment line is "n_jobs n_machines"; each
subsequent line lists that job's operation SEQUENCE as interleaved
(machine_id, duration) pairs, e.g. "2 15 0 21 1 55" means: this job's first
operation runs on machine 2 for 15 ticks, then machine 0 for 21 ticks, then
machine 1 for 55 ticks. Operations within a job are strictly ordered; a
job's operation k+1 cannot start before operation k finishes.

IMPORTANT HONESTY NOTE: the standard Taillard/Lawrence benchmark defines
ONLY processing times and machine orderings -- it is a makespan-minimization
benchmark and does NOT define job priorities or due dates. This project's
severity gate requires both (Impact, F, needs a priority and a deadline).
We therefore AUGMENT each loaded instance with:
  - a static priority tier (1-3), assigned by quartile of the job's TOTAL
    processing time (heavier jobs = less schedule slack = higher tier) --
    this is our own addition, not part of the published benchmark, and is
    reported as such everywhere this is discussed.
  - a synthetic due date = arrival (always 0, classical JSSP has no
    staggered arrivals) + total_processing_time * `due_date_factor`
    (default 1.6), a standard augmentation technique in the due-date-aware
    JSSP literature, not an invented ad hoc number.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class JSSPOperation:
    machine_id: int
    duration: int


@dataclass
class JSSPJobSpec:
    job_id: int
    operations: list  # list[JSSPOperation], in required execution order
    priority: int = 1
    deadline: int = 0

    @property
    def total_processing_time(self) -> int:
        return sum(op.duration for op in self.operations)


def load_taillard_instance(path: str, due_date_factor: float = 1.6) -> tuple:
    """
    Returns (jobs: list[JSSPJobSpec], n_machines: int, source_path: str).
    """
    with open(path) as f:
        lines = [l for l in f.read().splitlines() if l.strip() and not l.strip().startswith("#")]

    header = lines[0].split()
    n_jobs, n_machines = int(header[0]), int(header[1])

    jobs = []
    for j in range(n_jobs):
        tokens = [int(x) for x in lines[1 + j].split()]
        ops = []
        for i in range(0, len(tokens), 2):
            ops.append(JSSPOperation(machine_id=tokens[i], duration=tokens[i + 1]))
        jobs.append(JSSPJobSpec(job_id=j, operations=ops))

    # Priority tiers by quartile of total processing time (our augmentation, see module docstring)
    totals = sorted(job.total_processing_time for job in jobs)

    def tier_for(total):
        idx = totals.index(total)
        frac = idx / max(1, len(totals) - 1)
        if frac >= 0.66:
            return 3
        if frac >= 0.33:
            return 2
        return 1

    for job in jobs:
        job.priority = tier_for(job.total_processing_time)
        job.deadline = int(round(job.total_processing_time * due_date_factor))

    return jobs, n_machines, path


def list_bundled_instances(data_dir: str = None) -> list:
    """Lists the real benchmark instance files bundled with this project (data/taillard/)."""
    data_dir = data_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))), "data", "taillard")
    if not os.path.isdir(data_dir):
        return []
    return sorted(f for f in os.listdir(data_dir) if not f.startswith("."))
