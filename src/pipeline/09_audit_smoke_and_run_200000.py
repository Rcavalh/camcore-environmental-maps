from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


MODULE = Path(__file__).resolve().parents[1]
SMOKE = MODULE / "outputs/five_state_50000_smoke"
FULL = MODULE / "outputs/five_state_200000_complete"
SCRIPT = MODULE / "scripts/08_run_five_state_50000_smoke.py"
PREFIX = "FIVE_STATE_RF_50000_SMOKE"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def audit_smoke() -> dict:
    marker = SMOKE / f"{PREFIX}_OK"
    status_path = SMOKE / f"{PREFIX}_STATUS.json"
    metrics_path = SMOKE / f"tables/{PREFIX}_VALIDATION_METRICS.csv"
    registry_path = SMOKE / f"tables/{PREFIX}_FEATURE_REGISTRY.csv"
    predictions_path = SMOKE / f"tables/{PREFIX}_PREDICTIONS.parquet"
    gpkg_path = SMOKE / f"{PREFIX}_PREDICTIONS.gpkg"
    required = [marker, status_path, metrics_path, registry_path, predictions_path, gpkg_path]
    for path in required:
        require(path.exists() and path.stat().st_size > 0, f"Missing smoke artifact: {path}")

    status = json.loads(status_path.read_text(encoding="utf-8"))
    metrics = pd.read_csv(metrics_path)
    registry = pd.read_csv(registry_path)
    predictions = pd.read_parquet(
        predictions_path,
        columns=[
            "state",
            "annual_frost_probability_mean",
            "annual_frost_probability_p75",
            "expected_frost_days_mean",
            "event_minimum_temperature_mean_c",
        ],
    )

    require(status.get("status") == f"{PREFIX}_OK", "Smoke marker and status disagree")
    require(len(predictions) == 50_000, "Smoke prediction table is not exactly 50,000 points")
    expected_states = {state: 10_000 for state in ["MS", "PR", "RS", "SC", "SP"]}
    observed_states = predictions.groupby("state").size().astype(int).to_dict()
    require(observed_states == expected_states, f"Unexpected state allocation: {observed_states}")
    for column in [
        "annual_frost_probability_mean",
        "annual_frost_probability_p75",
        "expected_frost_days_mean",
        "event_minimum_temperature_mean_c",
    ]:
        require(predictions[column].notna().all(), f"Non-finite output in {column}")
    require(predictions.annual_frost_probability_mean.between(0, 1).all(), "Mean probability outside [0,1]")
    require(predictions.annual_frost_probability_p75.between(0, 1).all(), "P75 probability outside [0,1]")
    require(set(metrics.endpoint) == {"frost_any", "frost_days", "observed_season_tmin_c"}, "Three-endpoint contract incomplete")
    occurrence = metrics.loc[metrics.endpoint.eq("frost_any")].iloc[0]
    require(float(occurrence.roc_auc) > 0.5, "Occurrence model failed discrimination check")
    require(float(occurrence.balanced_accuracy) > 0.5, "Occurrence model failed balanced-accuracy check")

    block_counts = registry.groupby("block").size().astype(int).to_dict()
    require(block_counts.get("ERA5-Land") == 939, f"Unexpected ERA5 feature count: {block_counts}")
    require(block_counts.get("MODIS thermal") == 9, f"Unexpected MODIS feature count: {block_counts}")
    require(block_counts.get("Terrain/HAND") == 18, f"Unexpected terrain/HAND feature count: {block_counts}")

    return {
        "status": "SMOKE_50000_AUDIT_OK",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "points": len(predictions),
        "points_per_state": observed_states,
        "training_station_years": int(status["training_station_years"]),
        "training_stations": int(status["training_stations"]),
        "model_features": int(status["features"]),
        "feature_blocks": block_counts,
        "validation": {
            "roc_auc": float(occurrence.roc_auc),
            "pr_auc": float(occurrence.pr_auc),
            "balanced_accuracy": float(occurrence.balanced_accuracy),
            "brier": float(occurrence.brier),
        },
        "checks": {
            "all_required_artifacts_present": True,
            "all_three_endpoints_present": True,
            "all_predictions_finite": True,
            "probabilities_within_unit_interval": True,
            "exact_equal_state_allocation": True,
            "full_agreed_feature_contract_present": True,
        },
        "feature_contract_note": (
            "Complete agreed occurrence-model contract: all 939 usable ERA5-Land summaries, "
            "all 9 QC-filtered MODIS thermal summaries, all 16 ANADEM/HAND physiographic variables, "
            "latitude, longitude and year. NDVI remains excluded by study design."
        ),
    }


def main() -> int:
    FULL.mkdir(parents=True, exist_ok=True)
    audit = audit_smoke()
    audit_path = FULL / "PRE_200000_SMOKE_AUDIT.json"
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2), flush=True)
    environment = os.environ.copy()
    environment["FROST_TOTAL_POINTS"] = "200000"
    completed = subprocess.run([sys.executable, str(SCRIPT)], env=environment, check=False)
    if completed.returncode:
        raise RuntimeError(f"200,000-point complete run failed with exit code {completed.returncode}")
    print("FIVE_STATE_RF_200000_COMPLETE_AND_PREAUDIT_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
