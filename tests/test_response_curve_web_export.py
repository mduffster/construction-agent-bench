from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "response_curve"
WEB_DATA = ROOT / "web" / "src" / "game-data" / "s01_response_curve.json"
WEB_CHART = ROOT / "web" / "public" / "images" / "s01-response-curve.png"


def test_response_curve_web_export_matches_evidence_package() -> None:
    payload = json.loads(WEB_DATA.read_text())
    manifest_path = EVIDENCE / "evidence_manifest.json"
    table_path = EVIDENCE / "response_curve_by_level.csv"
    chart_path = EVIDENCE / "response_curve.png"
    manifest = json.loads(manifest_path.read_text())
    with table_path.open(newline="") as handle:
        table = list(csv.DictReader(handle))

    assert payload["experiment_id"] == manifest["experiment_id"]
    assert payload["schema_version"] == "constructsim.web_response_curve.v1"
    assert payload["source"]["evidence_manifest_sha256"] == _sha256(manifest_path)
    assert payload["source"]["response_table_sha256"] == _sha256(table_path)
    assert payload["source"]["chart_sha256"] == _sha256(chart_path)
    assert _sha256(WEB_CHART) == _sha256(chart_path)
    assert len(payload["levels"]) == len(table) == 5
    assert payload["haiku_confirmation"]["run_count"] == 50
    assert payload["haiku_confirmation"]["valid_run_count"] == 46
    assert payload["design"]["minimum_safe_request_usd"] == 200_000
    assert payload["design"]["maximum_safe_request_usd"] == 1_200_000


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
