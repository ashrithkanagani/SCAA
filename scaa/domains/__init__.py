"""
Phase 4: cross-domain generalization.

Each subpackage here (delivery, cloud, taillard) is a self-contained
environment + agent for a genuinely different sequential decision domain.
None of them modify scaa/severity.py -- the severity gate's core functions
(compute_irreversibility, compute_impact, compute_deviation,
apply_severity_gate) are already domain-agnostic by construction (they only
ever read generic DecisionStep fields: action type, duration, priority,
deadline, tick, chosen/runner-up score) and are imported and reused
VERBATIM by every domain below. That reuse is the actual empirical claim
being tested in Phase 4 -- not "we built three environments," but "the same
15 lines of gate logic, unmodified, produce a sensible selective-explanation
signal across three unrelated decision domains."

common.py provides the one piece of infrastructure that Domain 1 (Phase
1-3) did not need to expose generically: a domain-agnostic simulation loop
and a domain-agnostic deviation-calibration routine, both parameterized by
an `env_factory` callable rather than a hardcoded environment class.
"""
