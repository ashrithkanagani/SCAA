"""
Named scenarios for cross-scenario evaluation.

Three scenarios (as promised at the start of the project), built as
parameterizations of the same industrial/IoT scheduling environment rather
than three separate simulators. This was a deliberate scope decision: three
independent environments would have tripled Phase 1's validation surface
for a 2-3 month solo-coded timeline with no proportional benefit to the
paper's actual claim, which is about the SEVERITY GATE generalizing across
difficulty/composition, not about the scheduling domain itself being novel.

  - BALANCED        : the default scenario used throughout Phase 1/2.
  - HIGH_CONTENTION  : fewer machines relative to job load and a higher
                       arrival rate -> irreversibility (I) should dominate,
                       since almost every commitment is scarce and costly.
  - SAFETY_CRITICAL  : a much higher proportion of priority-3 ("critical")
                       jobs with tighter deadlines -> impact (F) should
                       dominate, stress-testing the gate in a CPS-flavored
                       high-stakes regime.

Reported together, these three let the paper claim the gate's behavior
(gate rate, which component dominates, selection diversity vs baselines)
is sensitive to scenario composition in the DIRECTION you'd expect from the
formulas -- which is itself a validity check on the I/F/D design, not just
a robustness footnote.
"""

from __future__ import annotations

from .config import EnvironmentConfig

SCENARIOS = {
    "balanced": EnvironmentConfig(
        n_machines=4, n_jobs=25, sim_horizon=60,
        job_arrival_rate=0.4, priority_levels=(1, 2, 3),
        deadline_jitter=(3, 12), seed=42,
    ),
    "high_contention": EnvironmentConfig(
        n_machines=2, n_jobs=25, sim_horizon=60,
        job_arrival_rate=0.55, priority_levels=(1, 2, 3),
        deadline_jitter=(3, 10), seed=42,
    ),
    "safety_critical": EnvironmentConfig(
        n_machines=4, n_jobs=25, sim_horizon=60,
        job_arrival_rate=0.4, priority_levels=(2, 3, 3),  # skew heavily toward critical jobs
        deadline_jitter=(2, 6),  # tighter deadlines
        seed=42,
    ),
}


def get_scenario(name: str, seed: int = None) -> EnvironmentConfig:
    """Return a copy of the named scenario, optionally overriding its seed."""
    from dataclasses import replace
    if name not in SCENARIOS:
        raise ValueError(f"unknown scenario '{name}', choose from {list(SCENARIOS)}")
    cfg = SCENARIOS[name]
    return replace(cfg, seed=seed) if seed is not None else replace(cfg)
