# ConstructSim

An AI-run company can receive the right information and still make the wrong business decision.
ConstructSim is a stateful research environment for following that failure from one company into a
shared, multi-company project.

Construction is the test environment. Six firms share a deadline, but each has different facts,
authority, costs, and private goals. Partners are expensive to replace. The harness can let every
firm make its own decisions; the controlled studies add that freedom one step at a time so a bad
outcome can be traced to fact selection, calculation, communication, or action.

## What the studies show so far

The first study varied the cost of replacing one AI-run steel supplier. The highest safe request
moved by $1M, but Claude Haiku asked for about $800K in 39 of 46 valid runs and $600K in the other
seven. Average avoidable loss was about $595K. A 15-run Claude Sonnet 5 confirmation also failed
to map the curve reliably: 60% of suppliers were replaced and average avoidable loss was about
$689K. This is a scenario comparison, not a general model ranking.

The two-company follow-up assigned 150 runs to test whether a contractor could calculate and pass
the useful number to the supplier. Whenever the live contractor calculated the number exactly, the
supplier made a safe choice (18/18). Written messages and structured records performed equally well
after a correct calculation; most failures occurred earlier, when the contractor selected or bound
the wrong facts.

A controlled multiplayer ladder then added AI-run companies until all six were live. All four steps
were valid and project-successful, and every expected information handoff arrived. Yet every AI-run
version narrowed the recovery to one steel lot and activated an expensive backup path. Information
arrival was not the same as a good decision.

A six-run pilot tested short, private decision summaries, followed by a preregistered 40-run
factorial confirmation: no summary, supplier only, contractor only, and both. All 20 runs with the
supplier summary reached the all-firm/no-backup path; none of the 20 runs without it did. The
contractor summary added no measurable benefit. The summary used only information each company was
already allowed to see, so supplier-only facts stayed private.

## Project success is not enough

ConstructSim scores both the public project and each firm's private target. In an earlier set of
open-decision, all-agent runs, 10 of 12 valid runs completed the project, but only 5 of those 10
successful projects also met every firm's private goal. Those runs mix settings and repair budgets,
so they are exploratory evidence rather than a controlled estimate. They show why project-level
success alone can hide a costly coordination failure.

## Research checks

Protocols are frozen before paid runs. The response-curve code checked 130 deterministic reference
outcomes before model calls. Saved evidence includes model inputs, decisions, validation repairs,
and cost stops. The public website imports generated study summaries rather than hand-maintaining
sample sizes or outcomes.

Read the generated [response-curve evidence package](docs/evidence/response_curve/evidence_package.md),
the [two-company protocol](docs/s01_distributed_threshold_handoff_spec.md) and
[results](docs/s01_distributed_threshold_handoff_results.md), the
[multiplayer protocol](docs/s01_v2_multiplayer_bridge_spec.md) and
[results](docs/s01_v2_multiplayer_bridge_results.md), and the
[decision-summary protocol](docs/s01_v2_derived_state_packet_protocol.md) and
[pilot results](docs/s01_v2_derived_state_packet_results.md), the
[factorial protocol](docs/s01_v2_decision_summary_factorial_protocol.md) and
[factorial results](docs/s01_v2_decision_summary_factorial_results.md), and the
[Sonnet confirmation results](docs/s01_response_curve_sonnet_confirmation_results.md).

## Reproduce without model calls

```bash
uv run python scripts/run_s01_response_curve.py --stage references
uv run python scripts/run_s01_handoff.py --stage references
uv run python scripts/run_s01_v2_multiplayer_ladder.py --preflight-only
uv run pytest -q
uv run ruff check .
uv run python scripts/audit_choice_consequences.py --output outputs/choice_consequence_audit.json
```

Rebuild the frozen public evidence:

```bash
uv run python scripts/build_response_curve_evidence.py
uv run python scripts/export_response_curve_web_data.py
uv run python scripts/export_research_program_web_data.py
```

Live Anthropic stages require an API key and an explicit opt-in. Each study runner has a hard cost
guard; see its frozen protocol before making paid calls.

The wider S00-S05 suite remains useful for deterministic runtime regression, but new research
questions are added one high-value scenario at a time.

## Contact

ConstructSim is built by Matt Duffy. Find the code and get in touch through
[GitHub](https://github.com/mduffster).
