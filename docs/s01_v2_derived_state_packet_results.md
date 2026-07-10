# S01 V2 supplier-GC derived-state packet results

Status: **COMPLETE — LOCAL MECHANISM GATE PASSED — 2026-07-10**

Experiment ID: `s01_v2_supplier_gc_derived_state_packet_v1`

Frozen live-run commit: `a797246f8a3fdc8e027d8ddc91a0a14c5fd6650f`

Accounting-correction replay commit: `da13b40b380b117392eeba3bd4d1087574aa22a7`

Protocol: `docs/s01_v2_derived_state_packet_protocol.md`

Archived live outputs: `outputs/s01_v2_derived_state_packet_v1_20260710`

Zero-call accounting replay:
`outputs/s01_v2_derived_state_packet_v1_20260710/posthoc_supplier_payoff_accounting_replay`

## Headline

A compact post-R1 decision-state packet changed the live supplier-GC trajectory in all three
paired periods. Every control chose a Lot-A-only cure and later activated backup. Every treatment
chose the full-sequence cure, made Lot B ready at tick 18, shipped both lots, and avoided backup
activation.

All six runs remained valid, repair-free, project-successful, and lineage-complete. Treatment
finished at tick `41` rather than `45` and reduced mean project cost from `$100.310M` to
`$96.093M`, a mean difference of about `$4.217M` in this scenario.

The predeclared local advancement rule passes after correcting a pre-existing supplier-payoff
accounting defect and replaying the archived submissions with zero model calls. This is a strong
scenario-specific mechanism result, not a population estimate or a general claim about structured
prompts.

## Frozen outcome table

| Measure | Current observation | Derived-state packet |
|---|---:|---:|
| Assigned runs | `3` | `3` |
| Valid / repair-free | `3/3` / `3/3` | `3/3` / `3/3` |
| Lineage-complete | `3/3` | `3/3` |
| Project success | `3/3` | `3/3` |
| Full-sequence cure at B1 | `0/3` | `3/3` |
| Lot B ready at tick 18 | `0/3` | `3/3` |
| Both lots shipped | `0/3` | `3/3` |
| Backup activated | `3/3` | `0/3` |
| Mean completion tick | `45` | `41` |
| Mean project cost | `$100.310M` | `$96.093M` |
| Corrected coalition success | `0/3` | `3/3` |
| Corrected joint outcome: coalition success without backup | `0/3` | `3/3` |

All three paired periods favored treatment on the corrected joint outcome. Treatment validity and
lineage completeness were no lower than control, so every predeclared advancement check passes.

## Mechanism trace

The treatment did not alter the opening part of the game. All six runs independently converged on
the same untreated A-cycle state:

- supplier request: `$1.8M` with all six documents submitted;
- GC provisional certification: `$1.8M`;
- GC inspection and owner/lender routes: the same four Lot A records;
- GC backup posture: `RESERVE`;
- GC bridge ceiling: `$300,000`; and
- published R1 eligible and initially releasable value: `$950,000`.

The first arm-level split occurred at the treated supplier B1 observation:

- controls selected `LOT_A_CURE` in `3/3` runs;
- treatments selected `FULL_SEQUENCE_CURE` in `3/3` runs;
- treatments declined competing outside work and committed Lot B for tick `18`; and
- controls still had `$1.70M` to `$1.96M` of eventual execution funding, above the `$1.15M`
  full-sequence threshold, but did not choose the full-sequence cure.

This confirms that the control failure was not simply too little money. The packet made the
relationship among verified value, the supplier's own thresholds, source status, and conditional
funding capacity explicit at the point where the supplier selected the cure scope.

At GC B2, every run in both arms selected `MAINTAIN` rather than `DROP`, so the experiment did not
show a direct packet effect on that backup-disposition field. Treatment GCs did request the full
visible owner support and bridge capacity. All controls requested only `$100,000` of owner support,
and two of three also requested a smaller bridge.
After R2 made Lot B ready, treatment GCs selected `PROCEED_PHASED` at C2 and never activated the
reserved backup. Controls reached C2 with Lot B unavailable and selected `ACTIVATE_BACKUP`.

The clean interpretation is therefore narrower than “the packet solved both agents.” The bundled
B1/B2 packet consistently changed the supplier's cure choice and the resulting shared state. The
downstream GC then chose the cheaper path from that improved state.

## Accounting incident and zero-call replay

The frozen live outputs initially recorded coalition failure in all six runs even though treatment
fixed the project path. Audit localized that result to an existing payoff bug, not a model or
packet failure:

1. C1 `supplier_recovery_spend_usd` was added to `scenario_costs.cure_usd`.
2. Supplier payoff subtracted the full `cure_usd` amount.
3. The same C1 recovery spend was then subtracted a second time from supplier payoff.

The correction removes only the duplicate subtraction. A regression test now verifies that one
dollar of supplier recovery spending lowers supplier payoff by one dollar, not two.

The original live outputs remain unchanged on their frozen commit. Each archived agent submission
was then replayed through the corrected harness on a separate commit. The replay record includes
source run hashes and proves that:

- every structured decision is identical;
- every project cost and completion tick is identical;
- validity, lineage, packet exposure, and mechanism outcomes are identical; and
- replay made zero model calls.

The only relevant change is the duplicated private-payoff charge. Corrected supplier payoffs are:

| Run | Control / treatment | Frozen payoff | Corrected payoff | Supplier private success |
|---|---|---:|---:|---|
| period 1 A | control | `$110k` | `$360k` | yes |
| period 1 B | treatment | `$20k` | `$270k` | yes |
| period 2 B | treatment | `$20k` | `$270k` | yes |
| period 2 A | control | `$110k` | `$360k` | yes |
| period 3 A | control | `-$30k` | `$220k` | no |
| period 3 B | treatment | `$120k` | `$320k` | yes |

Owner and GC private success still fail in every control and pass in every treatment. Corrected
coalition success is consequently `0/3` for control and `3/3` for treatment.

## What this supports

Within this frozen S01 V2 setting, the result supports a descriptive claim that a neutral,
attributed representation of already authorized post-inspection state changed the supplier's
decision mapping and prevented the expensive backup cascade. It also shows that the harness can
separate exposure, decision, deterministic consequence, and payoff-accounting failures.

It does not establish a stable success rate, identify which individual packet field caused the
change, prove that the B2 packet was necessary, or show that the effect survives more live roles.
Three samples per arm at temperature zero remain repeated hosted-model trajectories, not an
independent population.

## Next gate

The lowest-cost scientific follow-up is a component ablation: keep the B1 supplier packet but
remove the B2 GC packet. That tests whether the supplier-side threshold/source representation is
sufficient, as the observed decisions suggest. A broader three-live-role confirmation should
follow only after that component boundary is clear.

No additional model calls are included in this result. Any next live gate needs a new explicit
budget decision because the current program ledger is close to the user's ceiling.
