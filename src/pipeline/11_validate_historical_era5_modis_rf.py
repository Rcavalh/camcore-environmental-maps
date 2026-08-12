from __future__ import annotations

import importlib.util
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline


MODULE = Path(__file__).resolve().parents[1]
DB = MODULE / "database"
OUT = MODULE / "outputs/historical_paired_era5_modis_validation"
TABLE = OUT / "tables"
MODEL = OUT / "models"
ERA5_INDEX = DB / "ERA5_STATION_YEAR_PARTITION_INDEX.csv"
MODIS_MARKER = DB / "HISTORICAL_MODIS_STATION_YEAR_OK.json"
MODIS_PARTITIONS = DB / "modis_station_year_may15_aug15"
TERRAIN = DB / "STATION_PHYSIOGRAPHIC_COVARIATES_ANADEM_30M.parquet"
SMOKE_SCRIPT = MODULE / "scripts/08_run_five_state_50000_smoke.py"
OLD_STATUS = MODULE / "outputs/five_state_50000_smoke/FIVE_STATE_RF_50000_SMOKE_STATUS.json"
SEED = 20260806
TERRAIN_FEATURES = [
    "elevation", "slope_deg", "eastness", "northness", "TPI_native",
    "TRI_native", "roughness_native", "plan_curvature", "profile_curvature",
    "surface_curvature_laplacian", "cold_air_pooling_2000m",
    "elevation_above_local_min_2000m", "elevation_below_local_max_2000m",
    "local_relief_2000m", "local_sd_2000m", "HAND_selected_m",
]
MODIS_FEATURES = [
    "modis_lst_day_mean_c", "modis_lst_day_min_c", "modis_lst_day_p05_c",
    "modis_lst_day_valid_fraction", "modis_lst_night_mean_c",
    "modis_lst_night_min_c", "modis_lst_night_p05_c",
    "modis_lst_night_valid_fraction", "modis_diurnal_range_mean_c",
]


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("five_state_model_helpers", SMOKE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {SMOKE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classifier() -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("rf", RandomForestClassifier(
            n_estimators=600,
            max_depth=18,
            min_samples_leaf=5,
            max_features="sqrt",
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=SEED,
        )),
    ])


def regressor(seed: int, poisson: bool = False) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("rf", RandomForestRegressor(
            n_estimators=600,
            criterion="poisson" if poisson else "squared_error",
            min_samples_leaf=4,
            max_features=0.45,
            n_jobs=-1,
            random_state=seed,
        )),
    ])


def oof_predictions(model, frame: pd.DataFrame, features: list[str], target: str, classifier_mode: bool) -> tuple[np.ndarray, object]:
    y = frame[target].to_numpy()
    groups = frame.station_id.astype(str).to_numpy()
    prediction = np.full(len(frame), np.nan, dtype=float)
    folds = GroupKFold(n_splits=5)
    for train, test in folds.split(frame[features], y, groups):
        fitted = clone(model).fit(frame.iloc[train][features], y[train])
        prediction[test] = fitted.predict_proba(frame.iloc[test][features])[:, 1] if classifier_mode else fitted.predict(frame.iloc[test][features])
    final = clone(model).fit(frame[features], y)
    return prediction, final


def classification_metrics(y: np.ndarray, probability: np.ndarray, cohort: str, n_stations: int, n_features: int) -> dict:
    predicted = (probability >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    n = len(y)
    return {
        "cohort": cohort,
        "model": "Random Forest classifier",
        "endpoint": "INMET possible frost occurrence",
        "n_station_years": n,
        "n_stations": n_stations,
        "n_features": n_features,
        "roc_auc": roc_auc_score(y, probability),
        "pr_auc": average_precision_score(y, probability),
        "balanced_accuracy": balanced_accuracy_score(y, predicted),
        "sensitivity": recall_score(y, predicted, zero_division=0),
        "specificity": tn / (tn + fp),
        "precision": precision_score(y, predicted, zero_division=0),
        "f1": f1_score(y, predicted, zero_division=0),
        "brier_score": brier_score_loss(y, probability),
        "tn_pct": 100 * tn / n,
        "tp_pct": 100 * tp / n,
        "fn_pct": 100 * fn / n,
        "fp_pct": 100 * fp / n,
        "tn": int(tn),
        "tp": int(tp),
        "fn": int(fn),
        "fp": int(fp),
    }


def regression_metrics(y: np.ndarray, prediction: np.ndarray, cohort: str, endpoint: str, n_stations: int, n_features: int) -> dict:
    pearson = pearsonr(y, prediction).statistic if len(np.unique(y)) > 1 else np.nan
    spearman = spearmanr(y, prediction).statistic if len(np.unique(y)) > 1 else np.nan
    return {
        "cohort": cohort,
        "model": "Random Forest regressor",
        "endpoint": endpoint,
        "n_station_years": len(y),
        "n_stations": n_stations,
        "n_features": n_features,
        "r2": r2_score(y, prediction),
        "rmse": math.sqrt(mean_squared_error(y, prediction)),
        "mae": mean_absolute_error(y, prediction),
        "bias": float(np.mean(prediction - y)),
        "pearson_r": pearson,
        "spearman_rho": spearman,
    }


def load_modis() -> pd.DataFrame:
    files = sorted(MODIS_PARTITIONS.glob("state_group=*/year=*/features.parquet"))
    if len(files) != 104:
        raise RuntimeError(f"Expected 104 MODIS state-group/year partitions, found {len(files)}")
    return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)


def main() -> int:
    if not MODIS_MARKER.exists():
        raise RuntimeError("Historical MODIS station-year extraction is not complete")
    TABLE.mkdir(parents=True, exist_ok=True)
    MODEL.mkdir(parents=True, exist_ok=True)
    helper = load_smoke_module()
    era5 = helper.load_era5_wide()
    era5 = era5.loc[era5.source.eq("INMET") & era5.year.between(2000, 2025)].copy()
    targets = helper.load_targets()
    terrain = pd.read_parquet(TERRAIN)
    terrain = terrain.loc[terrain.source.eq("INMET")]
    terrain = terrain[["state", "source", "station_id"] + TERRAIN_FEATURES].drop_duplicates(["source", "station_id"])
    modis = load_modis()
    modis = modis.drop(columns=["latitude", "longitude"], errors="ignore")
    training = era5.merge(targets, on=["state", "station_id", "year"], how="inner", validate="one_to_one")
    training = training.merge(terrain, on=["state", "source", "station_id"], how="left", validate="many_to_one")
    training = training.merge(modis, on=["state", "source", "station_id", "year"], how="left", validate="one_to_one")
    era5_features = [column for column in era5.columns if column.startswith("era5__")]
    candidate_features = ["latitude", "longitude", "year"] + TERRAIN_FEATURES + era5_features + MODIS_FEATURES
    features = [column for column in candidate_features if training[column].notna().any()]
    era5_used = [column for column in era5_features if column in features]
    paired = training.modis_lst_day_n_valid_days.fillna(0).gt(0) & training.modis_lst_night_n_valid_days.fillna(0).gt(0)
    training["modis_temporally_paired"] = paired
    training.to_parquet(TABLE / "HISTORICAL_ERA5_MODIS_STATION_YEAR_MODELING_TABLE.parquet", index=False)
    training.head(1000).to_csv(TABLE / "HISTORICAL_ERA5_MODIS_STATION_YEAR_MODELING_TABLE_PREVIEW.csv", index=False)

    cohorts = {
        "all_years_with_missingness_indicators": training,
        "strict_era5_modis_temporal_pairing": training.loc[paired].copy(),
    }
    classification_rows = []
    regression_rows = []
    bundles = {}
    oof_rows = []
    for cohort_name, cohort in cohorts.items():
        if cohort.station_id.nunique() < 10 or cohort.frost_any.nunique() < 2:
            raise RuntimeError(f"Cohort {cohort_name} is insufficient for grouped validation")
        n_stations = int(cohort.station_id.nunique())
        class_prediction, class_model = oof_predictions(classifier(), cohort, features, "frost_any", True)
        classification_rows.append(classification_metrics(cohort.frost_any.to_numpy(), class_prediction, cohort_name, n_stations, len(features)))
        days_prediction, days_model = oof_predictions(regressor(SEED + 1, poisson=True), cohort, features, "frost_days", False)
        regression_rows.append(regression_metrics(cohort.frost_days.to_numpy(), days_prediction, cohort_name, "INMET frost-day count", n_stations, len(features)))
        tmin_prediction, tmin_model = oof_predictions(regressor(SEED + 2), cohort, features, "observed_season_tmin_c", False)
        regression_rows.append(regression_metrics(cohort.observed_season_tmin_c.to_numpy(), tmin_prediction, cohort_name, "Observed seasonal minimum temperature (°C)", n_stations, len(features)))
        oof = cohort[["state", "station_id", "year", "frost_any", "frost_days", "observed_season_tmin_c"]].copy()
        oof["cohort"] = cohort_name
        oof["frost_probability_oof"] = class_prediction
        oof["frost_days_oof"] = days_prediction
        oof["season_tmin_oof_c"] = tmin_prediction
        oof_rows.append(oof)
        bundles[cohort_name] = {
            "classifier": class_model,
            "frost_days_regressor": days_model,
            "season_tmin_regressor": tmin_model,
        }

    classification = pd.DataFrame(classification_rows)
    regression = pd.DataFrame(regression_rows)
    classification.to_csv(TABLE / "HISTORICAL_ERA5_MODIS_RF_CLASSIFICATION_METRICS.csv", index=False)
    regression.to_csv(TABLE / "HISTORICAL_ERA5_MODIS_RF_REGRESSION_METRICS.csv", index=False)
    pd.concat(oof_rows, ignore_index=True).to_parquet(TABLE / "HISTORICAL_ERA5_MODIS_RF_OOF_PREDICTIONS.parquet", index=False)
    coverage = training.groupby(["state", "year"], as_index=False).agg(
        station_years=("station_id", "size"),
        stations_with_paired_modis=("modis_temporally_paired", "sum"),
        mean_modis_day_valid_fraction=("modis_lst_day_valid_fraction", "mean"),
        mean_modis_night_valid_fraction=("modis_lst_night_valid_fraction", "mean"),
        frost_prevalence=("frost_any", "mean"),
    )
    coverage.to_csv(TABLE / "HISTORICAL_ERA5_MODIS_TRAINING_COVERAGE_BY_STATE_YEAR.csv", index=False)
    registry = pd.DataFrame(
        ([{"feature": feature, "block": "Coordinates/time"} for feature in ["latitude", "longitude", "year"]]
         + [{"feature": feature, "block": "ANADEM terrain/HAND"} for feature in TERRAIN_FEATURES]
         + [{"feature": feature, "block": "ERA5-Land historical"} for feature in era5_used]
         + [{"feature": feature, "block": "MODIS historical thermal"} for feature in MODIS_FEATURES])
    )
    registry.to_csv(TABLE / "HISTORICAL_ERA5_MODIS_MODEL_FEATURE_REGISTRY.csv", index=False)
    joblib.dump({"models": bundles, "features": features, "classification_metrics": classification_rows, "regression_metrics": regression_rows}, MODEL / "HISTORICAL_ERA5_MODIS_RF_MODELS.joblib")

    comparison = []
    if OLD_STATUS.exists():
        old = json.loads(OLD_STATUS.read_text(encoding="utf-8"))["metrics"][0]
        comparison.append({"model_version": "old_static_MODIS_anchor_smoke", **{key: old.get(key) for key in ["roc_auc", "pr_auc", "balanced_accuracy", "brier"]}})
    for row in classification_rows:
        comparison.append({
            "model_version": row["cohort"],
            "roc_auc": row["roc_auc"],
            "pr_auc": row["pr_auc"],
            "balanced_accuracy": row["balanced_accuracy"],
            "brier": row["brier_score"],
        })
    pd.DataFrame(comparison).to_csv(TABLE / "STATIC_ANCHOR_VS_HISTORICAL_PAIRING_COMPARISON.csv", index=False)

    status = {
        "status": "HISTORICAL_ERA5_MODIS_RF_VALIDATION_OK",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "season": "15 May-15 August",
        "years": [2000, 2025],
        "training_station_years": int(len(training)),
        "training_stations": int(training.station_id.nunique()),
        "strict_paired_station_years": int(paired.sum()),
        "strict_paired_stations": int(training.loc[paired, "station_id"].nunique()),
        "features_used": len(features),
        "era5_features_used": len(era5_used),
        "modis_features_used": len(MODIS_FEATURES),
        "terrain_hand_features_used": len(TERRAIN_FEATURES),
        "classification_metrics": classification_rows,
        "regression_metrics": regression_rows,
        "map_generation_authorized": False,
        "next_gate": "Review historical-pairing metrics before creating the 200,000-point map",
    }
    (OUT / "HISTORICAL_ERA5_MODIS_RF_VALIDATION_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (OUT / "HISTORICAL_ERA5_MODIS_RF_VALIDATION_OK").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
