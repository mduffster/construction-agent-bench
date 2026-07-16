# S01 V2 decision-summary factorial confirmation

Status: **FROZEN PROTOCOL / READY — 2026-07-15**

Experiment ID: `s01_v2_decision_summary_factorial_v1`

This protocol was written before confirmatory model calls. It replaces the bundled six-run pilot
with a four-way test that can tell whether the supplier summary, contractor summary, or both drove
the earlier result.

## Question

After inspection creates an authorized project record, which company needs a short decision
summary for the supplier and contractor to choose the full steel recovery path?

The summary does not make private information public. The supplier receives only public facts and
its own private cash limits. The contractor receives only facts already visible to the contractor.
The harness creates each summary from the recipient's current observation and records the exact
summary and source hashes.

## Fixed design

The supplier and contractor are live Claude Haiku organizations in every run. The owner, lender,
inspector, and labor company use the same state-aware rules in every run. Model, prompts, scenario,
payoffs, action spaces, validation, and consequence logic are fixed across arms.

The four arms are:

1. no decision summary;
2. supplier summary only at `S01_B1_SUPPLIER_COMMITMENT`;
3. contractor summary only at `S01_B2_GC_INTEGRATED_PACKAGE`; and
4. both summaries at their respective decision nodes.

There are 10 assigned runs per arm, 40 total. Each four-run block contains every arm once. The
predeclared sequence is stored in the study manifest. Runs use Claude Haiku, temperature 0, 1,200
maximum output tokens, repair budget 1, and the block number as the replicate seed. Invalid final
output counts against the assigned arm; there is no optional stopping or replacement of failed
runs.

## Outcomes

The primary outcome is the joint path already defined in the pilot: every firm's private target is
met and backup steel is not activated. Co-primary descriptive outcomes are all-firm success and
backup activation.

Mechanism outcomes include the supplier's B1 cure choice, the contractor's B2 backup decision,
Lot B readiness, both-lot shipment, lineage completeness, validation repairs, final cost, and
completion week.

The report will show assigned counts and rates for all four arms with two-sided 95% exact binomial
intervals. It will also show descriptive supplier-summary and contractor-summary risk differences
and the interaction on the risk-difference scale. Repeated API calls are not independent human
participants, so the intervals describe model-call variation in this frozen setting rather than a
population of firms or construction projects.

## Gates

Before paid calls, deterministic references must prove that:

- all four arms complete the same reference path;
- the summaries do not change canonical consequences by themselves;
- each arm exposes a summary only to its declared recipient and node;
- every displayed value can be reconstructed from that recipient's authorized observation;
- reference runs make zero model calls; and
- the full tests, linter, replay checks, and output contract pass on the frozen commit.

A provenance error stops the study. A malformed model decision follows the existing one-repair
rule and remains assigned to its original arm.

## Budget

The fresh hard cap for this study is `$6.80`. Each of 40 runs reserves `$0.17` before dispatch.
The runner stops before a call if the remaining cap is smaller than that reserve and stops after a
call if recorded usage exceeds the cap. This allocation is part of a fresh combined research cap
below `$10`; the companion Sonnet confirmation may use at most `$3.00`.

## Interpretation boundary

A supplier-only result would show that reorganizing the supplier's already authorized facts is
sufficient in this scenario. A both-only result would support a coordination or complementary
representation account. A null result would show that the original three-run change was unstable.
None of these outcomes establishes real-world construction performance or a general ranking of
models.
