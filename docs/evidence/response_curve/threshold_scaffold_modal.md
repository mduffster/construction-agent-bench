# Replacement-threshold worksheet diagnostic

*Preliminary modal mechanism test; frozen before live runs on 2026-07-09.*

## Question

Does the supplier's replaceability-curve failure disappear when its decision prompt supplies the
exact replacement-threshold formula and requires an auditable calculation before it chooses?

## Design

The intervention reused the original ten cells, Haiku model, temperature-zero sampling, supplier
facts, allowed actions, and deterministic counterparties. The only treatment change was the
worksheet specified in `docs/s01_response_curve_threshold_scaffold_spec.md`.

The precommitted mechanism gate required at least 90% validity, the same cell coverage, at least a
50% reduction in mean attainable regret, and no worsening of response-curve monotonicity.

## Result

Nine of ten runs were valid. Mean attainable regret fell from **$720,000** to **$506,667**, a
**29.6% reduction**. Replacement fell from **60.0%** to **44.4%**, but request-curve monotonicity
worsened from **one violation to three**. The intervention therefore **failed the frozen mechanism
gate**; a stochastic confirmation is not warranted.

## Calculation audit

All nine valid runs included a parseable worksheet note:

- **0/9** stated the correct all-in replacement threshold.
- **0/9** stated the correct largest allowed safe request.
- **9/9** submitted the request they recorded in their note.
- **3/9** knowingly submitted a request above their own stated replacement threshold.

The errors were not all of one type. Some runs selected the wrong alternative-source facts, some
performed incorrect arithmetic on the right-looking terms, and some omitted the risk premium.
At higher replacement-cost levels, the model also continued to anchor on an $800,000 cost-recovery
request instead of using the greater bargaining room it had calculated. The worksheet partially
reduced losses without producing a coherent response curve.

## Interpretation

The original failure is not explained solely by failure to notice that replaceability matters. Even
when given the decision rule, the model struggled to bind the correct facts to the formula, execute
the arithmetic, and consistently follow the resulting ceiling. This sharpens the next diagnostic:
provide a harness-computed threshold as a trusted fact, without revealing the recommended action.
That separates arithmetic and fact-selection errors from strategic use of a correct reservation
value.

That follow-on diagnostic has now been completed. Its modal and stochastic results are reported in
`trusted_threshold_modal.md`; both passed their frozen gates.

## Reproduction

```bash
uv run python scripts/run_s01_response_curve.py \
  --stage modal-pilot \
  --intervention replacement_threshold_worksheet_v1 \
  --baseline-analysis outputs/s01_response_curve_modal_pilot_20260709/response_curve_analysis.json \
  --allow-live-model

uv run python scripts/analyze_s01_threshold_scaffold.py \
  outputs/s01_response_curve_threshold_scaffold_modal_20260709
```

Structured audit rows are in `threshold_scaffold_audit.json` beside this note.
