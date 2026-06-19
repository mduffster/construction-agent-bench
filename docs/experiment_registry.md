# Experiment Registry

This registry separates legacy experiment infrastructure from the current feedback-cascade
agent-behavior experiment. Do not use a legacy runner as evidence for the current cascade
experiment unless it is explicitly listed under the current suite.

## Current Experiment: Feedback-Cascade Agent Suite

Status: **CURRENT, PARTIAL IMPLEMENTATION**

Purpose: evaluate agent behavior under constraints in a multi-firm construction workflow where
hidden material constraints create public symptoms, downstream consequences, and directed
counterparty assessment pressure.

Primary design document:

- `docs/feedback_cascade_design.md`

Runnable suite manifest:

- `configs/suites/feedback_cascade_suite.yaml`

Runnable scenario configs:

- `configs/scenarios/feedback_cascades/steel_standard_delivery.yaml`
- `configs/scenarios/feedback_cascades/steel_expedite_absorb_loss.yaml`

Runner:

- `scripts/run_feedback_cascade_suite.py`

Default policy mode: `ollama`.

Scripted mode is allowed only as a deterministic harness regression check. It is not the
behavioral experiment.

Current scope:

- The current runnable suite covers the steel-shock prototype branch where the supplier either
  preserves liquidity and reports standard delivery or expedites and absorbs a liquidity hit.
- The planned twenty-card feedback-cascade catalog remains a design target and is not yet fully
  implemented as scenario configs.

Validation expectations:

- Agent submissions must validate without transition rejections.
- The selected fixed option must match the scenario expectation.
- Standard delivery should propagate a downstream schedule delay.
- Expedited delivery should increase cost and reduce supplier cash without propagating a schedule
  delay.
- Private causes must appear in causal traces and closely held private state, not as automatic
  agent-to-agent private messages.

## Legacy: Baseline Steel Shock

Status: **LEGACY / BASELINE CONTROL**

Files:

- `configs/scenarios/steel_shock.yaml`
- `scripts/run_simulation.py`

Purpose: original single steel-market shock scenario with public market movement and supplier
private impact. Useful as a baseline control and regression fixture.

Not the current cascade suite.

## Legacy: Perturbation Scenario Suite

Status: **LEGACY / DIAGNOSTIC**

Files:

- `scripts/run_full_scenario_suite.py`
- `constructbench/perturbations.py`

Purpose: generates a designed 100-run perturbation suite from generic owner, GC, steel, labor,
lender, and inspector perturbation vectors.

Important distinction: this suite is not the feedback-cascade experiment. It can be useful for
stress-testing broad metrics, but it does not implement the current 20-scenario cascade catalog.

## Legacy: Random Behavioral Suite

Status: **LEGACY / DIAGNOSTIC**

Files:

- `scripts/run_behavioral_suite.py`

Purpose: randomized behavioral simulations over perturbations, local conditions, behavior
profiles, and oversight modes.

Important distinction: this runner may use LLM agents, but it operates on the legacy perturbation
generator rather than the current feedback-cascade scenario catalog.

## Legacy: Directed Trust Experiment

Status: **LEGACY / DIAGNOSTIC**

Files:

- `scripts/run_directed_trust_experiment.py`

Purpose: focused experiments around directed counterparty expectation updates.

Important distinction: this is related research infrastructure, not the current cascade-suite
runner.

## Operational Rule

When the task is to run or analyze the current cascade experiment, use
`scripts/run_feedback_cascade_suite.py` and the `configs/suites/feedback_cascade_suite.yaml`
manifest. Do not substitute `scripts/run_full_scenario_suite.py`.
