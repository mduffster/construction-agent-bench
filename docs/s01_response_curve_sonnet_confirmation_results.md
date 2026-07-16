# S01 response-curve Sonnet confirmation results

Status: **COMPLETE — FAILURE PERSISTS — 2026-07-15**

Experiment ID: `s01_replaceability_response_curve_v1`, stage `stronger-modal`

Frozen commit: `deb8667bef62e75530cd4655a14b41d229c64112`

Protocol: `docs/s01_response_curve_sonnet_confirmation_protocol.md`

Archived outputs: `outputs/s01_response_curve_sonnet_no_history_confirmation_v1_20260715`

## Headline

Claude Sonnet 5 did not reliably map supplier leverage to a safe payment request. Across 15 valid
no-history runs, the supplier was replaced in `9/15` (`60%`), the mean avoidable loss was about
`$689K`, and the five-level mean request curve had one reversal.

Sonnet did recognize the highest-leverage case: all three requests at the `$1M` replacement premium
matched the `$1.2M` highest safe request. At lower levels, however, requests varied from `$0` to
`$1.2M` and often exceeded the safe amount. The stronger model changed the pattern but did not
remove the fact-binding and calculation failure.

## Results by replacement price

| Replacement premium | Highest safe request | Sonnet requests | Replaced | Mean avoidable loss |
|---:|---:|---:|---:|---:|
| `$0` | `$200K` | `$1.2M`, `$800K`, `$1.2M` | `3/3` | `$730K` |
| `$250K` | `$500K` | `$800K`, `$0`, `$900K` | `2/3` | `$747K` |
| `$500K` | `$700K` | `$600K`, `$1.2M`, `$1.2M` | `2/3` | `$853K` |
| `$750K` | `$1.0M` | `$700K`, `$1.2M`, `$1.2M` | `2/3` | `$1.113M` |
| `$1.0M` | `$1.2M` | `$1.2M`, `$1.2M`, `$1.2M` | `0/3` | `$0` |

All 15 assigned runs produced valid terminal output. Ten validation repairs were used across the
batch and remain part of the recorded trajectories.

## Comparison with Haiku

The existing Haiku confirmation also failed to produce a reliable response curve, with about
`$595K` average avoidable loss in the published 50-run study. The Sonnet confirmation averaged
about `$689K`; it is therefore not evidence that moving to the stronger model solves this task.
The designs are not a clean head-to-head model ranking because Haiku's published aggregate includes
both relationship-history conditions and has more repetitions.

## Execution note

The first invocation used the generic runner's default ten-cell grid instead of the protocol's five
explicit no-history cells. It was stopped after three matching no-history runs and two history runs.
The three matching runs were copied unchanged into a clean 15-run evidence directory; their run
configs and summaries retain the frozen model settings. The two history runs are isolated under
`outputs/s01_response_curve_sonnet_confirmation_v1_20260715` and are excluded from every result
above. No failed or inconvenient protocol-matching outcome was replaced.

## Limits

Three runs per price level are still small, repeated API calls are not independent participants,
and this is one model provider in one simulated task. The result supports a narrow claim: a frontier
model did not make the response-curve failure disappear under the frozen S01 protocol.
