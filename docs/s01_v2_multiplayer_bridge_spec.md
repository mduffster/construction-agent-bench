# S01 V2 live multiplayer lineage bridge

Status: **V2 LIVE QUALIFICATION COMPLETE — 2026-07-10**

Experiment ID: `s01_v2_live_multiplayer_ladder_v2`

Live decision profile: `s01_v2_lineage_core_fields_v2`

## Research question

Can a growing set of AI-run firms preserve and act on decision-relevant data across a multi-hop
commercial workflow, and can the harness localize the first break to exposure, interpretation,
action, or deterministic realization?

This is the bridge between the completed two-agent threshold handoff and an unrestricted six-agent
population. It is a qualification study of a data-and-authority chain, not yet a claim that every
field in the wider S01 V2 game is strategically complete.

## Seven-link chain

1. Supplier-submitted documents to GC routing.
2. GC routing to inspector review scope and timing.
3. Published inspection result to the inspector's releasable-value decision.
4. Releasable value and the GC request to the lender-supported primary draw.
5. Primary draw plus private funds to deterministic supplier readiness.
6. Private readiness to the supplier's report and shipment request.
7. Released shipment and binding labor capacity to mobilization and completion.

Every agent-facing edge is measured from the observation actually recorded for that run. The
static visibility map establishes authorization but is never treated as proof that exposure
occurred. The funding-to-readiness link is a harness transition and is excluded from the exposure
denominator.

## Outcome record

Each edge records producer references and values, actual authorized exposure, the consumer action,
first-pass validation, operative-constraint conformance, realization or clipping, information
consistency, and whether the link preserved a viable project path.

Top-level measures are:

- expected exposure rate (`6` agent-facing edges);
- first-pass submission-conformance rate;
- operative-constraint conformance rate;
- action-realization rate;
- total and silent/unexplained clamp counts;
- complete lineage and earliest failed edge;
- viability-preserving chain and earliest viability break.

`lineage_complete` is intentionally separate from `viability_preserving_chain`. A losing but fully
observed and faithfully executed strategy is not mislabeled as a harness failure.

## Qualification changes to S01 V2

Before the ladder, S01 V2 was changed so that:

- structured prior decisions follow explicit role-scoped routes instead of being shown to every
  later actor;
- the GC's private backup economics stay private;
- routed documents, not merely recorded document IDs, determine verified value and draw controls;
- cross-field bounds are present in the first observation rather than discovered only after a
  failed submission;
- communication and no-evidence assessment records are optional;
- the GC draw request and inspector release cap constrain lender realization;
- cure and reinspection may expand value only from a valid initial inspector release;
- requested-to-realized clips are recorded explicitly in three consequence snapshots; and
- a seven-edge lineage record is written into S01 V2 analysis.

The v2 qualification also states the lender's action/amount coupling in the first observation:
direct release actions require zero escrow, escrow requires zero direct draw, and hold requires both
amounts to be zero. This was already enforced by validation in v1 but was not included in the
first-turn decision constraints.

The corrected audit initially exposed `64` fields that changed only the submitted record. Rather
than relabel those fields as meaningful, the qualification pass removed `58` duplicate, advisory,
or premature fields and made retained bridge, equity, offer-acceptance, price-adjustment, labor
release, and overtime terms operational. The resulting scenario has `73` parameter fields.

The deterministic efficient witness now has `6/6` expected exposures, `7/7` operative and realized
links, and zero unexplained clamps. The coordination-failure and excessive-conservatism witnesses
remain fully traceable while correctly failing the separate viability measure.

## Consequence audit and live projection

The audit now uses all six witness prefixes and each fixture's authored continuation, varies a field
against the other parameters in that exact decision, and excludes echoed decision bookkeeping.
The standard sweep covers all representative values: `259/259` pass across `73` fields and six
contexts per node.

For live roles, a wrapper exposes `72` lineage-relevant fields and fixes only the GC's private
`late_credit_usd` term to the reference value so the qualification study does not mix a separate
commercial-credit negotiation into the data-chain test. Missing live fields remain missing and
must pass the normal repair path; the wrapper cannot turn an omitted live decision into a valid
one.

## Cumulative live ladder

All non-live roles use the same state-aware efficient adjudication control.

| Rung | Live organizations |
|---|---|
| `supplier_gc` | supplier, GC |
| `add_inspector` | supplier, GC, inspector |
| `add_owner_lender` | supplier, GC, inspector, owner, lender |
| `full_six` | all six organizations, adding labor |

Model and parser settings are frozen to Claude Haiku, temperature `0`, maximum `1,200` output
tokens, and repair budget `1`. A rung stops the ladder on invalid required output or an incomplete
lineage. Project failure alone does not stop the ladder if the chain was fully exposed and faithfully
realized; that is a behavioral result rather than an instrumentation failure.

## V1 qualification incident

The first frozen live ladder spent `$0.612529` and stopped as designed at the five-live-role rung.
The supplier/GC and supplier/GC/inspector rungs were valid, successful, lineage-complete runs with
no repair attempts. At the next rung, the live lender twice paired a direct-release action with a
nonzero escrow amount, including after one targeted repair. The validator correctly stopped the
run as `INVALID_AGENT_OUTPUT`; the full-six rung was never called.

This is classified as an interface-qualification failure, not a multiplayer outcome. The validator
had enforced an action/amount rule that the initial observation had omitted. V2 changes only that
prompt contract and its version identifiers; it does not change payoffs, consequences, role mix,
model settings, or stop rules. All four rungs are rerun under the new frozen version so every row in
the final comparison has the same protocol provenance. V1 remains archived and counted in the
program cost ledger.

## Cost gate

The conservative prior program ledger is `$7.108282`, including the stopped v1 qualification. The
default rung reserves sum to `$1.92`, for a projected program total of `$9.028282`. New calls have a
`$2.00` allocation, the hard program stop is `$9.50`, and the user ceiling is `$10.00`, leaving at
least `$0.50` unspent by design.
Known pricing, clean commit, exact four-file output, settings, resume, and post-run cost checks are
mandatory.

Zero-cost preflight:

```bash
uv run python scripts/run_s01_v2_multiplayer_ladder.py --preflight-only
```

Authorized live ladder:

```bash
uv run python scripts/run_s01_v2_multiplayer_ladder.py --allow-live-batch
```

## Interpretation boundary

The successful ladder establishes that this particular multi-hop chain can be executed and
diagnosed under controlled role expansion. It does not validate all six-agent social dynamics,
human negotiation, or general construction decision-making. Broader commercial degrees of freedom
should still be added one at a time, with a new consequence audit and explicit research contrast.

The completed outcome record and next gate are reported in
`docs/s01_v2_multiplayer_bridge_results.md`.
