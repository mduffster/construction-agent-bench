# ConstructSim

ConstructSim is a stateful testbed for autonomous firms coordinating on one consequential project
under asymmetric information, separate commercial incentives, distributed authority, and costly
partner replacement.

The current research experiment is deliberately narrow: one LLM controls a steel supplier while
five deterministic counterparties respond to its delivery plan, commercial request, and claims.
The S01 replaceability response curve asks whether the supplier reduces its relief demand when a
known qualified replacement becomes cheaper.

## Current preliminary result

Across 50 temperature-1 Haiku runs, 46 were valid. The supplier requested `$800,000` in 39 valid
runs and `$600,000` in seven while the deterministic safe frontier moved from `$200,000` to
`$1,200,000`. It was replaced in 52% of valid runs and averaged about `$595,000` in attainable
regret. Recorded model spend for the pilot, confirmation, and small Sonnet probe was `$2.51`.

Read the generated [response-curve evidence package](docs/evidence/response_curve/evidence_package.md)
and the frozen [experiment specification](docs/s01_replaceability_response_curve_spec.md).

## Reproduce

Deterministic references and validation do not call a model:

```bash
uv run python scripts/run_s01_response_curve.py --stage references
uv run pytest -q
uv run ruff check .
uv run python scripts/audit_choice_consequences.py --output outputs/choice_consequence_audit.json
```

Live stages require an Anthropic API key and explicit opt-in:

```bash
uv run python scripts/run_s01_response_curve.py --stage modal-pilot --allow-live-model
uv run python scripts/run_s01_response_curve.py --stage haiku-confirmation --allow-live-model
```

Rebuild the frozen evidence packet from named outputs:

```bash
uv run python scripts/build_response_curve_evidence.py
```

The wider S00-S05 suite remains useful for deterministic runtime regression, but it is not the
active research agenda. New research scenarios are added one at a time only after the current
experiment is complete.
