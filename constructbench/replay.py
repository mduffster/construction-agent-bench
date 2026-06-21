from __future__ import annotations

import json
from pathlib import Path

from constructbench.events import replay_events
from constructbench.state import Event, RunState


def replay_run(output_dir: Path) -> RunState:
    config = json.loads((output_dir / "run_config.json").read_text())
    initial_state = RunState.model_validate(config["initial_state"])
    events = [
        Event.model_validate_json(line)
        for line in (output_dir / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    return replay_events(initial_state, events)
