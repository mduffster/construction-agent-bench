from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from constructbench.models import DEFAULT_ANTHROPIC_HAIKU_MODEL
from constructbench.validity import run_cheap_model_matrix, run_scripted_controls


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Component 8 validity-ladder gates.")
    parser.add_argument(
        "--gate",
        choices=["scripted-controls", "cheap-smoke", "cheap-pilot"],
        default="scripted-controls",
    )
    parser.add_argument("--variant", choices=["normal", "stressed"], default="normal")
    parser.add_argument("--provider", choices=["anthropic"], default="anthropic")
    parser.add_argument("--model", default=DEFAULT_ANTHROPIC_HAIKU_MODEL)
    parser.add_argument("--replicates-per-cell", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--allow-live-model", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or Path("outputs") / f"validity_{args.gate}_{stamp}"
    if args.gate == "scripted-controls":
        report = run_scripted_controls(output_dir=output_dir, variant=args.variant)
    else:
        replicates = args.replicates_per_cell or (2 if args.gate == "cheap-smoke" else 10)
        report = run_cheap_model_matrix(
            output_dir=output_dir,
            replicates_per_cell=replicates,
            allow_live_model=args.allow_live_model,
            provider=args.provider,
            model=args.model,
            variant=args.variant,
            temperature=args.temperature,
        )
    print(f"wrote {output_dir}")
    print(f"{report['gate_id']} passed={report['passed']}")


if __name__ == "__main__":
    main()
