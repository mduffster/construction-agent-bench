# ConstructBench Design and Very Early Output Summary

Last updated: 2026-06-21

## Purpose

ConstructBench is an early-stage stateful business-agent simulation for a toy large construction project. The current system is intended to test whether persistent organization-level agents can make consequential business decisions under public and private information, communicate with counterparties, and update directed assessments from observed outcomes.

This is not yet evidence of stable behavioral distributions. The current results are better read as a harness-validity and prompt-contract check: do the agents receive meaningful business situations, make structured choices, communicate, and produce private counterparty assessments that the harness can validate and replay?

## Current Runtime Design

The current runtime uses an event/phase loop rather than an idle tick loop. Project schedule ticks remain business facts, such as delivery at tick 14 or completion at tick 40, but the simulation calls agents only during meaningful execution or assessment phases.

Each run has six persistent business organizations:

- Owner / developer
- General contractor
- Steel supplier
- Labor subcontractor
- Lender
- Inspector

The harness owns canonical project state. Agents receive observations and return structured submissions containing:

- `decisions`: required choices for the active business decision nodes.
- `communications`: optional private or public business messages.
- `assessment_updates`: private directed changes to counterparty assessment scores.
- `assessment_reviews`: explicit no-update reviews when evidence does not change assessment.
- `private_notes`: short memory carried to later turns.

Invalid outputs block the run. Required decisions cannot be skipped, and consequences are not applied after invalid required output. The runtime writes replayable logs and summaries, including model prompts/responses in debug mode.

## Baseline Project Conditions

The toy project is represented as a dependency graph with 27 required deliverables, `D00` through `D26`. These cover owner approval, lender closing and draw releases, GC schedule/logistics and sitework, steel procurement and delivery, labor erection and interior work, inspections, substantial completion, closeout, and final retainage release.

Baseline normal case:

| Field | Value |
|---|---:|
| Baseline project cost | `$95,000,000` |
| Approved budget | `$100,000,000` |
| Opening contingency | `$5,000,000` |
| Success budget ceiling | `$102,000,000` |
| Contract target completion | tick `40` |
| Success deadline | tick `48` |
| Initial probability on time | `0.85` |
| Initial probability within budget | `0.85` |

Stressed starting condition:

| Field | Value |
|---|---:|
| Baseline project cost | `$98,600,000` |
| Approved budget | `$100,000,000` |
| Opening contingency | `$1,800,000` |
| Expected completion | tick `44` |
| Success deadline | tick `48` |
| Initial probability on time | `0.65` |
| Initial probability within budget | `0.65` |

Budget line items total `$95,000,000` in the normal baseline and cover preconstruction, sitework/foundations, structural steel, GC logistics, enclosure, MEP, interiors, inspections/closeout, and owner insurance/bonds/allowances.

The principal success condition is project completion within the configured budget and schedule viability bounds, with required terminal deliverables complete. The normal and stressed scenarios both use a success budget ceiling of `$102,000,000` and a success deadline of tick `48`.

## Scenarios

The current scenario set contains one no-perturbation reference scenario and five perturbation scenarios.

### S00: Base Project, No Perturbation

S00 is the reference path for ordinary project delivery. It establishes normal and stressed baseline cost/completion behavior without a scenario-specific shock.

### S01: Steel Market Shock and Delivery Cascade

S01 introduces a public steel-market shock and private supplier impact. The public event includes higher steel prices and longer market lead times. The steel supplier privately receives its own cost, liquidity, and delivery options.

Affected project areas include steel shop drawings, fabrication, site delivery, steel-dependent labor erection, and downstream completion. Important choices include supplier sourcing strategy, supplier commercial request, GC procurement response, owner amendment response, inspector source review if nonapproved sourcing is used, and labor mobilization.

### S02: Tower-Crane Failure Before Severe Weather

S02 tests GC recovery from crane failure and a weather window. The GC can rent replacement equipment, use a mobile crane, wait for diagnostics, or pursue repair. Interim choices affect crews, deliveries, exposed work, reimbursement requests, owner cost response, and possible inspection review.

Affected project areas include crane readiness, steel erection, general conditions/logistics, and schedule delay overhead.

### S03: Owner Liquidity Shortfall and Payment Cascade

S03 gives the owner private knowledge that expected funding will not arrive on time. Owner payment choices affect GC, lender, labor subcontractor, work rate, cash, and completion schedule.

Important choices include payment plan, financing source, lender accelerated draw response, GC response to payment amendment or short payment, labor response, and routine draw/payment resolution if the shortfall persists.

### S04: Structural Weld Failure at a Draw Milestone

S04 introduces a failed structural weld inspection. It tests repair strategy, inspection judgment, compliance release, draw release, and downstream schedule consequences.

Important choices include GC corrective strategy, engineering or retesting path, labor repair mode, inspector reinspection decision, possible second corrective strategy, final release, and lender draw response. The scenario explicitly separates physical compliance from official inspection approval.

### S05: Labor-Capacity Shortage and Fixed Inspection Window

S05 introduces a regional labor shortage near a fixed reserved inspection slot. Labor capacity choices affect the critical task readiness date, inspection booking, emergency slot handling, and downstream finishes/closeout.

Important choices include labor capacity plan, labor commercial request, GC staffing response, owner cost response, GC inspection booking, and inspector emergency-slot response when needed.

## Decision and Outcome Envelope

Scripted fixtures currently provide success and failure witnesses for normal and stressed variants. These fixtures are not behavioral evidence; they are deterministic harness checks showing that the scenario state machines have both viable and failing paths.

| Scenario | Case | Terminal status | Final cost | Completion |
|---|---|---:|---:|---:|
| S00 | normal success | PROJECT_SUCCESS | `$95.000M` | `40` |
| S00 | stressed success | PROJECT_SUCCESS | `$98.600M` | `44` |
| S01 | normal success | PROJECT_SUCCESS | `$95.200M` | `40` |
| S01 | normal failure | BUDGET_INFEASIBLE | `$103.250M` | `49` |
| S01 | stressed success | PROJECT_SUCCESS | `$100.200M` | `44` |
| S01 | stressed failure | BUDGET_INFEASIBLE | `$106.500M` | `50` |
| S02 | normal success | PROJECT_SUCCESS | `$97.800M` | `41` |
| S02 | normal failure | BUDGET_INFEASIBLE | `$106.350M` | `52` |
| S02 | stressed success | PROJECT_SUCCESS | `$100.450M` | `45` |
| S02 | stressed failure | BUDGET_INFEASIBLE | `$104.900M` | `52` |
| S03 | normal success | PROJECT_SUCCESS | `$95.000M` | `40` |
| S03 | normal failure | SCHEDULE_INFEASIBLE | `$97.950M` | `49` |
| S03 | stressed success | PROJECT_SUCCESS | `$99.000M` | `44` |
| S03 | stressed failure | SCHEDULE_INFEASIBLE | `$101.000M` | `50` |
| S04 | normal success | PROJECT_SUCCESS | `$97.000M` | `41` |
| S04 | normal failure | BUDGET_INFEASIBLE | `$102.200M` | `49` |
| S04 | stressed success | PROJECT_SUCCESS | `$100.910M` | `44` |
| S04 | stressed failure | BUDGET_INFEASIBLE | `$105.000M` | `50` |
| S05 | normal success | PROJECT_SUCCESS | `$96.300M` | `40` |
| S05 | normal failure | SCHEDULE_INFEASIBLE | `$97.950M` | `49` |
| S05 | stressed success | PROJECT_SUCCESS | `$100.300M` | `44` |
| S05 | stressed failure | SCHEDULE_INFEASIBLE | `$99.950M` | `49` |

This envelope suggests the harness has meaningful cost and schedule consequences. It does not prove that live agents will explore those paths without broader experimental runs.

## Counterparty Assessments

The current assessment model is private, directed, and dimensional. Every directed pair starts at `0.75` across:

- `performance_reliability`
- `information_reliability`
- `contractual_reliability`

Agents may change scores when assessment evidence is provided. If they do not change scores, they must submit a no-update review explaining why the evidence is irrelevant, nondiagnostic, already incorporated, offset by remediation, or otherwise insufficient.

The harness stores agent-submitted assessment values. It does not compute the "right" trust update. Aggregate mean assessment is reported only as a diagnostic summary; the primary state is the directed matrix.

## Very Early Live-Agent Output

The current small live suite used Claude Haiku 4.5 with collaborative behavior profiles. S01 was run before exact cost telemetry was added; S02-S05 include token and cost accounting. These runs are single samples, not distributions.

| Scenario | Run validity | Terminal status | Final cost | Completion | Messages | Assessment updates | No-update reviews |
|---|---:|---:|---:|---:|---:|---:|---:|
| S01 | valid | PROJECT_SUCCESS | `$95.200M` | `40` | 6 | 0 | 5 |
| S02 | valid | PROJECT_SUCCESS | `$98.525M` | `43` | 2 | 1 | 4 |
| S03 | valid | PROJECT_SUCCESS | `$95.200M` | `40` | 3 | 3 | 3 |
| S04 | valid | PROJECT_SUCCESS | `$98.000M` | `42` | 7 | 7 | 6 |
| S05 | valid | PROJECT_SUCCESS | `$95.8125M` | `40` | 7 | 9 | 2 |

Model usage for S02-S05 was:

| Calls | Input tokens | Output tokens | Estimated cost |
|---:|---:|---:|---:|
| 39 | 512,097 | 20,950 | `$0.616847` |

The cost estimate uses the current Haiku 4.5 price constants in the harness: `$1/M` input tokens and `$5/M` output tokens. Cache token fields are recorded; these runs reported zero cache tokens.

### Observed Live Choices

S01:

- Steel supplier selected `current_expedited`.
- Steel supplier requested `$600,000` price relief and `$500,000` advance payment, with no delivery-date amendment.
- GC accepted the selected plan.
- Labor subcontractor chose `flexible_hold`.
- Owner approved the advance but did not approve price or delivery-date amendment.
- Outcome: on-time steel delivery and project success at tick `40`.

S02:

- GC selected `accelerated_repair`.
- GC retained idle crews, postponed deliveries, and protected exposed work.
- GC requested 50% recovery-cost reimbursement.
- Owner approved the requested amount.
- Outcome: project success, but completion moved to tick `43`.

S03:

- Owner proposed a three-tick deferral.
- Owner proposed `$3,000,000` bridge funding, `$2,000,000` equity injection, and requested accelerated draw support.
- GC accepted and reduced work rate.
- Lender required missing documentation before disbursement.
- Outcome: project success at tick `40`; payment evidence later caused several counterparties to downgrade owner reliability.

S04:

- GC selected `engineering_disposition`, then `engineered_repair`.
- Labor subcontractor selected `overtime_crew`.
- Inspector requested additional testing before approval.
- GC repaired remaining identified welds.
- Inspector approved final release.
- Lender released the draw.
- Outcome: project success at tick `42`.

S05:

- Labor subcontractor selected `reallocate_and_overtime`.
- Labor requested advance support and 50% reimbursement.
- GC accepted the labor plan and kept the reserved tick-36 inspection slot.
- Owner approved half of the requested amount.
- Outcome: project success at tick `40`.

## Observed Assessment Behavior

S01 produced no numeric assessment changes. Agents explicitly held assessments flat because steel delivery occurred on time at tick `14`.

S02 produced one numeric update:

- Owner upgraded GC after recovery work finished inside the viable window:
  - performance `0.75 -> 0.85`
  - information `0.75 -> 0.82`
  - contractual `0.75 -> 0.82`

S03 produced negative updates against the owner after late payment:

- Lender downgraded owner to performance `0.65`, information `0.65`, contractual `0.70`.
- Steel supplier downgraded owner to performance `0.60`, contractual `0.60`, with information unchanged at `0.75`.
- Inspector downgraded owner to performance `0.62`, contractual `0.60`, with information unchanged at `0.75`.

S04 produced mostly positive updates after structural compliance and final release:

- Owner upgraded GC and inspector performance to `0.88`.
- Owner upgraded lender contractual reliability to `0.85`.
- Lender upgraded GC and inspector performance to `0.85`.
- Inspector upgraded GC to performance `0.85`, information `0.80`, contractual `0.85`.
- Inspector mildly upgraded lender to `0.78` across dimensions.

S05 produced broader positive updates after labor preserved the inspection window:

- Owner upgraded labor subcontractor to performance `0.88`, contractual `0.85`.
- GC upgraded labor subcontractor to performance `0.88`, information `0.85`, contractual `0.88`.
- Labor subcontractor upgraded GC, owner, and inspector.
- Lender upgraded labor subcontractor performance to `0.82` and information to `0.80`.

This pattern is directionally plausible: on-time or remediated performance tends to create upward revisions, late payment creates downward revisions, and weak attribution leads agents to explicitly leave some scores unchanged. It is still based on a very small sample.

## Early Validity Signals

The useful signals so far are limited but real:

- Agents are being asked to resolve concrete business decisions rather than pass through empty time ticks.
- Valid live runs contain business communications, not only option selection.
- Deterministic consequences change cost, schedule, and downstream decision availability.
- Scripted fixtures cover both passing and failing paths for the scenario state machines.
- Assessment updates are private, directed, and tied mostly to explicit outcome evidence.
- The deterministic test suite currently passes.
- Debug outputs include raw model I/O for auditability.

## Known Limitations and Issues

This is still early-stage. Important limitations:

- The live sample is small and mostly normal/collaborative. It should not be treated as a behavioral distribution.
- S01 live usage predated cost telemetry, so exact model cost is available only for S02-S05 in the current reported set.
- Some adapter normalization was added after observing reasonable Haiku outputs with variant field names such as `updated_scores` or `new_score`. This is acceptable as output-shape hardening, but it shows the contract is still stabilizing.
- One S05 mid-run owner-to-labor assessment update had empty `evidence_ids`. The content was meaningful, but structurally every assessment update should reference formal evidence or a generated message/decision evidence ID.
- The current scenarios are still toy scenarios. They are designed for interpretability and harness validation, not realism at full construction-project fidelity.
- The current experiments do not yet estimate sensitivity to behavior profile, model, seed, scenario combinations, or prompt variants.
- Trust scores are model-submitted judgments. They should be analyzed as agent behavior, not as ground-truth reputation.

## Current Interpretation

At this stage, ConstructBench appears useful as a controlled harness for studying whether business-role agents can maintain state, make structured project decisions, communicate, and update directed expectations from outcome evidence. The strongest current evidence is harness-level: scripted success/failure witnesses, replayable outputs, nonempty live agent decisions, and plausible assessment movement in a small Haiku run set.

The project is not yet ready to support broad claims about agent behavior. The next validity step is to run repeated batches across behavior profiles and scenario variants, exclude invalid runs from behavioral distributions, and report decisions, communications, assessment updates, no-update reviews, repairs, invalid outputs, project outcomes, and model cost separately.
