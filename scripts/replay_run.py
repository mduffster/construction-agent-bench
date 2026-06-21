from __future__ import annotations

import argparse
from pathlib import Path

from constructbench.replay import replay_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a ConstructBench output directory.")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    state = replay_run(args.output_dir)
    print(
        f"{state.terminal_status} cost={state.canonical_state['project']['project_cost']} "
        f"completion={state.canonical_state['project']['completion_tick']}"
    )


if __name__ == "__main__":
    main()
