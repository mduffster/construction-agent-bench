# Trusted replacement-threshold modal diagnostic

*Preliminary modal mechanism test; frozen before live runs on 2026-07-09.*

## Result

Supplying the correct all-in replacement threshold as a trusted harness fact produced a sharp
improvement relative to the unassisted modal baseline:

| Measure | Unassisted | Trusted threshold |
|---|---:|---:|
| Valid runs | 10/10 | 10/10 |
| Mean attainable regret | $720,000 | $72,000 |
| Supplier replaced | 60% | 0% |
| Monotonicity violations | 1 | 0 |

Mean attainable regret fell **90%**, so all four precommitted mechanism-gate checks passed.

The intervention perfectly matched the discrete safe request in R1 and R2, stayed safely below the
frontier in R3, and then returned to an $800,000 request in R4 and R5. It therefore eliminated
catastrophic over-asking without fully optimizing the supplier's upside at high replacement costs.

## Interpretation

The contrast between the two interventions localizes much of the original failure. Merely showing
the formula did not work: none of nine valid worksheet runs calculated the correct threshold. Giving
the computed threshold directly did work: the request curve became monotonic, no supplier was
replaced, and avoidable loss fell sharply. Fact binding and arithmetic execution are therefore
important bottlenecks, while the remaining high-level under-asking suggests a separate anchoring or
conservatism effect.

The passed modal gate authorizes only the small stochastic confirmation specified in
`docs/s01_response_curve_trusted_threshold_spec.md`.

## Stochastic confirmation

The frozen three-per-cell confirmation reproduced the modal result:

| Measure | Unassisted confirmation | Trusted-threshold confirmation |
|---|---:|---:|
| Valid runs | 46/50 | 30/30 |
| Mean attainable regret | $594,783 | $72,000 |
| Supplier replaced | 52.2% | 0% |
| Monotonicity violations | 4 | 0 |

Mean attainable regret fell **87.9%**. All four confirmation checks passed. Across the six valid
runs at each curve level, requests were:

- R1: $200,000 in 6/6;
- R2: $500,000 in 5/6 and $400,000 in 1/6;
- R3: $600,000 in 6/6;
- R4: $800,000 in 6/6; and
- R5: $800,000 in 6/6.

The confirmation reinforces the two-part interpretation: a trusted reservation value prevents
destructive over-asking and restores a monotonic response, but a persistent $800,000 recovery anchor
still leaves bargaining surplus unclaimed when the buyer's outside option is expensive.
