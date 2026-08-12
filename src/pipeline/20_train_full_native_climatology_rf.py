from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.base import clone
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import balanced_accuracy_score, mean_absolute_error, mean_squared_error, r2_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline


MODULE = Path(__file__).resolve().parents[1]
SOURCE_MODEL = MODULE / "outputs/historical_paired_model_statistics/models/HISTORICAL_PAIRED_RF_MODELS.joblib"
OUT = MODULE / "outputs/full_native_climatology_model"
TABLES = OUT / "tables"
MODELS = OUT / "models"
MAX_CLIMATE_FEATURES = 64
SEED = 20260806


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, MODULE / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def feature_importance(bundle: dict) -> pd.DataFrame:
    features = list(bundle["features"])
    pipeline = bundle["occurrence"]
    values = pipeline.named_steps["rf"].feature_importances_
    result = np.asarray(values[:len(features)], dtype=float)
    indicator = pipeline.named_steps["imputer"].indicator_
    if indicator is not None:
        for extra_index, original_index in enumerate(indicator.features_):
            result[int(original_index)] += values[len(features) + extra_index]
    return pd.DataFrame({"feature": features, "importance": result}).sort_values("importance", ascending=False)


def model(seed: int) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("rf", RandomForestRegressor(n_estimators=700, max_depth=14, min_samples_leaf=3,
                                     max_features=0.65, n_jobs=-1, random_state=seed)),
    ])


def cross_validate(frame: pd.DataFrame, features: list[str], target: str, seed: int) -> tuple[np.ndarray, Pipeline]:
    valid = frame[target].notna().to_numpy()
    work = frame.loc[valid].reset_index(drop=True)
    coordinates = work[["longitude", "latitude"]].to_numpy()
    groups = KMeans(n_clusters=5, random_state=SEED, n_init=20).fit_predict(coordinates)
    prediction = np.full(len(work), np.nan, dtype=float)
    estimator = model(seed)
    for train, test in GroupKFold(n_splits=5).split(work[features], work[target], groups):
        fitted = clone(estimator).fit(work.iloc[train][features], work.iloc[train][target])
        prediction[test] = fitted.predict(work.iloc[test][features])
    final = clone(estimator).fit(work[features], work[target])
    full_prediction = np.full(len(frame), np.nan, dtype=float)
    full_prediction[np.flatnonzero(valid)] = prediction
    return full_prediction, final


def metric_row(frame: pd.DataFrame, target: str, prediction: str, endpoint: str) -> dict:
    valid = frame[[target, prediction]].notna().all(axis=1)
    y = frame.loc[valid, target].to_numpy(float)
    p = frame.loc[valid, prediction].to_numpy(float)
    row = {
        "endpoint": endpoint, "n_stations": len(y), "r2": r2_score(y, p),
        "rmse": mean_squared_error(y, p) ** 0.5, "mae": mean_absolute_error(y, p),
        "bias": float(np.mean(p - y)), "pearson_r": pearsonr(y, p).statistic,
    }
    if target == "observed_annual_frost_probability":
        binary = (y >= 0.5).astype(int)
        clipped = np.clip(p, 0, 1)
        if np.unique(binary).size == 2:
            row["roc_auc_majority_endpoint"] = roc_auc_score(binary, clipped)
            row["balanced_accuracy_at_0_5"] = balanced_accuracy_score(binary, clipped >= 0.5)
        row["brier_against_observed_frequency"] = float(np.mean((clipped - y) ** 2))
    return row


def main() -> int:
    TABLES.mkdir(parents=True, exist_ok=True)
    MODELS.mkdir(parents=True, exist_ok=True)
    core = load_script("five_state_core_climatology", "08_run_five_state_50000_smoke.py")
    validation = load_script("paired_validation_climatology", "11_validate_historical_paired_models.py")
    table, _, _ = validation.build_table(core)
    bundle = joblib.load(SOURCE_MODEL)
    importance = feature_importance(bundle)
    terrain = list(core.TERRAIN_FEATURES)
    climate_candidates = [name for name in bundle["features"] if name.startswith("era5__") or name.startswith("modis_")]
    climate = importance.loc[importance.feature.isin(climate_candidates), "feature"].head(MAX_CLIMATE_FEATURES).tolist()
    features = ["latitude", "longitude"] + terrain + climate
    aggregation = {name: "median" for name in features}
    aggregation.update({"frost_any": "mean", "frost_days": "mean", "observed_season_tmin_c": lambda x: x.quantile(0.25), "year": "count"})
    stations = table.groupby(["state", "source", "station_id"], as_index=False).agg(aggregation).rename(columns={
        "frost_any": "observed_annual_frost_probability", "frost_days": "observed_expected_frost_days",
        "observed_season_tmin_c": "observed_season_tmin_p25_c", "year": "n_station_years",
    })
    targets = [
        ("observed_annual_frost_probability", "oof_annual_frost_probability", "Annual frost probability"),
        ("observed_expected_frost_days", "oof_expected_frost_days", "Expected frost days"),
        ("observed_season_tmin_p25_c", "oof_season_tmin_p25_c", "Seasonal minimum temperature P25"),
    ]
    fitted_models, metrics = {}, []
    for index, (target, prediction, endpoint) in enumerate(targets):
        stations[prediction], fitted_models[target] = cross_validate(stations, features, target, SEED + index)
        metrics.append(metric_row(stations, target, prediction, endpoint))
    metrics_frame = pd.DataFrame(metrics)
    stations.to_parquet(TABLES / "FULL_NATIVE_STATION_CLIMATOLOGY_MODELING_TABLE.parquet", index=False)
    stations.to_csv(TABLES / "FULL_NATIVE_STATION_CLIMATOLOGY_MODELING_TABLE.csv", index=False)
    metrics_frame.to_csv(TABLES / "FULL_NATIVE_CLIMATOLOGY_SPATIAL_CV_STATISTICS.csv", index=False)
    registry = importance.loc[importance.feature.isin(features)].copy()
    registry["block"] = np.where(registry.feature.isin(terrain), "Terrain/HAND",
                                  np.where(registry.feature.str.startswith("era5__"), "ERA5-Land", "MODIS"))
    registry.to_csv(TABLES / "FULL_NATIVE_SELECTED_FEATURES.csv", index=False)
    output_bundle = {
        "models": fitted_models, "features": features, "terrain_features": terrain,
        "climate_features": climate, "station_climatology": stations,
        "metrics": metrics, "selection_source": str(SOURCE_MODEL),
    }
    joblib.dump(output_bundle, MODELS / "FULL_NATIVE_CLIMATOLOGY_RF_MODELS.joblib")
    status = {
        "status": "FULL_NATIVE_CLIMATOLOGY_RF_MODEL_OK", "completed_at": datetime.now(timezone.utc).isoformat(),
        "stations": len(stations), "station_years": int(stations.n_station_years.sum()),
        "features": len(features), "terrain_hand_features": len(terrain), "selected_climate_features": len(climate),
        "spatial_validation": "five geographic K-means blocks; each station held out by block", "metrics": metrics,
    }
    (OUT / "FULL_NATIVE_CLIMATOLOGY_RF_MODEL_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (OUT / "FULL_NATIVE_CLIMATOLOGY_RF_MODEL_OK").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
