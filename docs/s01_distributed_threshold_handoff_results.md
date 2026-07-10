# S01 distributed threshold handoff — frozen pilot results

Status: **COMPLETED DESCRIPTIVE PILOT — 2026-07-10**

Experiment ID: `s01_distributed_threshold_handoff_v2_1`

Frozen code commit: `e0024de`

The protocol is defined in
[`s01_distributed_threshold_handoff_spec.md`](s01_distributed_threshold_handoff_spec.md).
This report is an outcome record, not a post-hoc change to that protocol.

## Result in one sentence

When the GC supplied the correct threshold, both typed data and equivalent prose produced safe,
viable supplier actions almost every time; with a live GC, end-to-end success fell to `30%` in both
representations because the GC usually calculated the wrong value before transmission.

## Runs and cost

- `150` assigned confirmation runs; `146` reached a valid terminal state.
- Confirmation model cost: `$5.391508`.
- Conservative all-program cost, including excluded development and qualification: `$6.495753`.
- Replicates are repeated API trials, not seeded independent samples.

## Equal-weight arm summary

Each arm contains ten assigned trials at each of R1, R3, and R5 (`n=30`). ITT outcomes count
invalid runs, missing exposure, and incorrect handoffs as failures. Regret is conditional on a
valid terminal run.

| Arm | First-pass valid | Exact transfer ITT | Safe action ITT | End-to-end | Viable deal | Replacement | Mean regret |
|---|---:|---:|---:|---:|---:|---:|---:|
| scripted silent | 100.0% | 0.0% | 33.3% | 0.0% | 33.3% | 66.7% | `$820,000` |
| scripted prose | 13.3% | 93.3% | 93.3% | 93.3% | 100.0% | 0.0% | `$3,704` |
| scripted structured | 10.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | `$13,333` |
| live prose | 13.3% | 30.0% | 56.7% | 30.0% | 58.1% | 41.9% | `$449,037` |
| live structured | 20.0% | 30.0% | 53.3% | 30.0% | 54.1% | 45.9% | `$501,185` |

## Predeclared descriptive contrasts

- Scripted structured minus scripted prose: end-to-end `+0.067`, safe action `+0.067`, mean regret
  `+$9,630`.
- Scripted structured minus silence: end-to-end `+1.000`, safe action `+0.667`, mean regret
  `-$806,667`.
- Scripted prose minus silence: end-to-end `+0.933`, safe action `+0.600`, mean regret
  `-$816,296`.
- Live structured minus scripted structured: end-to-end `-0.700`, safe action `-0.467`, mean regret
  `+$487,852`.
- Live prose minus scripted prose: end-to-end `-0.633`, safe action `-0.367`, mean regret
  `+$445,333`.
- Live structured minus live prose: end-to-end `0.000`, safe action `-0.033`, mean regret
  `+$52,148`.

These are pilot effect sizes. No null-hypothesis significance claim is made.

## Mechanism localization

Across the `60` live-GC assignments, the GC computed the frozen threshold exactly in `18` runs.
All `18` exact calculations led to a safe supplier action and end-to-end success. The other `42`
GC calculations were wrong; in the `40` cases with a valid downstream recipient action, the
supplier generally acted consistently with the value it was actually shown. Twenty-five wrong
signals induced a truth-relative unsafe request and replacement.

The recurrent wrong values were recognizable values elsewhere in the GC context—notably `$900k`
emergency replacement cost and `$1.15M` combinations or expected switch costs. This supports a
narrow conclusion: in this pilot, the dominant failure was upstream fact binding and calculation,
not loss of the transmitted number or a typed-data-versus-prose representation effect.

## What this does and does not establish

The deterministic adjudicator shows that the transmitted value is decision-relevant, and the
scripted sender arms show that either representation can carry it successfully. The live arms show
a large coordination tax when a model must derive that value from distributed business facts.

The study does not establish a general advantage for structured data, human negotiation behavior,
or autonomous construction readiness. First-pass validity was low in every non-silent model arm,
so schema/grid conformance remains a separate engineering bottleneck. The next experiment moves
from this one boundary to a controlled multi-hop data-and-authority chain in S01 V2.
