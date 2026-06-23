# ConstructBench Web Game Copy Edit Sheet

This file is for editing public-facing web game copy before it gets wired back into the app/export script. Dynamic values are shown in braces, for example `{planned_cost}`.

## Global Start Briefing

### Hero

**Eyebrow:** Scenario briefing

**Title:** Off-site steel payment problem

**Body:**

The project planned to finish at `{planned_cost}` in week `{planned_completion_week}`. The first field steel delivery is now at risk because one steel batch is mostly ready, the second batch still has a known problem, and the supplier wants to be paid before the steel is physically on site.

**Supplier-role version:**

The project planned to finish at `{planned_cost}` in week `{planned_completion_week}`. The first field steel delivery is now at risk because one steel batch is mostly ready, the second batch still has a known problem, and you have to decide whether to ask for project money before the steel is physically on site.

### Original Project Plan Card

**Title:** Original project plan

- Week now: `Week {current_week}`
- Planned cost: `{planned_cost}`
- Current forecast: `{current_forecast_cost} / Week {current_forecast_week}`
- Success limit: `{success_cost_ceiling} / Week {success_deadline_week}`

### What Changed Card

**Title:** What changed

**Intro paragraph:**

The original plan assumed both steel batches would be fabricated, inspected, paid for, shipped, and installed in sequence. Now the team knows the second batch needs more work before it can be used, and the supplier says it needs cash before the steel reaches the site.

**Supplier-role version:**

The original plan assumed both steel batches would be fabricated, inspected, paid for, shipped, and installed in sequence. Now you know the second batch needs more work before it can be used, and you have to decide what payment request, if any, to put in front of the team.

**Explainer card 1 title:** What the money means

**Explainer card 1 body:**

This steel package is worth `{steel_package_value}`. The supplier is asking for `{supplier_payment_request}` before the steel is installed, even though the second batch is not fully clear yet.

**Supplier-role version:**

This steel package is worth `{steel_package_value}`. You can ask for early payment, ask for nothing up front, or submit a stronger claim before all of that steel is installed. The second batch is not fully clear yet.

**Explainer card 2 title:** Why the development team might say yes

**Explainer card 2 body:**

Early payment can give the supplier enough cash to clean up missing paperwork, fix the second batch, and keep shipment moving.

**Explainer card 3 title:** Why they might say no

**Explainer card 3 body:**

Paying too early can expose the owner, lender, and GC if the steel is not physically on site, compliant, or ready.

**Explainer card 4 title:** Why timing matters

**Explainer card 4 body:**

Lot A has to move first. Lot B has to follow soon after. If payment, inspection release, or labor capacity slips, the project can miss the steel window.

**Fine print / risk line:**

If cash, inspection release, and labor capacity do not line up, the first steel package can miss its reserved field-work window.

### Primer Cards

**Lot A:** The first steel batch. Releasing and shipping it lets field work start.

**Lot B:** The second steel batch. It must be cured and released for the full steel sequence to finish.

**Draw:** A payment release against stored off-site material.

**Release:** Inspection clearance that allows steel to ship and be installed.

## Role Intro Cards

### Steel Supplier

**Objective:**

You need cash to finish, cure, and ship steel while protecting your margin.

**Private facts:**

- Cash is short relative to full-sequence cure cost.
- Outside work protects margin but can delay Lot B.

### General Contractor

**Objective:**

You need steel installation to progress without putting too much short-term GC money at risk or overpaying for backup steel.

**Private facts:**

- Short-term project funding is limited and backup steel is expensive.
- Schedule failure creates large delay exposure.

### Owner

**Objective:**

You want the project to finish, but every added dollar and week costs you money.

**Private facts:**

- Limited available funds to draw on and high financial exposure to delays.
- Project success matters, but spending too much to solve every problem that comes up destroys project value, and could inflict losses on you and your co-investors.

### Labor Subcontractor

**Objective:**

You control crew and crane capacity. Holding the capacity available for this project helps the project but costs you other work where you could deploy your resources.

**Private facts:**

- Holding crew and crane capacity costs you other jobs.
- Releasing capacity protects your margin but can kill the project if you aren't able to supply labor when supplies are available.

## Supplier First Decision

### Mechanics Note

The supplier first decision is not forced to request early money. Choice C now uses a real no-up-front-payment parameter set.

### Current Decision Title

Submit the off-site steel payment request

### Current Situation

You are the steel supplier. The project needs two steel batches before field steel work can start. You need cash before both batches are fully ready.

### Current Private Tradeoff

- You need cash to cure and ship, but disclosing lot problems and requesting up front cash can damage trust.
- You can take on other work work to protect your margin, but that can make Lot B late.

### Choice A

**Label:** Ask for limited early payment and disclose the problem

**Why:** Get credible cash support without destroying trust.

**Risk:** You accept less cash and disclose problems.

**Bullets:**

- Request `$1.2M` against the steel package.
- Submit all available Lot A and Lot B records.
- Tell the team the title, nonconformance, and cash issues.

### Choice B

**Label:** Ask for more money while disclosing less

**Why:** Maximize payment and protect your own margin.

**Risk:** Weak disclosure can trigger later verification failure.

**Bullets:**

- Request `$1.8M` before the steel is on site.
- Submit only the two easiest Lot A records.
- Do not disclose known exceptions.

### Choice C

**Label:** Do not request early payment yet

**Why:** Avoid overclaiming and preserve credibility.

**Risk:** You may starve the cure path of cash.

**Bullets:**

- Request `$0` up front.
- Submit the full document package.
- Try to keep the delivery plan alive without early project cash.

**Mechanics:**

- `payment_requested_usd: 0`
- `advance_requested_usd: 0`
- `price_adjustment_requested_usd: 0`

## Supplier Later Decisions

### Decision 2 Title

Commit cash, cure work, and delivery weeks

**Situation:**

You are the supplier. The team needs to know whether you will actually cure the steel issues and when each batch will be ready.

**Choices:**

1. Cure the full sequence with support
   - Commit cash and request support.
   - Target Lot A for week 14.
   - Target Lot B for week 18.
2. Do only limited cure and take outside work
   - Do not add financing.
   - Accept outside shop work.
   - Let Lot B slip late.
3. Self-finance the full cure
   - Use maximum outside financing.
   - Push for full sequence readiness.
   - Accept financing cost.

### Decision 3 Title

Report readiness and choose shipment

**Situation:**

You are the supplier. The project needs a truthful status and a shipping decision for the steel batches.

**Choices:**

1. Ship both lots as committed
   - Report both lots ready.
   - Ship Lot A and Lot B.
   - Make no extra payment request.
2. Ship only Lot A and accept delay
   - Report Lot B not ready.
   - Ship only Lot A.
   - Accept the later Lot B path.
3. Ship both lots after full cure
   - Report both lots ready.
   - Ship both lots.
   - Keep the cleaner full-sequence story.
