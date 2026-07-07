# AGENTS.md

## Project Scope

ConstructSim is now a stateful business-agent simulation for construction-project decision cascades. The source of truth for scenario content is:

```text
docs/constructbench_stateful_build_plan_with_5_scenarios.md
```

The runtime is not a tick-driven project simulator. Project ticks remain business facts inside scenarios. The simulation loop advances through meaningful phases only:

- `briefing_phase`
- `event_phase`
- `agent_execution_phase`
- `message_response_phase`
- `consequence_phase`
- `assessment_phase`

No empty ticks or empty action phases should be introduced.

## Baseline And Perturbation Scenarios

The project has one explicit no-perturbation reference case:

- `S00_BASE_PROJECT_NO_PERTURBATION`

This base case defines the normal project run against which perturbation scenarios are compared. It should have no perturbation events, but it should include the required delivery decisions that represent ordinary project execution. The normal reference is `$95,000,000` cost and completion tick `40`; the stressed reference is `$98,600,000` cost and completion tick `44`.

S00 must model the ordinary course of business, not an inert shortcut. It has baseline delivery nodes for all six agents:

- owner delivery authorization
- lender funding delivery
- GC delivery coordination
- steel supplier material delivery
- labor work delivery
- inspector approval delivery

The reference fixtures choose the ordinary path through those nodes. Nonordinary baseline choices must still produce deterministic cost, schedule, contingency, or delivery-state consequences.

S00 also owns the common budget envelope, schedule envelope, and normal deliverable inventory. The basic project plan is public business context known to all parties before any perturbation decision:

- baseline planned cost: `$95,000,000` normal, `$98,600,000` stressed
- approved budget: `$100,000,000`
- success budget ceiling: `$102,000,000`
- opening contingency: `$5,000,000` normal, `$1,800,000` stressed
- contract target completion tick: `40`
- baseline expected completion tick: `40` normal, `44` stressed
- success deadline tick: `48`
- milestone windows for notice to proceed, foundations, steel delivery, steel erection, payment current, structural release, structural draw, critical inspection readiness, reserved inspection, and substantial completion

The deliverable inventory is a toy project, but it should be explicit and defensible: every normal project deliverable has an ID, accountable agent, category, planned start/finish ticks, dependencies, required-for-completion flag, and perturbation hooks where relevant. The inventory must cover:

- owner governance, notice to proceed, payment, and acceptance
- lender loan closing, progress draws, structural draw, and closeout release
- GC scheduling, logistics, sitework, foundations, enclosure, commissioning, and closeout
- steel supplier shop drawings, fabrication, and site delivery
- labor structural erection, MEP/interior work, inspection readiness, finishes, and punch readiness
- inspector permit protocol, structural inspection, reserved inspection, and final inspection

Perturbation scenarios should be rebuilt against this baseline by altering expected deliverable outcomes, not by inventing unrelated standalone terminal equations.

Each perturbation scenario must declare its baseline impact surface:

- affected normal deliverables
- affected public milestones
- affected budget line items
- decision nodes that can move cost, timing, compliance, payment, or discoverability
- whether timing effects are additive delay deltas, tail changes, missed-slot effects, or critical-path deadlocks
- whether financial effects are project-cost deltas or private organization-ledger effects

Scenario choices may remain private, but any externally observable miss against the public baseline plan must surface through a checkpoint event before terminal finalization.

The perturbation pack contains five scenarios:

- `S01_STEEL_MARKET_SHOCK`
- `S02_CRANE_FAILURE_WEATHER`
- `S03_OWNER_LIQUIDITY_SHORTFALL`
- `S04_WELD_INSPECTION_FAILURE`
- `S05_LABOR_SHORTAGE_INSPECTION_WINDOW`

Each perturbation scenario must keep normal and stressed starting states, deterministic decision effects, and the four scripted witnesses from the plan:

- `normal_success`
- `normal_failure`
- `stressed_success`
- `stressed_failure`

These 20 perturbation witnesses are acceptance fixtures, not behavioral distributions. S00 adds reference fixtures; it is not counted as a perturbation witness.

## Runtime Contract

The harness owns all canonical state and all state transitions. Agents never mutate state directly.

Agents receive observations describing:

- role identity and objective
- behavior-linked goal posture
- known public facts
- private business facts
- received messages
- current required decisions
- assessment evidence and directed priors
- private notes from prior turns

Each LLM agent is initialized once as a persistent business organization before the first active phase. The initialization includes role identity, organization type, behavior profile, goal profile, startup private facts, communication powers, decision responsibilities, and memory instructions. Later observations provide current phase facts and may update or supersede startup facts.

Behavior profiles are goal postures, not forced behavior scripts:

- `collaborative`: project success and organization terminal value are both goals.
- `selfish`: organization terminal value is the primary goal.
- `passive`: preserving the intended schedule and approved project pathway is primary, with organization terminal value secondary.

Agents may send accurate, incomplete, selective, misleading, or false communications if they judge that useful for their assigned goal posture. The harness records claim accuracy, trust, audit, contract, and outcome consequences; it does not reject a communication merely because it may be misleading.

Agent submissions contain only:

- `decisions`
- `communications`
- `assessment_updates`
- `assessment_reviews`
- `private_notes`

If required decisions exist, empty `decisions` is invalid. A modeled inaction is valid only when it is an explicit scenario option, such as `wait_for_diagnostics` or `schedule_no_payment`.

Invalid JSON, invalid option IDs, missing parameters, or empty required decisions get targeted repair attempts for LLM policies: the runner re-prompts with the validation errors up to `repair_budget` times per turn (default 1; `--repair-budget` on batch scripts). If still invalid, the run stops as `INVALID_AGENT_OUTPUT`. Attempts are recorded in `histories["repair_attempts"]` and summarized in `run_summary.json` under `repair_summary`. The runner must not advance consequences or compute a fake project outcome after invalid required output.

## State Invariants

Preserve these invariants:

- Canonical, public, private, message, decision, and assessment state remain distinct.
- Public claims never overwrite canonical truth.
- Private facts and private messages do not leak to nonrecipients.
- Communications are optional and independent from decisions.
- False or misleading claims are schema-validated and delivered unchanged.
- Assessment state is private, directed, multidimensional, and changed only by agent submissions.
- If assessment evidence is present, the agent must submit either an update or an explicit no-update review.
- Every terminal outcome requires all active-path required business decisions to be resolved or explicitly modeled as inaction.
- Hidden or private decisions may remain undisclosed, but their externally observable missed milestones must surface as public checkpoint events before terminal finalization.
- Checkpoint events should report the observable business fact, not unnecessary private cause attribution. A missed delivery, missed payment, blocked release, weather damage, or missed inspection slot can be public without revealing the actor's private constraints.
- Observable checkpoint events should unlock narrow follow-on decisions for affected agents when a practical response remains available.
- Event replay from `run_config.json` plus `events.jsonl` must reconstruct final state.

## Output Contract

A normal run writes exactly four files:

```text
run_config.json
events.jsonl
turn_summaries.jsonl
run_summary.json
```

Debug model I/O is written only when explicitly requested. Do not add placeholder artifacts for breaches, disclosures, beliefs, oversight, or legacy traces.

All scenario and live-agent run outputs should go under `outputs/`.

## Public Web App

The `web/` directory is a static Vite + React + TypeScript dissemination app.
It is not the harness runtime and must not become a parallel source of
scenario truth.

The web app currently exposes:

- `/` overview page for ConstructSim
- `/play` actor selection
- `/play/s01` playable human version of `S01_V2_OFFSITE_STEEL_DRAW`
- `/results` comparison page for ideal fixture, Claude Haiku run, and player outcome

The S01 web game is generated from harness content by:

```bash
uv run python scripts/export_s01_v2_web_game.py
```

The export writes:

```text
web/src/game-data/s01_v2_game.json
```

Do not hand-maintain a separate scenario in the frontend. Scenario facts,
decision schemas, role briefs, payoff thresholds, witness outcomes, and content
hashes should come through the export script. Frontend copy may simplify those
facts for humans, but it should preserve the underlying harness semantics.

The one server-side piece is `web/api/playthroughs.ts`, a Vercel function that
stores anonymized playthrough counters (role, per-node choice tallies, outcome
counts) in Upstash Redis via REST. It needs `KV_REST_API_URL`/`KV_REST_API_TOKEN`
(or the `UPSTASH_REDIS_REST_*` equivalents) in the Vercel project; without them
it reports unavailable and the end-screen crowd panel stays hidden. It stores
no user identifiers.

The public human game is intentionally smaller than the full simulation:

- humans can play four roles: steel supplier, GC, owner, and labor subcontractor
- lender and inspector remain system-controlled roles in the web game
- the simulation harness still models all six organizations as agents

The web game is static and client-side only. It uses an authored TypeScript
state engine to mirror the S01 V2 coordination problem. Player choices should
mutate persistent game facts, including `story_flags`, and deterministic
counterparty choices should branch from those facts. Avoid click-through flows
where other actors follow one fixed path regardless of the player's choices.

Trust ratings in the web game are recorded for recap and reflection only; they
do not alter consequences in the current web version.

Run web checks after frontend or export changes:

```bash
cd web
npm run test
npm run build
npm run test:browser
```

Pushing this repository branch is not a deployment. Vercel/static deployment is
a separate release step.

## Tests

Run:

```bash
uv run pytest -q
uv run ruff check .
```

The required deterministic coverage includes:

- all 20 scripted witnesses
- unresolved required decisions stop as `INVALID_AGENT_OUTPUT`
- invalid options and missing parameters stop or repair
- modeled inaction advances
- private messages do not leak
- assessment updates are private and directed
- normal outputs contain exactly four files
- event replay reconstructs final state
- model parsing and repair are tested with a fake adapter
- observable checkpoint cascades for missed steel delivery, S02 weather disruption, S03 payment miss, S04 blocked structural release, and S05 missed inspection readiness
- shared-state combined-scenario fixture runs preserving module checkpoint events and stacking schedule-delay deltas

For the harness consequence invariant, run:

```bash
uv run python scripts/audit_choice_consequences.py --output outputs/choice_consequence_audit.json
```

This audit checks every reachable decision option and parameter value across all five scenarios and both starting variants. A choice passes only if it produces a distinguishable canonical consequence in at least one reachable context while holding the rest of the run deterministic.

Current combined-scenario support is `shared_state_additive_timing`: S00 supplies the implicit base project state, while perturbation modules contribute events, decisions, checkpoint rules, cost deltas, and schedule-delay deltas to one run. Cost deltas add directly to the S00 base cost. Completion is computed as the S00 baseline completion tick plus the sum of module schedule-delay deltas, so timing impacts stack instead of one module overwriting another with an absolute completion date.

## Hosted Model Gate

Local small-model (Ollama/Gemma) support is retired. Live agent runs use hosted Anthropic models, with Claude Haiku as the minimum model tier. Their earlier role — confirming that agents receive the right observations and trigger correctly — is covered without model calls by the deterministic fixture suite and by rendering the exact initialization prompts.

Before hosted-model batches, the deterministic suite must be green and, optionally, run one single-scenario Haiku smoke:

```bash
uv run python scripts/run_one.py --scenario S01 --variant normal --policy llm
```

Pass condition is valid required agent action, not project success.

Live LLM batch runs require an explicit opt-in:

```bash
uv run python scripts/run_batch.py --policy llm --provider anthropic --allow-live-batch
```

To inspect exact persistent initialization prompts without calling a model:

```bash
uv run python scripts/render_agent_initializations.py --output-dir outputs/prompt_audit_current
```

## Development Guidance

When making a judgment call about scenario content, check the five-scenario plan first. If the document is silent, make the smallest explicit assumption and keep it in scenario code or tests. Do not reintroduce old tick-loop behavior or legacy output artifacts.
