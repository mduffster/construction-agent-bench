# Experiment Registry

This registry separates legacy experiment infrastructure from the current feedback-cascade
agent-behavior experiment. Do not use a legacy runner as evidence for the current cascade
experiment unless it is explicitly listed under the current suite.

## Current Experiment: Feedback-Cascade Agent Suite

Status: **CURRENT**

Purpose: evaluate agent behavior under constraints in a multi-firm construction workflow where
hidden material constraints create public symptoms, downstream consequences, and directed
counterparty assessment pressure.

Primary design document:

- `docs/feedback_cascade_design.md`

Runnable suite manifest:

- `configs/suites/feedback_cascade_suite.yaml`

Runnable scenario definitions:

- The 20 current feedback-cascade scenarios are defined in
  `configs/suites/feedback_cascade_suite.yaml`.
- `scripts/run_feedback_cascade_suite.py` materializes those definitions into generated scenario
  YAML files under each suite output directory before running them.

Runner:

- `scripts/run_feedback_cascade_suite.py`

Default policy mode: `ollama`.

Scripted mode is allowed only as a deterministic harness regression check. It is not the
behavioral experiment.

Current scope:

- The current runnable suite covers the twenty feedback-cascade cards from the design direction.
- Each scenario exposes multiple fixed options to the relevant actor. The suite does not require
  a specific option; it verifies that the agent selected one valid visible option and that the
  deterministic cascade artifacts were produced.
- The scenario catalog is still toy-scale and should be expanded for richer construction market
  coverage, but it is now a runnable non-forced agent-behavior suite.

Validation expectations:

- Agent submissions must validate without transition rejections.
- Agent submissions must not fall back.
- The selected fixed option must be one of the visible options for that scenario.
- Each run must produce cascade events, one causal trace, one private cause, and one public symptom.
- Private causes must appear in causal traces and closely held private state, not as automatic
  agent-to-agent private messages.

## Regression Fixtures: Forced Cascade Branches

Status: **REGRESSION ONLY / NOT THE BEHAVIOR EXPERIMENT**

Files:

- `configs/scenarios/regression/steel_standard_delivery_forced.yaml`
- `configs/scenarios/regression/steel_expedite_absorb_loss_forced.yaml`

Purpose: deterministic branch fixtures for checking cascade propagation math. These files force
one branch and must not be used as evidence about agent choice behavior.

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
