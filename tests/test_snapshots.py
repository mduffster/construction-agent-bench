import json
from pathlib import Path
from typing import Any

from constructbench.config import load_agent_configs, load_project_config
from constructbench.io import append_jsonl
from constructbench.state import export_state_snapshot, initialize_state

ROOT = Path(__file__).resolve().parents[1]


def _snapshot() -> dict[str, Any]:
    project_config = load_project_config(ROOT / "configs" / "project_baseline.yaml")
    role_configs = load_agent_configs(ROOT / "configs" / "agents")
    state = initialize_state(project_config, role_configs)
    return export_state_snapshot(state)


def test_snapshot_is_json_serializable_and_separated() -> None:
    snapshot = _snapshot()

    json.dumps(snapshot)
    assert snapshot["canonical"]["tick"] == 0
    assert "canonical" in snapshot
    assert "public" in snapshot
    assert "private_by_agent" in snapshot
    assert "beliefs_by_agent" in snapshot
    assert snapshot["public"] == {"ledger": []}


def test_append_jsonl_writes_one_record_per_line(tmp_path: Path) -> None:
    snapshot = _snapshot()
    output_path = tmp_path / "state_snapshots.jsonl"

    append_jsonl(output_path, snapshot)
    append_jsonl(output_path, snapshot)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["canonical"]["tick"] == 0
    assert json.loads(lines[1])["canonical"]["tick"] == 0
