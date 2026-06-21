from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from constructbench.state import RunState

RUN_MANIFEST_SCHEMA_VERSION = "constructbench.run_manifest.v1"
OUTPUT_SCHEMA_VERSION = "constructbench.outputs.v1"
PRICING_TABLE_VERSION = "constructbench.anthropic_pricing.v1"

RELEVANT_FILE_GLOBS = (
    "constructbench/**/*.py",
    "configs/**/*.yaml",
    "scripts/**/*.py",
    "pyproject.toml",
    "uv.lock",
)


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_json_sha256(data: Any) -> str:
    return sha256_text(canonical_json(data))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_run_manifest(
    *,
    initial_state: RunState,
    final_state: RunState,
    debug_model_io: bool,
    output_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    repo_root = _repo_root()
    code = _code_manifest(repo_root)
    scenario = _scenario_manifest(final_state)
    run = _run_manifest(initial_state, final_state, debug_model_io)
    model = _model_manifest(final_state, repo_root)
    usage = _usage_manifest(final_state)
    return {
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "archival": not code["dirty"],
        "code": code,
        "scenario": scenario,
        "run": run,
        "model": model,
        "usage": usage,
        "outputs": output_hashes or {},
    }


def output_hashes(output_dir: Path) -> dict[str, str]:
    return {
        name: sha256_file(output_dir / name)
        for name in ["run_config.json", "events.jsonl", "turn_summaries.jsonl"]
    }


def _code_manifest(repo_root: Path) -> dict[str, Any]:
    git_commit = _git_output(repo_root, ["git", "rev-parse", "HEAD"])
    status_lines = _git_output(repo_root, ["git", "status", "--short"])
    dirty_status = status_lines.splitlines() if status_lines else []
    file_hashes = _relevant_file_hashes(repo_root)
    tags_at_head = _git_output(repo_root, ["git", "tag", "--points-at", "HEAD"])
    return {
        "git_commit": git_commit or None,
        "dirty": bool(dirty_status),
        "dirty_status": dirty_status,
        "dirty_paths": [line[3:] if len(line) > 3 else line for line in dirty_status],
        "tags_at_head": tags_at_head.splitlines() if tags_at_head else [],
        "worktree_content_sha256": canonical_json_sha256(file_hashes),
        "file_hashes": file_hashes,
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "package_version": _package_version(repo_root),
    }


def _scenario_manifest(final_state: RunState) -> dict[str, Any]:
    scenario = final_state.canonical_state.get("scenario", {})
    scenario_instance = scenario.get("scenario_instance", {})
    project = final_state.canonical_state.get("project", {})
    baseline_plan = final_state.canonical_state.get("baseline_project_plan", {})
    return {
        "scenario_key": scenario.get("scenario_key"),
        "scenario_id": final_state.scenario_id,
        "variant": final_state.variant,
        "scenario_class_name": scenario.get("scenario_class_name"),
        "baseline_plan_hash": canonical_json_sha256(baseline_plan),
        "baseline_impact_hash": canonical_json_sha256(project.get("scenario_baseline_impact", {})),
        "scenario_start_hash": scenario.get("scenario_start_hash"),
        "scenario_instance_id": scenario_instance.get("instance_id"),
        "scenario_instance_hash": scenario_instance.get("scenario_instance_hash"),
        "scenario_instance_treatment": scenario_instance.get("treatment"),
        "fixture_name": final_state.model_settings.get("fixture"),
    }


def _run_manifest(
    initial_state: RunState,
    final_state: RunState,
    debug_model_io: bool,
) -> dict[str, Any]:
    settings = initial_state.model_settings
    is_focal = settings.get("policy") == "focal"
    return {
        "run_id": initial_state.run_id,
        "seed": initial_state.seed,
        "policy_mode": settings.get("policy"),
        "focal_agent_id": settings.get("focal_agent_id"),
        "counterparty_policy_id": settings.get("counterparty_policy_id"),
        "focal_policy_provider": settings.get("focal_policy_provider")
        or (settings.get("provider") if is_focal else None),
        "focal_policy_model": settings.get("focal_policy_model")
        or (settings.get("model") if is_focal else None),
        "behavior_profile_by_agent": initial_state.behavior_profile_by_agent,
        "goal_profile_by_agent": {
            agent_id: profile.model_dump(mode="json")
            for agent_id, profile in initial_state.goal_profile_by_agent.items()
        },
        "debug_model_io": debug_model_io,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "run_valid": final_state.run_valid,
        "terminal_status": final_state.terminal_status,
    }


def _model_manifest(final_state: RunState, repo_root: Path) -> dict[str, Any]:
    records = final_state.histories.get("model_io", [])
    first_record = records[0] if records else {}
    settings = final_state.model_settings
    return {
        "provider": settings.get("provider"),
        "model_id": settings.get("model") or first_record.get("model"),
        "adapter_class": first_record.get("adapter_class"),
        "prompt_style": first_record.get("prompt_style"),
        "model_parameters": first_record.get("model_parameters") or settings.get("model_parameters", {}),
        "api_version": first_record.get("api_version"),
        "parser_adapter_source_hash": _source_hash(repo_root, "constructbench/models.py"),
    }


def _usage_manifest(final_state: RunState) -> dict[str, Any]:
    records = final_state.histories.get("model_io", [])
    totals: dict[str, Any] = {
        "call_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cost_usd": 0.0,
    }
    cost_known = True
    for record in records:
        totals["call_count"] += 1
        usage = record.get("usage") or {}
        for field in [
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ]:
            totals[field] += int(usage.get(field, 0) or 0)
        cost = record.get("cost_usd")
        if cost is None:
            cost_known = False
        else:
            totals["cost_usd"] += float(cost)
    totals["cost_usd"] = round(totals["cost_usd"], 6)
    return {
        **totals,
        "pricing_table_version": PRICING_TABLE_VERSION,
        "cost_known": cost_known,
    }


def _repo_root() -> Path:
    cwd = Path.cwd()
    output = _git_output(cwd, ["git", "rev-parse", "--show-toplevel"])
    return Path(output) if output else cwd


def _git_output(cwd: Path, args: list[str]) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _relevant_file_hashes(repo_root: Path) -> dict[str, str]:
    paths: set[Path] = set()
    for pattern in RELEVANT_FILE_GLOBS:
        paths.update(path for path in repo_root.glob(pattern) if path.is_file())
    return {
        path.relative_to(repo_root).as_posix(): sha256_file(path)
        for path in sorted(paths)
        if not _is_ignored_relevant_path(path.relative_to(repo_root))
    }


def _is_ignored_relevant_path(relative_path: Path) -> bool:
    parts = set(relative_path.parts)
    return bool(parts & {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv"})


def _source_hash(repo_root: Path, relative_path: str) -> str | None:
    path = repo_root / relative_path
    if not path.exists():
        return None
    return sha256_file(path)


def _package_version(repo_root: Path) -> str:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.exists():
        return "unknown"
    data = tomllib.loads(pyproject.read_text())
    return str(data.get("project", {}).get("version", "unknown"))
