# ConstructSim

ConstructSim is a stateful testbed for autonomous firms coordinating on one consequential project
under asymmetric information, separate commercial incentives, distributed authority, and costly
partner replacement.

The research program is deliberately staged. The completed S01 replaceability response curve
measures one LLM steel supplier against five deterministic counterparties. The next experiment is
a controlled bridge to multi-agent interaction: a GC and supplier must move a decision-relevant
replacement threshold across an organizational boundary while four other firms remain scripted.

## Current preliminary result

Across 50 temperature-1 Haiku runs, 46 were valid. The supplier requested `$800,000` in 39 valid
runs and `$600,000` in seven while the deterministic safe frontier moved from `$200,000` to
`$1,200,000`. It was replaced in 52% of valid runs and averaged about `$595,000` in attainable
regret. A formula worksheet did not repair the behavior, but supplying the computed threshold as an
attributed fact cut regret sharply and eliminated unnecessary replacement in the confirmation arm.

Read the generated [response-curve evidence package](docs/evidence/response_curve/evidence_package.md)
and the frozen [experiment specification](docs/s01_replaceability_response_curve_spec.md).
The next-stage design is frozen in the
[distributed threshold handoff specification](docs/s01_distributed_threshold_handoff_spec.md).

## Reproduce

Deterministic references and validation do not call a model:

```bash
uv run python scripts/run_s01_response_curve.py --stage references
uv run python scripts/run_s01_handoff.py --stage references
uv run pytest -q
uv run ruff check .
uv run python scripts/audit_choice_consequences.py --output outputs/choice_consequence_audit.json
```

Live stages require an Anthropic API key and explicit opt-in:

```bash
uv run python scripts/run_s01_response_curve.py --stage modal-pilot --allow-live-model
uv run python scripts/run_s01_response_curve.py --stage haiku-confirmation --allow-live-model
```

The handoff runner also exposes guarded modal stages for scripted structured/prose records, a silent
control, and handoff-only live GC structured/prose records. They are not run by the deterministic
command above and require `--allow-live-model`. The frozen V2.1 protocol and `$8.50` program ceiling
are documented in `docs/s01_distributed_threshold_handoff_spec.md`.

Rebuild the frozen evidence packet from named outputs:

```bash
uv run python scripts/build_response_curve_evidence.py
```

The wider S00-S05 suite remains useful for deterministic runtime regression, but it is not the
active research agenda. New research scenarios are added one at a time only after the current
experiment is complete.
