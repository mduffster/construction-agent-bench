from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from constructbench.analysis import load_run_summaries, write_analysis_outputs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build fixed ConstructSim analysis rows, tables, and figures from run outputs."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Run output directories, run_summary.json files, or parent directories.",
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or Path("outputs") / f"analysis_{stamp}"
    loaded = load_run_summaries(args.paths)
    if not loaded:
        raise SystemExit("no run_summary.json files found")
    records = [record for record, _ in loaded]
    source_paths = [str(path) for _, path in loaded]
    report = write_analysis_outputs(
        records,
        source_paths=source_paths,
        output_dir=output_dir,
    )
    print(f"wrote {output_dir}")
    print(
        "runs="
        f"{report['unconditional']['run_count']} "
        f"valid={report['unconditional']['valid_run_count']} "
        f"invalid={report['unconditional']['invalid_run_count']}"
    )


if __name__ == "__main__":
    main()
