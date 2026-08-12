from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (average_precision_score, balanced_accuracy_score, brier_score_loss,
                             confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import GroupKFold
from tabpfn import TabPFNClassifier, TabPFNRegressor
from xgboost import XGBClassifier


MODULE = Path(__file__).resolve().parents[1]
OUT = MODULE / "outputs/model_comparison_rf_xgb_tabpfn_final_snapshot"
TABLES = OUT / "tables"
MODELS = OUT / "models"
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


def metrics(model: str, y: np.ndarray, p: np.ndarray) -> dict:
    p = np.clip(np.asarray(p, float), 0, 1)
    pred = (p >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    n = len(y)
    return {
        "model": model, "n": n, "roc_auc": roc_auc_score(y, p),
        "pr_auc": average_precision_score(y, p),
        "balanced_accuracy": balanced_accuracy_score(y, pred),
        "sensitivity": recall_score(y, pred, zero_division=0),
        "specificity": tn / max(tn + fp, 1),
        "precision": precision_score(y, pred, zero_division=0),
        "f1": f1_score(y, pred, zero_division=0),
        "brier_score": brier_score_loss(y, p),
        "tn_percent": 100 * tn / n, "tp_percent": 100 * tp / n,
        "fn_percent": 100 * fn / n, "fp_percent": 100 * fp / n,
    }


def select_features(train: pd.DataFrame, y: np.ndarray, candidates: list[str], terrain: list[str]) -> list[str]:
    imputer = SimpleImputer(strategy="median")
    x = imputer.fit_transform(train[candidates])
    selector = ExtraTreesClassifier(n_estimators=240, min_samples_leaf=4, max_features="sqrt",
                                    class_weight="balanced", n_jobs=-1, random_state=SEED)
    selector.fit(x, y)
    importance = pd.Series(selector.feature_importances_, index=candidates)
    era5 = importance.loc[[c for c in candidates if c.startswith("era5__")]].nlargest(N_ERA5).index.tolist()
    modis = importance.loc[[c for c in candidates if c.startswith("modis_")]].nlargest(N_MODIS).index.tolist()
    static = [c for c in ["latitude", "longitude", "year"] + terrain if c in candidates]
    return list(dict.fromkeys(static + era5 + modis))


XGB_GRID = [
    dict(max_depth=3, learning_rate=0.03, min_child_weight=3, subsample=0.85, colsample_bytree=0.75),
    dict(max_depth=3, learning_rate=0.07, min_child_weight=5, subsample=0.90, colsample_bytree=0.90),
    dict(max_depth=5, learning_rate=0.03, min_child_weight=5, subsample=0.85, colsample_bytree=0.75),
    dict(max_depth=5, learning_rate=0.06, min_child_weight=3, subsample=0.90, colsample_bytree=0.90),
    dict(max_depth=7, learning_rate=0.03, min_child_weight=7, subsample=0.85, colsample_bytree=0.75),
    dict(max_depth=7, learning_rate=0.06, min_child_weight=5, subsample=0.90, colsample_bytree=0.90),
]


def xgb_model(params: dict, seed: int) -> XGBClassifier:
    return XGBClassifier(n_estimators=420, objective="binary:logistic", eval_metric="auc",
                         tree_method="hist", device="cuda", reg_lambda=2.0, reg_alpha=0.05,
                         random_state=seed, n_jobs=4, **params)


def tune_xgb(x: np.ndarray, y: np.ndarray, groups: np.ndarray, fold: int) -> tuple[dict, list[dict]]:
    records = []
    splits = min(3, len(np.unique(groups)))
    for index, params in enumerate(XGB_GRID):
        scores = []
        for tr, va in GroupKFold(n_splits=splits).split(x, y, groups):
            fitted = xgb_model(params, SEED + fold * 100 + index).fit(x[tr], y[tr])
            scores.append(roc_auc_score(y[va], fitted.predict_proba(x[va])[:, 1]))
        records.append({"outer_fold": fold, "candidate": index, "mean_inner_auc": float(np.mean(scores)), **params})
    best = max(records, key=lambda row: row["mean_inner_auc"])
    return {key: best[key] for key in XGB_GRID[0]}, records


def main() -> int:
    TABLES.mkdir(parents=True, exist_ok=True); MODELS.mkdir(parents=True, exist_ok=True)
    core = load_script("comparison_core", "08_run_five_state_50000_smoke.py")
    validation = load_script("comparison_table", "11_validate_historical_paired_models.py")
    table, candidates, _ = validation.build_table(core)
    work = table.loc[table.frost_any.notna()].reset_index(drop=True)
    y = work.frost_any.astype(int).to_numpy()
    station_groups = work.state.astype(str) + "__" + work.station_id.astype(str)
    splitter = GroupKFold(n_splits=5)
    predictions = {name: np.full(len(work), np.nan) for name in ["Random Forest balanced", "XGBoost tuned", "TabPFN classifier", "TabPFN regressor"]}
    selections, tuning = [], []
    fitted_last = {}
    terrain = list(core.TERRAIN_FEATURES)
    for fold, (train, test) in enumerate(splitter.split(work, y, station_groups), 1):
        selected = select_features(work.iloc[train], y[train], candidates, terrain)
        imputer = SimpleImputer(strategy="median")
        x_train = imputer.fit_transform(work.iloc[train][selected]).astype(np.float32)
        x_test = imputer.transform(work.iloc[test][selected]).astype(np.float32)
        for rank, feature in enumerate(selected, 1):
            selections.append({"outer_fold": fold, "rank": rank, "feature": feature,
                               "block": "ERA5-Land" if feature.startswith("era5__") else "MODIS" if feature.startswith("modis_") else "Terrain/HAND/space"})
        rf = RandomForestClassifier(n_estimators=700, max_depth=18, min_samples_leaf=5,
                                    max_features="sqrt", class_weight="balanced_subsample",
                                    n_jobs=-1, random_state=SEED + fold).fit(x_train, y[train])
        predictions["Random Forest balanced"][test] = rf.predict_proba(x_test)[:, 1]
        params, records = tune_xgb(x_train, y[train], station_groups.iloc[train].to_numpy(), fold)
        tuning.extend(records)
        xgb = xgb_model(params, SEED + fold).fit(x_train, y[train])
        predictions["XGBoost tuned"][test] = xgb.predict_proba(x_test)[:, 1]
        tabc = TabPFNClassifier(device="cuda", n_estimators=8, balance_probabilities=True,
                                fit_mode="fit_preprocessors", random_state=SEED + fold, show_progress_bar=False)
        tabc.fit(x_train, y[train])
        predictions["TabPFN classifier"][test] = tabc.predict_proba(x_test)[:, 1]
        del tabc; torch.cuda.empty_cache()
        tabr = TabPFNRegressor(device="cuda", n_estimators=8, fit_mode="fit_preprocessors",
                              random_state=SEED + fold, show_progress_bar=False)
        tabr.fit(x_train, y[train].astype(np.float32))
        predictions["TabPFN regressor"][test] = np.clip(tabr.predict(x_test), 0, 1)
        del tabr; torch.cuda.empty_cache()
        fitted_last = {"imputer": imputer, "features": selected, "rf": rf, "xgb": xgb}
        print(f"MODEL_COMPARISON_FOLD_OK={fold}/5 features={len(selected)}", flush=True)
    rows = [metrics(name, y, p) for name, p in predictions.items()]
    existing_table = pd.read_csv(MODULE / "outputs/historical_paired_model_statistics/tables/HISTORICAL_PAIRED_RF_COMPLETE_STATISTICS.csv")
    existing = existing_table.loc[existing_table.validation_set.str.startswith("All years")].iloc[0]
    rows.append({"model":"Random Forest full (1,040 candidates)", "n":int(existing.n_station_years),
                 **{key:existing[key] for key in ["roc_auc","pr_auc","balanced_accuracy","sensitivity","specificity","precision","f1","brier_score","tn_percent","tp_percent","fn_percent","fp_percent"]}})
    result = pd.DataFrame(rows)
    score = result[["roc_auc","pr_auc","balanced_accuracy","f1"]].mean(axis=1)
    result.insert(1, "rank", score.rank(ascending=False, method="min").astype(int))
    result = result.sort_values("rank")
    result.to_csv(TABLES / "RF_XGBOOST_TABPFN_OCCURRENCE_COMPARISON.csv", index=False)
    pd.DataFrame(selections).to_csv(TABLES / "OUTER_FOLD_BLOCK_BALANCED_FEATURE_SELECTION.csv", index=False)
    pd.DataFrame(tuning).to_csv(TABLES / "XGBOOST_NESTED_HYPERPARAMETER_TUNING.csv", index=False)
    work[["state","station_id","year","frost_any"]].assign(**{k:v for k,v in predictions.items()}).to_parquet(TABLES / "MODEL_COMPARISON_OOF_PREDICTIONS.parquet", index=False)
    joblib.dump(fitted_last, MODELS / "LAST_OUTER_FOLD_RF_XGB.joblib")
    status={"status":"RF_XGBOOST_TABPFN_COMPARISON_OK","completed_at":datetime.now(timezone.utc).isoformat(),
            "validation":"five-fold station-grouped outer CV; block-balanced feature selection and XGBoost tuning inside training data",
            "candidate_features":len(candidates),"era5_candidates":sum(c.startswith('era5__') for c in candidates),
            "modis_candidates":sum(c.startswith('modis_') for c in candidates),"selected_per_fold":{"era5":N_ERA5,"modis":N_MODIS,"terrain_hand_space":19},
            "results":result.to_dict(orient="records")}
    (OUT/"MODEL_COMPARISON_STATUS.json").write_text(json.dumps(status,indent=2),encoding="utf-8")
    print(json.dumps(status,indent=2),flush=True)
    return 0


if __name__ == "__main__": raise SystemExit(main())
