# S01 response-curve Sonnet confirmation

Status: **FROZEN PROTOCOL / READY — 2026-07-15**

Experiment ID: `s01_replaceability_response_curve_v1`, stage `stronger-modal`

## Question and design

Does the flat supplier request seen with Haiku persist when Claude Sonnet 5 faces the same frozen
response curve?

The study uses the five no-history replacement-price levels already defined in the response-curve
protocol. One Sonnet run at each level already served as a diagnostic. This confirmation assigns
three new runs per level, 15 total, at temperature 0 with repair budget 1. The steel supplier is the
only live model respondent; the other five firms follow the unchanged commercial-neutral rules.
There is no decision summary or threshold intervention.

All 15 assigned runs are reported. Invalid output remains an assigned failure. There is no optional
stopping, and the prompt, scenario, scoring, model version, and price levels may not change after
the frozen commit.

## Outcomes

The report will show validity, requested relief at each price level, replacement rate, request-curve
monotonicity breaks, and average avoidable loss. The result is a comparison on one scenario, not a
general model leaderboard.

## Gates and budget

The same 130 deterministic reference outcomes must pass before model calls. The runner records the
exact model settings and output files. The fresh hard cap is `$3.00`, with `$0.19` reserved before
each call so the last dispatch cannot knowingly cross the cap. Combined with the decision-summary
factorial's `$6.80` cap, the planned fresh research allocation is `$9.80`, below the user's `$10`
limit.

Run only from a frozen clean commit:

```bash
uv run python scripts/run_s01_response_curve.py \
  --stage stronger-modal \
  --replicates-per-cell 3 \
  --temperature 0 \
  --max-cost-usd 3.0 \
  --per-run-reserve-usd 0.19 \
  --allow-live-model
```
