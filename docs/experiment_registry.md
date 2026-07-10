# Experiment Registry

This registry identifies the runnable experiment infrastructure that matches the current
stateful ConstructSim harness. The previous feedback-cascade suite is legacy and should not be
used as the current experiment source.

## Current Baseline: Stateful Five-Scenario Harness

Status: **CURRENT / DETERMINISTIC ACCEPTANCE**

Purpose: validate the stateful multi-firm construction-project harness with public/private state,
required business decisions, optional communications, directed assessments, checkpoint cascades,
replayable outputs, and deterministic scenario consequences.

Primary design documents:

- `docs/constructbench_stateful_build_plan_with_5_scenarios.md`
- `docs/constructbench_low_budget_transition_plan.md`

Runnable scenarios:

- `S00_BASE_PROJECT_NO_PERTURBATION`
- `S01_STEEL_MARKET_SHOCK`
- `S01_V1` alias for `S01_STEEL_MARKET_SHOCK`
- `S01_V2_OFFSITE_STEEL_DRAW` staged as `S01_V2`
- `S02_CRANE_FAILURE_WEATHER`
- `S03_OWNER_LIQUIDITY_SHORTFALL`
- `S04_WELD_INSPECTION_FAILURE`
- `S05_LABOR_SHORTAGE_INSPECTION_WINDOW`

Primary commands:

- `uv run pytest -q`
- `uv run ruff check .`
- `uv run python scripts/audit_choice_consequences.py --output outputs/choice_consequence_audit.json`
- `uv run python scripts/run_one.py --scenario S01 --variant normal --policy fixture`
- `uv run python scripts/run_batch.py --policy fixture`
- `uv run python scripts/run_combined.py`

Output contract:

- Normal scenario outputs go under `outputs/`.
- Normal runs write exactly `run_config.json`, `events.jsonl`, `turn_summaries.jsonl`, and
  `run_summary.json`.
- Debug model I/O is written only when explicitly requested.

## Current Experiment Direction: S01 Replaceability Response Curve

Status: **CURRENT / PRELIMINARY EVIDENCE**

Purpose: measure whether a focal LLM steel supplier adjusts its commercial relief request as a
known qualified replacement becomes cheaper, while holding the private shock and project state
fixed.

Planning source:

- `docs/constructbench_low_budget_transition_plan.md`
- `docs/s01_replaceability_response_curve_spec.md`

Current evidence:

- `docs/evidence/response_curve/evidence_package.md`
- `docs/evidence/response_curve/threshold_scaffold_modal.md`
- `docs/evidence/response_curve/trusted_threshold_modal.md`
- ten treatment cells: five ordered replacement-cost levels crossed with two verified-history
  conditions;
- 130 valid deterministic reference trajectories with a monotonic best-response oracle;
- 10/10 valid Haiku modal runs and 46/50 valid temperature-1 Haiku confirmation runs;
- a five-cell no-history Sonnet modal diagnostic;
- a ten-cell Haiku replacement-threshold worksheet diagnostic: 9/10 valid, but it failed the
  frozen mechanism gate because regret fell only 29.6% and monotonicity worsened from one to three
  violations. None of the nine valid runs stated the correct replacement threshold or the correct
  discrete safe request, and three selected a request above their own stated ceiling;
- a trusted-threshold intervention that removed fact-selection and arithmetic ambiguity: the
  10/10-valid modal arm cut mean attainable regret 90%, eliminated replacement, and restored a
  monotonic request curve. A frozen 30-run temperature-1 confirmation was 30/30 valid, cut regret
  87.9% versus the unassisted confirmation, and again produced zero replacements and zero
  monotonicity violations. The remaining high-level $800,000 anchor leaves upside unrealized;
- `$2.51` recorded model spend, excluding a possibly billable interrupted request without durable
  telemetry.

Current implemented components:

- Component 0: run manifests embedded in `run_config.json` and `run_summary.json`.
- Component 1: harness-scored S01 payoff ledger and project-welfare accounting.
- Component 2: config-backed S01 scenario instances for relationship-history and outside-option
  treatment cells, with deterministic grid and welfare-ordering tests.
- Component 3: focal-agent policy mode with one focal LLM policy, deterministic S01
  commercially neutral counterparties, focal replay policies, and manifest metadata. The
  neutral GC/owner policy replaces the incumbent supplier only when replacing is genuinely
  cheaper than keeping it (`_replacement_is_rational`: cost-to-keep = relief asked + delay
  introduced; cost-to-replace = new-source cost + termination + replacement delay + risk
  premium). This supersedes an earlier degenerate rule (`replacement_cost <= max(price,
  250_000)`) that forced replacement in the credible-alternative cells regardless of the
  supplier's choices, which made those cells measure nothing about the focal agent.
- Component 4: serializable S01 pre-supplier-commercial checkpoint, treatment-instance fork
  patching, constrained treatment diffing, and equivalent-fork replay tests.
- Component 5: S01 structured claim schema and deterministic harness classification for
  incremental cost, liquidity requirement, delivery forecast/on-time probability, and recovery
  commitment claims.
- Component 6: factual relationship-history records, explicit outside-option economics,
  treatment-record hashes, role-scoped treatment visibility, and treatment-sensitive expected
  payoff catalog fields.
- Component 7: run-level analysis rows, deterministic payoff/regret/Pareto/claim metrics,
  fixed analysis tables and figures, and a deterministic S01 experiment runner.
- Component 8: validity-ladder runner with scripted supplier controls, cheap-model smoke/pilot
  gates, live-model opt-in guardrails, and deterministic gate reports. The 8C pilot is staged
  and adaptive (Stage A temperature-0 stability read, then instance-variant robustness or a
  temperature-1 distributional read) per the transition plan; `run_validity_ladder.py` exposes
  `--replicates-per-cell`, `--temperature`, `--instance-ids`, and the `stage-c-variants` and
  `stronger-model` gates. Sampling temperature is recorded in every run manifest, and the
  Anthropic adapter omits the sampling field for models that reject non-default sampling
  parameters (Sonnet 5, Opus 4.7/4.8, Fable 5). Local small-model (Ollama/Gemma) support is
  retired; live runs use hosted Anthropic models with Claude Haiku as the minimum tier.
- S01 disclosure instrument: the supplier's commercial request carries three required claim
  fields (`claimed_incremental_cost_usd`, `claimed_liquidity_requirement_usd`,
  `claimed_on_time_probability`), classified deterministically against the supplier's private
  truth at submission time. This fires on every focal run, so disclosure/overclaim metrics
  populate even when the model attaches no free-text message claims.
- S01 economic-variant grid: per treatment cell, `SWITCH_MID` and `GAP_HIGH` scenario instances
  perturb the switch-cost and liquidity economics for the Stage C robustness read.
- Component 9 evidence package: `scripts/build_evidence_package.py` reads named Stage A / Stage C
  / stronger-model / controls run directories and emits `docs/evidence/` (markdown plus copied
  figures) with no hand-typed numbers.
- S01 V2 marginal update: staged `S01_V2_OFFSITE_STEEL_DRAW` with 18 explicit decisions, three
  deterministic resolution handlers, explicit communication/assessment abstentions, six
  deterministic witnesses, V2 payoff/reporting records, and bounded choice-consequence audit
  sampling. `S01` remains the V1 default until the default switch is made deliberately.
  Backup activation costs `$3,400,000` (raised from `$1,600,000`) so that money-heavy recovery
  can breach the `$102M` success ceiling: the `budget_blowout_failure` witness pins
  `BUDGET_INFEASIBLE` at `$102,405,000` / tick 45 as a reachable terminal class distinct from
  schedule and compliance failures, while judicious backup use remains survivable.
- S01 V2 pre-flight combo evaluation: `scripts/evaluate_s01_v2_combos.py` runs 21 per-role
  archetype mixes (uniform paths, all single-role deviations, adversarial mixes) through the
  deterministic runtime with state-contingent parameter adaptation, asserting every combo
  terminates validly. Run it before any live all-agent batch.
- S01 V2 population batch: `scripts/run_s01_v2_population.py` runs N all-agent live runs
  (default temperature 1.0 for trajectory variety) behind `--allow-live-batch`, writing
  per-run rows and `population_summary.json`.
- Repair budget: the runner re-prompts an agent with its validation errors up to
  `repair_budget` times per turn (`--repair-budget` on the population script, default 1,
  recorded in the run manifest). Attempts land in `histories["repair_attempts"]` and every
  `run_summary.json` carries a `repair_summary` block, so batch invalid rates at different
  repair budgets are directly comparable.
- S01 V2 C4 share-cap consistency: `owner_cost_share_usd` max is `$4,000,000`, matching the
  `accepted_additional_cost_usd` max. The GC and supplier share caps sum to `$1.5M`, so the
  earlier `$1.5M` owner cap made any accepted cost above `$3M` (including the real `$3.4M`
  backup activation) impossible to share validly — a live repair-smoke run surfaced the trap.
- Web playthrough telemetry: `web/api/playthroughs.ts` (Vercel function, Upstash/KV REST)
  stores anonymized playthrough counters — role, per-node choice tallies, outcome counts,
  cost/week sums; no identifiers. The end screen submits once per completed game and renders
  a "you vs. other players" panel; when storage is unconfigured the endpoint reports
  unavailable and the panel stays hidden.

Next research gate:

- the single-focal response curve and frozen distributed-handoff pilot are complete. The dyad
  localized the dominant live failure upstream of representation: exact GC calculations always
  produced safe actions, while both live structured and live prose arms reached `30%` end-to-end.
  The S01 V2 multi-hop lineage ladder is the next research target.

## Staged Experiment: S01 Distributed Threshold Handoff

Status: **V2.1 FROZEN PILOT COMPLETE / DESCRIPTIVE RESULTS REPORTED**

Purpose: test whether a GC and steel supplier can move a decision-relevant reservation value across
an organizational boundary. The GC privately knows replacement economics; the supplier privately
knows its cost shock and liquidity position; the other four firms remain deterministic.

Planning source:

- `docs/s01_distributed_threshold_handoff_spec.md`
- `docs/s01_distributed_threshold_handoff_results.md`

Implemented surface:

- three diagnostic replacement levels: R1, R3, and R5;
- structured numeric and semantically equivalent rendered-prose protocols;
- a distinct GC pre-commercial phase before the supplier acts;
- counterparty attribution without labeling GC statements as harness truth;
- deterministic truthful structured, truthful prose, and silent controls;
- a handoff-only live GC, live supplier, and deterministic downstream adjudicator;
- fixed supplier source and non-price actions for causal identification;
- handoff analysis for calculation accuracy, transmission, viable deals, replacement, supplier
  regret, request error, ITT chain completion, and representation-to-action consistency.

Deterministic command:

```bash
uv run python scripts/run_s01_handoff.py --stage references
```

The nine deterministic reference runs must pass before any live stage. The completed V2 staircase
used
`scripted-prose-modal`, `scripted-structured-modal`, `scripted-silent-modal`,
`live-structured-modal`, and `live-prose-modal`; every stage requires `--allow-live-model`.
Three earlier R1 troubleshooting runs and the wrapper-failing V2 modal qualification are excluded;
the final confirmation contains `150` assignments (`146` valid) and cost `$5.391508`. Conservative
all-program cost including excluded development and qualification is `$6.495753`. Unrestricted
chat, new scenarios, and stronger-model arms remain deferred.

## Staged Experiment: S01 V2 Multiplayer Lineage Bridge

Status: **V2 LIVE QUALIFICATION COMPLETE**

Purpose: test whether a growing set of AI-run firms can preserve and act on business data across
the supplier-document, GC-routing, inspector-release, lender-draw, supplier-readiness, shipment,
and labor-mobilization chain.

Planning source:

- `docs/s01_v2_multiplayer_bridge_spec.md`
- `docs/s01_v2_multiplayer_bridge_results.md`

Implemented surface:

- role-scoped structured-record visibility and private GC backup economics;
- operational document routing and draw/release bounds;
- first-observation machine-readable cross-field constraints;
- seven edge-level lineage records based on actual observations and consequence snapshots;
- separate traceability and viability measures;
- state-aware deterministic counterparties and a cumulative four-rung live-role ladder;
- a consequence-audited 73-field S01 V2 surface, with the live lineage profile fixing only the
  separate GC late-credit term; and
- clean-commit, exact-output, resume, pricing, and total-program cost guards.

The frozen v1 live qualification spent `$0.612529`. Its first two rungs were valid and
lineage-complete; the five-live-role rung stopped at lender B5 because the validator enforced an
action/amount coupling that the first observation did not state. The full-six rung was not called.
V2 makes that coupling explicit, changes the experiment/profile IDs, and reruns all four rungs from
one clean frozen commit. Payoffs, consequences, role mix, and model settings are unchanged.

Deterministic command:

```bash
uv run python scripts/run_s01_v2_multiplayer_ladder.py --preflight-only
```

The completed V2 ladder passed all four rungs. Every rung was project-successful,
lineage-complete, and viability-preserving, with no realized clips. The full-six run needed three
successful repairs. All live rungs selected the costly backup path and missed coalition success,
cleanly separating correct data lineage from decision quality. V2 cost `$1.368483`; conservative
all-program spend is `$8.476765` against the user's `$10` ceiling.

The next gate is a six-run supplier-GC contrast at the earliest common divergence: current
observation versus a neutral, harness-derived decision-state packet for document-supported value,
funding thresholds, funding-source status, and operative caps. Broader live-role confirmation waits
for that local mechanism gate.

## Legacy: Feedback-Cascade Suite

Status: **LEGACY / SUPERSEDED**

Former files:

- `configs/suites/feedback_cascade_suite.yaml`
- `scripts/run_feedback_cascade_suite.py`
- generated feedback-cascade scenario YAMLs

Purpose: earlier cascade-oriented experiment infrastructure. It has been superseded by the
stateful five-scenario harness and should not be used as current evidence.

## Legacy: Forced Cascade Fixtures

Status: **LEGACY / SUPERSEDED**

Former files:

- `configs/scenarios/regression/steel_standard_delivery_forced.yaml`
- `configs/scenarios/regression/steel_expedite_absorb_loss_forced.yaml`

Purpose: deterministic branch fixtures for the old cascade propagation math.

## Legacy: Baseline Steel Shock

Status: **LEGACY / SUPERSEDED**

Former files:

- `configs/scenarios/steel_shock.yaml`
- `scripts/run_simulation.py`

Purpose: original single steel-market shock simulation. It has been replaced by
`S01_STEEL_MARKET_SHOCK`.

## Legacy: Perturbation And Behavioral Suites

Status: **LEGACY / SUPERSEDED**

Former files:

- `scripts/run_full_scenario_suite.py`
- `scripts/run_behavioral_suite.py`
- `scripts/run_condition_batch.py`
- `scripts/run_directed_trust_experiment.py`
- `constructbench/perturbations.py`

Purpose: earlier broad perturbation, behavioral, and directed-trust experiments. They do not match
the current harness contract.

## Operational Rule

For current harness validation, use the deterministic pytest suite, ruff, replay checks, and
`scripts/audit_choice_consequences.py`. For live model work, use `scripts/run_one.py` or
`scripts/run_batch.py` with an explicit hosted-provider configuration and preserve generated
artifacts under `outputs/`.
