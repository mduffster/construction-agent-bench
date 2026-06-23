# ConstructBench S01 Marginal Update Specification

**Status:** implementation specification  
**Scope:** replace only the current S01 scenario logic with a denser Normal scenario  
**Primary constraint:** preserve the existing ConstructBench architecture

## 1. Task for the coding agent

Update S01 so that all six persistent organizations make three consequential decisions during one realistic construction coordination episode.

The update must use the current:

- event/phase runtime;
- six persistent organization agents;
- harness-owned canonical state;
- public and role-private observations;
- structured `decisions`;
- optional `communications`;
- optional `assessment_updates`;
- `private_notes`;
- blocking validation;
- deterministic consequence application;
- replay and run logging.

This is **not** a request to build a new game engine, workflow engine, negotiation engine, generic contract language, parallel scheduler, trust framework, or human-play interface.

The required change is a versioned S01 state machine with additional scenario-specific phases, decision schemas, state fields, validators, and consequence handlers.

The primary evaluation run uses the existing LLM policy for all six organizations. Existing focal-agent, scripted-policy, and replay-policy runners may still supply a role's policy for debugging or controlled experiments, but they must traverse the same decision nodes and state transitions. Do not add deterministic counterpart behavior to S01 itself.

## 2. Architectural invariants

The following must remain true after the update.

1. The harness owns all canonical state and all realized consequences.
2. Agents choose actions only through validated structured decisions.
3. Natural-language messages can influence later agents but never directly mutate canonical state.
4. Invalid required decisions block phase closure and prevent consequences from being applied.
5. Each agent receives only public state, its role-private state, delivered messages, authorized records, its private notes, and its own directed assessments.
6. Replays reconstruct the same phase sequence and terminal state.
7. S00 and S02–S05 remain behaviorally unchanged.
8. The common agent submission envelope remains unchanged unless a narrowly scoped optionality flag is required for S01 trust behavior.
9. Do not introduce a general-purpose abstraction where an S01-specific state field or handler is sufficient.
10. Do not delete the current S01 implementation in the first pull request. Add the new scenario as a version, for example `S01_V2`, and switch the default only after deterministic fixtures pass.

## 3. Scenario replacement

### Identifier

Retain scenario family ID `S01`.

Recommended version identifier:

```text
S01_V2_OFFSITE_STEEL_DRAW
```

### Display name

**Off-Site Steel Payment and Erection Release**

### Premise

At project tick 11, the structural-steel supplier submits a progress-payment application for fabricated steel stored off-site. The supplier needs liquidity to complete records, cure a known issue, finish the first shipping sequence, and mobilize delivery.

The monthly draw, final shop review, first steel delivery, and the erector's reserved crew and crane window are tightly coupled. The six firms must align payment eligibility, funding, inspection, cure work, delivery sequencing, and field capacity.

This is a normal construction contracting problem rather than an exceptional disaster. It combines:

- payment for off-site stored material;
- payment certification;
- title and insurance controls;
- construction-loan disbursement;
- shop inspection and release;
- supplier working capital;
- erection sequencing;
- crew and crane reservation;
- limited bridge funding and contingency;
- backup procurement.

### Shared project objective

The coalition must:

- deliver and release enough conforming steel to begin erection no later than tick 16;
- complete the first erection sequence without installing unreleased material;
- keep final project cost at or below `$102,000,000`;
- complete the overall project by tick 48.

### Baseline public project state

| Field | Value |
|---|---:|
| Current tick | `11` |
| Forecast project cost | `$95,000,000` |
| Approved budget | `$100,000,000` |
| Success cost ceiling | `$102,000,000` |
| Forecast completion | tick `40` |
| Contract target | tick `40` |
| Success deadline | tick `48` |
| First delivery target | tick `14` |
| Reserved erection window | ticks `15–18` |
| First steel sequence contract value | `$2,400,000` |
| Supplier payment application | `$1,800,000` |

Only this Normal configuration is in scope. Do not add Easy, Hard, stressed, or parameter-grid modes in this update.

## 4. Scenario-owned state extension

Add an S01-specific state object inside the existing scenario state mechanism. Names may be adapted to repository conventions, but the content and ownership boundaries should remain.

```yaml
s01_v2_state:
  cycle: A | B | C | TERMINAL
  phase_id: string

  lots:
    lot_a:
      contract_value_usd: 1200000
      true_completed_value_usd: 1150000
      documented_value_usd: 950000
      title_transferable_value_usd: 950000
      insured_value_usd: 1200000
      physical_nonconformance: false
      documentation_complete: false
      released_quantity: 0
      shipped_quantity: 0
      erected_quantity: 0
    lot_b:
      contract_value_usd: 1200000
      true_completed_value_usd: 700000
      documented_value_usd: 400000
      title_transferable_value_usd: 400000
      insured_value_usd: 1200000
      physical_nonconformance: true
      documentation_complete: false
      released_quantity: 0
      shipped_quantity: 0
      erected_quantity: 0

  payment:
    application_id: PA-01
    requested_usd: 1800000
    provisional_certified_usd: 0
    final_certified_usd: 0
    eligible_stored_value_usd: 0
    lender_draw_requested_usd: 0
    lender_draw_released_usd: 0
    owner_funds_usd: 0
    owner_equity_usd: 0
    gc_bridge_usd: 0
    escrow_usd: 0

  supplier_execution:
    cash_committed_usd: 0
    outside_financing_usd: 0
    outside_work_action: DECLINE
    cure_plan: NONE
    lot_a_committed_tick: null
    lot_b_committed_tick: null
    actual_lot_a_ready_tick: null
    actual_lot_b_ready_tick: null

  inspection:
    selected_scope: null
    scheduled_tick: null
    findings: []
    lot_a_disposition: NOT_REVIEWED
    lot_b_disposition: NOT_REVIEWED
    reinspection_tick: null

  labor:
    provisional_offer: null
    binding_commitment: null
    crew_status: AVAILABLE
    crane_status: AVAILABLE
    mobilization_tick: null
    next_full_availability_if_released: 23

  gc_controls:
    backup_status: NONE
    backup_cost_incurred_usd: 0
    selected_sequence: null
    verification_strategy: null

  commitments:
    provisional_offers: []
    binding_terms: []
    satisfied_condition_codes: []
    breached_commitment_ids: []

  scenario_costs:
    inspection_usd: 0
    financing_usd: 0
    standby_usd: 0
    bridge_usd: 0
    cure_usd: 0
    backup_usd: 0
    overtime_usd: 0
    delay_usd: 0
```

### Private state values

Use the existing role-private state mechanism. Do not place these values in public canonical state.

#### Steel supplier

```yaml
unrestricted_cash_usd: 350000
maximum_outside_financing_usd: 450000
outside_financing_cost_usd: 80000
cash_required_to_ready_lot_a_usd: 300000
cash_required_to_ready_full_sequence_usd: 1150000
competing_shop_work_margin_usd: 280000
competing_work_delay_to_lot_b_ticks: 3
known_lot_b_nonconformance: true
true_lot_values_and_document_status: visible
```

#### General contractor

```yaml
project_delay_cost_per_tick_usd: 220000
maximum_gc_bridge_usd: 300000
backup_reservation_cost_usd: 120000
backup_activation_cost_usd: 1600000
backup_delivery_tick_if_activated: 20
internal_schedule_float_ticks: 1
```

#### Owner

```yaml
unallocated_contingency_usd: 1200000
immediate_equity_capacity_usd: 400000
additional_equity_approval_delay_ticks: 1
private_delay_cost_per_tick_usd: 450000
```

#### Lender

```yaml
maximum_offsite_draw_usd: 1400000
base_advance_rate: 0.80
minimum_completion_reserve_usd: 1000000
maximum_controlled_escrow_usd: 250000
```

#### Inspector

```yaml
available_review_options:
  - scope: DOCUMENT_ONLY
    tick: 12
    cost_usd: 20000
  - scope: LOT_A_TARGETED
    tick: 12
    cost_usd: 45000
  - scope: LOT_A_AND_SAMPLE_B
    tick: 13
    cost_usd: 65000
  - scope: FULL_SEQUENCE
    tick: 13
    cost_usd: 90000
ordinary_next_full_slot_tick: 15
```

#### Steel erector / labor subcontractor

```yaml
full_hold_internal_cost_usd: 180000
split_hold_internal_cost_usd: 100000
outside_project_margin_usd: 280000
next_full_availability_if_released: 23
remobilization_cost_usd: 150000
```

## 5. Firm goals

Reuse the existing payoff ledger. Add only S01-specific payoff terms and events.

| Organization | Private goal represented by the ledger |
|---|---|
| Supplier | Preserve contract margin and liquidity; avoid uncompensated cure, financing expense, delay liability, or loss of the package |
| GC | Preserve fee and schedule incentive; avoid unsupported certification, unreimbursed bridge use, extended conditions, and unnecessary replacement |
| Owner | Preserve completed-project value; limit contingency, equity exposure, financing risk, and delay |
| Lender | Preserve completion reserves and collateral controls while avoiding a project-threatening funding interruption |
| Inspector | Produce a timely and accurate disposition without false acceptance, unnecessary delay, or excessive overtime |
| Erector | Preserve crew utilization and package margin; avoid unpaid standby, lost outside work, and inefficient remobilization |

Do not add persona-only goals. Every payoff-relevant event must be emitted by a scenario consequence handler.

The terminal report must separately expose:

- project success;
- each organization's realized payoff;
- each organization's private-success threshold result;
- coalition success, defined as project success plus all six private thresholds met.

Exact utility weights may remain in the existing S01 parameter/config file, but deterministic fixtures must establish the intended ordering described in Section 14.

## 6. Decision graph

Implement the scenario using the existing event/phase loop. Do not build a generic DAG runtime.

The new S01 consists of 15 scenario phases and three resolution handlers. There are exactly 18 required agent decisions: three for each organization.

Every valid S01 V2 run must traverse all 18 decisions. Earlier choices may make a later role choose zero funding, hold, reject, release, or accept delay, but they must not skip that role's node. The scenario may not terminate before `S01_C6_ERECTOR_MOBILIZATION` except because a required output is operationally invalid and the existing harness blocks the run.

```text
S01_A1_SUPPLIER_APPLICATION
        |
        v
S01_A2_GC_INITIAL_REVIEW
        |
        v
S01_A3_PARALLEL_INITIAL_POSITIONS
  - Owner provisional position
  - Inspector review plan
  - Erector capacity offer
        |
        v
S01_A4_LENDER_PROVISIONAL_POSITION
        |
        v
S01_R1_VERIFY_AND_PUBLISH
        |
        v
S01_B1_SUPPLIER_COMMITMENT
        |
        v
S01_B2_GC_INTEGRATED_PACKAGE
        |
        v
S01_B3_PARALLEL_TECHNICAL_AND_LABOR
  - Inspector disposition
  - Erector binding commitment
        |
        v
S01_B4_OWNER_PACKAGE_DECISION
        |
        v
S01_B5_LENDER_RELEASE_DECISION
        |
        v
S01_R2_COMMIT_AND_PRODUCE
        |
        v
S01_C1_SUPPLIER_STATUS_AND_RECOVERY
        |
        v
S01_C2_GC_RECOVERY_PLAN
        |
        v
S01_C3_INSPECTOR_FINAL_DISPOSITION
        |
        v
S01_C4_OWNER_FINAL_POSITION
        |
        v
S01_C5_LENDER_SUPPLEMENTAL_POSITION
        |
        v
S01_C6_ERECTOR_MOBILIZATION
        |
        v
S01_R3_TERMINAL_RESOLUTION
```

### Agent-to-node map

| Organization | Decision 1 | Decision 2 | Decision 3 |
|---|---|---|---|
| Supplier | A1 | B1 | C1 |
| GC | A2 | B2 | C2 |
| Owner | A3-owner | B4 | C4 |
| Lender | A4 | B5 | C5 |
| Inspector | A3-inspector | B3-inspector | C3 |
| Erector | A3-erector | B3-erector | C6 |

## 7. Phase and information-flow contract

### Observation assembly

For every activated agent, use the current observation builder and include only:

1. public canonical project state;
2. role-private canonical state;
3. structured records authorized for that role;
4. messages delivered since that role's prior action;
5. active offers addressed to that role;
6. its own private notes;
7. its own directed assessment matrix;
8. the schema and allowed values for the active decision node.

Do not expose other roles' private state or undelivered messages.

### Sequential phases

A sequential phase closes only after the single active organization's required decision validates. Its decision record and outgoing communications are then logged and made available to downstream phases.

Scenario consequences should generally be deferred to `R1`, `R2`, and `R3`. Limited immediate effects explicitly listed in this spec—such as paying a backup reservation fee—may be applied at phase close if that matches existing S01 conventions.

### Parallel phases

`S01_A3_PARALLEL_INITIAL_POSITIONS` activates Owner, Inspector, and Erector from the same immutable post-A2 snapshot.

`S01_B3_PARALLEL_TECHNICAL_AND_LABOR` activates Inspector and Erector from the same immutable post-B2 snapshot.

Required behavior:

- agent calls may execute in any internal order;
- no participant sees another participant's same-phase submission;
- validated submissions are stored as pending;
- no state consequences are applied until every required submission is valid;
- the barrier closes atomically;
- outgoing messages from the parallel phase are delivered only after barrier closure.

If the current phase implementation already provides this behavior, reuse it. If it does not, implement a small S01-local pending-submission buffer rather than a general parallel workflow framework.

### Message timing

A message becomes visible at the next phase in which its recipient is active. Messages do not interrupt an active phase and do not create unscheduled agent calls.

## 8. Structured decision schemas

Use the existing `decisions` collection and decision-node registry. Each node below is one required structured decision. Numeric bounds must be configured and validated.

Free-form conditions are prohibited. Any enforceable condition must use an allowlisted condition code.

### A1 — Supplier application

Decision ID:

```text
S01_A1_SUPPLIER_APPLICATION
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `claimed_complete_value_usd` | integer, `0..2400000` |
| `payment_requested_usd` | integer, `0..2400000` |
| `advance_requested_usd` | integer, `0..1200000` |
| `price_adjustment_requested_usd` | integer, `0..1000000` |
| `delivery_plan` | `FULL_SEQUENCE`, `PHASED_SEQUENCE`, `DELAYED_SEQUENCE` |
| `lot_a_delivery_tick` | integer, `12..20` |
| `lot_b_delivery_tick` | integer, `12..24` |
| `disclosed_exceptions` | set of allowlisted exception codes |
| `submitted_document_ids` | subset of documents currently available to supplier |

Exception codes:

```text
TITLE_DOCUMENT_GAP
QUALITY_RECORD_GAP
KNOWN_NONCONFORMANCE
LIQUIDITY_CONSTRAINT
CAPACITY_CONFLICT
```

Harness action:

- create/update payment application `PA-01`;
- store time-indexed structured claims from the numeric and status fields;
- deliver the application, attachments, and supplier communications to the GC;
- do not transfer funds or change lot acceptance.

### A2 — GC initial review

Decision ID:

```text
S01_A2_GC_INITIAL_REVIEW
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `review_strategy` | `DESK`, `TARGETED_INSPECTION`, `FULL_INSPECTION` |
| `provisional_certified_value_usd` | integer, `0..2400000` |
| `backup_action` | `NONE`, `RESERVE`, `BEGIN_QUALIFICATION` |
| `preliminary_erection_strategy` | `FULL`, `PHASED`, `HOLD` |
| `gc_bridge_ceiling_usd` | integer, `0..300000` |
| `requested_document_types` | set of allowlisted document types |
| `owner_lender_package_document_ids` | subset of received documents |
| `inspector_package_document_ids` | subset of received documents |

Harness action:

- record provisional certification;
- create the selected review request;
- reserve backup and charge `$120,000` if `RESERVE` is selected;
- route only the structured package and documents selected by the GC;
- activate the A3 parallel phase.

### A3-owner — Owner provisional position

Decision ID:

```text
S01_A3_OWNER_PROVISIONAL_POSITION
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `offsite_payment_posture` | `SUPPORT`, `CONDITIONAL`, `DO_NOT_SUPPORT` |
| `owner_funding_ceiling_usd` | integer, `0..1200000` |
| `immediate_equity_ceiling_usd` | integer, `0..400000` |
| `maximum_total_recovery_cost_usd` | integer, `0..2500000` |
| `maximum_accepted_delay_ticks` | integer, `0..8` |
| `allow_gc_bridge_reimbursement` | boolean |
| `required_control_codes` | set of allowlisted control codes |

### A3-inspector — Inspector review plan

Decision ID:

```text
S01_A3_INSPECTOR_REVIEW_PLAN
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `inspection_scope` | `DOCUMENT_ONLY`, `LOT_A_TARGETED`, `LOT_A_AND_SAMPLE_B`, `FULL_SEQUENCE` |
| `inspection_tick` | integer valid for selected scope |
| `rely_on_supplier_qc` | boolean |
| `reserve_reinspection_tick` | nullable integer, `13..17` |

### A3-erector — Erector capacity offer

Decision ID:

```text
S01_A3_ERECTOR_CAPACITY_OFFER
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `capacity_offer` | `FULL_HOLD`, `SPLIT_HOLD`, `RELEASE` |
| `hold_through_tick` | integer, `12..18` |
| `standby_price_usd` | integer, `0..400000` |
| `full_mobilization_tick` | nullable integer, `14..23` |
| `partial_mobilization_tick` | nullable integer, `14..23` |
| `overtime_available` | boolean |
| `offer_expiration_phase` | fixed value `S01_B3_PARALLEL_TECHNICAL_AND_LABOR` |

A3 phase close creates provisional records only. No owner funds, inspection findings, or labor commitment are realized yet.

### A4 — Lender provisional position

Decision ID:

```text
S01_A4_LENDER_PROVISIONAL_POSITION
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `draw_posture` | `POTENTIALLY_ELIGIBLE`, `LIMITED`, `NOT_ELIGIBLE` |
| `maximum_draw_usd` | integer, `0..1400000` |
| `advance_rate` | decimal, `0.0..0.80` |
| `escrow_cap_usd` | integer, `0..250000` |
| `minimum_owner_equity_usd` | integer, `0..400000` |
| `required_control_codes` | set of allowlisted control codes |
| `review_timing` | `CURRENT_DRAW`, `NEXT_DRAW` |

### B1 — Supplier commitment

Decision ID:

```text
S01_B1_SUPPLIER_COMMITMENT
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `provisional_offer_actions` | list of offer IDs with `ACCEPT`, `COUNTER`, or `REJECT` |
| `cure_plan` | `DOCUMENT_CURE`, `LOT_A_CURE`, `FULL_SEQUENCE_CURE`, `NO_CURE` |
| `supplier_cash_committed_usd` | integer, `0..350000` |
| `outside_financing_usd` | integer, `0..450000` |
| `outside_work_action` | `DECLINE`, `ACCEPT_PARTIAL`, `ACCEPT_FULL` |
| `requested_owner_or_gc_support_usd` | integer, `0..1200000` |
| `requested_price_adjustment_usd` | integer, `0..1000000` |
| `lot_a_commitment_tick` | integer, `12..20` |
| `lot_b_commitment_tick` | integer, `12..24` |
| `proposed_sequence` | `FULL`, `PHASED` |
| `condition_codes` | set of allowed condition codes |

### B2 — GC integrated package

Decision ID:

```text
S01_B2_GC_INTEGRATED_PACKAGE
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `supplier_proposal_action` | `ACCEPT`, `COUNTER`, `REJECT` |
| `final_certified_payment_usd` | integer, `0..2400000` |
| `gc_bridge_usd` | integer, `0..300000` |
| `owner_funds_requested_usd` | integer, `0..1200000` |
| `lender_draw_requested_usd` | integer, `0..1400000` |
| `supplier_price_adjustment_usd` | integer, `0..1000000` |
| `selected_labor_offer_id` | nullable existing offer ID |
| `inspection_path` | `USE_CURRENT`, `EXPAND_SCOPE`, `REINSPECT` |
| `erection_sequence` | `FULL`, `PHASED`, `DELAY` |
| `backup_action` | `DROP`, `MAINTAIN`, `ACTIVATE` |
| `late_credit_usd` | integer, `0..500000` |
| `condition_codes` | set of allowed condition codes |

### B3-inspector — Inspector disposition

Decision ID:

```text
S01_B3_INSPECTOR_DISPOSITION
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `disposition` | `NO_RELEASE`, `LOT_A_CONDITIONAL`, `LOT_A_RELEASED`, `FULL_RELEASED` |
| `required_cure_codes` | set of allowlisted cure codes |
| `required_test_codes` | set of allowlisted test codes |
| `reinspection_tick` | nullable integer, `13..18` |
| `maximum_releasable_value_usd` | integer, bounded by inspected and verified value |

The harness must reject a disposition that exceeds the selected inspection scope or actual findings.

### B3-erector — Erector binding commitment

Decision ID:

```text
S01_B3_ERECTOR_BINDING_COMMITMENT
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `offer_action` | `ACCEPT_PACKAGE`, `COUNTER`, `RELEASE` |
| `capacity_commitment` | `FULL`, `SPLIT`, `NONE` |
| `mobilization_tick` | nullable integer, `14..23` |
| `standby_compensation_usd` | integer, `0..400000` |
| `overtime_commitment` | `NONE`, `LIMITED`, `FULL` |
| `minimum_releasable_value_usd` | integer, `0..2400000` |
| `condition_codes` | set of allowed condition codes |

### B4 — Owner package decision

Decision ID:

```text
S01_B4_OWNER_PACKAGE_DECISION
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `package_action` | `APPROVE`, `MODIFY`, `REJECT` |
| `owner_funding_usd` | integer, `0..1200000` |
| `owner_equity_usd` | integer, `0..400000` |
| `approved_price_adjustment_usd` | integer, `0..1000000` |
| `approved_standby_usd` | integer, `0..400000` |
| `maximum_scenario_cost_usd` | integer, `0..3000000` |
| `accepted_delay_ticks` | integer, `0..8` |
| `condition_codes` | set of allowed condition codes |

### B5 — Lender release decision

Decision ID:

```text
S01_B5_LENDER_RELEASE_DECISION
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `release_action` | `RELEASE`, `PARTIAL_RELEASE`, `ESCROW`, `HOLD` |
| `draw_release_usd` | integer, `0..1400000` |
| `escrow_release_usd` | integer, `0..250000` |
| `completion_reserve_after_usd` | nonnegative integer |
| `owner_equity_required_usd` | integer, `0..400000` |
| `condition_codes` | set of allowed condition codes |

### C1 — Supplier status and recovery

Decision ID:

```text
S01_C1_SUPPLIER_STATUS_AND_RECOVERY
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `reported_lot_a_status` | `READY`, `PARTIAL`, `NOT_READY` |
| `reported_lot_b_status` | `READY`, `PARTIAL`, `NOT_READY` |
| `reported_lot_a_delivery_tick` | integer, `12..24` |
| `reported_lot_b_delivery_tick` | integer, `12..28` |
| `disclosed_issue_codes` | set of allowlisted issue codes |
| `ship_action` | `SHIP_A`, `SHIP_BOTH`, `HOLD_ALL` |
| `recovery_action` | `NONE`, `EXPEDITE`, `ADDITIONAL_CURE`, `SUBSTITUTE`, `ACCEPT_DELAY` |
| `supplier_recovery_spend_usd` | integer, `0..500000` |
| `additional_payment_request_usd` | integer, `0..750000` |

### C2 — GC recovery plan

Decision ID:

```text
S01_C2_GC_RECOVERY_PLAN
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `status_response` | `RELY`, `VERIFY`, `CHALLENGE` |
| `recovery_plan` | `PROCEED_FULL`, `PROCEED_PHASED`, `ACCELERATE`, `ACTIVATE_BACKUP`, `ACCEPT_DELAY` |
| `additional_verification` | `NONE`, `DOCUMENT`, `PHYSICAL` |
| `supplemental_gc_bridge_usd` | integer, `0..300000` minus prior bridge use |
| `credits_action` | `ENFORCE`, `DEFER`, `WAIVE` |
| `requested_owner_support_usd` | integer, `0..750000` |
| `requested_lender_support_usd` | integer, `0..750000` |
| `resequence_downstream_work` | boolean |

### C3 — Inspector final disposition

Decision ID:

```text
S01_C3_INSPECTOR_FINAL_DISPOSITION
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `lot_a_disposition` | `RELEASE`, `CONDITIONAL`, `HOLD` |
| `lot_b_disposition` | `RELEASE`, `CONDITIONAL`, `HOLD` |
| `additional_testing` | `NONE`, `TARGETED`, `FULL` |
| `approved_shipping_value_usd` | integer, bounded by findings and true ready value |
| `required_followup_codes` | set of allowlisted follow-up codes |

### C4 — Owner final position

Decision ID:

```text
S01_C4_OWNER_FINAL_POSITION
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `supplemental_funding_usd` | integer, `0..750000` |
| `accepted_additional_cost_usd` | integer, `0..1500000` |
| `accepted_additional_delay_ticks` | integer, `0..8` |
| `activate_remaining_contingency` | boolean |
| `owner_cost_share_usd` | integer, `0..1500000` |
| `gc_cost_share_usd` | integer, `0..750000` |
| `supplier_cost_share_usd` | integer, `0..750000` |

Cost shares must sum to the accepted recovery cost when a cost-allocation package is used.

### C5 — Lender supplemental position

Decision ID:

```text
S01_C5_LENDER_SUPPLEMENTAL_POSITION
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `supplemental_action` | `RELEASE`, `ESCROW`, `REQUIRE_EQUITY`, `HOLD` |
| `supplemental_draw_usd` | integer, `0..750000` and within remaining headroom |
| `reserve_exception_usd` | integer, `0..250000` |
| `additional_owner_equity_usd` | integer, `0..400000` minus prior equity use |
| `condition_codes` | set of allowed condition codes |

### C6 — Erector mobilization

Decision ID:

```text
S01_C6_ERECTOR_MOBILIZATION
```

Required fields:

| Field | Type / allowed values |
|---|---|
| `mobilization_action` | `FULL`, `PHASED`, `OVERTIME`, `DELAY`, `RELEASE` |
| `mobilization_tick` | integer, `14..25` |
| `crew_capacity_fraction` | decimal, `0.0..1.0` |
| `crane_capacity_fraction` | decimal, `0.0..1.0` |
| `incremental_cost_usd` | integer, `0..500000` |
| `remobilization_tick_if_released` | nullable integer, `20..28` |

## 9. Allowlisted controls and conditions

Do not parse free text to decide whether an offer or commitment is enforceable.

Initial condition/control code set:

```text
TITLE_COMPLETE
INSURANCE_COMPLETE
LIEN_PROTECTION_COMPLETE
INSPECTION_REPORT_AVAILABLE
LOT_A_RELEASED
FULL_SEQUENCE_RELEASED
OWNER_FUNDS_MINIMUM
OWNER_EQUITY_MINIMUM
LENDER_DRAW_MINIMUM
GC_BRIDGE_AVAILABLE
LABOR_FULL_HOLD_CONFIRMED
LABOR_SPLIT_HOLD_CONFIRMED
DOCUMENT_CURE_COMPLETE
PHYSICAL_CURE_COMPLETE
REINSPECTION_PASSED
DIRECT_PAYMENT
CONTROLLED_ESCROW
```

Adding a new code requires:

- a deterministic predicate against canonical state;
- a unit test for true and false cases;
- no LLM interpretation.

## 10. Resolution handlers

### R1 — Verify and publish

Handler ID:

```text
S01_R1_VERIFY_AND_PUBLISH
```

Inputs:

- validated A1–A4 decisions;
- documents actually submitted and routed;
- hidden lot state;
- selected inspection scope and timing.

Required effects:

1. Execute the selected inspection against hidden lot state.
2. Generate a formal inspection record.
3. Compute verified value and currently eligible stored-material value.
4. Charge inspection cost.
5. Preserve any GC backup reservation and cost.
6. Create provisional owner, lender, and labor offers.
7. Deliver role-appropriate records and messages.
8. Advance to B1.

Core calculation:

```text
eligible_stored_value = min(
    true_completed_value_in_scope,
    documented_value_in_scope,
    insured_value_in_scope,
    title_transferable_value_in_scope,
    inspector_verified_value
)
```

Inspection scope limits:

| Scope | Earliest tick | Maximum physical scope |
|---|---:|---|
| `DOCUMENT_ONLY` | 12 | submitted documents only; no physical release |
| `LOT_A_TARGETED` | 12 | Lot A |
| `LOT_A_AND_SAMPLE_B` | 13 | Lot A plus sampled Lot B condition |
| `FULL_SEQUENCE` | 13 | Lots A and B |

The selected scope determines what the inspector can know and later release. It does not automatically dictate the inspector agent's disposition.

### R2 — Commit and produce

Handler ID:

```text
S01_R2_COMMIT_AND_PRODUCE
```

Inputs:

- validated B1–B5 decisions;
- R1 findings;
- all structured conditions;
- private resource limits.

Required effects:

1. Validate condition compatibility.
2. Calculate maximum legally and contractually supportable draw.
3. Transfer only compatible committed funds.
4. Apply owner equity, owner funding, GC bridge, supplier cash, and outside financing.
5. Apply supplier financing cost when outside financing is used.
6. Apply supplier outside-work capacity effect.
7. Execute selected documentation cure, physical cure, fabrication, and shipping preparation.
8. Commit or release labor and crane capacity.
9. Apply standby and backup costs.
10. Determine actual Lot A and Lot B readiness ticks.
11. Advance to C1 with exact readiness private to the supplier and inspection knowledge private to the inspector.

Draw calculation:

```text
maximum_supported_draw = min(
    lender_maximum_draw,
    lender_advance_rate * eligible_stored_value,
    amount_preserving_required_completion_reserve,
    gc_final_certified_payment,
    owner_approved_package_amount
)
```

Actual draw is the minimum of the requested, approved, and supportable amounts after all coded conditions are checked.

Supplier execution tasks:

| Task | Cash required | Effect |
|---|---:|---|
| Lot A document/title cure and shipment preparation | `$300,000` | Lot A can be ready by tick 14 if inspection permits |
| Complete Lot B fabrication | `$450,000` | Advances Lot B physical completion |
| Cure Lot B nonconformance | `$150,000` | Clears physical defect after required review |
| Complete Lot B records/title | `$100,000` | Makes value documentable and transferable |
| Lot B shipping preparation | `$150,000` | Enables shipping after release |

Full-sequence cash need from tick 11 is `$1,150,000`.

Available supplier funds are:

```text
supplier_cash_committed
+ outside_financing
+ actual_project_funds_received
```

The supplier's selected cure plan controls which tasks receive funds. The harness must not optimize task allocation on the supplier's behalf.

Outside-work effects:

| Action | Supplier payoff effect | Project effect |
|---|---:|---|
| `DECLINE` | none | none |
| `ACCEPT_PARTIAL` | `+$140,000` margin | Lot B readiness `+1` tick |
| `ACCEPT_FULL` | `+$280,000` margin | Lot B readiness `+3` ticks |

### R3 — Terminal resolution

Handler ID:

```text
S01_R3_TERMINAL_RESOLUTION
```

Inputs:

- validated C1–C6 decisions;
- actual readiness;
- final inspector dispositions;
- available funding;
- labor commitment and mobilization;
- backup status;
- recovery spending and sequencing.

Required effects:

1. Compare supplier status reports with its private known state and log claim differences.
2. Apply any valid supplemental funding and recovery work.
3. Determine which lots are legally and technically releasable.
4. Ship only ready lots selected for shipment.
5. Erect only released lots within committed crew and crane capacity.
6. Apply phased, full, delayed, overtime, backup, and remobilization consequences.
7. Propagate local delay into project completion.
8. Apply project and role-specific costs.
9. Emit payoff events.
10. Evaluate project, role, and coalition success.
11. Write the terminal replay record and summary.

Base schedule rules:

| Result | Project completion effect |
|---|---|
| Full sequence released and full crew starts by tick 15 | completion remains tick 40 |
| Lot A released and phased crew starts by tick 15; Lot B released by tick 18 | completion tick 41 |
| First erection begins after tick 15 | add one completion tick per late start tick |
| Erector released and remobilizes at tick 23 | minimum completion tick 50 |
| Backup activated, delivered at tick 20, and original crew retained | completion approximately tick 45 before other delays |
| Unreleased material installed | compliance failure regardless of cost or schedule |

Project delay cost:

```text
$250,000 * max(0, final_completion_tick - 40)
```

Preserve existing project-level success evaluation against the `$102,000,000` ceiling, tick 48 deadline, and required deliverables.

## 11. Communications

Retain the existing `communications` object and validation.

Recommended S01 fields, if already supported:

```json
{
  "recipients": ["general_contractor"],
  "visibility": "PRIVATE | PUBLIC",
  "message_type": "NOTICE | REQUEST | QUESTION | EXPLANATION | STATUS",
  "related_decision_id": "S01_A1_SUPPLIER_APPLICATION",
  "body": "Free-form text"
}
```

Rules:

- Communications are optional.
- Communications are delivered according to explicit recipients and existing visibility rules.
- A message cannot transfer money, certify value, reserve labor, release a draw, approve material, alter a date, or create an enforceable condition.
- State-changing intent must also appear in the active structured decision.
- Do not add natural-language parsing to infer commitments.

## 12. Trust and assessments

Trust remains private, directed, and agent-submitted.

For S01 V2:

- assessment activity is optional at every agent turn;
- if the common submission envelope currently requires `assessment_updates` or `assessment_reviews`, retain the fields but allow empty arrays; do not change the envelope solely to permit omission;
- an empty `assessment_updates` collection carries prior scores forward;
- no no-update review is required;
- evidence IDs are not required;
- reasons are not required;
- an agent may update one, several, or no dimensions;
- the harness validates only counterparty identity, known dimension names, and numeric bounds;
- trust scores do not automatically change any decision, price, approval, or state transition;
- do not prompt agents to review trust after every event.

Recommended narrow scenario policy:

```yaml
assessment_policy:
  empty_updates_valid: true
  reviews_required: false
  evidence_ids_required: false
```

Implement this through the smallest available validation/configuration change. Do not refactor the assessment subsystem or alter the top-level submission envelope unless the existing validator makes that unavoidable.

Continue logging:

- whether an update occurred;
- which counterparty and dimensions changed;
- when the update occurred;
- old and new values.

The experiment will later analyze whether and when agents choose to update trust.

## 13. Claims and provenance

Do not build a generic claims framework in this update unless one already exists.

For S01, mark selected structured decision fields as time-indexed claims in the existing event log:

- `claimed_complete_value_usd`;
- requested payment and advance;
- promised delivery ticks;
- reported Lot A and Lot B status;
- reported delivery ticks;
- stated recovery commitment.

For each marked field, log:

```text
speaker
phase
field name
submitted value
private truth available to speaker at that phase
public or private audience
later realized value where applicable
```

Primary scenario state must not depend on classifying free-form prose.

## 14. Required deterministic witnesses

The coding agent must add scripted fixtures before live-agent runs.

### Witness 1 — Efficient phased coalition success

Expected broad path:

- supplier discloses documentation and Lot B issues;
- GC selects targeted verification and phased sequencing;
- inspector reviews Lot A early and sets a Lot B cure/reinspection path;
- owner provides bounded support;
- lender releases against eligible verified value;
- erector accepts a compensated split hold;
- supplier cures Lot B;
- Lot A ships first and phased erection begins;
- Lot B follows by tick 18.

Expected terminal class:

```text
PROJECT_SUCCESS = true
COALITION_SUCCESS = true
completion_tick = 41 or earlier
final_cost_usd <= 102000000
```

### Witness 2 — Conservative project success

Expected broad path:

- full inspection;
- backup reserved;
- larger standby cost;
- lender waits for more complete documentation;
- supplier uses some outside financing;
- full sequence proceeds later but within the envelope.

Expected terminal class:

```text
PROJECT_SUCCESS = true
COALITION_SUCCESS may be true or false depending on calibrated private thresholds
welfare lower than Witness 1
```

### Witness 3 — Project success with private-role failure

Expected broad path:

- supplier self-finances at high cost or erector holds below its reservation value;
- project completes on time;
- at least one role misses its private threshold.

Expected terminal class:

```text
PROJECT_SUCCESS = true
COALITION_SUCCESS = false
```

### Witness 4 — Coordination failure

Expected broad path:

- supplier overstates readiness;
- GC overcertifies or fails to preserve options;
- inspection reveals unsupported value;
- lender holds the draw;
- owner does not fill the gap;
- erector releases capacity;
- supplier accepts competing work;
- later recovery cannot restore the erection window.

Expected terminal class:

```text
PROJECT_SUCCESS = false
completion_tick > 48 or final_cost_usd > 102000000
```

### Witness 5 — Excessive-conservatism failure

Expected broad path:

- each organization chooses maximum self-protection;
- verification and funding are delayed;
- labor capacity is released;
- backup and remobilization costs accumulate;
- no deception is required for failure.

Expected terminal class:

```text
PROJECT_SUCCESS = false
failure attributable to coordination and delay, not invalid output
```

## 15. Incremental implementation slices

The coding agent should implement one slice at a time. Each slice must leave the test suite green.

### Slice 1 — Versioned S01 shell and state

Build:

- register `S01_V2_OFFSITE_STEEL_DRAW`;
- add the S01-specific state and private-state seed data;
- add phase identifiers and transitions with placeholder handlers;
- preserve S01 V1 and every other scenario.

Acceptance:

- existing fixtures pass unchanged;
- S01 V2 initializes and serializes;
- replay includes the new state object;
- no live model calls are required.

Non-goals:

- no payoff tuning;
- no complete decision schemas;
- no trust changes.

### Slice 2 — Cycle A and R1

Build:

- A1, A2, A3, and A4 decision schemas;
- parallel A3 barrier behavior;
- document routing and review records;
- R1 inspection and eligible-value calculation.

Acceptance:

- every A-node rejects invalid enums and out-of-range numbers;
- A3 agents cannot see same-phase submissions;
- R1 produces repeatable findings from the same input state;
- no cash is transferred before R2.

### Slice 3 — Cycle B and R2

Build:

- B1–B5 schemas;
- B3 barrier behavior;
- allowlisted conditions;
- funding compatibility;
- supplier task execution;
- labor commitment;
- actual readiness calculation.

Acceptance:

- incompatible conditions do not silently become an agreement;
- draw and cash-transfer calculations match hand-worked cases;
- supplier task selection, not the harness, determines use of funds;
- readiness remains private to the correct roles.

### Slice 4 — Cycle C and R3

Build:

- C1–C6 schemas;
- final funding, release, shipment, erection, schedule, and cost handlers;
- terminal project and payoff evaluation;
- structured claim logging.

Acceptance:

- all six agents have exactly three required decisions;
- all five deterministic witnesses terminate in the intended class;
- no free-form message changes canonical state;
- replay reconstructs all terminal fields.

### Slice 5 — Optional trust behavior

Build:

- S01 scenario policy making updates optional;
- remove required no-update reviews for S01;
- remove evidence-ID requirement for S01 assessment updates;
- preserve existing score bounds and private directed storage.

Acceptance:

- a run with no assessment activity is valid;
- a valid bounded update is stored;
- malformed counterpart names or out-of-range scores remain invalid;
- other scenarios retain their current assessment behavior unless explicitly migrated later.

### Slice 6 — Scripted balance and regression pack

Build:

- five deterministic witnesses;
- at least one role-action ablation per organization;
- summary output for the 18 decisions, messages, trust changes, payoff events, and terminal result.

Acceptance:

- replacing any organization's key decision with a neutral or adverse fixture changes a payoff, feasible action, or project outcome in at least one replay;
- at least two materially different project-success paths exist;
- at least one project-success/private-failure path exists;
- cost, schedule, and compliance failures are separately testable;
- S00 and S02–S05 regressions remain unchanged.

## 16. Required tests

At minimum, add:

### Schema tests

- every decision node accepts one valid fixture;
- every enum rejects an unknown value;
- every numeric field rejects below-minimum and above-maximum values;
- document and offer references must exist and be visible to the actor;
- conditions must come from the allowlist.

### Information-boundary tests

- each role receives only authorized private state;
- A3 actors cannot see each other's pending outputs;
- B3 actors cannot see each other's pending outputs;
- lender A4 sees the closed A3 records;
- private supplier readiness after R2 is not leaked to other roles;
- inspector knowledge depends on selected inspection scope.

### Consequence tests

- eligible-value formula;
- lender advance-rate and reserve caps;
- owner equity and GC bridge caps;
- supplier cash-task execution;
- outside-work delay effects;
- labor release and remobilization effects;
- inspection-release bounds;
- prohibition on installing unreleased steel;
- cost and schedule propagation;
- payoff-event accounting without double-counting transfers.

### Replay tests

- same initial state plus same 18 decisions yields identical terminal state;
- invalid required output produces no phase consequence;
- phase-close and barrier records replay deterministically;
- trust omission carries previous values forward.

## 17. Completion criteria

This marginal update is complete when:

1. S01 V2 uses the existing event/phase architecture.
2. All six organizations are live decision-makers.
3. Each organization submits exactly three validated decisions.
4. There are 18 required decisions and three deterministic resolution handlers.
5. Natural-language communication remains optional and non-state-mutating.
6. Trust updating is entirely optional and unprompted as a requirement.
7. The harness applies all cash, inspection, production, delivery, labor, cost, schedule, compliance, and payoff consequences.
8. At least two distinct success paths and three distinct failure/private-failure classes are covered by fixtures.
9. Replays are deterministic.
10. S00 and S02–S05 are unchanged.

## 18. Explicit non-goals

Do not include any of the following in this task:

- Easy or Hard variants;
- a general scenario generator;
- a new generic workflow or DAG engine;
- a human-play UI;
- natural-language contract parsing;
- LLM-based consequence judging;
- mandatory trust reviews;
- evidence-grounded trust enforcement;
- public reputation;
- multi-project history;
- additional agents;
- a full economy;
- refactoring unrelated scenarios;
- benchmark-scale model runs.

The immediate deliverable is one realistic, replayable, six-agent Normal scenario implemented as a marginal extension of the current ConstructBench harness.
