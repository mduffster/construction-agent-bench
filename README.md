# ConstructSim

ConstructSim is a stateful testbed for autonomous firms coordinating on one consequential project
under asymmetric information, separate commercial incentives, distributed authority, and costly
partner replacement.

The research program is deliberately staged. A single-agent replaceability curve is followed by a
completed two-agent threshold-handoff pilot and then a controlled S01 V2 multiplayer lineage
ladder. The ladder adds live organizations cumulatively while tracing where a business datum is
exposed, interpreted, acted on, and realized.

## Current preliminary results

The response curve localized a large single-agent gap: supplying a computed threshold as an
attributed fact sharply reduced regret and unnecessary replacement. The frozen two-agent follow-up
then assigned 150 runs across structured, prose, and silent handoffs. Exact scripted senders reached
`100%` end-to-end success with structured data and `93.3%` with equivalent prose; both live-sender
arms reached `30%`. All `18/18` exact live GC calculations produced safe actions, while most errors
occurred before transmission when the GC bound the wrong business values into its calculation.

Read the generated [response-curve evidence package](docs/evidence/response_curve/evidence_package.md)
and the frozen [experiment specification](docs/s01_replaceability_response_curve_spec.md).
The completed dyad has a frozen
[protocol](docs/s01_distributed_threshold_handoff_spec.md) and
[results report](docs/s01_distributed_threshold_handoff_results.md). The next-stage design is the
[S01 V2 multiplayer lineage bridge](docs/s01_v2_multiplayer_bridge_spec.md).

## Reproduce

Deterministic references and validation do not call a model:

```bash
uv run python scripts/run_s01_response_curve.py --stage references
uv run python scripts/run_s01_handoff.py --stage references
uv run python scripts/run_s01_v2_multiplayer_ladder.py --preflight-only
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

The multiplayer ladder uses a state-aware scripted background, adds live roles cumulatively, and
stops on invalid output, a broken lineage, or its cost guard. Paid execution requires
`--allow-live-batch`; see `docs/s01_v2_multiplayer_bridge_spec.md`.

Rebuild the frozen evidence packet from named outputs:

```bash
uv run python scripts/build_response_curve_evidence.py
```

The wider S00-S05 suite remains useful for deterministic runtime regression, but it is not the
active research agenda. New research scenarios are added one at a time only after the current
experiment is complete.
