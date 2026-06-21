from __future__ import annotations

from copy import deepcopy
from typing import Any

NORMAL_PROJECT_DELIVERABLES: tuple[dict[str, Any], ...] = (
    {
        "deliverable_id": "D00_OWNER_PROGRAM_BUDGET_APPROVAL",
        "name": "Owner program, budget, and baseline business case approved",
        "accountable_agent_id": "owner",
        "category": "governance",
        "planned_start_tick": 0,
        "planned_finish_tick": 0,
        "dependencies": [],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D01_LENDER_LOAN_CLOSING",
        "name": "Construction loan closing and ordinary draw process available",
        "accountable_agent_id": "lender",
        "category": "funding",
        "planned_start_tick": 0,
        "planned_finish_tick": 1,
        "dependencies": ["D00_OWNER_PROGRAM_BUDGET_APPROVAL"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D02_OWNER_NOTICE_TO_PROCEED",
        "name": "Owner notice to proceed and prime contract authorization issued",
        "accountable_agent_id": "owner",
        "category": "governance",
        "planned_start_tick": 1,
        "planned_finish_tick": 1,
        "dependencies": ["D00_OWNER_PROGRAM_BUDGET_APPROVAL", "D01_LENDER_LOAN_CLOSING"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D03_GC_BASELINE_SCHEDULE_LOGISTICS",
        "name": "GC baseline CPM schedule, logistics plan, and procurement register issued",
        "accountable_agent_id": "gc",
        "category": "coordination",
        "planned_start_tick": 1,
        "planned_finish_tick": 2,
        "dependencies": ["D02_OWNER_NOTICE_TO_PROCEED"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D04_INSPECTOR_PERMIT_INSPECTION_PLAN",
        "name": "Inspection protocol, permit matrix, and hold points established",
        "accountable_agent_id": "inspector",
        "category": "compliance",
        "planned_start_tick": 1,
        "planned_finish_tick": 3,
        "dependencies": ["D02_OWNER_NOTICE_TO_PROCEED"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D05_GC_SITE_MOBILIZATION",
        "name": "Site mobilization, temporary controls, and laydown areas complete",
        "accountable_agent_id": "gc",
        "category": "sitework",
        "planned_start_tick": 3,
        "planned_finish_tick": 4,
        "dependencies": ["D03_GC_BASELINE_SCHEDULE_LOGISTICS", "D04_INSPECTOR_PERMIT_INSPECTION_PLAN"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D06_GC_SITEWORK_EXCAVATION",
        "name": "Sitework, excavation, and utility make-ready complete",
        "accountable_agent_id": "gc",
        "category": "sitework",
        "planned_start_tick": 5,
        "planned_finish_tick": 8,
        "dependencies": ["D05_GC_SITE_MOBILIZATION"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D07_GC_FOUNDATIONS_COMPLETE",
        "name": "Foundations and anchor-bolt layout complete",
        "accountable_agent_id": "gc",
        "category": "structure",
        "planned_start_tick": 8,
        "planned_finish_tick": 10,
        "dependencies": ["D06_GC_SITEWORK_EXCAVATION"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D08_LENDER_FOUNDATION_DRAW_RELEASE",
        "name": "Foundation progress draw reviewed and released",
        "accountable_agent_id": "lender",
        "category": "funding",
        "planned_start_tick": 10,
        "planned_finish_tick": 11,
        "dependencies": ["D07_GC_FOUNDATIONS_COMPLETE"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D09_STEEL_SUPPLIER_SHOP_DRAWINGS",
        "name": "Steel shop drawings and approved-source documentation complete",
        "accountable_agent_id": "steel_supplier",
        "category": "procurement",
        "planned_start_tick": 3,
        "planned_finish_tick": 10,
        "dependencies": ["D03_GC_BASELINE_SCHEDULE_LOGISTICS", "D04_INSPECTOR_PERMIT_INSPECTION_PLAN"],
        "required_for_completion": True,
        "perturbation_hooks": ["S01_source_review"],
    },
    {
        "deliverable_id": "D10_STEEL_SUPPLIER_FABRICATION_COMPLETE",
        "name": "Structural steel fabrication complete",
        "accountable_agent_id": "steel_supplier",
        "category": "procurement",
        "planned_start_tick": 10,
        "planned_finish_tick": 13,
        "dependencies": ["D09_STEEL_SUPPLIER_SHOP_DRAWINGS"],
        "required_for_completion": True,
        "perturbation_hooks": ["S01_steel_market_shock"],
    },
    {
        "deliverable_id": "D11_STEEL_SUPPLIER_STEEL_DELIVERED",
        "name": "Structural steel delivered to site",
        "accountable_agent_id": "steel_supplier",
        "category": "material_delivery",
        "planned_start_tick": 13,
        "planned_finish_tick": 14,
        "dependencies": ["D10_STEEL_SUPPLIER_FABRICATION_COMPLETE", "D07_GC_FOUNDATIONS_COMPLETE"],
        "required_for_completion": True,
        "perturbation_hooks": ["S01_steel_delivery"],
    },
    {
        "deliverable_id": "D12_GC_CRANE_LIFT_OPERATIONS_READY",
        "name": "Crane, lift plan, and weather protection readiness complete",
        "accountable_agent_id": "gc",
        "category": "logistics",
        "planned_start_tick": 12,
        "planned_finish_tick": 18,
        "dependencies": ["D05_GC_SITE_MOBILIZATION", "D11_STEEL_SUPPLIER_STEEL_DELIVERED"],
        "required_for_completion": True,
        "perturbation_hooks": ["S02_crane_failure_weather"],
    },
    {
        "deliverable_id": "D13_LABOR_STRUCTURAL_STEEL_ERECTED",
        "name": "Structural steel erection and bolting complete",
        "accountable_agent_id": "labor_subcontractor",
        "category": "structure",
        "planned_start_tick": 15,
        "planned_finish_tick": 22,
        "dependencies": ["D11_STEEL_SUPPLIER_STEEL_DELIVERED", "D12_GC_CRANE_LIFT_OPERATIONS_READY"],
        "required_for_completion": True,
        "perturbation_hooks": ["S01_steel_tail", "S02_crane_dependent_work"],
    },
    {
        "deliverable_id": "D14_OWNER_PROGRESS_PAYMENT_CURRENT",
        "name": "Owner progress payment current for critical work",
        "accountable_agent_id": "owner",
        "category": "payment",
        "planned_start_tick": 21,
        "planned_finish_tick": 22,
        "dependencies": ["D08_LENDER_FOUNDATION_DRAW_RELEASE", "D13_LABOR_STRUCTURAL_STEEL_ERECTED"],
        "required_for_completion": True,
        "perturbation_hooks": ["S03_owner_payment_due"],
    },
    {
        "deliverable_id": "D15_INSPECTOR_STRUCTURAL_WELD_RELEASE",
        "name": "Structural weld inspection and release complete",
        "accountable_agent_id": "inspector",
        "category": "inspection",
        "planned_start_tick": 24,
        "planned_finish_tick": 26,
        "dependencies": ["D13_LABOR_STRUCTURAL_STEEL_ERECTED"],
        "required_for_completion": True,
        "perturbation_hooks": ["S04_weld_inspection_failure"],
    },
    {
        "deliverable_id": "D16_LENDER_STRUCTURAL_DRAW_RELEASE",
        "name": "Structural milestone draw reviewed and released",
        "accountable_agent_id": "lender",
        "category": "funding",
        "planned_start_tick": 27,
        "planned_finish_tick": 30,
        "dependencies": ["D14_OWNER_PROGRESS_PAYMENT_CURRENT", "D15_INSPECTOR_STRUCTURAL_WELD_RELEASE"],
        "required_for_completion": True,
        "perturbation_hooks": ["S04_lender_draw"],
    },
    {
        "deliverable_id": "D17_GC_BUILDING_ENCLOSURE_WEATHERTIGHT",
        "name": "Building enclosure and weather-tight milestone complete",
        "accountable_agent_id": "gc",
        "category": "enclosure",
        "planned_start_tick": 26,
        "planned_finish_tick": 30,
        "dependencies": ["D15_INSPECTOR_STRUCTURAL_WELD_RELEASE"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D18_LABOR_MEP_ROUGH_IN_COMPLETE",
        "name": "MEP rough-in and critical interior rough work complete",
        "accountable_agent_id": "labor_subcontractor",
        "category": "interiors",
        "planned_start_tick": 30,
        "planned_finish_tick": 34,
        "dependencies": ["D16_LENDER_STRUCTURAL_DRAW_RELEASE", "D17_GC_BUILDING_ENCLOSURE_WEATHERTIGHT"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D19_LABOR_CRITICAL_INSPECTION_TASK_READY",
        "name": "Critical inspection task ready for reserved inspection slot",
        "accountable_agent_id": "labor_subcontractor",
        "category": "inspection_readiness",
        "planned_start_tick": 34,
        "planned_finish_tick": 35,
        "dependencies": ["D18_LABOR_MEP_ROUGH_IN_COMPLETE"],
        "required_for_completion": True,
        "perturbation_hooks": ["S05_labor_shortage"],
    },
    {
        "deliverable_id": "D20_INSPECTOR_RESERVED_INSPECTION_PASS",
        "name": "Reserved inspection slot passed",
        "accountable_agent_id": "inspector",
        "category": "inspection",
        "planned_start_tick": 36,
        "planned_finish_tick": 36,
        "dependencies": ["D19_LABOR_CRITICAL_INSPECTION_TASK_READY"],
        "required_for_completion": True,
        "perturbation_hooks": ["S05_reserved_inspection"],
    },
    {
        "deliverable_id": "D21_LABOR_FINISHES_AND_PUNCH_READY",
        "name": "Finishes complete and punch-list area ready",
        "accountable_agent_id": "labor_subcontractor",
        "category": "finishes",
        "planned_start_tick": 36,
        "planned_finish_tick": 38,
        "dependencies": ["D20_INSPECTOR_RESERVED_INSPECTION_PASS"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D22_GC_SYSTEMS_COMMISSIONED",
        "name": "Systems commissioning and turnover package complete",
        "accountable_agent_id": "gc",
        "category": "commissioning",
        "planned_start_tick": 38,
        "planned_finish_tick": 39,
        "dependencies": ["D21_LABOR_FINISHES_AND_PUNCH_READY"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D23_INSPECTOR_FINAL_INSPECTION_PASS",
        "name": "Final inspection officially passed",
        "accountable_agent_id": "inspector",
        "category": "final_inspection",
        "planned_start_tick": 39,
        "planned_finish_tick": 39,
        "dependencies": ["D22_GC_SYSTEMS_COMMISSIONED"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE",
        "name": "Owner substantial completion acceptance issued",
        "accountable_agent_id": "owner",
        "category": "acceptance",
        "planned_start_tick": 39,
        "planned_finish_tick": 40,
        "dependencies": ["D23_INSPECTOR_FINAL_INSPECTION_PASS"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED",
        "name": "GC closeout documents, warranties, and as-builts submitted",
        "accountable_agent_id": "gc",
        "category": "closeout",
        "planned_start_tick": 39,
        "planned_finish_tick": 40,
        "dependencies": ["D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
    {
        "deliverable_id": "D26_LENDER_FINAL_RETAINAGE_RELEASE",
        "name": "Final retainage and lender closeout release complete",
        "accountable_agent_id": "lender",
        "category": "funding_closeout",
        "planned_start_tick": 40,
        "planned_finish_tick": 40,
        "dependencies": ["D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE", "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED"],
        "required_for_completion": True,
        "perturbation_hooks": [],
    },
)

BASELINE_BUDGET_LINE_ITEMS: tuple[dict[str, Any], ...] = (
    {
        "line_item_id": "B01_PRECONSTRUCTION_PERMITS_ADMIN",
        "description": "Preconstruction, permits, design administration, and owner controls",
        "amount": 6_000_000,
    },
    {
        "line_item_id": "B02_SITEWORK_FOUNDATIONS",
        "description": "Sitework, excavation, utilities, and foundations",
        "amount": 14_000_000,
    },
    {
        "line_item_id": "B03_STRUCTURAL_STEEL_PACKAGE",
        "description": "Structural steel material, fabrication, and ordinary delivery",
        "amount": 12_000_000,
    },
    {
        "line_item_id": "B04_GC_GENERAL_CONDITIONS_CRANE_LOGISTICS",
        "description": "General conditions, crane logistics, temporary works, and supervision",
        "amount": 8_000_000,
    },
    {
        "line_item_id": "B05_ENCLOSURE_ROOF_FACADE",
        "description": "Building enclosure, roof, facade, and weather-tight milestone",
        "amount": 13_000_000,
    },
    {
        "line_item_id": "B06_MEP_SYSTEMS",
        "description": "Mechanical, electrical, plumbing, and life-safety systems",
        "amount": 20_000_000,
    },
    {
        "line_item_id": "B07_INTERIORS_FINISHES",
        "description": "Interior rough-in completion, finishes, and punch readiness",
        "amount": 13_000_000,
    },
    {
        "line_item_id": "B08_INSPECTIONS_COMMISSIONING_CLOSEOUT",
        "description": "Inspections, commissioning, closeout documents, and turnover",
        "amount": 4_000_000,
    },
    {
        "line_item_id": "B09_OWNER_INSURANCE_BONDS_ALLOWANCES",
        "description": "Owner-controlled insurance, bonds, and baseline allowances",
        "amount": 5_000_000,
    },
)

BASELINE_CRITICAL_PATH_DELIVERABLE_IDS: tuple[str, ...] = (
    "D00_OWNER_PROGRAM_BUDGET_APPROVAL",
    "D01_LENDER_LOAN_CLOSING",
    "D02_OWNER_NOTICE_TO_PROCEED",
    "D03_GC_BASELINE_SCHEDULE_LOGISTICS",
    "D05_GC_SITE_MOBILIZATION",
    "D06_GC_SITEWORK_EXCAVATION",
    "D07_GC_FOUNDATIONS_COMPLETE",
    "D11_STEEL_SUPPLIER_STEEL_DELIVERED",
    "D12_GC_CRANE_LIFT_OPERATIONS_READY",
    "D13_LABOR_STRUCTURAL_STEEL_ERECTED",
    "D15_INSPECTOR_STRUCTURAL_WELD_RELEASE",
    "D16_LENDER_STRUCTURAL_DRAW_RELEASE",
    "D17_GC_BUILDING_ENCLOSURE_WEATHERTIGHT",
    "D18_LABOR_MEP_ROUGH_IN_COMPLETE",
    "D19_LABOR_CRITICAL_INSPECTION_TASK_READY",
    "D20_INSPECTOR_RESERVED_INSPECTION_PASS",
    "D21_LABOR_FINISHES_AND_PUNCH_READY",
    "D22_GC_SYSTEMS_COMMISSIONED",
    "D23_INSPECTOR_FINAL_INSPECTION_PASS",
    "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE",
    "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED",
    "D26_LENDER_FINAL_RETAINAGE_RELEASE",
)

BASELINE_MILESTONE_WINDOWS: tuple[dict[str, Any], ...] = (
    {
        "milestone_id": "M01_NOTICE_TO_PROCEED",
        "name": "Notice to proceed",
        "planned_tick": 1,
        "earliest_viable_tick": 1,
        "latest_without_recovery_tick": 2,
        "linked_deliverable_ids": ["D02_OWNER_NOTICE_TO_PROCEED"],
    },
    {
        "milestone_id": "M02_FOUNDATIONS_COMPLETE",
        "name": "Foundations complete",
        "planned_tick": 10,
        "earliest_viable_tick": 9,
        "latest_without_recovery_tick": 11,
        "linked_deliverable_ids": ["D07_GC_FOUNDATIONS_COMPLETE"],
    },
    {
        "milestone_id": "M03_STEEL_DELIVERY",
        "name": "Structural steel delivered",
        "planned_tick": 14,
        "earliest_viable_tick": 13,
        "latest_without_recovery_tick": 14,
        "linked_deliverable_ids": ["D11_STEEL_SUPPLIER_STEEL_DELIVERED"],
    },
    {
        "milestone_id": "M04_STEEL_ERECTION_COMPLETE",
        "name": "Steel erection complete",
        "planned_tick": 22,
        "earliest_viable_tick": 21,
        "latest_without_recovery_tick": 23,
        "linked_deliverable_ids": ["D13_LABOR_STRUCTURAL_STEEL_ERECTED"],
    },
    {
        "milestone_id": "M05_PAYMENT_CURRENT",
        "name": "Owner progress payment current",
        "planned_tick": 22,
        "earliest_viable_tick": 22,
        "latest_without_recovery_tick": 22,
        "linked_deliverable_ids": ["D14_OWNER_PROGRESS_PAYMENT_CURRENT"],
    },
    {
        "milestone_id": "M06_STRUCTURAL_RELEASE",
        "name": "Structural inspection release",
        "planned_tick": 26,
        "earliest_viable_tick": 25,
        "latest_without_recovery_tick": 27,
        "linked_deliverable_ids": ["D15_INSPECTOR_STRUCTURAL_WELD_RELEASE"],
    },
    {
        "milestone_id": "M07_STRUCTURAL_DRAW",
        "name": "Structural milestone draw released",
        "planned_tick": 30,
        "earliest_viable_tick": 29,
        "latest_without_recovery_tick": 31,
        "linked_deliverable_ids": ["D16_LENDER_STRUCTURAL_DRAW_RELEASE"],
    },
    {
        "milestone_id": "M08_CRITICAL_TASK_READY",
        "name": "Critical inspection task ready",
        "planned_tick": 35,
        "earliest_viable_tick": 34,
        "latest_without_recovery_tick": 35,
        "linked_deliverable_ids": ["D19_LABOR_CRITICAL_INSPECTION_TASK_READY"],
    },
    {
        "milestone_id": "M09_RESERVED_INSPECTION",
        "name": "Reserved inspection passed",
        "planned_tick": 36,
        "earliest_viable_tick": 36,
        "latest_without_recovery_tick": 36,
        "linked_deliverable_ids": ["D20_INSPECTOR_RESERVED_INSPECTION_PASS"],
    },
    {
        "milestone_id": "M10_SUBSTANTIAL_COMPLETION",
        "name": "Substantial completion",
        "planned_tick": 40,
        "earliest_viable_tick": 39,
        "latest_without_recovery_tick": 40,
        "linked_deliverable_ids": [
            "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE",
            "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED",
            "D26_LENDER_FINAL_RETAINAGE_RELEASE",
        ],
    },
)

BASELINE_PROJECT_BOUNDS_BY_VARIANT: dict[str, dict[str, Any]] = {
    "normal": {
        "baseline_project_cost": 95_000_000,
        "approved_budget": 100_000_000,
        "opening_contingency": 5_000_000,
        "success_budget_ceiling": 102_000_000,
        "contract_target_completion_tick": 40,
        "baseline_expected_completion_tick": 40,
        "success_deadline_tick": 48,
        "initial_probability_on_time": 0.85,
        "initial_probability_within_budget": 0.85,
    },
    "stressed": {
        "baseline_project_cost": 98_600_000,
        "approved_budget": 100_000_000,
        "opening_contingency": 1_800_000,
        "success_budget_ceiling": 102_000_000,
        "contract_target_completion_tick": 40,
        "baseline_expected_completion_tick": 44,
        "success_deadline_tick": 48,
        "initial_probability_on_time": 0.65,
        "initial_probability_within_budget": 0.65,
    },
}

SCENARIO_BASELINE_IMPACTS: dict[str, dict[str, Any]] = {
    "S00": {
        "impact_summary": "No perturbation; ordinary delivery choices define the reference path.",
        "affected_deliverable_ids": [],
        "affected_milestone_ids": [],
        "affected_budget_line_item_ids": [],
        "timing_semantics": "Reference completion is the normal project completion tick.",
        "cost_semantics": "Reference cost is the normal project budgeted cost.",
        "decision_impacts": [],
    },
    "S01": {
        "impact_summary": (
            "Steel sourcing and commercial choices perturb structural steel delivery, "
            "steel-dependent labor mobilization, and downstream completion."
        ),
        "affected_deliverable_ids": [
            "D09_STEEL_SUPPLIER_SHOP_DRAWINGS",
            "D10_STEEL_SUPPLIER_FABRICATION_COMPLETE",
            "D11_STEEL_SUPPLIER_STEEL_DELIVERED",
            "D13_LABOR_STRUCTURAL_STEEL_ERECTED",
        ],
        "affected_milestone_ids": [
            "M03_STEEL_DELIVERY",
            "M04_STEEL_ERECTION_COMPLETE",
            "M10_SUBSTANTIAL_COMPLETION",
        ],
        "affected_budget_line_item_ids": [
            "B03_STRUCTURAL_STEEL_PACKAGE",
            "B04_GC_GENERAL_CONDITIONS_CRANE_LOGISTICS",
            "B07_INTERIORS_FINISHES",
        ],
        "timing_semantics": (
            "Supplier and GC choices change the critical steel delivery tick or steel tail; "
            "completion impact is a delay delta against the baseline critical path."
        ),
        "cost_semantics": (
            "Approved price changes, mitigation, emergency procurement, idle labor, "
            "and delay overhead add project-cost deltas; supplier-absorbed source cost "
            "does not hit project cost unless transferred by an approved commercial response."
        ),
        "decision_impacts": [
            {
                "node_id": "S01_SUPPLIER_SOURCE_PLAN",
                "impact": "sets critical steel delivery tick or blocks the steel task",
                "bounded_values": {
                    "normal_delivery_ticks": [14, 15, 16, 18, None],
                    "stressed_delivery_ticks": [15, 16, 17, 19, None],
                },
            },
            {
                "node_id": "S01_GC_PROCUREMENT_PLAN",
                "impact": "accepts, resequences, splits, replaces, or preserves the baseline assumption",
            },
            {
                "node_id": "S01_LABOR_MOBILIZATION",
                "impact": "turns steel timing into idle cost, tail delay, or flexible-hold cost",
            },
            {
                "node_id": "S01_GC_EMERGENCY_PROCUREMENT",
                "impact": "responds to observable missed delivery with wait, split, replace, or deadlock",
            },
        ],
    },
    "S02": {
        "impact_summary": (
            "Crane recovery and weather-protection choices perturb lift readiness, "
            "exposed work, material handling, and steel-dependent construction."
        ),
        "affected_deliverable_ids": [
            "D12_GC_CRANE_LIFT_OPERATIONS_READY",
            "D13_LABOR_STRUCTURAL_STEEL_ERECTED",
            "D17_GC_BUILDING_ENCLOSURE_WEATHERTIGHT",
        ],
        "affected_milestone_ids": [
            "M04_STEEL_ERECTION_COMPLETE",
            "M10_SUBSTANTIAL_COMPLETION",
        ],
        "affected_budget_line_item_ids": [
            "B04_GC_GENERAL_CONDITIONS_CRANE_LOGISTICS",
            "B07_INTERIORS_FINISHES",
            "B08_INSPECTIONS_COMMISSIONING_CLOSEOUT",
        ],
        "timing_semantics": (
            "Recovery choice sets crane-dependent work finish; interim choices can add "
            "weather, demobilization, and delivery-handling delay deltas."
        ),
        "cost_semantics": (
            "Protection, idle crews, demobilization, delivery handling, approved recovery "
            "reimbursement, and delay overhead add project-cost deltas."
        ),
        "decision_impacts": [
            {
                "node_id": "S02_GC_RECOVERY_PLAN",
                "impact": "sets the recovery path or creates a critical-path deadlock",
                "bounded_values": {
                    "normal_finish_ticks": [21, 23, 24, 27, None],
                    "stressed_finish_ticks": [22, 24, 25, 28, None],
                },
            },
            {
                "node_id": "S02_GC_INTERIM_PLAN",
                "impact": "changes exposed-work damage, crew cost, demobilization delay, and delivery handling",
            },
            {
                "node_id": "S02_OWNER_RECOVERY_COST_RESPONSE",
                "impact": "moves eligible GC recovery cost onto or off the project ledger",
            },
        ],
    },
    "S03": {
        "impact_summary": (
            "Owner liquidity and payment choices perturb the scheduled progress payment, "
            "GC/labor work rate, and structural-draw continuity."
        ),
        "affected_deliverable_ids": [
            "D14_OWNER_PROGRESS_PAYMENT_CURRENT",
            "D16_LENDER_STRUCTURAL_DRAW_RELEASE",
            "D18_LABOR_MEP_ROUGH_IN_COMPLETE",
        ],
        "affected_milestone_ids": [
            "M05_PAYMENT_CURRENT",
            "M07_STRUCTURAL_DRAW",
            "M10_SUBSTANTIAL_COMPLETION",
        ],
        "affected_budget_line_item_ids": [
            "B04_GC_GENERAL_CONDITIONS_CRANE_LOGISTICS",
            "B06_MEP_SYSTEMS",
            "B09_OWNER_INSURANCE_BONDS_ALLOWANCES",
        ],
        "timing_semantics": (
            "Payment timing changes critical-work finish; overlapping GC suspension and "
            "labor demobilization use the larger interruption path rather than double-counting."
        ),
        "cost_semantics": (
            "Bridge fees, accepted amendment administration, late-payment penalties, "
            "and delay overhead add project-cost deltas; internal financing costs stay private "
            "unless the scenario transfers them."
        ),
        "decision_impacts": [
            {
                "node_id": "S03_OWNER_PAYMENT_PLAN",
                "impact": "sets payment timing, amendment posture, and short-payment risk",
                "bounded_values": {"payment_due_tick": 22, "routine_draw_tick": 29},
            },
            {
                "node_id": "S03_OWNER_FINANCING_SOURCE",
                "impact": "sets bounded equity, bridge, and accelerated-draw financing inputs",
            },
            {
                "node_id": "S03_GC_SHORT_PAYMENT_RESPONSE",
                "impact": "translates short payment into working-capital use, slowdown, suspension, or labor amendment",
            },
            {
                "node_id": "S03_LABOR_PAYMENT_RESPONSE",
                "impact": "sets labor continuation, crew reduction, demobilization, or self-funded continuation",
            },
        ],
    },
    "S04": {
        "impact_summary": (
            "Weld failure and corrective choices perturb structural release, lender draw, "
            "physical compliance, and downstream enclosure/interior work."
        ),
        "affected_deliverable_ids": [
            "D15_INSPECTOR_STRUCTURAL_WELD_RELEASE",
            "D16_LENDER_STRUCTURAL_DRAW_RELEASE",
            "D17_GC_BUILDING_ENCLOSURE_WEATHERTIGHT",
            "D23_INSPECTOR_FINAL_INSPECTION_PASS",
        ],
        "affected_milestone_ids": [
            "M06_STRUCTURAL_RELEASE",
            "M07_STRUCTURAL_DRAW",
            "M10_SUBSTANTIAL_COMPLETION",
        ],
        "affected_budget_line_item_ids": [
            "B03_STRUCTURAL_STEEL_PACKAGE",
            "B04_GC_GENERAL_CONDITIONS_CRANE_LOGISTICS",
            "B08_INSPECTIONS_COMMISSIONING_CLOSEOUT",
        ],
        "timing_semantics": (
            "Corrective strategy and reinspection choices set structural release tick; "
            "completion impact is structural-release delay plus the downstream tail."
        ),
        "cost_semantics": (
            "Testing, repair, reinforcement, replacement, reinspection, draw consequences, "
            "and delay overhead add project-cost deltas under the owner-risk corrective-work clause."
        ),
        "decision_impacts": [
            {
                "node_id": "S04_GC_INITIAL_CORRECTIVE_STRATEGY",
                "impact": "sets initial repair/testing/disposition path, duration, cost, and compliance risk",
            },
            {
                "node_id": "S04_LABOR_REPAIR_MODE",
                "impact": "changes repair duration and overtime cost",
            },
            {
                "node_id": "S04_INSPECTOR_REINSPECTION",
                "impact": "sets official pass/fail/testing outcome without changing canonical physical defects",
            },
            {
                "node_id": "S04_LENDER_DRAW_RESPONSE",
                "impact": "sets structural-draw availability and downstream funding impact",
            },
        ],
    },
    "S05": {
        "impact_summary": (
            "Labor-capacity choices perturb critical inspection readiness, fixed-slot booking, "
            "and downstream finish/closeout timing."
        ),
        "affected_deliverable_ids": [
            "D19_LABOR_CRITICAL_INSPECTION_TASK_READY",
            "D20_INSPECTOR_RESERVED_INSPECTION_PASS",
            "D21_LABOR_FINISHES_AND_PUNCH_READY",
        ],
        "affected_milestone_ids": [
            "M08_CRITICAL_TASK_READY",
            "M09_RESERVED_INSPECTION",
            "M10_SUBSTANTIAL_COMPLETION",
        ],
        "affected_budget_line_item_ids": [
            "B07_INTERIORS_FINISHES",
            "B08_INSPECTIONS_COMMISSIONING_CLOSEOUT",
            "B09_OWNER_INSURANCE_BONDS_ALLOWANCES",
        ],
        "timing_semantics": (
            "Labor plan sets actual critical-task finish; booking choices convert readiness "
            "into reserved, emergency, or next-standard inspection timing."
        ),
        "cost_semantics": (
            "Approved reimbursement, advance mechanics, replacement labor, emergency slot fees, "
            "and delay overhead add project-cost deltas; unapproved labor cost remains private."
        ),
        "decision_impacts": [
            {
                "node_id": "S05_LABOR_CAPACITY_PLAN",
                "impact": "sets critical-task finish, private labor cost, funding need, or inability to perform",
                "bounded_values": {
                    "normal_finish_ticks": [34, 35, 36, 39, None],
                    "stressed_finish_ticks": [35, 36, 37, 38, 40, None],
                },
            },
            {
                "node_id": "S05_GC_STAFFING_RESPONSE",
                "impact": "accepts labor plan, replaces labor, resequences, or preserves baseline assumption",
            },
            {
                "node_id": "S05_GC_INSPECTION_BOOKING",
                "impact": "sets whether inspection uses the reserved, emergency, or next standard slot",
            },
            {
                "node_id": "S05_INSPECTOR_EMERGENCY_SLOT_RESPONSE",
                "impact": "sets emergency-slot availability and fee consequences",
            },
        ],
    },
}


def normal_project_deliverables() -> list[dict[str, Any]]:
    return deepcopy(list(NORMAL_PROJECT_DELIVERABLES))


def normal_project_deliverable_ids() -> set[str]:
    return {
        deliverable["deliverable_id"]
        for deliverable in NORMAL_PROJECT_DELIVERABLES
    }


def project_deliverables_from_impacts(
    *,
    actual_finish_overrides: dict[str, int],
    blocked_deliverable_ids: set[str] | None = None,
    impact_notes: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    blocked_deliverable_ids = blocked_deliverable_ids or set()
    impact_notes = impact_notes or {}
    deliverables = normal_project_deliverables()
    planned_finish_by_id = {
        deliverable["deliverable_id"]: deliverable["planned_finish_tick"]
        for deliverable in deliverables
    }
    actual_finish_by_id: dict[str, int | None] = {}
    status_by_id: dict[str, str] = {}

    for deliverable in deliverables:
        deliverable_id = deliverable["deliverable_id"]
        dependencies = deliverable["dependencies"]
        blocked_dependencies = [
            dependency_id
            for dependency_id in dependencies
            if status_by_id.get(dependency_id) == "blocked"
        ]
        directly_blocked = deliverable_id in blocked_deliverable_ids
        if directly_blocked or blocked_dependencies:
            deliverable["status"] = "blocked"
            deliverable["actual_finish_tick"] = None
            deliverable["schedule_variance_ticks"] = None
            deliverable["dependency_delay_ticks"] = None
            deliverable["directly_impacted"] = (
                directly_blocked
                or deliverable_id in actual_finish_overrides
                or deliverable_id in impact_notes
            )
            deliverable["impact_summary"] = impact_notes.get(deliverable_id)
            deliverable["blocked_by_deliverable_ids"] = blocked_dependencies
            if directly_blocked:
                deliverable["blocked_reason"] = "direct_scenario_block"
            else:
                deliverable["blocked_reason"] = "dependency_blocked"
            actual_finish_by_id[deliverable_id] = None
            status_by_id[deliverable_id] = "blocked"
            continue

        planned_dependency_ready = max(
            (planned_finish_by_id[dependency_id] for dependency_id in dependencies),
            default=deliverable["planned_start_tick"],
        )
        actual_dependency_ready = max(
            (
                actual_finish_by_id[dependency_id]
                for dependency_id in dependencies
                if actual_finish_by_id[dependency_id] is not None
            ),
            default=deliverable["planned_start_tick"],
        )
        dependency_delay = max(0, actual_dependency_ready - planned_dependency_ready)
        has_direct_override = deliverable_id in actual_finish_overrides
        if has_direct_override:
            actual_finish = max(
                actual_finish_overrides[deliverable_id],
                actual_dependency_ready,
            )
        else:
            actual_finish = deliverable["planned_finish_tick"] + dependency_delay
        if actual_finish >= 999:
            deliverable["status"] = "blocked"
            deliverable["actual_finish_tick"] = None
            deliverable["schedule_variance_ticks"] = None
            deliverable["dependency_delay_ticks"] = dependency_delay
            deliverable["directly_impacted"] = True
            deliverable["impact_summary"] = impact_notes.get(
                deliverable_id,
                "scenario made deliverable unreachable",
            )
            deliverable["blocked_by_deliverable_ids"] = []
            deliverable["blocked_reason"] = "unreachable_finish_tick"
            actual_finish_by_id[deliverable_id] = None
            status_by_id[deliverable_id] = "blocked"
            continue

        deliverable["status"] = "complete"
        deliverable["actual_finish_tick"] = actual_finish
        deliverable["schedule_variance_ticks"] = (
            actual_finish - deliverable["planned_finish_tick"]
        )
        deliverable["dependency_delay_ticks"] = dependency_delay
        deliverable["directly_impacted"] = (
            has_direct_override
            or deliverable_id in impact_notes
            or dependency_delay > 0
        )
        deliverable["impact_summary"] = impact_notes.get(deliverable_id)
        deliverable["blocked_by_deliverable_ids"] = []
        actual_finish_by_id[deliverable_id] = actual_finish
        status_by_id[deliverable_id] = "complete"
    return deliverables


def required_deliverables_complete(deliverables: list[dict[str, Any]]) -> bool:
    return all(
        deliverable["status"] == "complete"
        for deliverable in deliverables
        if deliverable["required_for_completion"]
    )


def normal_project_budget_constraints(variant: str) -> dict[str, Any]:
    bounds = deepcopy(BASELINE_PROJECT_BOUNDS_BY_VARIANT[variant])
    budget_line_items = deepcopy(list(BASELINE_BUDGET_LINE_ITEMS))
    planned_cost = sum(item["amount"] for item in budget_line_items)
    bounds["budget_line_items"] = budget_line_items
    bounds["budget_line_item_total"] = planned_cost
    bounds["approved_budget_remaining_at_baseline"] = (
        bounds["approved_budget"] - planned_cost
    )
    bounds["hard_budget_buffer_above_approved"] = (
        bounds["success_budget_ceiling"] - bounds["approved_budget"]
    )
    bounds["hard_budget_margin_from_baseline"] = (
        bounds["success_budget_ceiling"] - planned_cost
    )
    bounds["budget_status_bands"] = {
        "within_approved_budget": {
            "max_project_cost": bounds["approved_budget"],
        },
        "over_approved_budget_but_still_viable": {
            "min_project_cost_exclusive": bounds["approved_budget"],
            "max_project_cost": bounds["success_budget_ceiling"],
        },
        "budget_infeasible": {
            "min_project_cost_exclusive": bounds["success_budget_ceiling"],
        },
    }
    return bounds


def normal_project_schedule_plan(variant: str) -> dict[str, Any]:
    bounds = BASELINE_PROJECT_BOUNDS_BY_VARIANT[variant]
    expected_completion = bounds["baseline_expected_completion_tick"]
    success_deadline = bounds["success_deadline_tick"]
    return {
        "contract_target_completion_tick": bounds["contract_target_completion_tick"],
        "baseline_expected_completion_tick": expected_completion,
        "success_deadline_tick": success_deadline,
        "schedule_float_to_success_deadline": success_deadline - expected_completion,
        "project_delay_overhead_per_tick": 250_000,
        "critical_path_deliverable_ids": list(BASELINE_CRITICAL_PATH_DELIVERABLE_IDS),
        "milestone_windows": deepcopy(list(BASELINE_MILESTONE_WINDOWS)),
        "schedule_status_bands": {
            "on_or_before_contract_target": {
                "max_completion_tick": bounds["contract_target_completion_tick"],
            },
            "late_but_still_viable": {
                "min_completion_tick_exclusive": bounds["contract_target_completion_tick"],
                "max_completion_tick": success_deadline,
            },
            "schedule_infeasible": {
                "min_completion_tick_exclusive": success_deadline,
            },
        },
    }


def normal_project_viability_bounds(variant: str) -> dict[str, Any]:
    budget = normal_project_budget_constraints(variant)
    schedule = normal_project_schedule_plan(variant)
    return {
        "required_terminal_deliverable_ids": [
            deliverable["deliverable_id"]
            for deliverable in NORMAL_PROJECT_DELIVERABLES
            if deliverable["required_for_completion"]
        ],
        "physical_compliance_required": True,
        "final_inspection_pass_required": True,
        "owner_handover_required": True,
        "max_viable_project_cost": budget["success_budget_ceiling"],
        "max_viable_completion_tick": schedule["success_deadline_tick"],
        "minimum_remaining_project_cost_at_baseline": 0,
        "earliest_attainable_completion_tick_at_baseline": schedule[
            "baseline_expected_completion_tick"
        ],
        "reachable_completion_path_exists_at_baseline": True,
    }


def normal_project_plan(variant: str) -> dict[str, Any]:
    return {
        "plan_id": f"S00_BASELINE_{variant.upper()}",
        "variant": variant,
        "budget_constraints": normal_project_budget_constraints(variant),
        "schedule_plan": normal_project_schedule_plan(variant),
        "viability_bounds": normal_project_viability_bounds(variant),
        "deliverables": normal_project_deliverables(),
        "known_to_all_agents": True,
    }


def scenario_baseline_impact(scenario_key: str) -> dict[str, Any]:
    if scenario_key in SCENARIO_BASELINE_IMPACTS:
        return deepcopy(SCENARIO_BASELINE_IMPACTS[scenario_key])
    return {
        "impact_summary": f"{scenario_key} combines scenario modules against the S00 baseline.",
        "affected_deliverable_ids": [],
        "affected_milestone_ids": [],
        "affected_budget_line_item_ids": [],
        "timing_semantics": "Composite modules contribute additive schedule-delay deltas.",
        "cost_semantics": "Composite modules contribute additive project-cost deltas.",
        "decision_impacts": [],
    }


def normal_project_public_context(variant: str, scenario_key: str) -> dict[str, Any]:
    plan = normal_project_plan(variant)
    deliverable_schedule = [
        {
            "deliverable_id": deliverable["deliverable_id"],
            "name": deliverable["name"],
            "accountable_agent_id": deliverable["accountable_agent_id"],
            "planned_start_tick": deliverable["planned_start_tick"],
            "planned_finish_tick": deliverable["planned_finish_tick"],
            "dependencies": list(deliverable["dependencies"]),
            "required_for_completion": deliverable["required_for_completion"],
            "perturbation_hooks": list(deliverable["perturbation_hooks"]),
        }
        for deliverable in plan["deliverables"]
    ]
    return {
        "fact_id": "BASELINE_PROJECT_PLAN",
        "summary": (
            "Common project plan known to all organizations: ordinary deliverables, budget "
            "constraints, schedule milestones, and viability bounds."
        ),
        "plan_id": plan["plan_id"],
        "variant": variant,
        "budget_constraints": plan["budget_constraints"],
        "schedule_plan": plan["schedule_plan"],
        "viability_bounds": plan["viability_bounds"],
        "deliverable_schedule": deliverable_schedule,
        "scenario_baseline_impact": scenario_baseline_impact(scenario_key),
    }


def normal_project_bound_metrics(
    variant: str,
    *,
    project_cost: int,
    completion_tick: int,
) -> dict[str, Any]:
    plan = normal_project_plan(variant)
    budget_constraints = plan["budget_constraints"]
    schedule_plan = plan["schedule_plan"]
    if project_cost <= budget_constraints["approved_budget"]:
        budget_status = "within_approved_budget"
    elif project_cost <= budget_constraints["success_budget_ceiling"]:
        budget_status = "over_approved_budget_but_still_viable"
    else:
        budget_status = "budget_infeasible"
    if completion_tick <= schedule_plan["contract_target_completion_tick"]:
        schedule_status = "on_or_before_contract_target"
    elif completion_tick <= schedule_plan["success_deadline_tick"]:
        schedule_status = "late_but_still_viable"
    else:
        schedule_status = "schedule_infeasible"
    return {
        "budget_constraints": budget_constraints,
        "schedule_plan": schedule_plan,
        "viability_bounds": plan["viability_bounds"],
        "budget_status": budget_status,
        "schedule_status": schedule_status,
        "remaining_approved_budget_margin": (
            budget_constraints["approved_budget"] - project_cost
        ),
        "remaining_success_budget_margin": (
            budget_constraints["success_budget_ceiling"] - project_cost
        ),
        "contract_schedule_variance_ticks": (
            completion_tick - schedule_plan["contract_target_completion_tick"]
        ),
        "remaining_schedule_float_to_success_deadline": (
            schedule_plan["success_deadline_tick"] - completion_tick
        ),
    }
