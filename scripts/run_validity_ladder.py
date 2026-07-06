from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from constructbench.models import DEFAULT_ANTHROPIC_HAIKU_MODEL
from constructbench.validity import (
    S01_CREDIBLE_ALTERNATIVE_CELLS,
    S01_ECONOMIC_VARIANT_CELLS,
    run_cheap_model_matrix,
    run_scripted_controls,
    run_stronger_model_probe,
)

STRONGER_MODEL_DEFAULT = "claude-sonnet-5"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Component 8 validity-ladder gates.")
    parser.add_argument(
        "--gate",
        choices=[
            "scripted-controls",
            "cheap-smoke",
            "cheap-pilot",
            "stage-c-variants",
            "stronger-model",
        ],
        default="scripted-controls",
    )
    parser.add_argument("--variant", choices=["normal", "stressed"], default="normal")
    parser.add_argument("--provider", choices=["anthropic"], default="anthropic")
    parser.add_argument("--model", default=None)
    parser.add_argument("--instance-ids", default=None, help="Comma-separated scenario instance IDs.")
    parser.add_argument("--replicates-per-cell", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--allow-live-model", action="store_true")
    args = parser.parse_args()

    cli_instance_ids = args.instance_ids.split(",") if args.instance_ids else None

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or Path("outputs") / f"validity_{args.gate}_{stamp}"
    if args.gate == "scripted-controls":
        report = run_scripted_controls(output_dir=output_dir, variant=args.variant)
    elif args.gate == "stronger-model":
        report = run_stronger_model_probe(
            output_dir=output_dir,
            allow_live_model=args.allow_live_model,
            model=args.model or STRONGER_MODEL_DEFAULT,
            instance_ids=cli_instance_ids or S01_CREDIBLE_ALTERNATIVE_CELLS,
            replicates_per_cell=args.replicates_per_cell or 2,
            provider=args.provider,
            variant=args.variant,
            temperature=args.temperature,
        )
    else:
        if args.gate == "stage-c-variants":
            default_replicates = 1
            instance_ids = cli_instance_ids or S01_ECONOMIC_VARIANT_CELLS
        else:
            default_replicates = 2 if args.gate == "cheap-smoke" else 10
            instance_ids = cli_instance_ids
        replicates = args.replicates_per_cell or default_replicates
        report = run_cheap_model_matrix(
            output_dir=output_dir,
            replicates_per_cell=replicates,
            allow_live_model=args.allow_live_model,
            provider=args.provider,
            model=args.model or DEFAULT_ANTHROPIC_HAIKU_MODEL,
            variant=args.variant,
            temperature=args.temperature,
            instance_ids=instance_ids,
        )
    print(f"wrote {output_dir}")
    print(f"{report['gate_id']} passed={report['passed']}")


if __name__ == "__main__":
    main()
