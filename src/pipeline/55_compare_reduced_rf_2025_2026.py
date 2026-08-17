from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier, RandomForestRegressor
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


MODULE = Path(__file__).resolve().parents[1]
DB = MODULE / "database"
OUT = MODULE / "outputs" / "reduced_rf_2026_provisional_comparison"
TABLES = OUT / "tables"
TARGETS = (
    MODULE
    / "outputs"
    / "inmet_2026_provisional_extension"
    / "tables"
    / "INMET_STATION_YEAR_ENDPOINTS_2000_2026_PROVISIONAL.parquet"
)
TERRAIN = DB / "STATION_PHYSIOGRAPHIC_COVARIATES_ANADEM_30M.parquet"
MODIS_2025 = DB / "MODIS_ALL_MODEL_READY_STATION_YEAR_2000_2025.parquet"
MODIS_2026 = DB / "MODIS_ALL_MODEL_READY_STATION_YEAR_2000_2026_PROVISIONAL.parquet"
REFERENCE = (
    MODULE
    / "outputs"
    / "balanced_rf_reduced_validation"
    / "tables"
    / "REDUCED_RF_ALL_ENDPOINTS_VALIDATION_METRICS.csv"
)
SEED = 20260807
N_ERA5 = 64
N_MODIS = 32


def load_script(name: str, filename: str):
    path = MODULE / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_table(core, max_year: int, modis_path: Path) -> tuple[pd.DataFrame, list[str]]:
    era5 = core.load_era5_wide()
    era5 = era5.loc[
        era5.source.eq("INMET") & era5.year.between(2000, max_year)
    ].copy()
    targets = pd.read_parquet(TARGETS)
    targets = targets.loc[targets.year.between(2000, max_year)].copy()
    terrain = pd.read_parquet(TERRAIN)
    terrain = terrain.loc[terrain.source.eq("INMET")].copy()
    modis = pd.read_parquet(modis_path)
    modis = modis.loc[modis.year.between(2000, max_year)].copy()

    identifiers = ["state", "source", "station_id", "year"]
    table = era5.merge(
        targets,
        on=["state", "station_id", "year"],
        how="inner",
        validate="one_to_one",
        suffixes=("", "_target"),
    )
    table = table.merge(
        terrain.drop(columns=["latitude", "longitude"]),
        on=["state", "source", "station_id"],
        how="left",
        validate="many_to_one",
    )
    table = table.merge(
        modis.drop(columns=["latitude", "longitude"]),
        on=identifiers,
        how="left",
        validate="one_to_one",
    )
    candidates = (
        ["latitude", "longitude", "year"]
        + list(core.TERRAIN_FEATURES)
        + [column for column in table if column.startswith("era5__")]
        + [column for column in table if column.startswith("modis_")]
    )
    candidates = list(dict.fromkeys(column for column in candidates if column in table))
    return table.reset_index(drop=True), candidates


def select_features(
    train: pd.DataFrame,
    y: np.ndarray,
    candidates: list[str],
    terrain: list[str],
    fold_seed: int,
) -> list[str]:
    usable = [column for column in candidates if train[column].notna().any()]
    imputer = SimpleImputer(strategy="median")
    x = imputer.fit_transform(train[usable])
    selector = ExtraTreesClassifier(
        n_estimators=240,
        min_samples_leaf=4,
        max_features="sqrt",
        class_weight="balanced",
        n_jobs=-1,
        random_state=fold_seed,
    ).fit(x, y)
    importance = pd.Series(selector.feature_importances_, index=usable)
    era5 = importance.loc[[c for c in usable if c.startswith("era5__")]].nlargest(N_ERA5).index.tolist()
    modis = importance.loc[[c for c in usable if c.startswith("modis_")]].nlargest(N_MODIS).index.tolist()
    static = [c for c in ["latitude", "longitude", "year"] + terrain if c in usable]
    return list(dict.fromkeys(static + era5 + modis))


def class_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    p = np.clip(np.asarray(p, dtype=float), 0, 1)
    predicted = (p >= 0.5).astype(np.uint8)
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    n = len(y)
    return {
        "endpoint": "frost_any",
        "n": n,
        "roc_auc": roc_auc_score(y, p),
        "pr_auc": average_precision_score(y, p),
        "brier_score": brier_score_loss(y, p),
        "balanced_accuracy": balanced_accuracy_score(y, predicted),
        "sensitivity": recall_score(y, predicted, zero_division=0),
        "specificity": tn / max(tn + fp, 1),
        "precision": precision_score(y, predicted, zero_division=0),
        "f1": f1_score(y, predicted, zero_division=0),
        "tn_percent": 100 * tn / n,
        "tp_percent": 100 * tp / n,
        "fn_percent": 100 * fn / n,
        "fp_percent": 100 * fp / n,
    }


def regression_metrics(endpoint: str, y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "endpoint": endpoint,
        "n": len(y),
        "r2": r2_score(y, p),
        "rmse": mean_squared_error(y, p) ** 0.5,
        "mae": mean_absolute_error(y, p),
        "bias": float(np.mean(p - y)),
    }


def station_fold_map(table: pd.DataFrame) -> dict[str, int]:
    groups = table.state.astype(str) + "__" + table.station_id.astype(str)
    mapping: dict[str, int] = {}
    for fold, (_, test) in enumerate(
        GroupKFold(n_splits=5).split(table, table.frost_any.astype(int), groups), 1
    ):
        for group in groups.iloc[test].unique():
            mapping[group] = fold
    return mapping


def validate_scenario(
    name: str,
    table: pd.DataFrame,
    candidates: list[str],
    terrain: list[str],
    fold_map: dict[str, int] | None,
) -> tuple[list[dict], pd.DataFrame, list[dict]]:
    work = table.loc[table.frost_any.notna()].reset_index(drop=True)
    groups = work.state.astype(str) + "__" + work.station_id.astype(str)
    if fold_map is None:
        fold_map = station_fold_map(work)
    work["outer_fold"] = groups.map(fold_map)
    if work.outer_fold.isna().any():
        raise RuntimeError(f"Scenario {name} contains stations without a fold assignment")
    work["outer_fold"] = work.outer_fold.astype(int)
    predictions = {
        "frost_any": np.full(len(work), np.nan),
        "frost_days": np.full(len(work), np.nan),
        "observed_season_tmin_c": np.full(len(work), np.nan),
    }
    selections: list[dict] = []

    for fold in range(1, 6):
        train = np.flatnonzero(work.outer_fold.ne(fold).to_numpy())
        test = np.flatnonzero(work.outer_fold.eq(fold).to_numpy())
        y_class = work.iloc[train].frost_any.astype(int).to_numpy()
        features = select_features(
            work.iloc[train], y_class, candidates, terrain, SEED + fold
        )
        imputer = SimpleImputer(strategy="median")
        x_train = imputer.fit_transform(work.iloc[train][features]).astype(np.float32)
        x_test = imputer.transform(work.iloc[test][features]).astype(np.float32)
        classifier = RandomForestClassifier(
            n_estimators=900,
            max_depth=18,
            min_samples_leaf=5,
            max_features="sqrt",
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=SEED + fold,
        ).fit(x_train, y_class)
        predictions["frost_any"][test] = classifier.predict_proba(x_test)[:, 1]
        for offset, (endpoint, criterion) in enumerate(
            [("frost_days", "poisson"), ("observed_season_tmin_c", "squared_error")], 1
        ):
            y_train = work.iloc[train][endpoint].to_numpy(dtype=float)
            regressor = RandomForestRegressor(
                n_estimators=700,
                criterion=criterion,
                min_samples_leaf=4,
                max_features=0.45,
                n_jobs=-1,
                random_state=SEED + offset,
            ).fit(x_train, y_train)
            predictions[endpoint][test] = regressor.predict(x_test)
        for rank, feature in enumerate(features, 1):
            selections.append(
                {
                    "scenario": name,
                    "outer_fold": fold,
                    "rank": rank,
                    "feature": feature,
                    "block": "ERA5-Land" if feature.startswith("era5__") else "MODIS" if feature.startswith("modis_") else "Terrain/HAND/space",
                }
            )
        print(f"REDUCED_RF_2026_COMPARISON_FOLD_OK={name}/{fold} n={len(test)} features={len(features)}", flush=True)

    for endpoint, values in predictions.items():
        if not np.isfinite(values).all():
            raise RuntimeError(f"Incomplete predictions for {name}/{endpoint}")
    metrics = [class_metrics(work.frost_any.astype(int).to_numpy(), predictions["frost_any"])]
    metrics.append(regression_metrics("frost_days", work.frost_days.to_numpy(float), predictions["frost_days"]))
    metrics.append(regression_metrics("observed_season_tmin_c", work.observed_season_tmin_c.to_numpy(float), predictions["observed_season_tmin_c"]))
    for row in metrics:
        row["scenario"] = name
        row["years"] = f"{int(work.year.min())}-{int(work.year.max())}"
        row["stations"] = int(groups.nunique())
        row["provisional_2026_rows"] = int(work.year.eq(2026).sum())
    prediction_table = work[["state", "station_id", "year", "outer_fold", "frost_any", "frost_days", "observed_season_tmin_c"]].copy()
    prediction_table["scenario"] = name
    prediction_table["oof_frost_probability"] = predictions["frost_any"]
    prediction_table["oof_frost_days"] = predictions["frost_days"]
    prediction_table["oof_seasonal_tmin_c"] = predictions["observed_season_tmin_c"]
    return metrics, prediction_table, selections


def main() -> int:
    TABLES.mkdir(parents=True, exist_ok=True)
    core = load_script("reduced_2026_core", "08_run_five_state_50000_smoke.py")
    baseline, baseline_candidates = build_table(core, 2025, MODIS_2025)
    updated, updated_candidates = build_table(core, 2026, MODIS_2026)
    common = [c for c in baseline_candidates if c in updated_candidates and baseline[c].notna().any() and updated[c].notna().any()]
    baseline_groups = baseline.state.astype(str) + "__" + baseline.station_id.astype(str)
    fold_map = station_fold_map(baseline)
    updated_groups = updated.state.astype(str) + "__" + updated.station_id.astype(str)
    matched = updated.loc[updated_groups.isin(set(baseline_groups))].reset_index(drop=True)

    all_metrics: list[dict] = []
    all_predictions = []
    all_selections = []
    scenarios = [
        ("baseline_2000_2025_rerun", baseline, fold_map),
        ("updated_2000_2026_matched_stations_provisional", matched, fold_map),
        ("updated_2000_2026_all_available_provisional", updated, None),
    ]
    for name, table, mapping in scenarios:
        metrics, predictions, selections = validate_scenario(
            name, table, common, list(core.TERRAIN_FEATURES), mapping
        )
        all_metrics.extend(metrics)
        all_predictions.append(predictions)
        all_selections.extend(selections)

    metrics_frame = pd.DataFrame(all_metrics)
    metrics_frame.to_csv(TABLES / "REDUCED_RF_2000_2025_VS_2000_2026_METRICS.csv", index=False)
    pd.concat(all_predictions, ignore_index=True).to_parquet(
        TABLES / "REDUCED_RF_2000_2025_VS_2000_2026_OOF_PREDICTIONS.parquet", index=False
    )
    pd.DataFrame(all_selections).to_csv(
        TABLES / "REDUCED_RF_2000_2025_VS_2000_2026_FEATURE_SELECTION.csv", index=False
    )

    base = metrics_frame.loc[metrics_frame.scenario.eq("baseline_2000_2025_rerun")].set_index("endpoint")
    revised = metrics_frame.loc[metrics_frame.scenario.eq("updated_2000_2026_matched_stations_provisional")].set_index("endpoint")
    delta_rows = []
    for endpoint in base.index:
        for metric in ["roc_auc", "pr_auc", "brier_score", "balanced_accuracy", "sensitivity", "specificity", "precision", "f1", "r2", "rmse", "mae", "bias"]:
            if metric in base and pd.notna(base.loc[endpoint, metric]) and pd.notna(revised.loc[endpoint, metric]):
                delta_rows.append({
                    "endpoint": endpoint,
                    "metric": metric,
                    "baseline_2000_2025": float(base.loc[endpoint, metric]),
                    "updated_2000_2026_matched": float(revised.loc[endpoint, metric]),
                    "delta_updated_minus_baseline": float(revised.loc[endpoint, metric] - base.loc[endpoint, metric]),
                })
    delta = pd.DataFrame(delta_rows)
    delta.to_csv(TABLES / "REDUCED_RF_2026_PROVISIONAL_METRIC_DELTAS.csv", index=False)

    reference = pd.read_csv(REFERENCE)
    reference.to_csv(TABLES / "PUBLISHED_2000_2025_REDUCED_RF_REFERENCE.csv", index=False)
    status = {
        "status": "REDUCED_RF_2026_PROVISIONAL_COMPARISON_OK",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "warning": "2026 is provisional because observations and environmental covariates do not yet cover the complete 15 May-15 August season",
        "comparison_design": "Identical station-held-out folds for the baseline and matched-station update; block-balanced feature selection repeated within every outer training fold",
        "common_candidate_features": len(common),
        "scenarios": metrics_frame[["scenario", "years", "n", "stations", "provisional_2026_rows"]].drop_duplicates().to_dict(orient="records"),
        "metrics_file": str(TABLES / "REDUCED_RF_2000_2025_VS_2000_2026_METRICS.csv"),
        "delta_file": str(TABLES / "REDUCED_RF_2026_PROVISIONAL_METRIC_DELTAS.csv"),
    }
    (OUT / "REDUCED_RF_2026_PROVISIONAL_COMPARISON_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (OUT / "REDUCED_RF_2026_PROVISIONAL_COMPARISON_OK").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
