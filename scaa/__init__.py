"""
SCAA: Selective Causal Auditing for Agentic Systems
-----------------------------------------------------
A severity-gated explanation framework for sequential agent decisions
in safety-critical settings, evaluated on an industrial/IoT scheduling task.

Phase 1 modules (this package):
    environment.py  - discrete-event simulation of an industrial/IoT scheduling task
    agent.py        - decision-making policy agent that acts in the environment
    trace.py        - data schema for capturing per-step decision traces
    attribution.py  - drop/hold-out counterfactual influence scoring
    severity.py     - the novel severity gate: Irreversibility + Impact + Deviation -> S
    pipeline.py     - orchestrates: run agent -> capture trace -> attribute -> score severity
"""

__version__ = "0.1.0-phase1"
