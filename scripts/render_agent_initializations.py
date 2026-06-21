from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from constructbench.models import base_system_prompt, initialization_prompt
from constructbench.scenarios import SCENARIOS
from constructbench.state import AGENT_IDS, default_behavior_profiles


def main() -> None:
    parser = argparse.ArgumentParser(description="Render exact persistent agent initialization prompts.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), action="append")
    parser.add_argument(
        "--behavior-profile",
        choices=["collaborative", "selfish", "passive"],
        action="append",
    )
    parser.add_argument("--variant", choices=["normal", "stressed"], default="normal")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    scenarios = args.scenario or sorted(SCENARIOS)
    behavior_profiles = args.behavior_profile or ["collaborative", "selfish", "passive"]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or Path("outputs") / f"prompt_audit_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, object]] = []
    for scenario_key in scenarios:
        scenario = SCENARIOS[scenario_key]
        for behavior_profile in behavior_profiles:
            state = scenario.create_state(
                run_id=f"prompt_audit_{scenario_key}_{behavior_profile}",
                variant=args.variant,
                behavior_profile_by_agent=default_behavior_profiles(behavior_profile),
                model_settings={
                    "policy": "prompt_audit",
                    "behavior_profile": behavior_profile,
                },
            )
            for agent_id in AGENT_IDS:
                briefing = state.briefings_by_agent[agent_id]
                exact_initialization = initialization_prompt(briefing)
                path = output_dir / scenario_key / behavior_profile / f"{agent_id}.txt"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "\n".join(
                        [
                            "SYSTEM MESSAGE 1",
                            base_system_prompt(),
                            "",
                            "SYSTEM MESSAGE 2",
                            exact_initialization,
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                manifest.append(
                    {
                        "scenario": scenario_key,
                        "variant": args.variant,
                        "behavior_profile": behavior_profile,
                        "agent_id": agent_id,
                        "path": str(path),
                        "goal_profile": briefing.goal_profile.model_dump(mode="json"),
                        "behavior_summary": briefing.behavior_profile.summary,
                        "initialization": json.loads(exact_initialization),
                    }
                )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output_dir}")


if __name__ == "__main__":
    main()
