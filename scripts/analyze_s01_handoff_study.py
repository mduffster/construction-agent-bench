from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from constructbench.handoff_study import (
    analyze_handoff_study,
    render_handoff_study_markdown,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine frozen S01 handoff arms into one descriptive pilot analysis."
    )
    parser.add_argument("study_dir", type=Path)
    parser.add_argument("--excluded-development-spend-usd", type=float, default=0.0)
    args = parser.parse_args()

    row_paths = sorted(args.study_dir.glob("*/handoff_rows.jsonl"))
    if not row_paths:
        raise SystemExit(f"no handoff_rows.jsonl files found under {args.study_dir}")
    rows: list[dict[str, Any]] = []
    for path in row_paths:
        rows.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    analysis = analyze_handoff_study(
        rows,
        excluded_development_spend_usd=args.excluded_development_spend_usd,
    )
    (args.study_dir / "study_analysis.json").write_text(
        json.dumps(analysis, indent=2, sort_keys=True) + "\n"
    )
    (args.study_dir / "study_rows.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )
    (args.study_dir / "study_report.md").write_text(render_handoff_study_markdown(analysis))
    print(
        f"runs={analysis['run_count']} valid={analysis['valid_run_count']} "
        f"study_cost=${analysis['total_model_cost_usd']:.4f} "
        f"program_cost=${analysis['program_spend_including_development_usd']:.4f}"
    )
    print(f"wrote {args.study_dir}")


if __name__ == "__main__":
    main()
