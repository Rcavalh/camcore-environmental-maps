#!/usr/bin/env python
"""Portable local Random Forest workflow for the three frost endpoints.

Input tables must contain the predictor names listed in the feature manifest and
the endpoint columns. This reference implementation is independent of the HPC
scheduler and works with CSV or Parquet files on Windows, macOS and Linux.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold, KFold, cross_val_predict
from sklearn.pipeline import Pipeline


ENDPOINTS = {
    "probability": {"column": "frost_any", "kind": "classifier"},
    "frost_days": {"column": "frost_days", "kind": "poisson_regressor"},
    "seasonal_tmin_c": {"column": "observed_season_tmin_c", "kind": "regressor"},
}


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported table format: {path}")


def write_table(frame: pd.DataFrame, path: Path) -> None:
    if path.suffix.lower() == ".csv":
        frame.to_csv(path, index=False)
    else:
        frame.to_parquet(path, index=False)


def load_features(path: Path) -> list[str]:
    manifest = pd.read_csv(path)
    if "feature" not in manifest:
        raise ValueError("Feature manifest must contain a 'feature' column")
    features = manifest["feature"].dropna().astype(str).tolist()
    if not features or len(features) != len(set(features)):
        raise ValueError("Feature manifest is empty or contains duplicates")
    return features


def estimator(kind: str, trees: int, jobs: int, seed: int) -> Pipeline:
    common = dict(n_estimators=trees, min_samples_leaf=4, max_features=0.45,
                  n_jobs=jobs, random_state=seed)
    if kind == "classifier":
        model = RandomForestClassifier(class_weight="balanced_subsample", **common)
    elif kind == "poisson_regressor":
        model = RandomForestRegressor(criterion="poisson", **common)
    else:
        model = RandomForestRegressor(criterion="squared_error", **common)
    return Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", model)])


def split_strategy(frame: pd.DataFrame, group_column: str | None, folds: int, seed: int):
    if group_column and group_column in frame and frame[group_column].nunique() >= folds:
        return GroupKFold(n_splits=folds), frame[group_column].astype(str).to_numpy(), "grouped"
    return KFold(n_splits=folds, shuffle=True, random_state=seed), None, "random"


def classification_metrics(y: np.ndarray, probability: np.ndarray) -> dict:
    prediction = probability >= 0.5
    return {
        "ROC_AUC": roc_auc_score(y, probability),
        "PR_AUC": average_precision_score(y, probability),
        "balanced_accuracy": balanced_accuracy_score(y, prediction),
        "sensitivity": recall_score(y, prediction, zero_division=0),
        "precision": precision_score(y, prediction, zero_division=0),
        "F1": f1_score(y, prediction, zero_division=0),
        "Brier_score": brier_score_loss(y, probability),
    }


def regression_metrics(y: np.ndarray, prediction: np.ndarray) -> dict:
    return {
        "RMSE": mean_squared_error(y, prediction) ** 0.5,
        "MAE": mean_absolute_error(y, prediction),
        "R2": r2_score(y, prediction),
    }


def train(args: argparse.Namespace) -> int:
    table = read_table(args.training)
    features = load_features(args.features)
    missing = sorted(set(features) - set(table.columns))
    if missing:
        raise ValueError(f"Training table is missing {len(missing)} predictors; first: {missing[:10]}")
    if args.quick_check and len(table) > args.quick_check:
        table = table.sample(args.quick_check, random_state=args.seed).reset_index(drop=True)

    args.output.mkdir(parents=True, exist_ok=True)
    models, metrics = {}, []
    for index, (endpoint, spec) in enumerate(ENDPOINTS.items()):
        target = spec["column"]
        if target not in table:
            raise ValueError(f"Missing endpoint column: {target}")
        work = table.loc[table[target].notna()].reset_index(drop=True)
        x = work[features]
        y = work[target].to_numpy()
        cv, groups, validation = split_strategy(work, args.group_column, args.folds, args.seed)
        pipe = estimator(spec["kind"], args.trees, args.jobs, args.seed + index)
        method = "predict_proba" if spec["kind"] == "classifier" else "predict"
        cv_prediction = cross_val_predict(pipe, x, y, cv=cv, groups=groups, method=method,
                                          n_jobs=1)
        if spec["kind"] == "classifier":
            cv_prediction = cv_prediction[:, 1]
            score = classification_metrics(y.astype(int), cv_prediction)
        else:
            score = regression_metrics(y.astype(float), cv_prediction.astype(float))
        metrics.append({"endpoint": endpoint, "n": len(work), "validation": validation, **score})
        pipe.fit(x, y)
        models[endpoint] = pipe
        print(f"LOCAL_RF_ENDPOINT_OK={endpoint} n={len(work)} validation={validation}", flush=True)

    bundle = {
        "status": "LOCAL_RF_THREE_ENDPOINTS_OK",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "features": features,
        "endpoints": ENDPOINTS,
        "models": models,
        "training_rows": len(table),
        "random_seed": args.seed,
    }
    joblib.dump(bundle, args.output / "frost_rf_three_endpoints.joblib", compress=3)
    pd.DataFrame(metrics).to_csv(args.output / "validation_metrics.csv", index=False)
    contract = {k: v for k, v in bundle.items() if k != "models"}
    (args.output / "model_contract.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")

    if args.prediction:
        predict_table(args.prediction, args.output / "frost_rf_three_endpoints.joblib",
                      args.output / "predictions.parquet")
    return 0


def predict_table(input_path: Path, model_path: Path, output_path: Path) -> None:
    table = read_table(input_path)
    bundle = joblib.load(model_path)
    missing = sorted(set(bundle["features"]) - set(table.columns))
    if missing:
        raise ValueError(f"Prediction table is missing {len(missing)} predictors; first: {missing[:10]}")
    x = table[bundle["features"]]
    result = table.copy()
    result["predicted_frost_probability"] = bundle["models"]["probability"].predict_proba(x)[:, 1]
    result["predicted_frost_days"] = np.maximum(0, bundle["models"]["frost_days"].predict(x))
    result["predicted_seasonal_tmin_c"] = bundle["models"]["seasonal_tmin_c"].predict(x)
    write_table(result, output_path)
    print(f"LOCAL_RF_PREDICTIONS_OK={output_path}", flush=True)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--training", type=Path, required=True)
    p.add_argument("--features", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--prediction", type=Path)
    p.add_argument("--group-column", default="station_id")
    p.add_argument("--trees", type=int, default=700)
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--jobs", type=int, default=-1)
    p.add_argument("--seed", type=int, default=20260807)
    p.add_argument("--quick-check", type=int, metavar="N", help="Use at most N rows for a reduced-scale integration check")
    return p


if __name__ == "__main__":
    raise SystemExit(train(parser().parse_args()))
