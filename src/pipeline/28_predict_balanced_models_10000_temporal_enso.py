from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from tabpfn import TabPFNClassifier, TabPFNRegressor
from xgboost import XGBClassifier


MODULE = Path(__file__).resolve().parents[1]
PROJECT = MODULE.parent.parent
OUT = MODULE / "outputs/balanced_models_10000_temporal_enso"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"
MODELS = OUT / "models"
SOURCE_POINTS = MODULE / "outputs/updated_historical_10000_smoke/tables/UPDATED_HISTORICAL_RF_10000_PREDICTIONS.parquet"
METRICS = MODULE / "outputs/model_comparison_rf_xgb_tabpfn_final_snapshot/tables/RF_XGBOOST_TABPFN_OCCURRENCE_COMPARISON.csv"
ENSO = PROJECT / "4.Modelling/articles/tables/temporal_enso/NOAA_RONI_FROST_SEASON_2000_2025.csv"
YEARS = list(range(2000, 2026))
SEED = 20260807


def load_script(name: str, filename: str):
    path = MODULE / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def batched_probability(model, matrix: np.ndarray, classifier: bool, batch: int = 2000) -> np.ndarray:
    chunks = []
    for start in range(0, len(matrix), batch):
        x = matrix[start:start + batch]
        if classifier:
            chunks.append(model.predict_proba(x)[:, 1])
        else:
            chunks.append(np.clip(model.predict(x), 0, 1))
    return np.concatenate(chunks).astype(np.float32)


def fit_models(work: pd.DataFrame, candidates: list[str], terrain: list[str], comparison):
    y = work.frost_any.astype(int).to_numpy()
    selected = comparison.select_features(work, y, candidates, terrain)
    imputer = SimpleImputer(strategy="median")
    x = imputer.fit_transform(work[selected]).astype(np.float32)
    rf = RandomForestClassifier(
        n_estimators=900, max_depth=18, min_samples_leaf=5, max_features="sqrt",
        class_weight="balanced_subsample", n_jobs=-1, random_state=SEED,
    ).fit(x, y)
    # Modal/central configuration from nested grouped tuning; no retuning on the map support.
    xgb = XGBClassifier(
        n_estimators=420, objective="binary:logistic", eval_metric="auc", tree_method="hist",
        device="cuda", max_depth=5, learning_rate=0.03, min_child_weight=5,
        subsample=0.85, colsample_bytree=0.75, reg_lambda=2.0, reg_alpha=0.05,
        random_state=SEED, n_jobs=4,
    ).fit(x, y)
    tabc = TabPFNClassifier(
        device="cuda", n_estimators=8, balance_probabilities=True,
        fit_mode="fit_preprocessors", random_state=SEED, show_progress_bar=False,
    ).fit(x, y)
    tabr = TabPFNRegressor(
        device="cuda", n_estimators=8, fit_mode="fit_preprocessors",
        random_state=SEED, show_progress_bar=False,
    ).fit(x, y.astype(np.float32))
    return selected, imputer, rf, xgb, tabc, tabr


def plot_grid(points: pd.DataFrame, boundaries: gpd.GeoDataFrame, panels: list[tuple[str, str]],
              filename: str, metrics: dict[str, dict] | None = None):
    n = len(panels)
    cols = 2 if n > 1 else 1
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(12.4, 5.4 * rows), squeeze=False)
    for ax, (column, title) in zip(axes.ravel(), panels):
        subtitle = ""
        if metrics and title in metrics:
            m = metrics[title]
            subtitle = f"\nAUC {m['roc_auc']:.3f} | PR-AUC {m['pr_auc']:.3f} | BA {m['balanced_accuracy']:.3f}"
        art = ax.scatter(points.longitude, points.latitude, c=points[column], cmap="RdYlBu",
                         vmin=0, vmax=1, s=3.0, linewidths=0, rasterized=True)
        boundaries.boundary.plot(ax=ax, color="#222222", linewidth=0.55)
        ax.set_title(title + subtitle, fontsize=11)
        ax.set_axis_off()
    for ax in axes.ravel()[n:]:
        ax.set_visible(False)
    bar = fig.colorbar(art, ax=axes.ravel().tolist(), fraction=0.022, pad=0.012, shrink=0.82)
    bar.set_label("Annual frost-occurrence probability (blue = higher)")
    fig.subplots_adjust(left=0.02, right=0.91, top=0.96, bottom=0.025, wspace=0.03, hspace=0.08)
    light = FIGURES / f"{filename}_LIGHT.png"
    hd = FIGURES / f"{filename}_620DPI.png"
    pdf = FIGURES / f"{filename}.pdf"
    fig.savefig(light, dpi=170, facecolor="white", bbox_inches="tight")
    fig.savefig(hd, dpi=620, facecolor="white", bbox_inches="tight")
    fig.savefig(pdf, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return [str(light), str(hd), str(pdf)]


def main() -> int:
    for path in [OUT, TABLES, FIGURES, MODELS]:
        path.mkdir(parents=True, exist_ok=True)
    core = load_script("balanced_map_core", "08_run_five_state_50000_smoke.py")
    validation = load_script("balanced_map_validation", "11_validate_historical_paired_models.py")
    predictor = load_script("balanced_map_predictor", "12_predict_historical_paired_200000.py")
    comparison = load_script("balanced_map_comparison", "27_compare_rf_xgb_tabpfn_block_balanced.py")

    table, candidates, _ = validation.build_table(core)
    work = table.loc[table.frost_any.notna()].reset_index(drop=True)
    points = pd.read_parquet(SOURCE_POINTS)
    keep = ["point_id", "state", "longitude", "latitude"] + list(core.TERRAIN_FEATURES)
    points = points[keep].copy()
    counts = points.groupby("state").size().to_dict()
    if len(points) != 10_000 or set(counts.values()) != {2000}:
        raise RuntimeError(f"Expected exactly 2,000 points/state; got {counts}")

    selected, imputer, rf, xgb, tabc, tabr = fit_models(work, candidates, list(core.TERRAIN_FEATURES), comparison)
    pd.DataFrame({"feature": selected}).assign(
        block=lambda d: np.select(
            [d.feature.str.startswith("era5__"), d.feature.str.startswith("modis_")],
            ["ERA5-Land", "MODIS"], default="Terrain/HAND/space/time"),
    ).to_csv(TABLES / "FINAL_BLOCK_BALANCED_FEATURES.csv", index=False)
    joblib.dump({"features": selected, "imputer": imputer, "rf": rf, "xgb": xgb},
                MODELS / "RF_XGBOOST_BLOCK_BALANCED_FINAL.joblib")

    era5_features = [x for x in selected if x.startswith("era5__")]
    modis_features = [x for x in selected if x.startswith("modis_")]
    era5 = core.load_era5_wide().loc[lambda d: d.year.between(2000, 2025)]
    modis = predictor.load_modis().loc[lambda d: d.year.between(2000, 2025)]
    static = points[["latitude", "longitude"] + list(core.TERRAIN_FEATURES)].reset_index(drop=True)
    predictions = {name: [] for name in ["rf", "xgb", "tabpfn_classifier", "tabpfn_regressor"]}
    coverage = []
    for year in YEARS:
        e = era5.loc[era5.year.eq(year)].drop_duplicates(["source", "station_id"])
        m = modis.loc[modis.year.eq(year)].drop_duplicates(["source", "station_id"])
        em = core.idw_lookup(e, points, era5_features, k=4)
        mm = predictor.interpolate_or_missing(core, m, points, modis_features)
        matrix = pd.concat([static, pd.DataFrame(em, columns=era5_features),
                            pd.DataFrame(mm, columns=modis_features)], axis=1)
        matrix.insert(2, "year", year)
        x = imputer.transform(matrix[selected]).astype(np.float32)
        predictions["rf"].append(rf.predict_proba(x)[:, 1].astype(np.float32))
        predictions["xgb"].append(xgb.predict_proba(x)[:, 1].astype(np.float32))
        predictions["tabpfn_classifier"].append(batched_probability(tabc, x, True))
        predictions["tabpfn_regressor"].append(batched_probability(tabr, x, False))
        coverage.append({"year": year, "era5_locations": len(e), "modis_locations": len(m)})
        np.savez_compressed(TABLES / "ANNUAL_PREDICTIONS_PARTIAL.npz",
                            years=np.array(YEARS[:len(predictions['rf'])]),
                            **{k: np.stack(v) for k, v in predictions.items()})
        print(f"BALANCED_10000_YEAR_OK={year}", flush=True)

    for key in predictions:
        predictions[key] = np.stack(predictions[key])
        points[f"{key}_all_years_mean"] = predictions[key].mean(axis=0)
    points.to_parquet(TABLES / "BALANCED_MODELS_10000_ALL_YEARS.parquet", index=False)
    pd.DataFrame(coverage).to_csv(TABLES / "ANNUAL_ENVIRONMENTAL_COVERAGE.csv", index=False)
    np.savez_compressed(TABLES / "ANNUAL_PREDICTIONS_2000_2025.npz", years=np.array(YEARS), **predictions)

    stats = pd.read_csv(METRICS).set_index("model").to_dict(orient="index")
    labels = {"rf": "Random Forest balanced", "xgb": "XGBoost tuned",
              "tabpfn_classifier": "TabPFN classifier", "tabpfn_regressor": "TabPFN regressor"}
    outputs = []
    outputs += plot_grid(points, core.load_boundaries(),
                         [(f"{k}_all_years_mean", labels[k]) for k in labels],
                         "BALANCED_RF_XGBOOST_TABPFN_2000_2025_10000", stats)

    periods = {
        "2000-2005": list(range(2000, 2006)), "2006-2010": list(range(2006, 2011)),
        "2011-2015": list(range(2011, 2016)), "2016-2020": list(range(2016, 2021)),
        "2021-2025": list(range(2021, 2026)),
    }
    period_rows = []
    for label, years in periods.items():
        idx = [YEARS.index(y) for y in years]
        col = f"rf_period_{label.replace('-', '_')}"
        points[col] = predictions["rf"][idx].mean(axis=0)
        period_rows.append((col, label))
    outputs += plot_grid(points, core.load_boundaries(), period_rows,
                         "RF_BALANCED_FIVE_YEAR_PERIODS_10000")

    enso = pd.read_csv(ENSO)
    enso_rows = []
    enso_audit = []
    for phase in ["El Niño", "Neutral", "La Niña"]:
        years = enso.loc[enso.enso_phase.eq(phase), "year"].astype(int).tolist()
        years = [y for y in years if y in YEARS]
        idx = [YEARS.index(y) for y in years]
        slug = phase.lower().replace(" ", "_").replace("ñ", "n")
        col = f"rf_enso_{slug}"
        points[col] = predictions["rf"][idx].mean(axis=0)
        enso_rows.append((col, f"{phase} (n={len(years)} years)"))
        enso_audit.append({"phase": phase, "n_years": len(years), "years": ";".join(map(str, years))})
    outputs += plot_grid(points, core.load_boundaries(), enso_rows,
                         "RF_BALANCED_ENSO_PHASES_10000")
    points.to_parquet(TABLES / "BALANCED_MODELS_10000_PERIOD_ENSO.parquet", index=False)
    pd.DataFrame(enso_audit).to_csv(TABLES / "ENSO_YEAR_ASSIGNMENT.csv", index=False)

    del tabc, tabr
    torch.cuda.empty_cache()
    status = {
        "status": "BALANCED_MODELS_10000_TEMPORAL_ENSO_OK",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "points": len(points), "points_per_state": counts,
        "training_station_years": len(work), "features": len(selected),
        "era5_features": len(era5_features), "modis_features": len(modis_features),
        "terrain_hand_space_time_features": len(selected) - len(era5_features) - len(modis_features),
        "period_rule": "same fitted RF; annual predictions averaged within non-overlapping periods",
        "enso_rule": "same fitted RF; annual predictions averaged by NOAA RONI frost-season phase",
        "outputs": outputs,
    }
    (OUT / "BALANCED_MODELS_10000_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (OUT / "BALANCED_MODELS_10000_TEMPORAL_ENSO_OK").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
