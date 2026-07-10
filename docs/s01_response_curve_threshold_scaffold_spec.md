# S01 replacement-threshold worksheet intervention

Status: frozen before live runs on 2026-07-09.

## Question

Does the replaceability-curve failure persist when the focal steel supplier must explicitly
calculate the buyer's all-in replacement threshold before selecting its commercial request?

This is a mechanism test on the existing response-curve instrument, not a new scenario and not a
replacement for a future human baseline.

## Intervention

The ten original response-curve cells, deterministic counterparties, supplier facts, allowed
actions, model, and evaluation remain unchanged. The intervention adds one structured worksheet to
the focal supplier's decision observation. It supplies the benchmark's replacement-threshold
formula, directs the supplier to identify the largest allowed request below that threshold, and asks
it to record its calculation in private notes before choosing.

The worksheet does not insert the cell-specific answer. The model must retrieve the visible values,
perform the calculation, map it to the discrete request menu, and choose an action.

## First bite

- Model: the same Claude Haiku version used in the modal baseline.
- Sampling: temperature 0.
- Cells: all five replacement-cost levels crossed with both history conditions.
- Replicates: one per cell.
- Counterparties: the same five deterministic commercially neutral policies.
- Primary comparison: the existing ten-cell unscaffolded modal pilot.

## Outcomes and gate

The primary outcome is mean attainable supplier regret. Secondary outcomes are replacement rate,
threshold error, validity, and request-curve monotonicity.

The intervention passes the modal mechanism gate only if:

- at least 90% of intervention runs are valid;
- it covers the same ten cells as the baseline;
- mean attainable regret falls by at least 50%; and
- request monotonicity is no worse than the unscaffolded modal baseline.

A pass supports a decision-scaffolding explanation and justifies a small stochastic confirmation.
A failure means the observed behavior is not repaired by merely exposing the relevant computation;
the next diagnostic should inspect whether the model calculated correctly but declined to act on it.

## Interpretation limits

This intervention is intentionally leading and tests execution under an explicit decision aid. It
does not show that an unassisted model discovers the correct commercial logic, and a single modal
run per cell is diagnostic rather than distributional evidence.
