# Addendum — Narration Construct-Validity Fix

**Found by:** actually running the human-study pilot session (rater_3, balanced scenario, explain-everything condition) and trying to answer the quiz — not by code review or automated testing. This is worth stating explicitly in the paper: the flaw was caught by dogfooding the evaluation protocol, which is itself a small piece of evidence the evaluation design was taken seriously.

## What was wrong

Three related problems, all in `narration.py` and `human_study.py`:

1. **Question/answer mismatch.** Quiz questions asked *"Why did the agent choose X?"* — a question about the agent's own scheduling logic. The narration only ever answered *"Why did SCAA flag this decision?"* — a different question (severity-gate reasoning). No rater could correctly answer the question as asked, because the information given never addressed it.

2. **Structural monotony, not random bad luck.** `ScoringAgent._score_assign()` does not use `machine_id` in its scoring at all — every free machine gets an identical score for a given job. This means most `assign->Mx` vs `assign->My` comparisons are genuine ties, broken only by machine index. Since irreversibility (I) is high for essentially all `assign` actions, and this is the dominant action type in the `balanced` scenario, the old narration's "Flagged because... irreversibility... deviation..." sentence looked nearly identical across most decisions — not because of a text-generation bug, but because the underlying policy genuinely doesn't differentiate between tied machines, and the old narration never said so.

3. **False claims in the explain-everything condition.** The old narration said "Flagged because..." for every decision shown under `explain_all`, including the 18/27 decisions SCAA's own gate never actually flagged. This overstated what the gate had done.

## The fix

`narration.py` now produces two separate sentences per decision:
- **Sentence 1, always present:** the agent's own rationale for choosing this action over the runner-up, derived from the actual scoring policy's logic (tied machines / urgency vs. waiting / salvageable vs. not). For genuinely tied machine choices, it says so honestly ("Machines 1 and 2 were both free and scored identically... the scheduling policy does not distinguish between otherwise-idle machines") rather than inventing a fake machine-specific justification.
- **Sentence 2, conditional:** the severity-gate reasoning (I/F/D), included only if `step.explanation_worthy` is actually `True`. If the step is shown only because the explain-everything condition displays everything, this is now stated honestly instead of falsely claiming the step was flagged.

`human_study.py`'s quiz-question selection was also changed from pure random sampling to **stratified sampling across five comparison categories** (tied-machines, assign-over-defer, assign-over-reject, defer-over-assign, reject), so a 5-question quiz can no longer land on the same category 5 times by chance — verified on the exact session that exposed the bug: the regenerated quiz now spans 4 distinct categories across its 5 questions.

## Validation

- 4 new regression tests added to `tests/test_narration.py`, specifically encoding this bug so it cannot silently reappear: agent-rationale presence, honest tied-machine explanation, no false "flagged" claims on non-gated steps, correct "flagged" claims on gated steps.
- Full suite: **48/48 tests passing** (44 → 48).
- All human-study session files and answer keys regenerated with the fix; `reports/human_study/` now reflects the corrected version. **Any session files your teammates may have already started filling in from the old version should be discarded and redone from the regenerated files** — the old ones are not just cosmetically different, they are unanswerable as designed.

## Why this is worth a sentence in the paper, not just a changelog entry

This is genuine evidence of iterative empirical validation, in the same spirit as the two corrections already documented in `PHASE_1_REPORT.md` (the completion-detection bug, the irreversibility-collapse calibration issue). A methods section that says "we found and fixed X during pilot testing" reads as more rigorous than one that presents the final system as if it were correct on the first attempt — consider including a compressed version of this fix as a third example in whatever section of the paper discusses validation history.
