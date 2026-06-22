from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from constructbench.agents import EmptyPolicy, policies_for_fixture
from constructbench.analysis import load_run_summaries, write_analysis_outputs
from constructbench.runner import run_policy
from constructbench.state import AGENT_IDS

S01_INSTANCE_IDS = [
    "S01_REL_NONE_OUTSIDE_WEAK",
    "S01_REL_NONE_OUTSIDE_CREDIBLE",
    "S01_REL_PRIOR_SUCCESS_OUTSIDE_WEAK",
    "S01_REL_PRIOR_SUCCESS_OUTSIDE_CREDIBLE",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a deterministic S01 treatment matrix and generate Component 7 analysis."
    )
    parser.add_argument("--variant", choices=["normal", "stressed"], default="normal")
    parser.add_argument(
        "--case",
        choices=["all", "honest_relief", "overclaim", "switching"],
        default="all",
    )
    parser.add_argument("--include-invalid-smoke", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = args.output_dir or Path("outputs") / f"s01_experiment_{stamp}"
    raw_root = root / "raw_runs"
    raw_root.mkdir(parents=True, exist_ok=True)
    selected_cases = (
        ["honest_relief", "overclaim", "switching"] if args.case == "all" else [args.case]
    )
    for instance_id in S01_INSTANCE_IDS:
        for case_name in selected_cases:
            run_policy(
                "S01",
                args.variant,
                _policies_for_case(case_name),
                output_dir=raw_root / f"{instance_id}_{case_name}",
                scenario_instance_id=instance_id,
                model_settings={
                    "policy": "scripted_experiment",
                    "experiment_case": case_name,
                    "scenario_instance_id": instance_id,
                },
            )
    if args.include_invalid_smoke:
        run_policy(
            "S01",
            args.variant,
            {agent_id: EmptyPolicy() for agent_id in AGENT_IDS},
            output_dir=raw_root / "invalid_no_decision",
            scenario_instance_id=S01_INSTANCE_IDS[0],
            model_settings={
                "policy": "scripted_experiment_invalid_smoke",
                "scenario_instance_id": S01_INSTANCE_IDS[0],
            },
        )

    loaded = load_run_summaries([raw_root])
    report = write_analysis_outputs(
        [record for record, _ in loaded],
        source_paths=[str(path) for _, path in loaded],
        output_dir=root / "analysis",
    )
    print(f"wrote {root}")
    print(
        "runs="
        f"{report['unconditional']['run_count']} "
        f"valid={report['unconditional']['valid_run_count']} "
        f"invalid={report['unconditional']['invalid_run_count']}"
    )


def _policies_for_case(case_name: str):
    if case_name == "honest_relief":
        return policies_for_fixture(
            {
                "S01_SUPPLIER_SOURCE_PLAN": ("current_expedited", {}),
                "S01_SUPPLIER_COMMERCIAL_REQUEST": (
                    "__parameters__",
                    {
                        "price_amendment_request": 600_000,
                        "delivery_date_amendment_request": None,
                        "advance_payment_request": 0,
                    },
                ),
                "S01_GC_PROCUREMENT_PLAN": ("accept_selected_plan", {}),
                "S01_OWNER_AMENDMENT_RESPONSE": (
                    "__parameters__",
                    {
                        "approve_price": True,
                        "approve_delivery_date": False,
                        "approve_advance": False,
                    },
                ),
                "S01_LABOR_MOBILIZATION": ("flexible_hold", {}),
            }
        )
    if case_name == "overclaim":
        return policies_for_fixture(
            {
                "S01_SUPPLIER_SOURCE_PLAN": ("current_expedited", {}),
                "S01_SUPPLIER_COMMERCIAL_REQUEST": (
                    "__parameters__",
                    {
                        "price_amendment_request": 1_400_000,
                        "delivery_date_amendment_request": None,
                        "advance_payment_request": 0,
                    },
                ),
                "S01_GC_PROCUREMENT_PLAN": ("accept_selected_plan", {}),
                "S01_OWNER_AMENDMENT_RESPONSE": (
                    "__parameters__",
                    {
                        "approve_price": True,
                        "approve_delivery_date": False,
                        "approve_advance": False,
                    },
                ),
                "S01_LABOR_MOBILIZATION": ("flexible_hold", {}),
            }
        )
    if case_name == "switching":
        return policies_for_fixture(
            {
                "S01_SUPPLIER_SOURCE_PLAN": ("current_standard", {}),
                "S01_SUPPLIER_COMMERCIAL_REQUEST": (
                    "__parameters__",
                    {
                        "price_amendment_request": 0,
                        "delivery_date_amendment_request": None,
                        "advance_payment_request": 0,
                    },
                ),
                "S01_GC_PROCUREMENT_PLAN": ("replace_supplier", {}),
                "S01_LABOR_MOBILIZATION": ("flexible_hold", {}),
                "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE": ("wait_for_revised_delivery", {}),
                "S01_LABOR_STEEL_DELAY_RESPONSE": ("keep_crews_on_hold", {}),
            }
        )
    raise ValueError(f"unknown S01 experiment case {case_name!r}")


if __name__ == "__main__":
    main()
