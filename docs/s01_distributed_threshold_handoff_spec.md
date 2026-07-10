# S01 distributed threshold handoff experiment

Status: **V2.1 FROZEN PILOT PROTOCOL — 2026-07-10**

Experiment ID: `s01_distributed_threshold_handoff_v2_1`

The pilot is complete. Outcomes are recorded separately in
[`s01_distributed_threshold_handoff_results.md`](s01_distributed_threshold_handoff_results.md) so
this frozen protocol remains an auditable pre-result specification.

The three live R1 runs made before this freeze are development diagnostics. They cost `$0.05809`,
were produced from changing dirty worktrees, and are excluded from every V2 effect estimate. The
successful diagnostic also required one repair. Their only use was instrument debugging.

The first V2 modal qualification is also excluded. It exposed that the handoff-only GC wrapper did
not forward model repair and usage hooks. Known V2 qualification cost plus a conservative `$0.25`
allowance for the unrecorded call brings excluded pre-V2.1 spend to `$0.563522`. V2.1 adds a
deterministic lifecycle test and refreezes before any evidentiary call. The new V2.1 modal-gate cost
will also be excluded and added to the program ledger before confirmation.

## Research question

Can two AI firms convert distributed private commercial facts into an efficient price decision, and
does representing the same counterparty-authored threshold as typed data rather than prose change
the result?

This is a representation-to-action experiment, not a claim about human negotiation or autonomous
construction readiness.

## Formal game

The game has two live players embedded in a deterministic six-organization environment:

- the GC privately observes the components of its replacement option;
- the supplier privately observes its material shock and retained-contract economics;
- owner, lender, labor, and inspector policies execute fixed commercial consequences;
- after the supplier acts, a deterministic commercially neutral GC adjudicator applies the
  keep-versus-replace rule. A live GC is active only at the handoff node.

Nature assigns the GC replacement threshold `T` through one of three response-curve levels:

| Level | True threshold | Highest allowed safe request |
|---|---:|---:|
| R1 | `$250,000` | `$200,000` |
| R3 | `$750,000` | `$700,000` |
| R5 | `$1,250,000` | `$1,200,000` |

Sequence:

1. GC computes `T_hat`, records confidence, and chooses whether to share.
2. The harness renders the shared GC record through the assigned representation.
3. Supplier chooses a price-amendment request from the frozen action grid.
4. Deterministic counterparties approve a request at or below the true threshold and replace above
   it, subject to ordinary S01 consequence rules.

For identification, `current_expedited` is the supplier's only source option. Delivery amendment,
advance request, and claim fields are fixed to truthful neutral values. Only the requested price is
free. These degrees of freedom return in the later multiplayer bridge.

The legacy S01 payoff ledger has no private GC utility. This experiment therefore reports an
explicit buyer-side proxy, normalized to the replacement option:

```text
buyer_surplus_vs_replacement = T - approved_price_relief  if retained
                               0                           if replaced
```

Supplier payoff remains the ordinary S01 realized payoff. Their sum is labeled
`joint_surplus_proxy_usd`; it is not presented as a complete GC accounting ledger.

## Representations

- `structured_numeric`: an attributed fact contains separate
  `replacement_threshold_usd` and `handoff_confidence` fields plus the comparator semantics.
- `rendered_prose`: an attributed fact contains the same source, value, confidence, comparator
  direction, and consequence in a deterministic sentence, without a numeric threshold field.
- `silent`: the handoff opportunity is visible but no value or confidence is exposed.

The value is always labeled as an unverified, self-interested GC statement. V2 deliberately does
not use unrestricted agent-authored messaging; that would confound representation with content
selection and is deferred to multiplayer work.

## Frozen arms

Each arm is crossed with R1, R3, and R5:

1. `scripted-structured`: exact scripted GC, structured representation, live supplier.
2. `scripted-prose`: exact scripted GC, equivalent rendered prose, live supplier.
3. `scripted-silent`: scripted GC withholds the value, live supplier.
4. `live-structured`: handoff-only live GC, structured representation, live supplier.
5. `live-prose`: handoff-only live GC, rendered prose, live supplier.

The assigned-arm analysis is intention-to-treat. If a live GC withholds or miscalculates, that is a
failure of the assigned end-to-end chain rather than an exclusion.

## Outcomes and contrasts

Primary outcome:

- equal-weighted R1/R3/R5 supplier attainable regret relative to the frozen deterministic reference
  policy, conditional on a valid terminal run; validity is reported alongside it.

Primary end-to-end reliability outcome:

- valid run + exact GC calculation + exact exposure + safe supplier request + mutually viable deal.
  Invalid output, withholding, or missing transmission counts as failure.

Secondary outcomes:

- first-pass and repaired validity;
- exact calculation and exact-transfer ITT rates;
- safe-action ITT rate and request error;
- replacement and mutually viable deal rates;
- supplier payoff, buyer-surplus proxy, and joint-surplus proxy.

Predeclared descriptive contrasts:

- scripted structured minus scripted prose: representation effect;
- either exact handoff minus silence: information effect;
- live minus scripted within representation: coordination tax;
- live structured minus live prose: live interface effect.

Report per-level cells, equal-weight arm summaries, Wilson 95% intervals for binary cell rates, and
descriptive differences. No null-hypothesis significance claim is planned for this pilot.

## Run plan and budget

Model: `claude-haiku-4-5-20251001`; collaborative profiles; normal variant; repair budget `1`.

1. Deterministic nine-run gate, cost `$0`.
2. Excluded temperature-zero modal gate: one run in each of 15 arm-level cells.
3. If no code or prompt change follows the modal gate, temperature-one frozen pilot: ten repeated
   API trials in each of 15 cells, `150` runs total.

Anthropic receives no sampling seed, so replicate numbers are bookkeeping and repeated API trials
are not represented as reproducible independent model samples.

The paid-program ceiling is `$8.50`, including the `$0.05809` development spend, with at least
`$1.50` left below the user's `$10` limit. Every dispatch reserves `$0.25` before starting; unknown
model pricing is an error. If modal costs project the frozen pilot above `$8.50`, stop before the
pilot and report it.

## Gates

Before any paid V2 run:

- worktree is clean and the frozen commit is recorded;
- deterministic references are valid and replayable;
- truthful R1/R3/R5 supplier payoffs are `$130k`, `$630k`, and `$1.13M`;
- truthful structured and prose arms have identical economics and outcomes;
- silent R1/R3 replace while silent R5 remains viable;
- supplier observations contain no replacement cost or termination cost;
- GC observations contain full replacement economics;
- supplier source and non-price actions are fixed;
- live GC policy is active only at the handoff phase;
- resume checks reject different commits, settings, output contracts, and unknown costs;
- the full deterministic test and choice-consequence suites are green.

Any prompt, action-space, payoff, parser, or consequence change after the modal gate invalidates the
modal tranche and requires a new experiment ID or an explicit protocol amendment before more runs.

## Deferred multiplayer bridge

The next research object is S01 V2's multi-hop payment/release lineage:

```text
supplier documents and claims
  -> GC certification and routing
  -> inspector verified/releasable value
  -> lender-supported draw
  -> supplier readiness and shipping
  -> labor mobilization
```

It will reuse the same exposure -> transmission -> interpretation -> action -> consequence labels.
Before a live ladder, S01 V2 must enforce role-scoped record visibility, expose machine-readable
cross-field constraints, remove mandatory no-op communications, and add lineage metrics. Live roles
will then be added cumulatively against state-aware scripted controls, stopping at the first invalid
or behavior-changing link.

## Non-goals

- no human-behavior claim;
- no unrestricted chat in the frozen dyad;
- no relationship-history factor;
- no new construction scenario;
- no stronger-model comparison;
- no stochastic six-agent batch.
