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

## Current Experiment Direction: S01 Low-Budget Transition

Status: **IN DEVELOPMENT**

Purpose: turn the S01 steel-market shock into a controlled focal-agent experiment on supplier
disclosure, bargaining, relationship history, outside options, utility, and project welfare.

Planning source:

- `docs/constructbench_low_budget_transition_plan.md`

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

Next queued components:

- Rotate the focal role from supplier to GC (transition plan section 9).

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
