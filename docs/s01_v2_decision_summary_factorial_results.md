# S01 V2 decision-summary factorial results

Status: **COMPLETE — SUPPLIER-SIDE EFFECT REPLICATED — 2026-07-15**

Experiment ID: `s01_v2_decision_summary_factorial_v1`

Frozen commit: `deb8667bef62e75530cd4655a14b41d229c64112`

Protocol: `docs/s01_v2_decision_summary_factorial_protocol.md`

Archived outputs: `outputs/s01_v2_decision_summary_factorial_v1_20260715`

## Headline

The supplier's private decision summary was sufficient to change the two-company recovery path.
The contractor summary added no measurable benefit in this setting.

All 20 runs in which the supplier received a summary—supplier-only and both-summary arms—prepared
the full steel sequence, made Lot B ready, avoided backup steel, and met every firm's private goal.
All 20 runs without a supplier summary—no-summary and contractor-only arms—chose the Lot-A-only
cure and missed the all-firm/no-backup outcome.

The result replicated the original six-run pilot and removed its bundled-treatment ambiguity. It
does not show that summaries work generally or that contractor-side decision support is never
useful. It identifies the operative recipient for this frozen decision cascade.

## Predeclared outcome table

| Arm | Assigned / valid | All-firm success without backup | 95% exact interval | Backup activated | Full-sequence cure | Mean cost | Mean finish |
|---|---:|---:|---:|---:|---:|---:|---:|
| No summary | `10 / 10` | `0/10` | `0%–30.8%` | `8/10` | `0/10` | `$99.825M` | week `45.8` |
| Supplier only | `10 / 10` | `10/10` | `69.2%–100%` | `0/10` | `10/10` | `$96.036M` | week `41.0` |
| Contractor only | `10 / 10` | `0/10` | `0%–30.8%` | `8/10` | `0/10` | `$99.818M` | week `45.8` |
| Both summaries | `10 / 10` | `10/10` | `69.2%–100%` | `0/10` | `10/10` | `$96.064M` | week `41.0` |

All 40 runs were valid and lineage-complete. No run needed a repair. Every exposure audit passed:
the no-summary arm received no summary, the single-recipient arms exposed exactly one summary at
the declared node, and the both-summary arm exposed exactly two. Deterministic references proved
that attaching the summary alone did not change canonical consequences.

## Factorial read

On the predeclared joint outcome, the descriptive supplier-summary risk difference was `+1.00`:
`20/20` with a supplier summary versus `0/20` without one. The contractor-summary main-effect risk
difference was `0.00`: `10/20` with it versus `10/20` without it. The interaction on the
risk-difference scale was also `0.00`.

The cleaner mechanism statement is therefore: reorganizing the supplier's already authorized
post-inspection facts changed the supplier's B1 cure decision. Once the supplier committed the full
sequence, the contractor could finish the cheaper recovery path from ordinary observations.

## Project success versus firm success

The no-summary and contractor-only arms still completed the public project in `8/10` runs each.
None met every firm's private target. This is the distinction ConstructSim is designed to expose:
a project can look successful while the commercial path quietly leaves firms worse off.

## Limits

These are repeated temperature-zero calls to one model in one toy construction scenario. The exact
intervals describe variation in this frozen API setting, not a population of firms or projects.
The intervention bundles several supplier-side representations—verified value, cash thresholds,
source status, and operative caps—so this study identifies the recipient, not the individual field
that mattered. A later study can ablate the supplier summary itself if that narrower question is
worth the cost.
