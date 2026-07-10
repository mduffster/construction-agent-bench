# S01 trusted replacement-threshold intervention

Status: frozen before live runs on 2026-07-09.

## Question

When the harness supplies the correct all-in replacement threshold as a trusted fact, does the
focal steel supplier use that reservation value coherently in its commercial request?

This follows the failed replacement-threshold worksheet diagnostic. It is designed to remove fact
selection and arithmetic from the task while preserving the supplier's strategic choice.

## Intervention

The ten original response-curve cells, deterministic counterparties, supplier facts, allowed
actions, model, and evaluation remain unchanged. The focal supplier receives one additional trusted
harness fact: the cell's all-in replacement threshold. The prompt defines this as the amount above
which replacement is commercially cheaper for the buyer.

The prompt does not reveal the best request or the largest allowed request below the threshold. The
model must map the trusted continuous threshold to the discrete action menu and decide how to use it.

## First bite

- Model: the same Claude Haiku version used in the modal baseline and worksheet arm.
- Sampling: temperature 0.
- Cells: all five replacement-cost levels crossed with both history conditions.
- Replicates: one per cell.
- Primary comparison: the existing ten-cell unscaffolded modal pilot.
- Diagnostic comparison: the failed ten-cell threshold-worksheet arm.

## Outcomes and gate

The primary outcome is mean attainable supplier regret. Secondary outcomes are replacement rate,
threshold error, validity, and request-curve monotonicity.

The trusted-threshold arm passes its modal mechanism gate only if:

- at least 90% of runs are valid;
- it covers the same ten cells as the baseline;
- mean attainable regret falls by at least 50% relative to the unscaffolded modal baseline; and
- request monotonicity is no worse than the unscaffolded modal baseline.

A pass supports fact binding or arithmetic as an important bottleneck and justifies a small
stochastic confirmation. A failure indicates that access to a correct reservation value is not
sufficient to produce coherent commercial action.

## Conditional confirmation

Frozen after the modal gate passed and before confirmation calls on 2026-07-09.

- Sampling: temperature 1.
- Replicates: three per cell, 30 total runs.
- Primary comparison: the existing five-per-cell unscaffolded Haiku confirmation.
- Confirmation checks: at least 90% validity, at least a 50% reduction in mean attainable regret,
  fewer request-curve monotonicity violations, and a lower replacement rate than the unscaffolded
  confirmation.

This is a small robustness read, not a precise estimate of a behavioral distribution. No stronger
model arm or new scenario is authorized by this confirmation.

## Interpretation limits

This is an oracle-information intervention. It tests whether the agent can use a correct computed
fact, not whether it can discover or calculate that fact independently. One modal run per cell is a
diagnostic rather than distributional evidence.
