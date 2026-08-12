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


MODULE = Path(__file__).resolve().parents[1]
DB = MODULE / "database"
SOURCE_SPATIAL = MODULE / "outputs/five_state_200000_complete/tables/FIVE_STATE_RF_200000_COMPLETE_PREDICTIONS.parquet"
MODEL_PATH = MODULE / "outputs/historical_paired_model_statistics/models/HISTORICAL_PAIRED_RF_MODELS.joblib"
OUT = MODULE / "outputs/historical_paired_200000_complete"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"
PAIR_MIN_VALID_DAYS = 5
YEARS = range(2000, 2026)


def load_core():
    path = MODULE / "scripts/08_run_five_state_50000_smoke.py"
    spec = importlib.util.spec_from_file_location("five_state_core", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_modis() -> pd.DataFrame:
    unified = DB / "MODIS_ALL_MODEL_READY_STATION_YEAR_2000_2025.parquet"
    marker = DB / "MODIS_ALL_MODEL_READY_STATION_YEAR_OK.json"
    if unified.exists() and marker.exists():
        return pd.read_parquet(unified)
    paths = sorted((DB / "modis_station_year_may15_aug15").rglob("features.parquet"))
    if len(paths) != 104:
        raise RuntimeError(f"Expected 104 MODIS station-year partitions, found {len(paths)}")
    return pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)


def interpolate_or_missing(core, source: pd.DataFrame, target: pd.DataFrame, features: list[str]) -> np.ndarray:
    if source.empty or not source[features].notna().any(axis=None):
        return np.full((len(target), len(features)), np.nan, dtype=np.float32)
    return core.idw_lookup(source, target, features, k=4)


def plot_maps(result: gpd.GeoDataFrame, boundaries: gpd.GeoDataFrame) -> tuple[Path, Path, Path]:
    panels = [
        ("annual_frost_probability_mean", "(a) Mean annual frost probability", "Probability", "RdYlBu", 0, 1),
        ("annual_frost_probability_p75", "(b) P75 annual frost probability", "Probability", "RdYlBu", 0, 1),
        ("expected_frost_days_mean", "(c) Expected frost days per season", "Days", "RdYlBu", 0, None),
        ("event_minimum_temperature_mean_c", "(d) Seasonal minimum temperature", "Temperature (°C)", "RdYlBu_r", None, None),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(12.4, 13.0))
    for ax, (column, title, label, cmap, vmin, vmax) in zip(axes.ravel(), panels):
        scatter = ax.scatter(
            result.longitude, result.latitude, c=result[column], s=1.35,
            cmap=cmap, vmin=vmin, vmax=vmax, linewidths=0, rasterized=True,
        )
        boundaries.boundary.plot(ax=ax, color="#222222", linewidth=0.55)
        ax.set_title(title, fontsize=12)
        ax.set_axis_off()
        colorbar = fig.colorbar(scatter, ax=ax, fraction=0.035, pad=0.015, shrink=0.78)
        colorbar.set_label(label, fontsize=9)
    fig.suptitle("Historical paired Random Forest — 200,000 spatial samples", fontsize=16, y=0.985)
    fig.text(
        0.5, 0.012,
        "Station-held-out RF; ANADEM terrain, HAND, ERA5-Land and QC-filtered MODIS are paired by year and 15 May–15 August season (2000–2025).",
        ha="center", fontsize=8.5,
    )
    fig.subplots_adjust(left=0.025, right=0.98, top=0.955, bottom=0.04, wspace=0.08, hspace=0.08)
    light = FIGURES / "HISTORICAL_PAIRED_RF_200000_LIGHT.png"
    hd = FIGURES / "HISTORICAL_PAIRED_RF_200000_620DPI.png"
    pdf = FIGURES / "HISTORICAL_PAIRED_RF_200000.pdf"
    fig.savefig(light, dpi=160, facecolor="white", bbox_inches="tight")
    fig.savefig(hd, dpi=620, facecolor="white", bbox_inches="tight")
    fig.savefig(pdf, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return light, hd, pdf


def main() -> int:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    core = load_core()
    boundaries = core.load_boundaries()

    source = pd.read_parquet(SOURCE_SPATIAL)
    keep = ["point_id", "state", "longitude", "latitude"] + list(core.TERRAIN_FEATURES)
    points = source[keep].copy()
    if len(points) != 200_000:
        raise RuntimeError(f"Expected 200,000 spatial support points, found {len(points)}")

    bundle = joblib.load(MODEL_PATH)
    features = list(bundle["features"])
    era5_features = [feature for feature in features if feature.startswith("era5__")]
    modis_features = [feature for feature in features if feature.startswith("modis_")]
    era5 = core.load_era5_wide().loc[lambda x: x.year.between(2000, 2025)].copy()
    modis = load_modis()

    annual_probability: list[np.ndarray] = []
    annual_days: list[np.ndarray] = []
    annual_tmin: list[np.ndarray] = []
    coverage: list[dict] = []
    static = points[["latitude", "longitude"] + list(core.TERRAIN_FEATURES)].reset_index(drop=True)

    for year in YEARS:
        era5_year = era5.loc[era5.year.eq(year)].drop_duplicates(["source", "station_id"])
        modis_year = modis.loc[
            modis.year.eq(year)
            & modis.modis_lst_day_n_valid_days.fillna(0).ge(PAIR_MIN_VALID_DAYS)
            & modis.modis_lst_night_n_valid_days.fillna(0).ge(PAIR_MIN_VALID_DAYS)
        ].drop_duplicates(["source", "station_id"])

        climate_matrix = core.idw_lookup(era5_year, points, era5_features, k=4)
        modis_matrix = interpolate_or_missing(core, modis_year, points, modis_features)
        prediction = pd.concat(
            [
                static,
                pd.DataFrame(climate_matrix, columns=era5_features),
                pd.DataFrame(modis_matrix, columns=modis_features),
            ],
            axis=1,
        )
        prediction.insert(2, "year", year)
        prediction = prediction[features]

        annual_probability.append(bundle["occurrence"].predict_proba(prediction)[:, 1].astype(np.float32))
        annual_days.append(np.clip(bundle["frost_days"].predict(prediction), 0, None).astype(np.float32))
        annual_tmin.append(bundle["seasonal_tmin"].predict(prediction).astype(np.float32))
        coverage.append({
            "year": year,
            "era5_source_locations": int(len(era5_year)),
            "modis_paired_source_locations": int(len(modis_year)),
        })
        print(f"HISTORICAL_PAIRED_PREDICTION_YEAR_OK={year}", flush=True)

    probability = np.stack(annual_probability)
    days = np.stack(annual_days)
    tmin = np.stack(annual_tmin)
    result = points.copy()
    result["annual_frost_probability_mean"] = probability.mean(axis=0)
    result["annual_frost_probability_p75"] = np.quantile(probability, 0.75, axis=0)
    result["expected_frost_days_mean"] = days.mean(axis=0)
    result["expected_frost_days_p75"] = np.quantile(days, 0.75, axis=0)
    result["event_minimum_temperature_mean_c"] = tmin.mean(axis=0)
    result["event_minimum_temperature_p25_c"] = np.quantile(tmin, 0.25, axis=0)
    result.to_parquet(TABLES / "HISTORICAL_PAIRED_RF_200000_PREDICTIONS.parquet", index=False)
    result.head(1000).to_csv(TABLES / "HISTORICAL_PAIRED_RF_200000_PREDICTIONS_PREVIEW.csv", index=False)
    pd.DataFrame(coverage).to_csv(TABLES / "HISTORICAL_PAIRED_RF_200000_TEMPORAL_COVERAGE.csv", index=False)

    geo = gpd.GeoDataFrame(result, geometry=gpd.points_from_xy(result.longitude, result.latitude), crs=4326)
    geo[[
        "point_id", "state", "annual_frost_probability_mean", "annual_frost_probability_p75",
        "expected_frost_days_mean", "expected_frost_days_p75",
        "event_minimum_temperature_mean_c", "event_minimum_temperature_p25_c", "geometry",
    ]].to_file(OUT / "HISTORICAL_PAIRED_RF_200000_PREDICTIONS.gpkg", driver="GPKG")
    light, hd, pdf = plot_maps(geo, boundaries)

    status = {
        "status": "HISTORICAL_PAIRED_RF_200000_OK",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "points": int(len(result)),
        "points_per_state": result.groupby("state").size().astype(int).to_dict(),
        "season": "15 May-15 August",
        "years": [2000, 2025],
        "model_features": int(len(features)),
        "era5_features": int(len(era5_features)),
        "modis_features": int(len(modis_features)),
        "terrain_hand_features": int(len(core.TERRAIN_FEATURES)),
        "modis_temporal_rule": "QC-filtered station-year values; at least five valid day and night observations",
        "spatial_climate_transfer": "inverse-distance weighting from annual station support (k=4)",
        "light_map": str(light),
        "hd_map": str(hd),
        "pdf_map": str(pdf),
    }
    (OUT / "HISTORICAL_PAIRED_RF_200000_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (OUT / "HISTORICAL_PAIRED_RF_200000_OK").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
