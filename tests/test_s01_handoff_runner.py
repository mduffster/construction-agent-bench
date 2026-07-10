from __future__ import annotations

import json

import pytest

from scripts.run_s01_handoff import _validate_existing_run


def _write_run(tmp_path, *, settings: dict, commit: str = "abc", cost_known: bool = True):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run_config.json").write_text(json.dumps({"model_settings": settings}) + "\n")
    (run_dir / "events.jsonl").write_text("{}\n")
    (run_dir / "turn_summaries.jsonl").write_text("{}\n")
    (run_dir / "run_summary.json").write_text(
        json.dumps(
            {
                "run_manifest": {
                    "archival": True,
                    "code": {"git_commit": commit},
                    "usage": {"cost_known": cost_known},
                },
                "model_usage_summary": {"total": {"cost_usd": 0.01}},
            }
        )
        + "\n"
    )
    return run_dir


def test_resume_accepts_only_exact_archival_run(tmp_path) -> None:
    settings = {"stage": "frozen", "replicate_index": 0}
    run_dir = _write_run(tmp_path, settings=settings)

    summary = _validate_existing_run(
        run_dir,
        expected_settings=settings,
        current_commit="abc",
        require_archival=True,
    )

    assert summary["run_manifest"]["usage"]["cost_known"] is True


@pytest.mark.parametrize("mismatch", ["settings", "commit", "cost"])
def test_resume_rejects_incompatible_or_unknown_cost_run(tmp_path, mismatch: str) -> None:
    settings = {"stage": "frozen", "replicate_index": 0}
    run_dir = _write_run(
        tmp_path,
        settings=settings,
        commit="wrong" if mismatch == "commit" else "abc",
        cost_known=mismatch != "cost",
    )
    expected = settings if mismatch != "settings" else {"stage": "other"}

    with pytest.raises(RuntimeError):
        _validate_existing_run(
            run_dir,
            expected_settings=expected,
            current_commit="abc",
            require_archival=True,
        )


def test_resume_rejects_extra_output_files(tmp_path) -> None:
    settings = {"stage": "frozen", "replicate_index": 0}
    run_dir = _write_run(tmp_path, settings=settings)
    (run_dir / "unexpected.json").write_text("{}\n")

    with pytest.raises(RuntimeError, match="output contract"):
        _validate_existing_run(
            run_dir,
            expected_settings=settings,
            current_commit="abc",
            require_archival=True,
        )
