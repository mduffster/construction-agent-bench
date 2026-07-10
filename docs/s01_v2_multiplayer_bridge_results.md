# S01 V2 live multiplayer lineage bridge results

Status: **V2 QUALIFICATION COMPLETE — 2026-07-10**

Experiment ID: `s01_v2_live_multiplayer_ladder_v2`

Frozen code commit: `cdeff2cc329935ee7d7ec979299015bb8742ee8f`

Model: `claude-haiku-4-5-20251001`, temperature `0`, repair budget `1`

Protocol: `docs/s01_v2_multiplayer_bridge_spec.md`

Durable output: `outputs/s01_v2_multiplayer_ladder_v2_20260710`

## Headline

The cumulative ladder reached a valid project-success outcome with two, three, five, and all six
organizations run by Claude Haiku. Every rung exposed all six expected agent-facing data links,
realized all seven lineage links without clipping, and preserved a viable project path. The
five-live-role rung passed without repair after the lender's action/amount contract was made
explicit.

This qualifies the harness for a controlled live multiplayer experiment. It does not yet show that
the live population made good commercial decisions. Every live rung activated the expensive backup
path, finished four ticks later than the deterministic efficient reference, and failed the private
coalition-success criterion despite achieving project success.

## V1 interface qualification

The first frozen ladder, `s01_v2_live_multiplayer_ladder_v1`, ran on commit
`0c18b134c7d6a175b20537562742b64d839c5d42`. Its first two rungs were valid and lineage-complete.
The five-live-role rung stopped at lender B5 after one repair, and the full-six rung was never
called. The lender selected `PARTIAL_RELEASE`, a `$760,000` direct draw, and a `$190,000` escrow,
treating the separately displayed maxima as additive. Validation rejected the combination because
direct-release actions require zero escrow.

V2 added that action/amount coupling to the first observation, versioned the experiment and live
profile, and reran all four rungs from one clean commit. Payoffs, consequences, role mix, model,
temperature, and stop rules were unchanged. V1 cost `$0.612529` and remains part of the program
ledger rather than being discarded as an inconvenient run.

## V2 ladder outcomes

The deterministic reference used the efficient state-aware fixture for all organizations. Live
rungs cumulatively replaced fixture organizations with Claude Haiku at temperature `0`, with one
repair allowed per turn.

| Rung | Live roles | Valid | Project / coalition success | Whole-run repairs | Completion | Project cost | Model cost |
|---|---:|---|---|---:|---:|---:|---:|
| deterministic reference | 0 | yes | yes / yes | 0 | 41 | `$95.650M` | `$0` |
| `supplier_gc` | 2 | yes | yes / no | 0 | 45 | `$100.310M` | `$0.156916` |
| `add_inspector` | 3 | yes | yes / no | 0 | 45 | `$100.260M` | `$0.228316` |
| `add_owner_lender` | 5 | yes | yes / no | 0 | 45 | `$100.310M` | `$0.377859` |
| `full_six` | 6 | yes | yes / no | 3 | 45 | `$100.310M` | `$0.605392` |

The V2 ladder made `51` model calls, used `1,280,433` input tokens and `17,610` output tokens, and
cost `$1.368483`. Adding the conservative prior ledger, including V1, gives a program total of
`$8.476765`, `$1.523235` below the user's `$10` ceiling.

Across `48` live required decisions, `45` were valid on the first submission (`93.75%`) and all
`48` were ultimately valid.

## Lineage and conformance

All four live rungs recorded the same top-level lineage result:

- `6/6` expected agent-facing exposures;
- `7/7` operative constraints satisfied;
- `7/7` requested actions realized;
- zero realized clips and zero silent or unexplained clips;
- `lineage_complete = true`; and
- `viability_preserving_chain = true`.

The first three rungs passed every live required decision on the first submission: `6/6`, `9/9`,
and `15/15`. The full-six run passed `15/18` live decisions on the first submission and repaired all
three failures within the frozen one-repair budget:

1. labor omitted its initial capacity-offer decision;
2. the owner initially requested funding above the visible GC package request; and
3. the owner initially assigned GC and supplier cost shares above their schema maxima.

The lineage measure's own first-pass score remained `6/6` because those three repaired decisions
were outside the six agent-facing consumer links in its denominator. Whole-run conformance and
edge-level lineage should therefore remain separate reported measures.

## Decision-quality finding

The deterministic reference completed at tick `41`, cost `$95.650M`, and met every organization's
private-success threshold. Every live run instead converged on the same locally safe but expensive
Lot-A-only path:

| Decision surface | Efficient reference | Every live rung |
|---|---|---|
| supplier payment request | `$1.2M` | `$1.8M` |
| GC inspector route | all six submitted records, including Lot B | four clean Lot A records |
| GC initial backup posture | `NONE` | `RESERVE` |
| supplier cure | `FULL_SEQUENCE_CURE` | `LOT_A_CURE` |
| GC backup disposition | `DROP` | `MAINTAIN` |
| shipment | both lots | Lot A only |
| final inspection | both lots released at `$1.35M` | Lot A released; Lot B held at `$950K` |
| recovery | `PROCEED_PHASED` | `ACTIVATE_BACKUP` |

This was not a funding shortage. Every live run had `$1.75M` to `$2.14M` of execution funds against
the `$1.15M` full-sequence threshold; the efficient reference needed `$1.51M`. The narrower evidence
route and Lot-A-only cure kept Lot B from becoming ready. By the final GC recovery decision, backup
activation could therefore be a rational rescue of an already narrowed path rather than the
original mistake.

The live runs completed at tick `45`, incurred about `$3.52M` in backup costs, and ended between
`$100.26M` and `$100.31M`. In the all-live run, the owner, GC, and supplier missed their
private-success thresholds while labor, lender, and inspector met theirs.

That separation is the useful result: the harness can now distinguish a data-chain failure from a
valid but economically poor strategy. Here the chain worked, but the supplier and GC prematurely
narrowed the technical scope. The next research target is the earliest supplier-GC divergence, not
more transport plumbing or a downstream recovery choice whose feasible set has already collapsed.

## Interpretation boundary

There is one frozen temperature-zero trajectory per rung. These are qualification cases, not
behavioral frequencies, and the cumulative role additions do not identify an individual-role
effect. The study supports claims about executability, observability, repair localization, and this
specific trajectory. It does not support a population success rate or a claim that role count has
no effect. V1 and V2 also differed on repeated temperature-zero choices, so the hosted setting
should not be described as deterministic sampling.

Free-text grounding is also incomplete. In the full-six run, the lender messaged that escrow
"remains at `$400K`," while its structured cap was `$250K` and its actual escrow release was zero;
the message carried no structured claim for evaluation. That is a real instrumentation backlog,
but it is not the next experimental variable.

## Next gate: supplier-GC derived decision-state packet

Keep the normal S01 V2 state, with only the supplier and GC live and the other four organizations
using the same state-aware deterministic controls. Compare two interleaved, otherwise identical
arms with three Haiku trials per arm:

1. the current lineage-core observation; and
2. the same authorized facts plus a deterministic, attributed decision-state packet showing the
   eligible value supported by each routed document set, Lot A and full-sequence cash thresholds,
   hard versus provisional funding totals, and the applicable request, certification, and draw
   caps.

The packet must not recommend an action, reveal an efficient-fixture answer or hidden fact, or show
another organization's private payoff. Deterministic replay must first prove that every derived
value is correct and attributed to facts already authorized for that recipient.

Predeclare coalition success and backup activation as primary outcomes; document-supported
certification, full-sequence readiness, earliest divergence, final cost/tick regret, validity,
repairs, and lineage completeness are mechanism or secondary outcomes. Advance only if the packet
improves the efficient-path rate without reducing validity or lineage. Five- and six-live-role
confirmation should wait for that local gate.

At the observed `$0.156916` supplier-GC cost, six trials estimate to `$0.941496`; a conservative
`$0.17` per-run reserve is `$1.02`. That would project cumulative program spend to `$9.496765`,
preserving the existing `$9.50` hard cap and leaving about `$0.50` below the user ceiling. No calls
for this proposed gate are included in the current results.

This is a direct continuation of the two-agent handoff result: first establish that the right data
arrives, then test whether a compact decision structure helps an agent map that data to the right
choice.

## Derived-state packet gate outcome

Status: **COMPLETE — LOCAL GATE PASSED — 2026-07-10**

The six-run contrast is reported in
`docs/s01_v2_derived_state_packet_results.md`. The packet produced full-sequence cure, Lot B
readiness, both-lot shipment, and no backup activation in `3/3` treatment runs; controls produced
those outcomes in `0/3` runs and activated backup in `3/3`. Every run was valid, repair-free,
project-successful, and lineage-complete. Treatment finished four ticks earlier and about `$4.217M`
lower in mean project cost.

A pre-existing duplicate supplier recovery-spend deduction initially obscured coalition success.
The original runs remain archived unchanged; zero-call replay of the identical submissions through
the corrected accounting gives coalition success `0/3` control versus `3/3` treatment and passes
the predeclared local advancement rule.
