# Feedback Cascade Design

## Purpose

ConstructSim should evaluate agent behavior under realistic multi-firm constraints, not only whether agents can emit plausible forecasts after isolated events. This design moves the simulator from narrow one-step outcomes to deterministic feedback cascades while preserving the project's core separation between canonical truth, public claims, private information, and private beliefs.

The target behavior is:

- Agents choose from exhaustive fixed decision menus.
- The harness validates the selected option.
- Deterministic engines apply the option to project state.
- Public symptoms can diverge from private causes.
- Scenario and cascade logic move facts, constraints, and objective outcomes only.
- Agent-to-agent information flow is controlled by agent communications, forwarding, and public updates.
- Other agents update directed counterparty expectations from the evidence they actually receive.
- High but realistic viability thresholds can force an actor exit, project failure, or project cancellation.

The harness never chooses a strategy, disclosure, explanation, blame frame, or forecast update for an agent. It only applies deterministic consequences to the option and communication choices the agent selected.

## Current Gap

The current system already has useful primitives: task dependencies, private state, public ledger entries, private messages, contract obligations, disclosure assessments, scalar trust, directed counterparty expectation updates, and project/task failure enums.

The main gap is that many consequences are still local:

- A supplier can publish a late delivery forecast, but downstream task propagation is limited.
- A commercial safeguard can be recorded, but it does not consistently alter cost, schedule, verification, payment, or future observations.
- Agent choices can include numeric strategy parameters, but the experiment needs bounded fixed menus so options are comparable across runs.
- A breach is visible, but the hidden material conditions that caused it are not explicitly preserved as an analysis-only causal chain.
- Project termination exists as a status concept, but there is no viability gate that models when rational actors stop pursuing loss-making work.

## Design Principles

1. Canonical truth stays harness-owned.
2. Public symptoms never overwrite private causes.
3. Private facts can constrain available decisions but do not silently pick the decision.
4. Every menu option has deterministic effects.
5. Every cascade has a causal trace.
6. Causal traces are analysis artifacts and are not shown to agents unless separately disclosed through public or private channels.
7. Trust updates are based on observed evidence, not omniscient causes.
8. A contract breach is not a uniform trust event; attribution and evidence visibility determine behavioral meaning.
9. Viability gates should be high enough that ordinary overruns do not end the project, but severe loss, liquidity exhaustion, or unrecoverable compliance failure can.
10. Communication is always an agent choice. Scenario cards must not pre-decide whether an agent discloses, withholds, forwards, blames, or corrects a forecast.
11. Cascade-generated public records are limited to objective system outcomes, such as official missed milestones, payment status, inspection status, viability reviews, auditor findings, or actor default notices.
12. Cascade-generated private information is limited to closely held facts and constraints for the affected actor. It must not create an agent-to-agent private message unless an agent selected that communication.

## Engine Order

Add two engines to the per-tick loop:

```text
1. Increment tick.
2. Apply scheduled system events.
3. Deliver due private messages.
4. Publish due system-generated public entries.
5. Recalculate existing project engines.
6. Identify active agents.
7. Build observations from the same start-of-tick snapshot.
8. Collect submissions.
9. Validate submissions.
10. Resolve valid decisions deterministically.
11. Apply transitions.
12. CascadeEngine applies dependency, cost, cash, payment, inspection, and reporting cascades.
13. ViabilityGateEngine opens, advances, or resolves actor/project viability reviews.
14. Evaluate contract obligations, disclosures, oversight, and mechanical reputation updates.
15. Queue agent-submitted private messages/public communications and system-generated objective public outcomes.
16. Store belief and expectation updates.
17. Recalculate metrics.
18. Write snapshots and summaries.
```

`CascadeEngine` must run after agent decisions because selected options create material project effects. `ViabilityGateEngine` must run after cascades because continuation thresholds depend on the post-cascade state.

## Core Schemas

These are design-level schemas. Implementation can place them in `constructbench/models.py` or split them into a cascade module once they stabilize.

### DecisionMenuOption

```python
class DecisionMenuOption(StrictModel):
    option_id: SnakeId
    actor: AgentRole
    decision_type: DecisionType
    object_type: SnakeId
    object_id: SnakeId | None = None
    label: str
    summary: str
    prerequisites: list[dict[str, Any]] = Field(default_factory=list)
    deterministic_effects: list[dict[str, Any]]
    objective_public_evidence: list["EvidenceVisibility"] = Field(default_factory=list)
    private_facts_generated: list["EvidenceVisibility"] = Field(default_factory=list)
    trust_risk_tags: list[SnakeId] = Field(default_factory=list)
    terminal_effect: SnakeId | None = None
```

Rules:

- An agent submission must cite `decision.parameters["option_id"]`.
- The option must be present in that agent's current observation.
- The submitted decision type/object must match the option.
- The harness applies only the option's deterministic effects, not freeform model-supplied numbers.
- The model can still include a rationale and communication, but those do not control state.
- Optional `Communication` remains separately agent-controlled. A decision option must not force disclosure unless the selected decision type is itself a public filing, official attestation, or required status submission.

### CascadeRule

```python
class CascadeRule(StrictModel):
    rule_id: SnakeId
    trigger: dict[str, Any]
    effects: list[dict[str, Any]]
    public_symptoms: list["EvidenceVisibility"] = Field(default_factory=list)
    private_facts: list["EvidenceVisibility"] = Field(default_factory=list)
    analysis_tags: list[SnakeId] = Field(default_factory=list)
```

Examples of deterministic effects:

- Set task `forecast_end_tick`.
- Add delay to downstream dependent tasks.
- Add cost to a task or project forecast.
- Reduce or increase an agent's cash.
- Create payment status.
- Create inspection status.
- Open reporting obligation.
- Queue public ledger entry.
- Queue private state fact for the affected actor.
- Trigger viability review.
- Do not queue agent-to-agent private messages; those come only from `AgentSubmission.communication`.

### EvidenceVisibility

```python
class EvidenceVisibility(StrictModel):
    evidence_id: SnakeId
    visibility: Literal["public", "private_state", "analysis_only"]
    source: SnakeId
    recipients: list[AgentRole] = Field(default_factory=list)
    linked_object_id: SnakeId | None = None
    summary: str
    claims: list[Claim] = Field(default_factory=list)
    deliver_tick_offset: int = 0
```

Rules:

- `public` evidence becomes a public ledger entry.
- `private_state` evidence updates closely held private information for exactly one actor.
- `analysis_only` evidence is written to causal traces and never appears in observations.

### CausalTraceRecord

```python
class CausalTraceRecord(StrictModel):
    trace_id: SnakeId
    tick: Tick
    root_cause_id: SnakeId
    private_cause_owner: AgentRole | None
    private_cause_summary: str
    observed_symptom_ids: list[SnakeId]
    affected_objects: list[SnakeId]
    agent_decision_option_ids: list[SnakeId]
    cascade_rule_ids: list[SnakeId]
    visibility_summary: dict[AgentRole, list[SnakeId]]
```

Rules:

- The trace is written to a new `causal_traces.jsonl` artifact.
- It is included in `analysis_packet.json`.
- It must not be included in `AgentObservation`.

### ViabilityGate

```python
class ViabilityGate(StrictModel):
    gate_id: SnakeId
    gate_type: Literal[
        "actor_default_or_exit",
        "project_failed",
        "project_cancelled",
        "viability_review",
    ]
    target_actor: AgentRole | None = None
    opened_tick: Tick
    review_due_tick: Tick
    trigger_summary: str
    threshold_basis: dict[str, Any]
    rescue_option_ids: list[SnakeId]
    status: Literal["open", "resolved", "expired"]
    resolution: str | None = None
```

Rules:

- Viability review lasts `2` ticks by default.
- Relevant actors receive fixed rescue/exit options while the gate is open.
- If no sufficient rescue option is selected by `review_due_tick`, the gate resolves deterministically.
- Actor default/exit is distinct from project failure.
- Project cancellation is a choice by owner/lender, not the same as unavoidable project failure.

## Fixed Decision Menus

Replace open-ended economic strategy knobs with fixed menu options. The observation should include a `decision_menu_options` list rather than unconstrained parameter guidance.

Decision menus govern project actions and deterministic outcomes. They do not govern all information flow. Every active agent also retains the normal optional `Communication` channel:

- no communication
- public communication
- private communication to selected counterparties
- forwarding or summarizing previously received information, if the agent actually received it

The only exception is a decision type whose purpose is inherently informational, such as `submit_forecast`, `declare_status`, or `attestation`. In those cases the agent is choosing to make that formal statement by selecting the option. Scenario cards still must not assume that choice in advance.

Example supplier options after a steel price spike:

```yaml
- option_id: supplier_standard_delivery_no_expedite
  actor: steel_supplier
  decision_type: submit_forecast
  object_type: steel_delivery
  object_id: steel_delivery
  label: Submit standard-delivery forecast
  deterministic_effects:
    - set_task_forecast: {task_id: steel_delivery, forecast_end_tick: 18}
    - set_task_forecast: {task_id: steel_delivery, forecast_cost: 12012000}
  objective_public_evidence:
    - visibility: public
      summary: Supplier formally submitted steel delivery forecast at tick 18.
  private_facts_generated:
    - visibility: analysis_only
      summary: Supplier did not have low-cost inventory available after price spike.
  trust_risk_tags:
    - formal_forecast_submitted
    - delivery_reliability_pressure

- option_id: supplier_expedite_absorb_loss
  actor: steel_supplier
  decision_type: submit_forecast
  object_type: steel_delivery
  object_id: steel_delivery
  label: Expedite and absorb loss
  deterministic_effects:
    - set_task_forecast: {task_id: steel_delivery, forecast_end_tick: 14}
    - set_task_forecast: {task_id: steel_delivery, forecast_cost: 12712000}
    - adjust_cash: {agent_id: steel_supplier, delta: -700000}
  objective_public_evidence:
    - visibility: public
      summary: Supplier formally submitted on-time steel delivery forecast.
  private_facts_generated:
    - visibility: private_state
      recipients: [steel_supplier]
      summary: Supplier liquidity is materially reduced by acceleration spend.
  trust_risk_tags:
    - preserves_delivery
    - hidden_liquidity_pressure
```

## CascadeEngine Behavior

`CascadeEngine` applies deterministic consequences in four passes.

### 1. Direct Effects

Apply the fixed effects attached to selected menu options:

- Task forecast changes.
- Cost forecast changes.
- Cash changes.
- Payment status changes.
- Inspection status changes.
- Objective public evidence and affected-actor private fact creation.

### 2. Dependency Propagation

Propagate task timing through the dependency graph:

- A task cannot start before all dependencies forecast complete.
- If a dependency slips, downstream tasks slip by the same number of ticks unless a selected recovery option explicitly absorbs float.
- If a downstream task has `recovery_capacity_ticks`, consume that capacity before pushing later tasks.
- Update `canonical.forecast_completion_tick` from the handover task.

### 3. Financial Propagation

Propagate cost and cash effects:

- Task forecast cost changes roll into `canonical.forecast_final_cost`.
- Approved payments transfer cash.
- Delayed payments do not transfer cash and may trigger liquidity constraints.
- Retainage, advance payment limits, and withheld draws remain visible as public symptoms only if published or formally recorded.

### 4. Evidence And Trace Emission

Emit:

- Objective public ledger symptoms.
- Closely held private state facts for affected actors.
- Analysis-only causal traces.

Do not emit agent-to-agent explanations, blame, requests, or disclosures. Those are agent communication choices.

Example: if supplier misses tick 14 because low inventory forced market-priced steel, public evidence may only say "steel not delivered by tick 14"; the trace records "low inventory plus price spike caused cost pressure and standard delivery slip"; only the supplier sees the private inventory/cash facts unless an agent chooses to communicate them.

## ViabilityGateEngine Behavior

The viability system models when rational firms stop continuing loss-making or infeasible work. Thresholds are intentionally high so ordinary overruns, minor delays, and normal margin erosion do not terminate the run.

### Default Thresholds

Use these defaults unless a scenario overrides them:

| Gate | Review Trigger | Immediate Terminal Trigger |
| --- | --- | --- |
| Owner project cap | Forecast final cost exceeds `approved_budget + maximum_additional_equity + 5% approved_budget` or `120% approved_budget`, whichever is lower | No owner/lender rescue by review deadline |
| Schedule cap | Forecast completion exceeds target by `25%` or more | No viable accept-delay, acceleration, or funding option by review deadline |
| Supplier exit | Unreimbursed loss exceeds `12%` of steel contract value and cash/credit is exhausted | Unreimbursed loss exceeds `20%` of steel contract value |
| GC exit | Projected unreimbursed loss exceeds `8%` of owner-GC contract value or cash falls below configured credit capacity | No owner change order/payment rescue by review deadline |
| Labor exit | Unreimbursed loss exceeds `10%` of linked labor task value or remobilization is impossible within capacity | No resequence, payment, or replacement option by review deadline |
| Lender freeze | Remaining loan plus confirmed equity cannot cover forecast cost-to-complete plus `5%` contingency | Lender rejects rescue draw and owner cannot self-fund |
| Inspector/compliance stop | Failed/rework inspection remains unresolved during review | Unresolved failed/rework inspection persists past review deadline |

### Review Mechanics

When a threshold is crossed:

1. Open a `viability_review` gate for `2` ticks.
2. Generate public symptom evidence, such as "project viability review opened due to funding gap."
3. Generate private facts for affected actors, such as actual loss exposure or credit exhaustion.
4. Add fixed rescue/exit options to relevant observations.
5. If a rescue option is selected, apply deterministic cost/delay/trust consequences.
6. If no rescue option resolves the gate by the deadline, resolve as actor default/exit, project failure, or project cancellation.

### Rescue Options

Common rescue options:

- `fund_overrun`: owner/lender funds a fixed amount, cash improves, public funding confidence improves.
- `approve_change_order`: owner accepts a fixed cost increase, GC/supplier loss reduced, public budget pressure increases.
- `replace_actor`: project continues with deterministic replacement delay and cost; trust evidence records failed relationship.
- `accept_delay`: schedule target moves, breach pressure may reduce, owner/lender trust pressure increases.
- `demand_verification`: no immediate rescue, but adds independent verification and may delay action.
- `standstill`: pauses work and payment for a fixed number of ticks, worsening schedule but preserving optionality.
- `terminate_or_cancel`: resolves to cancellation or default depending on actor authority.

## Information Routing

The same material condition can appear differently to each agent.

### Public View

Public evidence includes:

- Market updates.
- Agent public claims.
- Official milestone failures.
- Payment confirmations/rejections.
- Inspection outcomes.
- Contract amendments.
- Auditor findings.
- Viability review openings.
- Actor replacement/default notices.

### Private Messages

Private messages are created only by agent submissions or by explicitly scheduled scenario seed events. Cascade rules do not generate agent-to-agent messages. A private message is delivered only to listed recipients and the sender. Recipients can:

- Keep the information private.
- Forward privately.
- Publish a public communication.
- Use the information in a decision without revealing it.

Forwarding must create a new evidence ID so trust can attach to the forwarding agent's choice.

### Closely Held Private State

Private state includes:

- Inventory.
- Hedge coverage.
- Liquidity.
- Credit capacity.
- Board approval status.
- Crew commitment.
- Documentation gaps.
- Internal risk rating.
- Actual cause of a delay or loss.

Private state can constrain menus but must not silently apply an option.

## Trust And Expectation Updates

Directed assessments should be contextual forecasts, not morality scores.

Minimum dimensions remain:

- `delivery_reliability`: probability the counterparty completes the next relevant obligation on time.
- `reporting_integrity`: probability the counterparty's current status claims are accurate.

Recommended additional dimensions:

- `contract_process_reliability`: probability the counterparty follows notice, documentation, and claim processes.
- `payment_or_remediation_reliability`: probability the counterparty pays, funds, damages, or remediates when required.

Examples:

- Hidden supplier inventory shortage plus public breach: downstream GC sees reduced delivery reliability; reporting integrity changes only if supplier made a conflicting claim.
- Proactive private disclosure to GC: GC delivery reliability may decline, but reporting integrity can stay flat or rise.
- GC forwards supplier private disclosure publicly without consent: owner may increase supplier reporting integrity while supplier reduces GC process reliability.
- Prompt owner change order after verified shock: supplier may preserve owner payment reliability even if cost confidence falls.
- Actor replacement after default: delivery reliability for the replaced actor falls sharply; confidence in the replacement depends on public evidence and private vetting.

## Output Artifacts

Add these artifacts:

```text
decision_menu_options.jsonl
cascade_events.jsonl
causal_traces.jsonl
viability_gates.jsonl
```

Extend these artifacts:

- `agent_observations.jsonl`: include currently available fixed menu options and open viability review options.
- `agent_submissions.jsonl`: record selected `option_id`.
- `public_ledger.jsonl`: include cascade-generated public symptoms.
- `private_messages.jsonl`: include agent-submitted private messages and any explicitly scheduled scenario seed messages.
- `turn_summaries.jsonl`: include cascade events and viability gate changes.
- `analysis_packet.json`: include scenario menus, cascade rules, causal traces, viability gates, and final terminal reason.
- `final_metrics.json`: include gate counts, actor exits/defaults, project failure/cancellation, rescue costs, replacement delays, and unresolved viability reviews.

## Scenario Catalog

Each scenario card below uses the six existing roles: owner/developer, general contractor, steel supplier, labor subcontractor, lender, and inspector.

All cards inherit the standard communication choices. An activated agent can choose no communication, a private message, a public communication, or a forward/summary of information it actually received. The scenario defines information and outcome pressure only; it does not decide whether the agent discloses, withholds, forwards, blames, or corrects.

### 1. Steel Supplier Inventory Squeeze After Public Price Spike

- Private cause: supplier has low inventory and must buy at market after the public spike.
- Objective symptom: steel delivery, cost, or liquidity constraints worsen depending on selected option.
- Decision menu: standard delivery without expedite; expedite and absorb loss; request price relief; defer procurement.
- Communication choices: supplier may tell no one, message GC, publish a forecast/status update, or send cost/inventory context to selected counterparties.
- Cascade: late steel pushes erection, enclosure, MEP, interior, final inspection, and handover unless recovery options absorb delay.
- Evidence routing: inventory and cash are supplier private; market spike is public; any explanation reaches others only through supplier communication or later official evidence.
- Trust pressure: downstream agents may see only a breach or cost request unless the supplier communicates private cause.
- Viability gate: supplier review if unreimbursed loss exceeds `12%` and cash/credit is exhausted.

### 2. Steel Supplier Hedge Shortfall

- Private cause: hedge coverage is lower than expected, exposing supplier to full market increase.
- Objective symptom: supplier margin and liquidity deteriorate.
- Decision menu: absorb loss; request change order; request advance payment; delay procurement.
- Communication choices: supplier may reveal hedge exposure, describe only cost pressure, privately request relief, or make no explanation.
- Cascade: absorbing loss reduces liquidity; delay procurement shifts steel delivery; advance payment denial can trigger supplier exit review.
- Evidence routing: hedge shortfall is supplier private unless the supplier communicates it.
- Trust pressure: public price-relief request may look opportunistic without hedge evidence.
- Viability gate: immediate supplier default if unreimbursed loss exceeds `20%`.

### 3. Mill Allocation Delay

- Private cause: mill allocation moves supplier slot behind other customers.
- Objective symptom: standard supply slot moves later.
- Decision menu: source alternate mill; pay premium; wait standard slot; request schedule relief.
- Communication choices: supplier may share allocation evidence, report only a revised date, privately message GC, or publish no update until required.
- Cascade: alternate mill adds cost but reduces delay; waiting creates breach risk.
- Evidence routing: allocation notice is supplier private; official milestone miss is public.
- Trust pressure: if supplier discloses allocation early, reporting integrity rises while delivery reliability falls.
- Viability gate: none unless premium creates supplier loss threshold.

### 4. Supplier Advance-Payment Request And GC Denial

- Private cause: supplier has enough capacity but insufficient working capital to secure steel.
- Objective symptom: procurement cannot proceed on time without a cash source.
- Decision menu: GC approve advance; GC deny; GC require bond; supplier self-fund; supplier delay.
- Communication choices: supplier and GC may keep the request private, escalate to owner, publish payment status, or explain liquidity constraints.
- Cascade: approval reduces GC/owner cash but preserves delivery; denial worsens supplier liquidity and may cause delay.
- Evidence routing: supplier cash position private; advance request visible only to recipients selected by supplier communication or formal request routing.
- Trust pressure: denial followed by breach creates attribution ambiguity.
- Viability gate: supplier review if denial causes cash exhaustion.

### 5. GC Site-Readiness Slippage Blocks Steel Delivery

- Private cause: GC foundation/site readiness is behind plan.
- Objective symptom: steel cannot be installed even if supplier can deliver.
- Decision menu: resequence work; pay storage/standby; hold supplier to date; request labor adjustment.
- Communication choices: GC may privately explain readiness, publicly update the site milestone, ask supplier/labor for adjustment, or make no proactive statement.
- Cascade: storage cost and erection delay propagate; conflicting later evidence can affect trust.
- Evidence routing: GC readiness is GC private until inspection/milestone evidence appears.
- Trust pressure: unsupported agent communications about responsibility harm reporting integrity if later contradicted.
- Viability gate: GC review if accumulated standby/resequence loss crosses threshold.

### 6. GC Float Exhaustion Under Current Public Plan

- Private cause: GC has consumed schedule float and internally knows later work has little recovery room.
- Objective symptom: downstream tasks become sensitive to any new delay.
- Decision menu: accelerate now; resequence without added spend; hold plan and preserve cash; request owner schedule relief.
- Communication choices: GC may update the public completion forecast, privately warn owner/lender/subs, request information, or say nothing.
- Cascade: acceleration adds cost and restores fixed float; holding plan preserves cash but leaves later objective slippage more likely if another shock occurs.
- Evidence routing: float exhaustion is GC private; current public forecast changes only if GC submits a forecast or required attestation.
- Trust pressure: if later public outcomes contradict prior GC communications, reporting integrity falls; if no communication was made, observers mainly update delivery/process reliability.
- Viability gate: schedule review if forecast completion exceeds target by `25%`.

### 7. GC Coordination Bottleneck Creates Labor Idle Time

- Private cause: GC cannot coordinate access, crane, or sequencing.
- Objective symptom: labor cannot work productively during scheduled window.
- Decision menu: pay idle time; deny claim; resequence; request labor acceleration.
- Communication choices: GC/labor may exchange private notices, publish claim status, forward schedule evidence, or keep dispute details private.
- Cascade: denied idle claim strains labor cash; paid claim increases project cost; resequencing delays downstream work.
- Evidence routing: coordination bottleneck private to GC/labor unless published.
- Trust pressure: labor may reduce GC process reliability while owner sees only schedule slip.
- Viability gate: labor review if unreimbursed idle loss exceeds `10%` of linked task value.

### 8. Owner Contingency Freeze

- Private cause: owner contingency is frozen by internal governance.
- Objective symptom: change-order funding is unavailable or delayed.
- Decision menu: defer decision; reject change; approve partial change; request lender support.
- Communication choices: owner may disclose funding constraint, privately message GC/lender, publish updated cost forecast, or provide no explanation.
- Cascade: deferred changes delay recovery; rejection shifts loss to GC/supplier.
- Evidence routing: board/contingency status owner private; rejection public if recorded.
- Trust pressure: counterparties may see nonpayment as process unreliability.
- Viability gate: owner cap if total forecast exceeds approved budget plus equity cushion.

### 9. Owner Board Approval Delay

- Private cause: board approval for extra funds cannot occur until a future tick.
- Objective symptom: owner cannot immediately authorize extra funds.
- Decision menu: request lender bridge; delay decision; cancel discretionary recovery; self-fund within current authority.
- Communication choices: owner may disclose board timing, privately message lender/GC, publish funding forecast, or make no proactive update.
- Cascade: bridge prevents cash shock; delay creates contractor liquidity stress.
- Evidence routing: board calendar private to owner unless the owner communicates it.
- Trust pressure: late disclosure lowers owner payment/remediation reliability.
- Viability gate: project review if no funding path by due tick.

### 10. Lender Covenant Review Delay

- Private cause: lender risk team flags covenant concern after cost increase.
- Objective symptom: draw release slows or becomes conditional.
- Decision menu: approve draw; request documents; delay draw; reject draw.
- Communication choices: lender may share covenant rationale, request documents privately, publish funding outcome, or provide minimal status.
- Cascade: delayed draw reduces owner cash and slows payments; rejection can open project viability review.
- Evidence routing: internal lender risk private; documentation requests public or private depending channel.
- Trust pressure: owner may reduce lender payment reliability if delay appears liquidity-driven.
- Viability gate: lender freeze if loan plus equity cannot cover cost-to-complete plus `5%`.

### 11. Lender Documentation Demand Creates Subcontractor Cash Strain

- Private cause: lender requires extra documentation before draw.
- Objective symptom: owner/GC cash available for invoices is delayed.
- Decision menu: owner self-fund interim; wait for draw; partial pay; reject invoice pending docs.
- Communication choices: lender/owner/GC may forward documentation requirements, privately explain delay, publish payment status, or communicate nothing.
- Cascade: late payment worsens supplier/labor cash, increasing default risk.
- Evidence routing: lender demand private to owner/lender unless forwarded.
- Trust pressure: supplier may blame GC/owner, while true cause is lender documentation.
- Viability gate: affected actor review if cash exhausted.

### 12. Labor Crew Reassigned After Steel Delay

- Private cause: labor commits crew to another job after steel delay.
- Objective symptom: steel is ready but erection cannot start on the original crew plan.
- Decision menu: remobilize later; pay premium crew; request schedule extension; hold original commitment if feasible.
- Communication choices: labor may reveal crew conflict, privately negotiate premium, publish schedule update, or wait for GC request.
- Cascade: premium crew adds cost; later remobilization pushes all downstream work.
- Evidence routing: crew commitments labor private; public symptom is erection delay.
- Trust pressure: GC may reduce labor delivery reliability; labor may blame supplier's earlier delay.
- Viability gate: labor exit if remobilization impossible within capacity.

### 13. Labor Overtime Recovery Creates Quality Risk

- Private cause: labor can recover schedule only by overtime with higher defect risk.
- Objective symptom: recovery creates a fixed quality/rework risk.
- Decision menu: use overtime; hold standard pace; request second crew; request schedule extension.
- Communication choices: labor may disclose quality risk, privately warn GC, publish schedule plan, or omit the risk.
- Cascade: overtime reduces delay but can trigger rework; second crew adds cost with lower quality risk.
- Evidence routing: fatigue/quality risk labor private; inspection outcome public.
- Trust pressure: if rework follows undisclosed overtime risk, reporting integrity falls.
- Viability gate: inspection stop if unresolved rework persists.

### 14. Inspector Capacity Backlog

- Private cause: inspector capacity is constrained by other projects.
- Objective symptom: closeout inspection slot is unavailable at the requested tick.
- Decision menu: schedule late inspection; request third-party support; hold requested status; prioritize this project over another queued item.
- Communication choices: inspector may disclose backlog, privately request documents, publish schedule, or provide minimal status.
- Cascade: inspection delay pushes handover even if work is physically complete.
- Evidence routing: capacity private to inspector; scheduled date public if posted.
- Trust pressure: owner/GC may reduce inspector delivery reliability if backlog was hidden.
- Viability gate: compliance stop if inspection cannot complete before review deadline.

### 15. Inspector Documentation Rework

- Private cause: submitted documents are incomplete or inconsistent.
- Objective symptom: inspection cannot pass without fixed documentation correction.
- Decision menu: pass if supported; request rework; delay for evidence; fail inspection.
- Communication choices: inspector may publish deficiency, privately identify missing documents, request rework details, or give limited status.
- Cascade: rework adds cost/delay and may reveal earlier unsupported claims.
- Evidence routing: detailed documentation gaps private to inspector/submitter unless published.
- Trust pressure: reporting integrity declines for the party whose claims conflict with documents.
- Viability gate: compliance stop if unresolved after review.

### 16. Hidden Foundation Condition

- Private cause: foundation condition discovered by GC requires sequencing change.
- Objective symptom: steel erection path shifts or site access is delayed.
- Decision menu: resequence; request change order; absorb repair; delay steel access.
- Communication choices: GC may disclose condition, privately message owner/supplier/labor, publish change request, or wait.
- Cascade: repair adds cost and may block steel erection; agent communications determine who learns why.
- Evidence routing: field discovery private to GC initially; inspection or change request may become public.
- Trust pressure: late disclosure can look like poor coordination rather than hidden physical condition.
- Viability gate: owner cap if repair pushes forecast beyond funding capacity.

### 17. Design Clarification/RFI Changes Steel Specification

- Private cause: design clarification changes steel specification after procurement starts.
- Objective symptom: fabrication cannot proceed on the old specification without risk.
- Decision menu: accept old spec risk; wait for RFI; approve substitution; pay redesign premium.
- Communication choices: GC/owner/supplier may forward RFI context, privately negotiate substitution, publish change status, or keep details close.
- Cascade: waiting delays delivery; substitution can create inspection risk; premium increases cost.
- Evidence routing: RFI details private to GC/owner/designer proxy; supplier sees only approved change unless forwarded.
- Trust pressure: supplier may distrust GC process reliability if design changes arrive late.
- Viability gate: supplier or owner review if redesign premium creates loss/funding threshold.

### 18. Retainage Or Payment Dispute Blocks Acceleration

- Private cause: supplier or labor refuses acceleration because earlier payment is withheld.
- Objective symptom: acceleration option is unavailable unless payment issue is resolved.
- Decision menu: release retainage; keep withholding; partial settlement; demand verification.
- Communication choices: parties may keep dispute private, publish payment status, privately explain refusal, or escalate to owner/lender.
- Cascade: release improves liquidity and recovery; withholding protects owner/GC but worsens schedule.
- Evidence routing: payment dispute visible to parties, not necessarily public.
- Trust pressure: payment/remediation reliability becomes primary dimension.
- Viability gate: actor review if withheld amount plus acceleration cost exceeds liquidity.

### 19. Auditor Finding Exposes Unsupported Forecast

- Private cause: an actor has private facts that make a prior forecast unsupported.
- Objective symptom: auditor flags inconsistency in oversight modes where the conflict is detectable.
- Decision menu: correct forecast; dispute finding; provide evidence; replace reporting cadence.
- Communication choices: target actor may explain privately, publish correction, dispute publicly, or withhold underlying private cause.
- Cascade: correction shifts schedule/cost forecasts; dispute may delay rescue.
- Evidence routing: auditor finding public in central auditor mode; underlying data may remain private.
- Trust pressure: reporting integrity declines for unsupported forecaster; process reliability may recover if corrected promptly.
- Viability gate: schedule or funding review if corrected forecast crosses threshold.

### 20. Prompt Remediation With Persistent Public Breach Record

- Private cause: actor breached because of material condition but remediated quickly.
- Objective symptom: breach remains recorded even though physical impact is reduced.
- Decision menu: pay damages; request waiver; complete remediation; accept breach consequence.
- Communication choices: actor may publish remediation, privately explain cause, request waiver with evidence, or let the breach record stand alone.
- Cascade: remediation reduces downstream delay but breach remains in public evidence.
- Evidence routing: cause may remain private; remediation can be public.
- Trust pressure: delivery reliability may fall from breach, while remediation reliability can stay stable or recover.
- Viability gate: none if remediation keeps loss below thresholds.

## Experiment Design

The first cascade experiment should be paired and controlled:

- Keep the public steel shock fixed.
- Vary one private material constraint at a time.
- Vary what the environment initially reveals, such as public market shock only, supplier-only private cause, or private cause also sent as an initial scenario seed message to one counterparty.
- Do not force any agent to disclose, forward, correct, or publish information after the run starts.
- Treat nondisclosure, selective disclosure, private-only disclosure, public disclosure, and forwarding as observed agent behaviors.
- Compare `scalar_baseline` against `structured_dimensional`.
- Run through target completion or terminal viability result, not only through tick 14.

Recommended initial grid:

- Supplier condition: comfortable, normal, strained.
- Supplier behavior: collaborative, selfish, passive.
- GC condition: normal, strained.
- Oversight: normal operations, central auditor, signed attestations.
- Assessment mode: scalar baseline, structured dimensional.

Primary comparisons:

- Same private cause, different initial evidence distribution.
- Same private cause, different communication affordances or reporting obligations.
- Same public breach, different private-cause visibility.
- Same private-cause visibility, different observed agent communication behavior.
- Same safeguard, with and without deterministic downstream effect.
- Same loss threshold, with rescue versus no rescue.

## Metrics

Add or extend metrics:

- `cascade_event_count`
- `causal_trace_count`
- `public_symptom_count`
- `private_cause_count`
- `private_cause_disclosed_count`
- `private_cause_forwarded_count`
- `private_cause_never_disclosed_count`
- `mean_public_private_lag_ticks`
- `actor_default_count`
- `project_failed`
- `project_cancelled`
- `viability_review_count`
- `viability_review_resolved_count`
- `rescue_cost`
- `replacement_delay_ticks`
- `forecast_error_before_observed_disclosure`
- `forecast_error_after_observed_disclosure`
- `delivery_reliability_delta_after_breach`
- `reporting_integrity_delta_after_observed_disclosure`
- `payment_or_remediation_reliability_delta`

## Tests

Add tests in phases.

### Menu Validation

- A submission with a visible option ID is valid and applies exactly the option's deterministic effects.
- A submission with no option ID is invalid for menu-governed decisions.
- A submission with a hidden or expired option ID is invalid.
- Freeform numeric parameters do not override fixed option effects.

### Cascade Propagation

- Steel delivery slip pushes steel erection, enclosure, MEP, interior, inspection, and handover.
- Available float absorbs delay before pushing handover.
- Recovery option reduces delay by the configured fixed amount.
- Cost effects roll into project forecast final cost.

### Visibility

- Private inventory/cash cause is visible only to supplier.
- Public breach is visible to all agents with ledger access.
- Private message recipient can forward information.
- Non-recipient does not receive private fact unless forwarded or publicly disclosed.
- Causal trace contains private cause but is absent from observations.

### Trust

- Public breach with no private cause reduces delivery reliability more than reporting integrity.
- If an agent chooses proactive private disclosure, delivery reliability may fall while reporting integrity is preserved or improves for the recipient.
- Late inaccurate public claim reduces both delivery reliability and reporting integrity.
- Prompt remediation improves payment/remediation reliability while preserving breach history.

### Viability

- Supplier loss above review threshold opens a two-tick review.
- Rescue option resolves review and continues project with deterministic cost/delay.
- No rescue by due tick resolves actor default/exit.
- Owner/lender cancellation resolves project cancellation rather than project failure.
- Same seed, same scenario, and same menu choices reproduce identical gates and traces.

## Implementation Phasing

### Phase 1: Documentation And Schemas

- Add schemas for menu options, cascade rules, causal traces, evidence visibility, and viability gates.
- Add artifacts to logger touch/write lists.
- Add config loading for scenario-level menus and cascade rules.

### Phase 2: Menu-Governed Decisions

- Add `decision_menu_options` to observations.
- Update policies/prompts to select `option_id`.
- Update validation to reject non-menu governed economic decisions.
- Update transition resolver to pass selected option records to cascade logic.

### Phase 3: CascadeEngine

- Apply direct option effects.
- Propagate task dependency delays.
- Roll up cost and cash consequences.
- Generate public/private evidence and causal traces.

### Phase 4: ViabilityGateEngine

- Detect thresholds.
- Open review windows.
- Add rescue/exit menu options.
- Resolve continuation, default, failure, or cancellation.

### Phase 5: Scenario Suite And Metrics

- Encode the 20 scenario cards as scenario configs.
- Add paired cascade experiment runner.
- Add metrics and visualizations around evidence timing, directed expectations, cascades, and viability gates.

## Grounding Sources

These sources motivate the default thresholds and scenario patterns:

- [FAR Part 16](https://www.acquisition.gov/far/part-16): fixed-price contracts place substantially more performance-cost risk on contractors than cost-reimbursement arrangements, and contract type should reflect uncertainty and risk allocation.
- [Smith Currie: Anticipating Material Supply Chain Issues in Construction Projects](https://www.smithcurrie.com/publications/common-sense-contract-law/material-cost-escalation/): material escalation clauses are a practical response to volatile material pricing and supply-chain risk.
- [ConsensusDocs: Price Escalation Clauses in Construction](https://www.consensusdocs.org/resources/price-escalation-clause/): price escalation clauses tie adjustments to objective metrics and make volatility allocation explicit.
- [CFMA: Construction's Lifeline - Key Metrics for Measuring Financial Health](https://cfma.org/articles/construction-s-lifeline-key-metrics-for-measuring-financial-health): construction firms operate under tight margin and cash-flow constraints, making financial health central to project viability.
- [Sustainability: Payment Delay and Its Effects in Construction Projects](https://www.mdpi.com/2071-1050/11/15/4115): delayed payments can propagate through construction participants and affect project performance.
- [Sustainability: Information Asymmetry in Construction Projects](https://www.mdpi.com/2071-1050/15/13/9979): hidden or unevenly distributed information is a core driver of project coordination and trust problems.
