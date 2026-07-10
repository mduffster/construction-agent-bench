# S01 V2 supplier-GC derived-state packet experiment

Status: **FROZEN PROTOCOL / READY — 2026-07-10**

Experiment ID: `s01_v2_supplier_gc_derived_state_packet_v1`

This protocol is frozen before evidentiary model calls. It defines a small, descriptive mechanism
study; it does not contain results.

## Research question

After the first inspection and release record exists, can a neutral, attributed summary of the
already authorized decision state help a live steel supplier and GC choose the full-sequence
recovery path without sacrificing output validity or data-lineage completeness?

The intervention tests state representation, not access to new business facts. It asks whether
turning scattered observations into explicit thresholds, source-status labels, and operative caps
improves the mapping from authorized data to coordinated action.

## Experimental setting

All six organizations remain in the normal variant of `S01_V2_OFFSITE_STEEL_DRAW`:

- the steel supplier and GC use the live lineage-core policy;
- owner, lender, inspector, and labor use the same state-aware deterministic controls as the
  completed multiplayer ladder;
- scenario content, payoffs, role profiles, action spaces, consequence logic, and deterministic
  controls are identical across arms; and
- Claude Haiku runs at temperature `0`, with a maximum of `1,200` output tokens and repair budget
  `1`.

The supplier and GC remain persistent organizations throughout a run. The experiment changes only
two post-R1 observations in the treatment arm. Their A1 and A2 observations and every C-stage
observation are untreated.

## Why the intervention begins after R1

An earlier design placed a document-supported dollar ledger in the GC's A2 observation. That is not
a safe or clean intervention in the current scenario.

At A2, the GC can see submitted document identifiers, but an exact dollar statement about verified
or releasable value would require either an incomplete inference from those identifiers or access
to hidden canonical lot and verification state. Exposing the latter would leak facts that the GC
has not yet been authorized to observe. In addition, routing Lot B material at A2 changes review
and cure context but does not, by itself, determine the R1 eligible or releasable value. A dollar
packet there would therefore imply a causal determination the current mechanics do not make.

R1 resolves this ambiguity. The actual inspection and initial release record then becomes an
authorized observation, so the harness can summarize it without reaching behind the visibility
boundary. The experiment consequently targets the earliest *safe* shared recovery boundary:

1. supplier node `S01_B1_SUPPLIER_COMMITMENT`; then
2. GC node `S01_B2_GC_INTEGRATED_PACKAGE`.

This choice leaves the observed A1 request and A2 routing divergence intact. The study can test
whether clearer post-R1 decision state repairs the downstream cure-and-backup choice, not whether a
different document-routing prompt changes the initial review.

## Frozen arms and order

Arm A, `current_observation`, receives the existing lineage-core observation with no added packet.

Arm B, `derived_state_packet`, receives that same observation plus one deterministic packet at B1
for the supplier and one at B2 for the GC. No other observation changes.

There are three trials per arm, dispatched as three paired periods in the frozen order:

| Period | First run | Second run |
|---|---|---|
| 1 | A | B |
| 2 | B | A |
| 3 | A | B |

The complete sequence is `ABBAAB`. Pairing and reversal distribute simple run-order effects; they
do not make repeated hosted-model calls statistically independent. Replicate IDs are bookkeeping,
and all six trials are reported.

## Packet contract

Each packet is a harness-authored structured record with a schema version, recipient, node,
calculation ID, value and unit, status, formula or comparison rule, and explicit source references.
It may contain only values deterministically derived from facts already authorized for that
recipient at that node.

The B1 supplier packet summarizes, where supported by the current observation:

- the R1 document-supported value and applicable request or release cap;
- the Lot A cash threshold and full-sequence cash threshold;
- each visible funding source, separated into hard and provisional status;
- hard and provisional totals without treating an offer as realized cash; and
- the operative bounds on the supplier's current request and commitment fields.

The B2 GC packet uses the public R1 record, the supplier's authorized B1 record, and the GC's own
authorized facts to summarize:

- the current document-supported value;
- the supplier's stated funding and cure posture;
- hard and provisional sources and totals, kept separate;
- applicable certification, owner-request, lender-draw, and bridge caps; and
- whether each displayed amount is a submitted request, provisional offer, hard commitment,
  verified amount, or operative maximum.

Source status is part of the value. The packet must not add provisional and hard amounts into one
unqualified funding total. If an authorized source is absent or insufficient to derive a field,
the packet records the value as unavailable rather than imputing canonical state.

## Neutrality and provenance rules

The packet must:

- describe facts, formulas, classifications, and caps without recommending an option;
- avoid labels such as `efficient`, `correct`, `safe choice`, or fixture names;
- contain no counterfactual terminal outcome or predicted project-success claim;
- expose no hidden canonical fact, another organization's private fact, or private payoff;
- preserve attribution to the harness calculation and the underlying authorized records;
- use the same deterministic calculation and rendering code in every treatment run; and
- be recorded with the actual agent observation so exposure is auditable.

The packet may identify that a value is below, equal to, or above an operative threshold because
that is a direct comparison. It may not translate that comparison into an action instruction.

Before live dispatch, deterministic tests must reconstruct every packet field from its cited
recipient-visible inputs, reject unauthorized source references, prove that A1, A2, and C-stage
observations are unchanged, and confirm that the control arm contains no packet.

## Outcomes

The predeclared primary outcomes are:

- coalition success at terminal assessment;
- backup activation, reported as a rate where lower is better; and
- joint efficient-path attainment: coalition success with no backup activation.

The joint-path measure is a behavioral label for this frozen S01 V2 outcome, not a claim that the
underlying actions are universally optimal. Assigned-arm outcomes are intention-to-treat: a valid
model choice that ignores the packet remains a treatment observation.

Mechanism outcomes are the supplier's B1 cure and funding selections, the GC's B2 certification,
funding requests and backup disposition, document-supported certification, full-sequence funding
and readiness, the joint `FULL_SEQUENCE_CURE`/`DROP` decision pair, and the earliest divergence
from the deterministic reference path.

Secondary and safety outcomes are final project cost and completion-tick regret, terminal validity,
first-pass validity, repair attempts, packet exposure and provenance correctness, lineage
completeness, realized clips, and project success.

## Analysis and advancement rule

Report all six trajectories, arm counts and rates, the three paired-period contrasts, and exact
decision-path records. With three trials per arm, the analysis is descriptive only. It supports no
null-hypothesis significance claim, population success rate, or claim of deterministic hosted-model
behavior.

Advance to a broader live-role confirmation only if:

1. treatment joint efficient-path attainment is strictly greater than control attainment;
2. treatment valid-terminal rate is no lower than control; and
3. treatment lineage-complete rate is no lower than control.

Coalition success and backup activation remain co-primary reported outcomes even if the advancement
rule is not met. A provenance failure, unauthorized field, or inconsistent packet calculation
invalidates the treatment tranche and stops interpretation until a new protocol version is frozen.

## Preflight and execution gates

Before any live call:

- the worktree and frozen commit are recorded;
- the deterministic S01 V2 witnesses, replay checks, full test suite, linter, and
  choice-consequence audit are green;
- treatment and control differ only at the two declared observation sites;
- every packet field passes the recipient-authorization and recomputation tests;
- all model, parser, pricing, output-contract, clean-commit, resume, and dispatch guards pass; and
- no prompt, packet schema, action space, payoff, validator, or consequence change occurs after the
  frozen commit.

Any such change requires a new experiment ID or an explicit protocol amendment before further
evidentiary calls.

## Interpretation boundary

A positive result would show that a compact, neutral representation of authorized post-inspection
state can improve this supplier-GC recovery decision in the toy S01 V2 environment. It would not
show that document routing is solved, that all six live organizations coordinate reliably, or that
the same packet generalizes to real construction projects. A null or mixed result would localize
the remaining problem beyond simple threshold-and-cap representation and would be useful evidence
against expanding the live population prematurely.
