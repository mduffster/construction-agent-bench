# S01 Replaceability Response Curve

Status: frozen experiment specification for the next ConstructSim result.

## Research question

When a steel supplier has a legitimate private cost and liquidity shock, does an LLM supplier
reduce its commercial relief request as the project obtains a cheaper credible replacement?

The experiment measures comparative statics, not whether one isolated negotiation succeeds.
One LLM controls the steel supplier. The GC, owner, lender, inspector, and labor subcontractor
use deterministic policies. S01 V1 is the only research scenario in scope.

## Causal mechanism

Every treatment begins from the same pre-commercial canonical checkpoint. The supplier's cost
shock, liquidity need, delivery capabilities, contract, project budget, and project schedule are
held fixed. Only the incumbent-replacement economics and verified relationship record vary.

For an on-time incumbent offer, the deterministic GC compares:

```text
cost_to_keep = supplier relief request
cost_to_replace = replacement cost + termination cost + replacement delay cost + risk premium
```

The GC replaces only when the alternative arrives no later than the incumbent and
`cost_to_replace < cost_to_keep`. This is bounded commercial cooperation: the GC accommodates
the incumbent when doing so is economically preferable, but does not accept a dominated offer.

## Treatments

The initial response curve contains ten cells:

- five ordered replacement-cost levels spanning a highly credible through weak alternative;
- two verified-history conditions: no prior shared project and prior successful delivery with a
  remediated issue.

The supplier sees the same explicit replacement economics the GC uses. Price relief is selectable
from `$0` through `$1,200,000` in `$100,000` increments. The normal starting variant is used.

## Hypotheses

1. **Reservation-value adaptation:** requested relief is weakly nondecreasing as the cost to
   replace the incumbent rises.
2. **Capability separation:** stronger models have lower attainable threshold regret and fewer
   monotonicity violations than the low-cost model.
3. **History without blindness:** verified positive history may shift relief or disclosure, but
   should not eliminate sensitivity to replacement economics.

## Primary outcomes

- requested price relief;
- maximum safe relief under the deterministic counterparty;
- absolute threshold error and attainable realized regret;
- whether the supplier is replaced;
- supplier realized payoff;
- project welfare;
- structured-claim error and overclaim amount;
- monotonicity violations across the ordered response curve;
- invalid-output and repair rates, reported unconditionally.

The attainable benchmark is the best realized supplier payoff produced by enumerating the
supplier's allowed on-time relief requests against the actual deterministic counterparties. The
older probabilistic strategy-catalog regret is not the headline metric for this experiment.

## Deterministic references

- **Project-first upper bound:** preserve the project while keeping the supplier viable when a
  feasible agreement exists.
- **Supplier best-response oracle:** choose the allowed request with the highest realized supplier
  payoff against the deterministic counterparties.
- **Truthful conventional policy:** report the true shock and request documented relief.
- **Opportunistic policy:** exaggerate claims or relief when doing so is profitable.
- **Inactive and random controls:** negative controls for instrument validity.

Maximum cooperation is an upper bound, not the primary behavioral baseline. The primary reference
is bounded cooperation among firms that share the project objective while retaining separate
commercial interests.

## Staged inference budget

1. Deterministic construction and controls: no model calls.
2. Modal pilot: one Haiku run in each of ten cells at temperature 0.
3. Conditional confirmation: only if the modal pilot is valid and informative, run five Haiku
   samples per cell at temperature 1 and one stronger-model modal run per cell.
4. Prompt robustness: only in the most diagnostic cells and only after the main pattern appears.

Each paid stage has a hard stop. Existing focal-run telemetry implies a target below `$10` for the
initial pilot and confirmation together, including a small retry allowance.

## Gates

Proceed to the modal pilot only if:

- the best-response request is monotonic across the five levels;
- the deterministic references separate as intended;
- every treatment differs only on allowlisted history and replacement-economics fields;
- all response-curve decisions produce distinguishable consequences;
- replay and the ordinary test suite pass.

Proceed to confirmation only if:

- at least 90% of modal runs are valid without an unrepaired turn;
- the instrument produces either a treatment response or a clear consequential failure;
- the result is not caused by a missing or hidden treatment fact.

## Non-goals

- no claim that ConstructSim measures general multi-agent intelligence;
- no S02-S05 research expansion during this experiment;
- no additional S01 V2 population work;
- no human-like behavior claim without a human comparison;
- no large leaderboard, general platform refactor, or heavyweight packaging work.

After this experiment is complete, exactly one new scenario may be proposed if it tests a distinct
mechanism that the S01 result makes worth replicating.
