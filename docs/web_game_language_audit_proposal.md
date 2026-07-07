# Web Game Language Audit — Non-Practitioner Pass (Proposal)

Read as someone who knows nothing about construction management. Every line a
player sees should make sense on first read with no glossary. (The per-node
"term" cards exist in the export data but are not rendered anywhere in the UI,
so nothing can rely on them.)

Status: APPLIED 2026-07-07 (user approved all items; PA-01 killed everywhere,
longer bullets accepted, retitled banners accepted). Applied to
`scripts/export_s01_v2_web_game.py`, `web/src/App.tsx`, and
`web/src/lib/gameEngine.ts`, then re-exported. A rendered-field jargon sweep
of the exported JSON confirmed zero leftovers. Future copy edits should go
directly into the export-script dictionaries.

---

## 1. Vocabulary swaps (applied consistently everywhere)

| Jargon | Proposed plain language | Notes |
|---|---|---|
| PA-01 | "the supplier's payment request" | Drop the form number entirely. It's realism flavor that costs comprehension. |
| cure / cure work / "after cure" | "fix" / "repairs" / "once it's fixed" | |
| certify / certified value | "approve for payment" / "the amount you've approved" | |
| release / released steel (inspector sense) | "approve for use" / "inspector-approved steel" | "unreleased steel" → "steel the inspector hasn't approved" |
| draw / loan draw | "loan money" / "loan payout" | |
| escrow | "a controlled account" | "money parked in a controlled account until conditions are met" |
| equity | "the owner's own cash" | |
| controls | "checks" | "if the checks pass (ownership paperwork, inspection)" |
| title / title gaps | "ownership paperwork" / "missing ownership paperwork" | |
| nonconformance | "a failed quality check" / "the Lot B defect" | |
| contingency | "the project's emergency fund" | |
| supplemental funding | "extra money" | |
| mobilize / remobilize | "bring the crew to the site" / "bring the crew back later" | |
| standby | keep, glossed at first use: "standby pay (paid to keep the crew waiting)" | |
| verified value | "the steel the team has verified" | |
| phased | keep, but anchor at first use: "the phased plan — first batch now, second once it's fixed" | |
| resequence downstream work | "reshuffle the later schedule around the steel delay" | |

## 2. Shared "Public info" lines (every role sees these)

| Current | Proposed |
|---|---|
| PA-01 asks for $1.8M against a $2.4M steel sequence. | The supplier wants $1.8M of the $2.4M steel contract paid now, before the steel is on site. |
| Supplier says the cash protects document cure, Lot B correction, and delivery. | The supplier says the money will pay for paperwork fixes, the Lot B repair, and on-time delivery. |
| Round A left a possible phased path: Lot A first, Lot B after cure. | Round A kept one plan alive: ship the first batch now, ship the second once it's fixed. |
| This round turns the package into money, release, and delivery commitments. | This round is where promises become commitments: who pays, what steel gets approved, and when it ships. |
| Final round: shipment, release, funding, and field mobilization. | Final round: steel ships or doesn't, inspections pass or don't, money moves or doesn't, and the crew shows up or walks. |
| The project can finish if released steel and labor capacity line up. | The project can still finish if approved steel and a ready crew arrive at the same time. |
| Steel has to arrive by week 14 to use the week 15-18 field-work window. | Steel has to arrive by week 14 to use the crew time reserved for weeks 15–18. |

## 3. Round-banner titles

| Current | Proposed |
|---|---|
| Submit the off-site steel payment request | Decide how much to ask to be paid up front |
| Set the owner's provisional funding position | Decide how much cash to offer now |
| Assemble the commercial recovery package | Assemble the rescue package |
| Make the labor commitment binding | Turn your offer into a real commitment |
| Report readiness and choose shipment | Report what's ready and decide what ships |
| Set the owner's final cost and delay position | Decide how much more cost and delay you'll accept |
| Mobilize the crew and crane | Decide when the crew shows up |
| (unchanged: Review the supplier's payment request; Offer crew and crane capacity; Choose the final recovery plan; Approve or reject the recovery package; Commit cash, cure work → "Commit cash, repairs, and delivery weeks") | |

## 4. GC-visible lines (the original complaint)

| Current | Proposed |
|---|---|
| SITUATION: You decide how much of the off-site steel request can be certified and whether to keep a backup steel source available. | You decide how much of the supplier's payment request to approve, and whether to line up a backup steel source just in case. |
| Certify $950K for the verified Lot A path. | Approve $950K — just the part you've verified. |
| Certify the supplier's high application. | Approve the full $1.8M request as-is. |
| Route only the limited submitted records. | Pass along only the few documents the supplier sent. |
| Send available records to owner, lender, and inspector. | Share what documents you have with the owner, lender, and inspector. |
| Hold the initial field-work strategy. | Keep the original work plan until the review clears. |
| Certify no payment. | Approve nothing for payment. |
| Keep downstream work resequenced. | Keep the later schedule reshuffled around the steel delay. |
| Challenge status. | Push back on the supplier's status report. |
| Verify supplier status. | Double-check what the supplier says is ready. |
| SITUATION (B2): You combine supplier, owner, lender, inspector, labor, and backup positions into one executable path. | Everyone has stated a position. You stitch them into one plan that can actually be executed. |

## 5. Owner-visible lines

| Current | Proposed |
|---|---|
| Add $100K immediate equity. | Put in $100K of your own cash now. |
| Make $250K available if controls clear. | Offer $250K once the checks pass. |
| Require title and inspection controls. | Require ownership paperwork and an inspection first. |
| Keep the delay tolerance narrow. | Accept almost no delay. |
| Use contingency if needed. | Tap the project's emergency fund if needed. |
| Provide no supplemental funding. | Put in no extra money. |
| Allocate cost shares explicitly. | Spell out who pays what. |
| Approve standby for the labor subcontractor. | Pay to keep the crew on standby. |

## 6. Supplier-visible lines

| Current | Proposed |
|---|---|
| Request $1.2M against the steel package. | Ask for $1.2M of the steel contract now. |
| Tell the team the title, nonconformance, and cash issues. | Tell the team everything: the paperwork gaps, the Lot B defect, and your cash squeeze. |
| Do not disclose known exceptions. | Keep the known problems to yourself. |
| SITUATION (B1): The team needs to know whether you will actually cure the steel issues... | The team needs to know whether you will actually fix the steel problems and when each batch will be ready. |
| Use maximum outside financing. | Borrow as much as you can. |
| Push for full sequence readiness. | Get both batches fully ready. |
| Keep the cleaner full-sequence story. | Ship with a spotless record. |
| DISCLOSURE: ...the title gaps, the Lot B nonconformance, and your cash squeeze. | ...the paperwork gaps, the Lot B defect, and your cash squeeze. |

## 7. Labor-sub-visible lines

| Current | Proposed |
|---|---|
| Offer partial mobilization at week 15. | Offer half the crew starting week 15. |
| Charge standby for the hold. | Charge a standby fee to keep them available. |
| Make the project remobilize later. | If steel shows up later, the project waits for you to come back. |
| Avoid standby exposure. | Take no risk of unpaid waiting. |
| Mobilize partial capacity in week 15. | Bring half the crew in week 15. |
| Require Lot A release. | Only if the first batch is approved to ship. |
| Return only after remobilization. | Come back only when it's worth it — which takes time. |
| Avoid installing unreleased steel. | Don't install steel the inspector hasn't approved. |
| Release current capacity. / Return only after week 23. | Let the crew go now. / Come back after week 23 at the earliest. |

## 8. Lender / inspector partner-card labels and summaries

| Current | Proposed |
|---|---|
| Offer a limited loan draw | Offer part of the loan money |
| Make this loan draw ineligible | Refuse to release loan money |
| Use escrow and reserve controls | Move money only into a controlled account |
| Release the partial loan draw | Release $760K of loan money |
| Hold the loan draw | Hold the loan money |
| Move funds only through escrow | Pay only into a controlled account |
| Hold all supplemental funding | Refuse any extra loan money |
| Require equity before more lender funds | Owner pays in first, then the bank follows |
| SUMMARY: Loan funds can still support verified steel value if owner equity and controls line up. | Loan money is still possible for the steel the team has verified — if the owner puts in cash and the checks pass. |
| SUMMARY: Funds move through escrow, protecting the loan but limiting immediate supplier liquidity. | Money moves into a controlled account: the loan stays protected, but the supplier can't spend it right away. |
| SUMMARY: Keep Lot B blocked until the issue is cured. | Keep Lot B blocked until the defect is fixed. |

## 9. Role objectives (briefing card)

| Current | Proposed |
|---|---|
| (lender) You can release loan funds only when stored value, controls, equity, and reserves make the draw defensible. | You release loan money only when you can prove the steel is real, the owner has skin in the game, and the loan stays protected. |
| (inspector) You decide what material can be released without creating compliance risk for the project. | You decide what steel is safe and legal to use. |
| (supplier) You need cash to finish, cure, and ship steel while protecting your margin. | You need cash to fix, finish, and ship the steel — without giving away your margin. |
| (gc / owner / labor sub) | Already plain; keep. |

## 10. Engine status lines (end-of-round verdicts)

| Current | Proposed |
|---|---|
| The current path keeps cash, release, labor, and schedule within the success window. | Cash, approvals, labor, and the schedule are all still inside the success window. |
| Lot B never became ready for the full steel sequence. | The second steel batch was never ready to finish the job. |
| Risk has stacked high enough that the current path is not viable as planned. | Enough risk has piled up that the current plan no longer works as written. |
