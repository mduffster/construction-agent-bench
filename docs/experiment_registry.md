# Experiment Registry

This registry identifies the runnable experiment infrastructure that matches the current
stateful ConstructBench harness. The previous feedback-cascade suite is legacy and should not be
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
  commercially neutral counterparties, focal replay policies, and manifest metadata.
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
  gates, live-model opt-in guardrails, and deterministic gate reports.

Next queued components:

- Component 9 evidence package.

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
