from __future__ import annotations

import gc
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GroupKFold


MODULE = Path(__file__).resolve().parents[1]
PROJECT = MODULE.parent.parent
OUT = MODULE / "outputs" / "hand15_rf_tabpfn_2000_2026"
TABLES = OUT / "tables"
MODELS = OUT / "models"
BASE_TERRAIN = MODULE / "database" / "STATION_PHYSIOGRAPHIC_COVARIATES_ANADEM_30M.parquet"
HAND15_ENV = "FROST_HAND15_RASTER"
DEFAULT_HAND15 = Path("data/covariates/HAND_flowpath_within_15000m_filled_zero.tif")
MODIS = MODULE / "database" / "MODIS_ALL_MODEL_READY_STATION_YEAR_2000_2026_PROVISIONAL.parquet"
SEED = 20260815
YEARS = tuple(range(2000, 2027))


def load_script(name: str, filename: str):
    path = MODULE / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def station_key(frame: pd.DataFrame) -> pd.Series:
    return frame.state.astype(str) + "__" + frame.station_id.astype(str)


def extract_hand15() -> tuple[Path, pd.DataFrame]:
    source = Path(os.environ.get(HAND15_ENV, str(DEFAULT_HAND15)))
    if not source.is_file() or source.stat().st_size == 0:
        raise FileNotFoundError(f"HAND 15-km raster is missing: {source}")
    terrain = pd.read_parquet(BASE_TERRAIN).copy()
    required = {"state", "source", "station_id", "latitude", "longitude", "HAND_selected_m"}
    missing = sorted(required - set(terrain.columns))
    if missing:
        raise RuntimeError(f"Base terrain table lacks columns: {missing}")

    with rasterio.open(source) as src:
        if src.crs is None:
            raise RuntimeError(f"HAND raster has no CRS: {source}")
        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        xx, yy = transformer.transform(
            terrain.longitude.to_numpy(float), terrain.latitude.to_numpy(float)
        )
        sampled = np.asarray(
            [value[0] for value in src.sample(zip(xx, yy), masked=True)], dtype=float
        )

    # The supplied filled-zero product uses zero for unresolved cells. Preserve
    # the established modeling contract by treating those cells as missing,
    # never as true valley-bottom HAND=0 observations.
    resolved = np.isfinite(sampled) & (sampled > 0)
    terrain["HAND_2000m_previous_m"] = terrain["HAND_selected_m"]
    terrain["HAND_selected_m"] = np.where(resolved, sampled, np.nan)
    terrain["HAND_status"] = np.where(resolved, "complete_15000m", "source_zero_filled_na_15000m")
    terrain["hand_source"] = str(source)
    terrain["hand_flowpath_radius_m"] = 15000

    output = TABLES / "STATION_PHYSIOGRAPHIC_COVARIATES_ANADEM30M_HAND15000M.parquet"
    terrain.to_parquet(output, index=False)
    terrain.to_csv(output.with_suffix(".csv"), index=False)

    audit = (
        terrain.assign(
            previous_resolved=terrain.HAND_2000m_previous_m.notna(),
            hand15_resolved=terrain.HAND_selected_m.notna(),
        )
        .groupby("state", dropna=False)
        .agg(
            stations=("station_id", "size"),
            hand2_resolved=("previous_resolved", "sum"),
            hand15_resolved=("hand15_resolved", "sum"),
        )
        .reset_index()
    )
    audit["recovered_by_15km"] = audit.hand15_resolved - audit.hand2_resolved
    audit.to_csv(TABLES / "HAND15_STATION_COVERAGE_AUDIT.csv", index=False)
    return output, terrain


def fold_assignments(work: pd.DataFrame) -> dict[str, int]:
    groups = station_key(work)
    mapping: dict[str, int] = {}
    splitter = GroupKFold(n_splits=5)
    for fold, (_, test) in enumerate(splitter.split(work, work.frost_any.astype(int), groups), 1):
        for group in groups.iloc[test].unique():
            mapping[group] = fold
    return mapping


def summarize(comparison, model: str, predictions: dict[str, np.ndarray], work: pd.DataFrame) -> list[dict]:
    rows = [comparison.class_metrics(work.frost_any.astype(int).to_numpy(), predictions["frost_any"])]
    rows.append(comparison.regression_metrics("frost_days", work.frost_days.to_numpy(float), predictions["frost_days"]))
    rows.append(
        comparison.regression_metrics(
            "observed_season_tmin_c",
            work.observed_season_tmin_c.to_numpy(float),
            predictions["observed_season_tmin_c"],
        )
    )
    for row in rows:
        row.update(
            model=model,
            years=f"{int(work.year.min())}-{int(work.year.max())}",
            climate_prediction_period="2000-2026",
            n_stations=int(station_key(work).nunique()),
            hand_radius_m=15000 if "HAND15" in model else 2000,
        )
    return rows


def evaluate_rf(
    comparison,
    work: pd.DataFrame,
    candidates: list[str],
    terrain_features: list[str],
    mapping: dict[str, int],
    label: str,
) -> tuple[dict[str, np.ndarray], dict[int, list[str]], list[dict], list[dict]]:
    groups = station_key(work)
    outer_fold = groups.map(mapping).astype(int).to_numpy()
    predictions = {
        "frost_any": np.full(len(work), np.nan),
        "frost_days": np.full(len(work), np.nan),
        "observed_season_tmin_c": np.full(len(work), np.nan),
    }
    features_by_fold: dict[int, list[str]] = {}
    fold_metrics: list[dict] = []
    selections: list[dict] = []

    for fold in range(1, 6):
        train = np.flatnonzero(outer_fold != fold)
        test = np.flatnonzero(outer_fold == fold)
        features = comparison.select_features(
            work.iloc[train], work.iloc[train].frost_any.astype(int).to_numpy(),
            candidates, terrain_features, SEED + fold,
        )
        if len(features) != 115:
            raise RuntimeError(f"{label}/fold {fold}: expected 115 features, found {len(features)}")
        features_by_fold[fold] = features
        imputer = SimpleImputer(strategy="median")
        x_train = imputer.fit_transform(work.iloc[train][features]).astype(np.float32)
        x_test = imputer.transform(work.iloc[test][features]).astype(np.float32)

        classifier = RandomForestClassifier(
            n_estimators=900, max_depth=18, min_samples_leaf=5,
            max_features="sqrt", class_weight="balanced_subsample",
            n_jobs=-1, random_state=SEED + fold,
        ).fit(x_train, work.iloc[train].frost_any.astype(int).to_numpy())
        predictions["frost_any"][test] = classifier.predict_proba(x_test)[:, 1]
        for offset, (endpoint, criterion) in enumerate(
            [("frost_days", "poisson"), ("observed_season_tmin_c", "squared_error")], 1
        ):
            regressor = RandomForestRegressor(
                n_estimators=700, criterion=criterion, min_samples_leaf=4,
                max_features=0.45, n_jobs=-1, random_state=SEED + fold + offset,
            ).fit(x_train, work.iloc[train][endpoint].to_numpy(float))
            predictions[endpoint][test] = regressor.predict(x_test)

        local = work.iloc[test].reset_index(drop=True)
        local_predictions = {key: value[test] for key, value in predictions.items()}
        for row in summarize(comparison, label, local_predictions, local):
            row["outer_fold"] = fold
            fold_metrics.append(row)
        for rank, feature in enumerate(features, 1):
            selections.append({"model": label, "outer_fold": fold, "rank": rank, "feature": feature})
        print(f"HAND15_RF_FOLD_OK={label}/{fold} train={len(train)} test={len(test)}", flush=True)
    return predictions, features_by_fold, fold_metrics, selections


def evaluate_tabpfn(
    comparison,
    work: pd.DataFrame,
    features_by_fold: dict[int, list[str]],
    mapping: dict[str, int],
) -> tuple[dict[str, np.ndarray], list[dict]]:
    import torch
    from tabpfn import TabPFNClassifier, TabPFNRegressor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    groups = station_key(work)
    outer_fold = groups.map(mapping).astype(int).to_numpy()
    predictions = {
        "frost_any": np.full(len(work), np.nan),
        "frost_days": np.full(len(work), np.nan),
        "observed_season_tmin_c": np.full(len(work), np.nan),
    }
    fold_metrics: list[dict] = []

    for fold in range(1, 6):
        train = np.flatnonzero(outer_fold != fold)
        test = np.flatnonzero(outer_fold == fold)
        features = features_by_fold[fold]
        imputer = SimpleImputer(strategy="median")
        x_train = imputer.fit_transform(work.iloc[train][features]).astype(np.float32)
        x_test = imputer.transform(work.iloc[test][features]).astype(np.float32)

        classifier = TabPFNClassifier(
            n_estimators=8, device=device, random_state=SEED + fold,
            fit_mode="fit_preprocessors", n_preprocessing_jobs=4,
            show_progress_bar=False,
        )
        classifier.fit(x_train, work.iloc[train].frost_any.astype(int).to_numpy())
        predictions["frost_any"][test] = classifier.predict_proba(x_test)[:, 1]
        del classifier
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        for offset, endpoint in enumerate(("frost_days", "observed_season_tmin_c"), 1):
            regressor = TabPFNRegressor(
                n_estimators=8, device=device, random_state=SEED + fold + offset,
                fit_mode="fit_preprocessors", n_preprocessing_jobs=4,
                show_progress_bar=False,
            )
            regressor.fit(x_train, work.iloc[train][endpoint].to_numpy(float))
            predictions[endpoint][test] = regressor.predict(x_test)
            del regressor
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        local = work.iloc[test].reset_index(drop=True)
        local_predictions = {key: value[test] for key, value in predictions.items()}
        for row in summarize(comparison, "TABPFN_HAND15", local_predictions, local):
            row["outer_fold"] = fold
            fold_metrics.append(row)
        print(f"HAND15_TABPFN_FOLD_OK={fold} device={device} train={len(train)} test={len(test)}", flush=True)
    return predictions, fold_metrics


def train_production_rf(comparison, core, work: pd.DataFrame, candidates: list[str]) -> Path:
    y = work.frost_any.astype(int).to_numpy()
    features = comparison.select_features(work, y, candidates, list(core.TERRAIN_FEATURES), SEED)
    if len(features) != 115:
        raise RuntimeError(f"Production contract requires 115 features, found {len(features)}")
    imputer = SimpleImputer(strategy="median")
    x = imputer.fit_transform(work[features]).astype(np.float32)
    classifier = RandomForestClassifier(
        n_estimators=900, max_depth=18, min_samples_leaf=5,
        max_features="sqrt", class_weight="balanced_subsample",
        n_jobs=-1, random_state=SEED,
    ).fit(x, y)
    models = {"probability": classifier}
    for offset, (key, target, criterion) in enumerate(
        [("frost_days", "frost_days", "poisson"),
         ("seasonal_tmin_c", "observed_season_tmin_c", "squared_error")], 1
    ):
        models[key] = RandomForestRegressor(
            n_estimators=700, criterion=criterion, min_samples_leaf=4,
            max_features=0.45, n_jobs=-1, random_state=SEED + offset,
        ).fit(x, work[target].to_numpy(float))
    bundle = {
        "status": "RF_HAND15_2000_2026_PRODUCTION_OK",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "requested_period": [2000, 2026],
        "observed_training_years": [int(work.year.min()), int(work.year.max())],
        "event_window": "15 May to 15 August",
        "hand_flowpath_radius_m": 15000,
        "training_rows": int(len(work)),
        "stations": int(station_key(work).nunique()),
        "features": features,
        "imputer": imputer,
        "models": models,
        "target_contract": {
            "probability": "frost_any",
            "frost_days": "frost_days",
            "seasonal_tmin_c": "observed_season_tmin_c",
        },
    }
    path = MODELS / "RF_HAND15_ALL_ENDPOINTS_2000_2026.joblib"
    joblib.dump(bundle, path, compress=3)
    path.with_suffix(".json").write_text(
        json.dumps({key: value for key, value in bundle.items() if key not in {"imputer", "models", "features"}}, indent=2),
        encoding="utf-8",
    )
    pd.DataFrame({"rank": range(1, len(features) + 1), "feature": features}).to_csv(
        TABLES / "RF_HAND15_PRODUCTION_FEATURES.csv", index=False
    )
    return path


def main() -> int:
    TABLES.mkdir(parents=True, exist_ok=True)
    MODELS.mkdir(parents=True, exist_ok=True)
    core = load_script("hand15_core", "08_run_five_state_50000_smoke.py")
    comparison = load_script("hand15_comparison", "55_compare_reduced_rf_2025_2026.py")

    hand15_table_path, station_terrain = extract_hand15()
    baseline_table, baseline_candidates = comparison.build_table(core, 2026, MODIS)
    comparison.TERRAIN = hand15_table_path
    hand15_table, hand15_candidates = comparison.build_table(core, 2026, MODIS)
    response_years_by_contract = {}
    for label, table in (("HAND2", baseline_table), ("HAND15", hand15_table)):
        observed_years = set(table.loc[table.frost_any.notna(), "year"].astype(int))
        response_years_by_contract[label] = sorted(observed_years)
        # Prediction uses all 27 climate years. The current INMET endpoint table
        # has no eligible 2000 response, so statistical validation legitimately
        # starts in 2001 and this is recorded instead of fabricating a label.
        expected_observed = set(range(2001, 2027))
        if observed_years != expected_observed:
            raise RuntimeError(
                f"{label}: expected observed response years 2001-2026 within the "
                f"requested 2000-2026 climate period; got {min(observed_years)}-"
                f"{max(observed_years)} with gaps {sorted(expected_observed-observed_years)}"
            )

    baseline_work = baseline_table.loc[baseline_table.frost_any.notna()].reset_index(drop=True)
    hand15_work = hand15_table.loc[hand15_table.frost_any.notna()].reset_index(drop=True)
    keys = ["state", "station_id", "year"]
    if not baseline_work[keys].equals(hand15_work[keys]):
        raise RuntimeError("HAND2 and HAND15 tables do not contain identical station-year rows")
    mapping = fold_assignments(hand15_work)

    rf2_pred, _, rf2_folds, rf2_sel = evaluate_rf(
        comparison, baseline_work, baseline_candidates, list(core.TERRAIN_FEATURES), mapping, "RF_HAND2"
    )
    rf15_pred, hand15_features, rf15_folds, rf15_sel = evaluate_rf(
        comparison, hand15_work, hand15_candidates, list(core.TERRAIN_FEATURES), mapping, "RF_HAND15"
    )
    tab_pred, tab_folds = evaluate_tabpfn(comparison, hand15_work, hand15_features, mapping)

    overall = []
    overall.extend(summarize(comparison, "RF_HAND2", rf2_pred, baseline_work))
    overall.extend(summarize(comparison, "RF_HAND15", rf15_pred, hand15_work))
    overall.extend(summarize(comparison, "TABPFN_HAND15", tab_pred, hand15_work))
    pd.DataFrame(overall).to_csv(TABLES / "HAND15_RF_TABPFN_OVERALL_METRICS.csv", index=False)
    pd.DataFrame(rf2_folds + rf15_folds + tab_folds).to_csv(
        TABLES / "HAND15_RF_TABPFN_FOLD_METRICS.csv", index=False
    )
    pd.DataFrame(rf2_sel + rf15_sel).to_csv(TABLES / "HAND15_RF_FEATURE_SELECTION_BY_FOLD.csv", index=False)

    oof = hand15_work[keys + ["frost_any", "frost_days", "observed_season_tmin_c"]].copy()
    oof["outer_fold"] = station_key(hand15_work).map(mapping).astype(int)
    for prefix, values in (("rf_hand2", rf2_pred), ("rf_hand15", rf15_pred), ("tabpfn_hand15", tab_pred)):
        oof[f"{prefix}_frost_probability"] = values["frost_any"]
        oof[f"{prefix}_frost_days"] = values["frost_days"]
        oof[f"{prefix}_seasonal_tmin_c"] = values["observed_season_tmin_c"]
    oof.to_parquet(TABLES / "HAND15_RF_TABPFN_OOF_PREDICTIONS.parquet", index=False)

    model_path = train_production_rf(comparison, core, hand15_work, hand15_candidates)
    status = {
        "status": "HAND15_RF_TABPFN_2000_2026_OK",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "requested_climate_prediction_years": [2000, 2026],
        "observed_response_years": [2001, 2026],
        "response_years_by_contract": response_years_by_contract,
        "event_window": "15 May to 15 August",
        "hand_flowpath_radius_m": 15000,
        "n_station_years": int(len(hand15_work)),
        "n_stations": int(station_key(hand15_work).nunique()),
        "station_hand15_resolved": int(station_terrain.HAND_selected_m.notna().sum()),
        "production_model": str(model_path),
        "metrics": str(TABLES / "HAND15_RF_TABPFN_OVERALL_METRICS.csv"),
    }
    (OUT / "STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (OUT / "HAND15_RF_TABPFN_2000_2026_OK").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
