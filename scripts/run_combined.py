from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from constructbench.combined import run_combined_fixtures
from constructbench.scenarios import SCENARIOS


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a shared-state combined ConstructSim fixture set.")
    parser.add_argument(
        "--case",
        action="append",
        required=True,
        help="Scenario fixture in SCENARIO:fixture form, for example S02:normal_failure.",
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    cases = []
    for raw_case in args.case:
        try:
            scenario_key, fixture_name = raw_case.split(":", 1)
        except ValueError as exc:
            raise SystemExit(f"invalid --case {raw_case!r}; expected SCENARIO:fixture") from exc
        if scenario_key not in SCENARIOS:
            raise SystemExit(f"unknown scenario {scenario_key!r}")
        if fixture_name not in SCENARIOS[scenario_key].fixtures:
            raise SystemExit(f"unknown fixture {fixture_name!r} for {scenario_key}")
        cases.append((scenario_key, fixture_name))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or Path("outputs") / f"combined_fixture_{stamp}"
    result = run_combined_fixtures(cases, output_dir=output_dir)
    print(f"wrote {output_dir}")
    print(json.dumps(result.summary, indent=2))


if __name__ == "__main__":
    main()
