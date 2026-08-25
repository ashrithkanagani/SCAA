"""
Central configuration for SCAA.

All numbers that a reviewer might reasonably ask "why this value?" live here,
so that Phase 3's ablation study can sweep them systematically instead of
hunting through the codebase.
"""

from dataclasses import dataclass, field


@dataclass
class EnvironmentConfig:
    """Parameters defining the industrial/IoT scheduling simulation."""

    n_machines: int = 4
    n_jobs: int = 25
    sim_horizon: int = 60          # discrete time ticks
    job_arrival_rate: float = 0.4  # probability of a new job arriving per tick
    priority_levels: tuple = (1, 2, 3)      # 1 = low, 3 = critical (e.g. safety interlock job)
    deadline_jitter: tuple = (3, 12)        # min/max ticks-until-deadline at arrival
    reassignment_penalty: float = 8.0       # cost incurred if a committed job is reassigned
    sla_violation_penalty: float = 5.0      # cost per tick a job is late
    seed: int = 42


@dataclass
class SeverityWeights:
    """
    Tunable weights for the severity gate:

        S = w_irrev * I + w_impact * F + w_deviation * D

    I, F, D are each normalized to [0, 1] before weighting (see severity.py).
    These three weights are the primary ablation axis for Phase 3.
    """

    w_irrev: float = 0.4
    w_impact: float = 0.4
    w_deviation: float = 0.2

    # Decision is promoted to "explanation-worthy" if S exceeds this threshold.
    # 0.62 was chosen empirically on the default scenario to give a
    # meaningfully selective ~30% gate rate rather than near-100%; the full
    # threshold sweep (0.5-0.7) is exactly Phase 3's ablation study data.
    gate_threshold: float = 0.62

    # "absolute": flag steps with S >= gate_threshold (fixed, auditable, but
    #             not scenario-invariant -- see severity.py docstring).
    # "percentile": flag the top `gate_percentile` fraction of S scores
    #             within the trajectory (scenario-adaptive order-statistic
    #             threshold; see severity.py docstring).
    gate_mode: str = "absolute"
    gate_percentile: float = 0.30

    def normalized(self) -> "SeverityWeights":
        total = self.w_irrev + self.w_impact + self.w_deviation
        return SeverityWeights(
            w_irrev=self.w_irrev / total,
            w_impact=self.w_impact / total,
            w_deviation=self.w_deviation / total,
            gate_threshold=self.gate_threshold,
            gate_mode=self.gate_mode,
            gate_percentile=self.gate_percentile,
        )


@dataclass
class AttributionConfig:
    """Parameters for the drop/hold-out counterfactual attribution engine."""

    # Outcome metric used to score counterfactual trajectories.
    # One of: "sla_penalty" (lower is better -> influence is negated),
    #         "completed_jobs" (higher is better)
    outcome_metric: str = "sla_penalty"

    # Number of alternative candidate actions considered per hold-out replay.
    # 1 = only the "next-best" candidate; >1 averages over several alternatives.
    n_counterfactuals: int = 1


@dataclass
class PipelineConfig:
    env: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    weights: SeverityWeights = field(default_factory=SeverityWeights)
    attribution: AttributionConfig = field(default_factory=AttributionConfig)
    output_dir: str = "outputs"
