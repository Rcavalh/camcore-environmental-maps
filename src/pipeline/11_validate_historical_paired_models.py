from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
import numpy as np
import pandas as pd
import shap
from scipy import stats
from sklearn.base import clone
from sklearn.decomposition import PCA
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
from sklearn.preprocessing import StandardScaler


MODULE = Path(__file__).resolve().parents[1]
PROJECT = MODULE.parent.parent
DB = MODULE / "database"
OUT = MODULE / "outputs/historical_paired_model_statistics"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"
MODELS = OUT / "models"
REPORTS = OUT / "reports"
MODIS_INDEX = DB / "MODIS_STATION_YEAR_PARTITION_INDEX.csv"
MODIS_MARKER = DB / "HISTORICAL_MODIS_STATION_YEAR_OK.json"
MODIS_UNIFIED = DB / "MODIS_ALL_MODEL_READY_STATION_YEAR_2000_2025.parquet"
MODIS_UNIFIED_MARKER = DB / "MODIS_ALL_MODEL_READY_STATION_YEAR_OK.json"
TERRAIN = DB / "STATION_PHYSIOGRAPHIC_COVARIATES_ANADEM_30M.parquet"
CORE_PATH = MODULE / "scripts/08_run_five_state_50000_smoke.py"
SEED = 20260806
PAIR_MIN_VALID_DAYS = 5
RISK_LABELS = ["Very low", "Low", "Moderate", "High", "Extreme"]
RISK_BINS = [-np.inf, 0.2, 0.4, 0.6, 0.8, np.inf]


def load_core():
    spec = importlib.util.spec_from_file_location("historical_pair_core", CORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {CORE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ensure_dirs() -> None:
    for path in [OUT, TABLES, FIGURES, MODELS, REPORTS]:
        path.mkdir(parents=True, exist_ok=True)


def classifier() -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("rf", RandomForestClassifier(
            n_estimators=520,
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
            n_estimators=520,
            criterion="poisson" if poisson else "squared_error",
            min_samples_leaf=4,
            max_features=0.45,
            n_jobs=-1,
            random_state=seed,
        )),
    ])


def load_modis() -> pd.DataFrame:
    if MODIS_UNIFIED.exists() and MODIS_UNIFIED_MARKER.exists():
        return pd.read_parquet(MODIS_UNIFIED)
    if not MODIS_MARKER.exists():
        raise RuntimeError("Historical MODIS station-year extraction has not completed")
    index = pd.read_csv(MODIS_INDEX)
    frames = [pd.read_parquet(path) for path in index.loc[index.status.eq("COMPLETE"), "output"]]
    return pd.concat(frames, ignore_index=True)


def feature_block(name: str) -> str:
    clean = name.replace("missingindicator_", "")
    if clean.startswith("era5__"):
        return "ERA5-Land"
    if clean.startswith("modis_"):
        return "MODIS"
    if clean in {"latitude", "longitude", "year"}:
        return "Space/time"
    return "Terrain/HAND"


def feature_label(name: str) -> str:
    clean = name.replace("missingindicator_", "")
    exact = {
        "latitude": "Latitude",
        "longitude": "Longitude",
        "year": "Year",
        "elevation": "Elevation",
        "HAND_selected_m": "HAND",
        "cold_air_pooling_2000m": "Cold-air pooling potential",
        "elevation_above_local_min_2000m": "Elevation above local minimum",
        "elevation_below_local_max_2000m": "Elevation below local maximum",
        "local_relief_2000m": "Local topographic relief",
        "local_sd_2000m": "Local elevation variability",
        "slope_deg": "Slope",
        "northness": "Northness",
        "eastness": "Eastness",
        "modis_lst_day_mean_c": "MODIS mean daytime LST",
        "modis_lst_day_min_c": "MODIS minimum daytime LST",
        "modis_lst_day_p05_c": "MODIS daytime LST P05",
        "modis_lst_day_valid_fraction": "MODIS daytime valid fraction",
        "modis_lst_night_mean_c": "MODIS mean nighttime LST",
        "modis_lst_night_min_c": "MODIS minimum nighttime LST",
        "modis_lst_night_p05_c": "MODIS nighttime LST P05",
        "modis_lst_night_valid_fraction": "MODIS nighttime valid fraction",
        "modis_diurnal_range_mean_c": "MODIS mean diurnal LST range",
    }
    if clean in exact:
        label = exact[clean]
    elif clean.startswith("era5__"):
        pieces = clean.removeprefix("era5__").split("__")
        label = f"ERA5 {' '.join(pieces[:-1]).replace('_', ' ')} ({pieces[-1]})"
    else:
        label = clean.replace("_2000m", "").replace("_", " ").title()
    if name.startswith("missingindicator_"):
        label += " — missingness"
    return label


def build_table(core) -> tuple[pd.DataFrame, list[str], list[str]]:
    era5 = core.load_era5_wide()
    era5 = era5.loc[era5.source.eq("INMET") & era5.year.between(2000, 2025)].copy()
    targets = core.load_targets()
    terrain = pd.read_parquet(TERRAIN)
    terrain = terrain.loc[terrain.source.eq("INMET")].copy()
    modis = load_modis()
    identifiers = ["state", "source", "station_id", "year"]
    table = era5.merge(targets, on=["state", "station_id", "year"], how="inner", validate="one_to_one")
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
    era5_features = [column for column in table if column.startswith("era5__")]
    # Every QA-filtered, model-ready MODIS summary in the frozen snapshot is
    # eligible. Raw QA layers never enter the matrix; coverage summaries do.
    modis_features = [column for column in table if column.startswith("modis_")]
    candidate = ["latitude", "longitude", "year"] + list(core.TERRAIN_FEATURES) + era5_features + modis_features
    features = [column for column in candidate if table[column].notna().any()]
    return table, features, era5_features


def oof_predictions(model, table: pd.DataFrame, features: list[str], target: str, kind: str):
    work = table.loc[table[target].notna()].copy().reset_index(drop=True)
    y = work[target].to_numpy()
    groups = work.station_id.astype(str).to_numpy()
    prediction = np.full(len(work), np.nan, dtype=float)
    for train, test in GroupKFold(n_splits=5).split(work[features], y, groups):
        fitted = clone(model).fit(work.iloc[train][features], y[train])
        if kind == "classifier":
            prediction[test] = fitted.predict_proba(work.iloc[test][features])[:, 1]
        else:
            prediction[test] = fitted.predict(work.iloc[test][features])
    final = clone(model).fit(work[features], y)
    work[f"oof_{target}"] = prediction
    return work, final


def classification_metrics(work: pd.DataFrame, prediction_column: str, validation_set: str) -> dict:
    y = work.frost_any.to_numpy(dtype=int)
    probability = work[prediction_column].to_numpy(dtype=float)
    predicted = (probability >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    n = len(y)
    return {
        "model": "Random Forest classifier",
        "endpoint": "Frost occurrence probability",
        "validation_set": validation_set,
        "covariates": "Terrain + HAND + ERA5-Land + MODIS",
        "n_station_years": n,
        "n_stations": int(work.station_id.nunique()),
        "roc_auc": roc_auc_score(y, probability),
        "pr_auc": average_precision_score(y, probability),
        "balanced_accuracy": balanced_accuracy_score(y, predicted),
        "sensitivity": recall_score(y, predicted, zero_division=0),
        "specificity": tn / (tn + fp),
        "precision": precision_score(y, predicted, zero_division=0),
        "f1": f1_score(y, predicted, zero_division=0),
        "brier_score": brier_score_loss(y, probability),
        "tn_percent": 100 * tn / n,
        "tp_percent": 100 * tp / n,
        "fn_percent": 100 * fn / n,
        "fp_percent": 100 * fp / n,
    }


def regression_metrics(work: pd.DataFrame, target: str, prediction_column: str, endpoint: str) -> dict:
    y = work[target].to_numpy(dtype=float)
    prediction = work[prediction_column].to_numpy(dtype=float)
    return {
        "model": "Random Forest regressor",
        "endpoint": endpoint,
        "validation_set": "Historically paired MODIS observations",
        "covariates": "Terrain + HAND + ERA5-Land + MODIS",
        "n_station_years": len(work),
        "n_stations": int(work.station_id.nunique()),
        "r2": r2_score(y, prediction),
        "rmse": mean_squared_error(y, prediction) ** 0.5,
        "mae": mean_absolute_error(y, prediction),
        "bias": float(np.mean(prediction - y)),
    }


def add_regression_panel(
    ax,
    x: np.ndarray,
    y: np.ndarray,
    xlabel: str,
    letter: str,
    color_values: np.ndarray,
    xmax: float | None = None,
):
    valid = np.isfinite(x) & np.isfinite(y)
    if xmax is not None:
        valid &= x <= xmax
    x, y, colors = x[valid], y[valid], color_values[valid]
    ax.scatter(x, y, c=colors, cmap="RdYlBu", vmin=0, vmax=1, s=10, alpha=0.33, linewidths=0, rasterized=True)
    order = np.argsort(x)
    xs, ys = x[order], y[order]
    slope, intercept, r, p, _ = stats.linregress(xs, ys)
    fitted = intercept + slope * xs
    n = len(xs)
    residual = ys - fitted
    standard_error = math.sqrt(np.sum(residual**2) / max(n - 2, 1))
    denominator = np.sum((xs - xs.mean()) ** 2)
    confidence = stats.t.ppf(0.975, max(n - 2, 1)) * standard_error * np.sqrt(
        1 / n + (xs - xs.mean()) ** 2 / max(denominator, 1e-12)
    )
    ax.plot(xs, fitted, color="#252525", linewidth=1.5)
    ax.fill_between(xs, fitted - confidence, fitted + confidence, color="#555555", alpha=0.15, linewidth=0)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Out-of-fold frost probability")
    ax.set_ylim(-0.02, 1.02)
    if xmax is not None:
        ax.set_xlim(0, xmax)
    ax.set_title(f"({letter}) {xlabel}\nPearson r = {r:.3f} | R² = {r*r:.3f} | P = {p:.2g}", loc="left", fontsize=10)
    ax.grid(alpha=0.18)


def plot_relationships(work: pd.DataFrame) -> list[Path]:
    probability = work.oof_frost_any.to_numpy()
    fig, axes = plt.subplots(2, 2, figsize=(11.4, 9.1))
    panels = [
        (work.latitude.to_numpy(), "Latitude", "a", None),
        (work.observed_season_tmin_c.to_numpy(), "Minimum temperature recorded at weather stations (°C)", "b", None),
        (work.elevation.to_numpy(), "Elevation (m)", "c", None),
        (work.HAND_selected_m.to_numpy(), "HAND (m)", "d", 250),
    ]
    for ax, (x, label, letter, xmax) in zip(axes.ravel(), panels):
        add_regression_panel(ax, x, probability, label, letter, probability, xmax=xmax)
    scalar = plt.cm.ScalarMappable(cmap="RdYlBu", norm=plt.Normalize(0, 1))
    colorbar_ax = fig.add_axes([0.925, 0.19, 0.018, 0.62])
    colorbar = fig.colorbar(scalar, cax=colorbar_ax)
    colorbar.set_label("Out-of-fold frost probability (red = low; blue = high)")
    fig.suptitle("Observed station environment versus cross-validated frost probability", fontsize=14)
    fig.subplots_adjust(left=0.08, right=0.88, bottom=0.08, top=0.91, wspace=0.24, hspace=0.30)
    paths = [FIGURES / "HISTORICAL_PAIRED_RF_RELATIONSHIPS_LIGHT.png", FIGURES / "HISTORICAL_PAIRED_RF_RELATIONSHIPS_620DPI.png", FIGURES / "HISTORICAL_PAIRED_RF_RELATIONSHIPS.pdf"]
    fig.savefig(paths[0], dpi=180, facecolor="white")
    fig.savefig(paths[1], dpi=620, facecolor="white")
    fig.savefig(paths[2], facecolor="white")
    plt.close(fig)
    return paths


def grouped_permutation_importance_cv(work: pd.DataFrame, features: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estimate block importance without rewarding blocks merely for having more columns."""
    y = work.frost_any.to_numpy(dtype=int)
    groups = work.station_id.astype(str).to_numpy()
    block_features = {
        block: [feature for feature in features if feature_block(feature) == block]
        for block in ["Terrain/HAND", "ERA5-Land", "MODIS", "Space/time"]
    }
    rng = np.random.default_rng(SEED + 91)
    rows = []
    for fold, (train, test) in enumerate(GroupKFold(n_splits=5).split(work[features], y, groups), start=1):
        fitted = classifier().fit(work.iloc[train][features], y[train])
        test_frame = work.iloc[test][features].copy()
        baseline = roc_auc_score(y[test], fitted.predict_proba(test_frame)[:, 1])
        permutation = rng.permutation(len(test_frame))
        for block, columns in block_features.items():
            shuffled = test_frame.copy()
            shuffled.loc[:, columns] = shuffled[columns].to_numpy()[permutation]
            permuted_auc = roc_auc_score(y[test], fitted.predict_proba(shuffled)[:, 1])
            rows.append({
                "fold": fold,
                "block": block,
                "n_features": len(columns),
                "baseline_auc": baseline,
                "permuted_auc": permuted_auc,
                "auc_decrease": baseline - permuted_auc,
            })
    fold_frame = pd.DataFrame(rows)
    summary = fold_frame.groupby(["block", "n_features"], as_index=False).agg(
        mean_auc_decrease=("auc_decrease", "mean"),
        sd_auc_decrease=("auc_decrease", "std"),
        min_auc_decrease=("auc_decrease", "min"),
        max_auc_decrease=("auc_decrease", "max"),
    )
    summary["se_auc_decrease"] = summary.sd_auc_decrease / math.sqrt(5)
    summary["ci95_auc_decrease"] = 1.96 * summary.se_auc_decrease
    return fold_frame, summary.sort_values("mean_auc_decrease", ascending=False)


def shap_analysis(model: Pipeline, work: pd.DataFrame, features: list[str]):
    rng = np.random.default_rng(SEED)
    sample_indices = rng.choice(len(work), size=min(1000, len(work)), replace=False)
    sample = work.iloc[sample_indices][features]
    transformed = model.named_steps["imputer"].transform(sample)
    transformed_names = list(model.named_steps["imputer"].get_feature_names_out(features))
    values = shap.TreeExplainer(model.named_steps["rf"]).shap_values(transformed)
    if isinstance(values, list):
        values = values[1]
    elif values.ndim == 3:
        values = values[:, :, 1]
    importance = pd.DataFrame({
        "transformed_feature": transformed_names,
        "feature": [name.replace("missingindicator_", "") for name in transformed_names],
        "block": [feature_block(name) for name in transformed_names],
        "mean_abs_shap": np.abs(values).mean(axis=0),
    })
    collapsed = importance.groupby(["feature", "block"], as_index=False).mean_abs_shap.sum().sort_values("mean_abs_shap", ascending=False)
    collapsed["formal_label"] = collapsed.feature.map(feature_label)
    collapsed.to_csv(TABLES / "HISTORICAL_PAIRED_RF_SHAP_VARIABLE_IMPORTANCE.csv", index=False)
    grouped = collapsed.groupby("block", as_index=False).mean_abs_shap.sum().sort_values("mean_abs_shap", ascending=False)
    grouped["percent_total_shap"] = 100 * grouped.mean_abs_shap / grouped.mean_abs_shap.sum()
    grouped.to_csv(TABLES / "HISTORICAL_PAIRED_RF_SHAP_BLOCK_IMPORTANCE.csv", index=False)
    permutation_folds, permutation = grouped_permutation_importance_cv(work, features)
    permutation_folds.to_csv(TABLES / "HISTORICAL_PAIRED_RF_GROUPED_PERMUTATION_FOLDS.csv", index=False)
    permutation.to_csv(TABLES / "HISTORICAL_PAIRED_RF_GROUPED_PERMUTATION_IMPORTANCE.csv", index=False)

    top = collapsed.head(25).sort_values("mean_abs_shap")
    viridis = plt.cm.viridis
    block_colors = {
        "Terrain/HAND": viridis(0.12),
        "ERA5-Land": viridis(0.40),
        "MODIS": viridis(0.68),
        "Space/time": viridis(0.88),
    }
    display_labels = {
        "Terrain/HAND": "Physiography + HAND",
        "ERA5-Land": "ERA5-Land",
        "MODIS": "MODIS",
        "Space/time": "Space/time",
    }
    fig, axes = plt.subplots(1, 2, figsize=(14.2, 10.4), gridspec_kw={"width_ratios": [3.2, 1.15]})
    ax = axes[0]
    ax.barh(top.formal_label, top.mean_abs_shap, color=top.block.map(block_colors), edgecolor="none")
    ax.set_xlabel("Mean absolute SHAP value")
    ax.set_title("(a) SHAP importance of individual covariates", loc="left", fontsize=13)
    ax.grid(axis="x", alpha=0.2)
    handles = [
        plt.Line2D([0], [0], marker="s", linestyle="", color=color, label=display_labels[block], markersize=8)
        for block, color in block_colors.items()
    ]
    ax.legend(handles=handles, frameon=False, loc="lower right")
    block_plot = permutation.sort_values("mean_auc_decrease")
    axes[1].barh(
        block_plot.block.map(display_labels),
        block_plot.mean_auc_decrease,
        xerr=block_plot.ci95_auc_decrease,
        color=block_plot.block.map(block_colors),
        edgecolor="none",
        error_kw={"ecolor": "#333333", "elinewidth": 1.0, "capsize": 3},
    )
    axes[1].axvline(0, color="#777777", linewidth=0.8)
    axes[1].set_xlabel("Cross-validated ROC-AUC decrease")
    axes[1].set_title("(b) Unique contribution\nof covariate blocks", loc="left", fontsize=12)
    axes[1].grid(axis="x", alpha=0.2)
    upper_limit = float((block_plot.mean_auc_decrease + block_plot.ci95_auc_decrease).max())
    axes[1].set_xlim(min(-0.01, float(block_plot.mean_auc_decrease.min()) * 1.4), upper_limit * 1.22)
    for row_index, row in block_plot.reset_index(drop=True).iterrows():
        axes[1].text(row.mean_auc_decrease + row.ci95_auc_decrease, row_index, f"  {row.mean_auc_decrease:.3f}", va="center", fontsize=9)
    fig.suptitle("Random Forest frost-occurrence model — SHAP/WASP importance", fontsize=14)
    fig.text(
        0.5,
        0.025,
        "Block contribution is the mean ROC-AUC decrease after jointly permuting all covariates in that block within station-held-out folds; error bars are 95% confidence intervals across folds.",
        ha="center",
        fontsize=8.5,
    )
    fig.subplots_adjust(left=0.28, right=0.98, top=0.93, bottom=0.10, wspace=0.35)
    paths = [FIGURES / "HISTORICAL_PAIRED_RF_SHAP_WASP_LIGHT.png", FIGURES / "HISTORICAL_PAIRED_RF_SHAP_WASP_620DPI.png", FIGURES / "HISTORICAL_PAIRED_RF_SHAP_WASP.pdf"]
    fig.savefig(paths[0], dpi=180, facecolor="white")
    fig.savefig(paths[1], dpi=620, facecolor="white")
    fig.savefig(paths[2], facecolor="white")
    plt.close(fig)
    return collapsed, grouped, paths


def shap_beeswarm_sensitivity(model: Pipeline, work: pd.DataFrame, features: list[str]):
    """Plot directional SHAP effects after removing redundant covariates.

    Redundancy control keeps a single temporal summary per ERA5-Land variable,
    applies a greedy absolute-Spearman filter (rho >= 0.90), and limits the
    number of representatives contributed by each predictor block.
    """
    import re
    import textwrap

    rng = np.random.default_rng(SEED + 303)
    sample_indices = rng.choice(len(work), size=min(1000, len(work)), replace=False)
    sample = work.iloc[sample_indices][features].copy()
    imputer = model.named_steps["imputer"]
    transformed = imputer.transform(sample)
    transformed_names = list(imputer.get_feature_names_out(features))
    values = shap.TreeExplainer(model.named_steps["rf"]).shap_values(transformed)
    if isinstance(values, list):
        values = values[1]
    elif values.ndim == 3:
        values = values[:, :, 1]

    transformed_lookup = {name: index for index, name in enumerate(transformed_names)}
    mean_abs = {
        feature: float(np.abs(values[:, transformed_lookup[feature]]).mean())
        for feature in features
        if feature in transformed_lookup
    }

    def family(feature: str) -> str:
        if feature.startswith("era5__"):
            base = feature.split("__")[1]
            base = re.sub(r"_(min|max|sum)$", "", base)
            if base in {"u_component_of_wind_10m", "v_component_of_wind_10m"}:
                base = "horizontal_wind_10m"
            return f"era5__{base}"
        if feature.startswith("modis_"):
            return re.sub(r"_(mean|min|p05|max|p95)(_c)?$", "", feature)
        if feature.startswith("elevation_above_local_min_") or feature.startswith("elevation_below_local_max_"):
            return "relative_elevation_context"
        return feature

    block_caps = {"ERA5-Land": 6, "Terrain/HAND": 3, "MODIS": 2, "Space/time": 1}
    selected = []
    selected_families = set()
    block_counts = {block: 0 for block in block_caps}
    ranked = sorted(mean_abs, key=mean_abs.get, reverse=True)
    for feature in ranked:
        block = feature_block(feature)
        if block not in block_caps or block_counts[block] >= block_caps[block]:
            continue
        if family(feature) in selected_families:
            continue
        candidate = pd.to_numeric(sample[feature], errors="coerce")
        redundant = False
        for retained in selected:
            correlation = candidate.corr(pd.to_numeric(sample[retained], errors="coerce"), method="spearman")
            if pd.notna(correlation) and abs(correlation) >= 0.90:
                redundant = True
                break
        if redundant:
            continue
        selected.append(feature)
        selected_families.add(family(feature))
        block_counts[block] += 1
        if len(selected) == 12:
            break

    fig, ax = plt.subplots(figsize=(11.2, 9.4))
    long_rows = []
    y_positions = np.arange(len(selected))[::-1]
    for y_position, feature in zip(y_positions, selected):
        feature_values = pd.to_numeric(sample[feature], errors="coerce").to_numpy(dtype=float)
        median = np.nanmedian(feature_values)
        feature_values = np.where(np.isfinite(feature_values), feature_values, median)
        low, high = np.nanpercentile(feature_values, [5, 95])
        normalized = np.clip((feature_values - low) / max(high - low, 1e-12), 0, 1)
        shap_values = values[:, transformed_lookup[feature]]
        jitter = rng.normal(0, 0.115, len(shap_values))
        ax.scatter(shap_values, y_position + jitter, c=normalized, cmap="RdYlBu", vmin=0, vmax=1,
                   s=14, alpha=0.58, linewidths=0, rasterized=True)
        long_rows.extend({"feature": feature, "formal_label": feature_label(feature), "value": raw,
                          "scaled_value_5_95": scaled, "shap_probability_contribution": shap_value}
                         for raw, scaled, shap_value in zip(feature_values, normalized, shap_values))
    ax.axvline(0, color="#333333", linewidth=1.0)
    ax.set_xlim(-0.04, 0.04)
    ax.set_xticks([-0.04, -0.02, 0.00, 0.02, 0.04])
    ax.set_yticks(y_positions)
    ax.set_yticklabels([textwrap.fill(feature_label(feature), 34) for feature in selected], fontsize=9)
    ax.set_xlabel("SHAP contribution to predicted frost probability\n← decreases probability | increases probability →")
    ax.set_title("Directional effects of non-redundant covariates", loc="left", fontsize=13)
    ax.grid(axis="x", alpha=0.18)
    scalar = plt.cm.ScalarMappable(cmap="RdYlBu", norm=plt.Normalize(0, 1))
    colorbar = fig.colorbar(scalar, ax=ax, fraction=0.025, pad=0.02)
    colorbar.set_ticks([0, 1], labels=["Low", "High"])
    colorbar.set_label("Covariate value")

    y_true = work.frost_any.to_numpy(dtype=int)
    probability = work.oof_frost_any.to_numpy(dtype=float)
    thresholds = np.linspace(0.05, 0.95, 91)
    sensitivities, specificities = [], []
    for threshold in thresholds:
        prediction = probability >= threshold
        tn, fp, fn, tp = confusion_matrix(y_true, prediction, labels=[0, 1]).ravel()
        sensitivities.append(tp / max(tp + fn, 1))
        specificities.append(tn / max(tn + fp, 1))
    fig.suptitle("Random Forest frost-occurrence model: directional SHAP effects", fontsize=14)
    fig.subplots_adjust(left=0.32, right=0.94, bottom=0.11, top=0.91)
    paths = [
        FIGURES / "HISTORICAL_PAIRED_RF_SHAP_BEESWARM_NONREDUNDANT_LIGHT.png",
        FIGURES / "HISTORICAL_PAIRED_RF_SHAP_BEESWARM_NONREDUNDANT_620DPI.png",
        FIGURES / "HISTORICAL_PAIRED_RF_SHAP_BEESWARM_NONREDUNDANT.pdf",
    ]
    fig.savefig(paths[0], dpi=180, facecolor="white")
    fig.savefig(paths[1], dpi=620, facecolor="white")
    fig.savefig(paths[2], facecolor="white")
    plt.close(fig)
    pd.DataFrame({
        "rank": np.arange(1, len(selected) + 1),
        "feature": selected,
        "formal_label": [feature_label(feature) for feature in selected],
        "block": [feature_block(feature) for feature in selected],
        "mean_abs_shap": [mean_abs[feature] for feature in selected],
    }).to_csv(TABLES / "HISTORICAL_PAIRED_RF_SHAP_NONREDUNDANT_FEATURES.csv", index=False)
    pd.DataFrame(long_rows).to_parquet(TABLES / "HISTORICAL_PAIRED_RF_SHAP_NONREDUNDANT_VALUES.parquet", index=False)
    pd.DataFrame({"threshold": thresholds, "sensitivity": sensitivities, "specificity": specificities}).to_csv(
        TABLES / "HISTORICAL_PAIRED_RF_THRESHOLD_SENSITIVITY.csv", index=False
    )
    return paths


def add_confidence_ellipse(ax, x: np.ndarray, y: np.ndarray, color):
    if len(x) < 4:
        return
    covariance = np.cov(x, y)
    if not np.isfinite(covariance).all():
        return
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = eigenvalues.argsort()[::-1]
    eigenvalues, eigenvectors = eigenvalues[order], eigenvectors[:, order]
    angle = np.degrees(np.arctan2(*eigenvectors[:, 0][::-1]))
    width, height = 2 * 1.96 * np.sqrt(np.maximum(eigenvalues, 0))
    ax.add_patch(Ellipse((x.mean(), y.mean()), width, height, angle=angle, fill=False, color=color, linewidth=1.2, alpha=0.8))


def pca_analysis(work: pd.DataFrame, shap_importance: pd.DataFrame):
    """Descriptive PCA using exactly the non-redundant SHAP representatives."""
    import textwrap

    registry_path = TABLES / "HISTORICAL_PAIRED_RF_SHAP_NONREDUNDANT_FEATURES.csv"
    if not registry_path.exists():
        raise RuntimeError("Non-redundant SHAP feature registry is missing")
    registry = pd.read_csv(registry_path).sort_values("rank")
    selected_meta = [
        (row.feature, row.formal_label, row.block)
        for row in registry.itertuples(index=False)
        if row.feature in work.columns and work[row.feature].notna().any()
    ]
    selected = [row[0] for row in selected_meta]
    if len(selected) < 5:
        raise RuntimeError(f"Insufficient curated PCA variables: {selected}")
    matrix = SimpleImputer(strategy="median").fit_transform(work[selected])
    matrix = StandardScaler().fit_transform(matrix)
    pca = PCA(n_components=2, random_state=SEED)
    scores = pca.fit_transform(matrix)
    risk_class = pd.cut(work.oof_frost_any, bins=RISK_BINS, labels=RISK_LABELS, right=False)
    colors = dict(zip(RISK_LABELS, plt.cm.RdYlBu(np.linspace(0.06, 0.94, len(RISK_LABELS)))))
    fig, ax = plt.subplots(figsize=(14.2, 9.2))
    for label in RISK_LABELS:
        mask = risk_class.eq(label).to_numpy()
        if not mask.any():
            continue
        ax.scatter(scores[mask, 0], scores[mask, 1], s=14, alpha=0.35, color=colors[label], linewidths=0, label=label)
        add_confidence_ellipse(ax, scores[mask, 0], scores[mask, 1], colors[label])
    loadings = pca.components_.T
    loading_rows = []
    source_colors = {
        "Terrain/HAND": "#2c7fb8",
        "MODIS": "#f28e2b",
        "ERA5-Land": "#41ab5d",
        "Space/time": "#5b5b5b",
    }
    score_scale = 0.56 * min(np.ptp(scores[:, 0]), np.ptp(scores[:, 1])) / max(np.abs(loadings).max(), 1e-8)
    vector_labels = []
    for index, (feature, label, source) in enumerate(selected_meta):
        x, y = score_scale * loadings[index]
        color = source_colors[source]
        loading_rows.append({
            "feature": feature,
            "formal_label": label,
            "source": source,
            "PC1_loading": loadings[index, 0],
            "PC2_loading": loadings[index, 1],
        })
        ax.annotate(
            "",
            xy=(x, y),
            xytext=(0, 0),
            arrowprops={"arrowstyle": "-|>", "color": color, "lw": 1.5, "alpha": 0.95},
        )
        vector_labels.append({"x": x, "y": y, "label": label, "color": color})

    # Keep the full variable names at the vector tips while gently separating
    # labels that point in nearly identical directions.
    for side in [-1, 1]:
        entries = sorted([row for row in vector_labels if (row["x"] >= 0) == (side > 0)], key=lambda row: row["y"])
        if not entries:
            continue
        adjusted = [entries[0]["y"]]
        for row in entries[1:]:
            adjusted.append(max(row["y"], adjusted[-1] + 0.58))
        shift = np.mean([row["y"] for row in entries]) - np.mean(adjusted)
        adjusted = [value + shift for value in adjusted]
        for row, label_y in zip(entries, adjusted):
            label_x = row["x"] + side * 0.18
            ax.annotate(
                textwrap.fill(row["label"], 25),
                xy=(row["x"], row["y"]),
                xytext=(label_x, label_y),
                textcoords="data",
                fontsize=8.3,
                color=row["color"],
                ha="left" if side > 0 else "right",
                va="center",
                arrowprops={"arrowstyle": "-", "color": row["color"], "lw": 0.8, "alpha": 0.75},
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.70, "pad": 0.5},
            )
    x_min, x_max = ax.get_xlim()
    ax.set_xlim(x_min - 0.35, x_max + 1.65)
    ax.axhline(0, color="#999999", linewidth=0.7)
    ax.axvline(0, color="#999999", linewidth=0.7)
    ax.set_xlabel(f"PC1 ({100*pca.explained_variance_ratio_[0]:.1f}% explained)")
    ax.set_ylabel(f"PC2 ({100*pca.explained_variance_ratio_[1]:.1f}% explained)")
    ax.set_title("PCA scores and non-redundant SHAP vectors", loc="left", fontsize=13)
    ax.legend(title="Frost-risk class", frameon=False, loc="best")
    ax.grid(alpha=0.15)
    fig.suptitle("PCA fingerprint of the non-redundant covariates retained in the SHAP summary", fontsize=14)
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.09, top=0.90)
    paths = [FIGURES / "HISTORICAL_PAIRED_RF_PCA_SHAP_NONREDUNDANT_LIGHT.png", FIGURES / "HISTORICAL_PAIRED_RF_PCA_SHAP_NONREDUNDANT_620DPI.png", FIGURES / "HISTORICAL_PAIRED_RF_PCA_SHAP_NONREDUNDANT.pdf"]
    fig.savefig(paths[0], dpi=180, facecolor="white")
    fig.savefig(paths[1], dpi=620, facecolor="white")
    fig.savefig(paths[2], facecolor="white")
    plt.close(fig)
    pd.DataFrame(loading_rows).to_csv(TABLES / "HISTORICAL_PAIRED_RF_PCA_LOADINGS.csv", index=False)
    pd.DataFrame(selected_meta, columns=["feature", "formal_label", "source"]).to_csv(TABLES / "HISTORICAL_PAIRED_RF_PCA_SHAP_VECTOR_REGISTRY.csv", index=False)
    pd.DataFrame({"PC1": scores[:, 0], "PC2": scores[:, 1], "risk_class": risk_class.astype(str), "frost_probability": work.oof_frost_any}).to_parquet(TABLES / "HISTORICAL_PAIRED_RF_PCA_SCORES.parquet", index=False)
    return paths


def write_report(metrics: pd.DataFrame, coverage: pd.DataFrame, files: list[Path]) -> Path:
    report = REPORTS / "HISTORICAL_PAIRED_RF_MODEL_REPORT.html"
    metric_html = metrics.round(4).fillna("").to_html(index=False, classes="metrics")
    coverage_html = coverage.round(4).fillna("").to_html(index=False, classes="metrics")
    image_html = "".join(f'<h2>{path.stem}</h2><img src="../figures/{path.name}" style="max-width:100%;height:auto">' for path in files if path.suffix.lower() == ".png" and "LIGHT" in path.name)
    report.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Historical paired RF model report</title>"
        "<style>body{font-family:Arial,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#222}"
        "table{border-collapse:collapse;width:100%;font-size:12px}th,td{border-bottom:1px solid #ddd;padding:6px;text-align:right}th:first-child,td:first-child{text-align:left}"
        "h1,h2{font-weight:500}</style></head><body>"
        "<h1>Historical ERA5-Land + MODIS + terrain/HAND frost models</h1>"
        "<p>All MODIS predictors are paired by station, year and the 15 May–15 August season. The primary analysis requires at least five valid QC-filtered daytime and nighttime MODIS observations.</p>"
        f"<h2>Validation statistics</h2>{metric_html}<h2>MODIS temporal coverage</h2>{coverage_html}{image_html}</body></html>",
        encoding="utf-8",
    )
    return report


def main() -> int:
    ensure_dirs()
    core = load_core()
    table, features, era5_catalogued = build_table(core)
    paired = table.loc[
        table.modis_lst_day_n_valid_days.fillna(0).ge(PAIR_MIN_VALID_DAYS)
        & table.modis_lst_night_n_valid_days.fillna(0).ge(PAIR_MIN_VALID_DAYS)
    ].copy()
    if paired.station_id.nunique() < 20 or len(paired) < 200:
        raise RuntimeError(f"Insufficient historically paired support: {len(paired)} rows, {paired.station_id.nunique()} stations")

    occurrence_work, occurrence_model = oof_predictions(classifier(), paired, features, "frost_any", "classifier")
    days_work, days_model = oof_predictions(regressor(SEED + 1, poisson=True), paired, features, "frost_days", "regressor")
    tmin_work, tmin_model = oof_predictions(regressor(SEED + 2), paired, features, "observed_season_tmin_c", "regressor")
    all_year_work, _ = oof_predictions(classifier(), table, features, "frost_any", "classifier")

    metrics = [
        classification_metrics(occurrence_work, "oof_frost_any", "Historically paired MODIS observations"),
        classification_metrics(all_year_work, "oof_frost_any", "All years; missing MODIS handled inside folds"),
        regression_metrics(days_work, "frost_days", "oof_frost_days", "Expected frost days"),
        regression_metrics(tmin_work, "observed_season_tmin_c", "oof_observed_season_tmin_c", "Seasonal minimum temperature"),
    ]
    metrics_frame = pd.DataFrame(metrics)
    metrics_frame.to_csv(TABLES / "HISTORICAL_PAIRED_RF_COMPLETE_STATISTICS.csv", index=False)
    occurrence_work.to_parquet(TABLES / "HISTORICAL_PAIRED_RF_OCCURRENCE_OOF_PREDICTIONS.parquet", index=False)

    registry = pd.DataFrame({"feature": features})
    registry["block"] = registry.feature.map(feature_block)
    registry["formal_label"] = registry.feature.map(feature_label)
    registry["training_missing_percent"] = [100 * paired[feature].isna().mean() for feature in features]
    registry.to_csv(TABLES / "HISTORICAL_PAIRED_RF_FEATURE_REGISTRY.csv", index=False)

    coverage = pd.read_csv(DB / "MODIS_STATION_YEAR_TEMPORAL_COVERAGE.csv")
    relationship_paths = plot_relationships(occurrence_work)
    shap_importance, shap_blocks, shap_paths = shap_analysis(occurrence_model, occurrence_work, features)
    directional_shap_paths = shap_beeswarm_sensitivity(occurrence_model, occurrence_work, features)
    pca_paths = pca_analysis(occurrence_work, shap_importance)
    all_paths = relationship_paths + shap_paths + directional_shap_paths + pca_paths
    joblib.dump(
        {"occurrence": occurrence_model, "frost_days": days_model, "seasonal_tmin": tmin_model, "features": features},
        MODELS / "HISTORICAL_PAIRED_RF_MODELS.joblib",
    )
    report = write_report(metrics_frame, coverage, all_paths)
    status = {
        "status": "HISTORICAL_PAIRED_RF_STATISTICS_OK",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "season": "15 May-15 August",
        "years": [2000, 2025],
        "paired_min_valid_days_per_period": PAIR_MIN_VALID_DAYS,
        "paired_station_years": len(paired),
        "paired_stations": int(paired.station_id.nunique()),
        "all_station_years": len(table),
        "all_stations": int(table.station_id.nunique()),
        "features_used": len(features),
        "feature_blocks": registry.groupby("block").size().astype(int).to_dict(),
        "era5_features_catalogued": len(era5_catalogued),
        "metrics": metrics,
        "report": str(report),
    }
    (OUT / "HISTORICAL_PAIRED_RF_STATISTICS_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (OUT / "HISTORICAL_PAIRED_RF_STATISTICS_OK").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
