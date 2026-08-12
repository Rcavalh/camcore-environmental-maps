from __future__ import annotations

import importlib.util
import json
import os
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
SOURCE = MODULE / "outputs/five_state_200000_complete/tables/FIVE_STATE_RF_200000_COMPLETE_PREDICTIONS.parquet"
MODEL = MODULE / "outputs/historical_paired_model_statistics/models/HISTORICAL_PAIRED_RF_MODELS.joblib"
OUT = MODULE / "outputs/updated_historical_10000_smoke"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"
N_POINTS = int(os.environ.get("FROST_SMOKE_POINTS", "10000"))
SEED = 20260806
YEARS = range(2000, 2026)
MIN_VALID_DAYS = 5


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, MODULE / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def stratified_sample(frame: pd.DataFrame) -> pd.DataFrame:
    states = sorted(frame.state.dropna().unique())
    base, remainder = divmod(N_POINTS, len(states))
    chunks = []
    for index, state in enumerate(states):
        n = base + int(index < remainder)
        subset = frame.loc[frame.state.eq(state)]
        chunks.append(subset.sample(n=min(n, len(subset)), random_state=SEED + index))
    result = pd.concat(chunks, ignore_index=True)
    if len(result) != N_POINTS:
        raise RuntimeError(f"Requested {N_POINTS:,} points but selected {len(result):,}")
    return result.sample(frac=1, random_state=SEED).reset_index(drop=True)


def draw_maps(result: gpd.GeoDataFrame, boundaries: gpd.GeoDataFrame) -> list[Path]:
    panels = [
        ("annual_frost_probability_mean", "(a) Mean annual frost probability", "Probability", "RdYlBu", 0, 1),
        ("annual_frost_probability_p75", "(b) P75 annual frost probability", "Probability", "RdYlBu", 0, 1),
        ("expected_frost_days_mean", "(c) Expected frost days", "Days per season", "RdYlBu", 0, None),
        ("event_minimum_temperature_mean_c", "(d) Seasonal minimum temperature", "Temperature (°C)", "RdYlBu_r", None, None),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(12.4, 13.0))
    for ax, (column, title, label, cmap, vmin, vmax) in zip(axes.ravel(), panels):
        artist = ax.scatter(result.longitude, result.latitude, c=result[column], s=2.2, cmap=cmap,
                            vmin=vmin, vmax=vmax, linewidths=0, rasterized=True)
        boundaries.boundary.plot(ax=ax, color="#202020", linewidth=0.55)
        ax.set_title(title, fontsize=11.5)
        ax.set_axis_off()
        bar = fig.colorbar(artist, ax=ax, fraction=0.035, pad=0.015, shrink=0.78)
        bar.set_label(label, fontsize=9)
    fig.suptitle(f"Five-state historical RF smoke — {len(result):,} stratified cells", fontsize=15, y=0.985)
    fig.text(0.5, 0.012, "ANADEM 30 m + HAND + ERA5-Land + QC-filtered MODIS; 15 May–15 August, 2000–2025.",
             ha="center", fontsize=8.5)
    fig.subplots_adjust(left=0.025, right=0.98, top=0.955, bottom=0.04, wspace=0.08, hspace=0.08)
    paths = [FIGURES / "UPDATED_HISTORICAL_RF_10000_LIGHT.png", FIGURES / "UPDATED_HISTORICAL_RF_10000_620DPI.png",
             FIGURES / "UPDATED_HISTORICAL_RF_10000.pdf"]
    fig.savefig(paths[0], dpi=160, facecolor="white", bbox_inches="tight")
    fig.savefig(paths[1], dpi=620, facecolor="white", bbox_inches="tight")
    fig.savefig(paths[2], facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return paths


def main() -> int:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    core = load_script("five_state_core_updated_smoke", "08_run_five_state_50000_smoke.py")
    predictor = load_script("historical_200k_helpers", "12_predict_historical_paired_200000.py")
    source = pd.read_parquet(SOURCE)
    points = stratified_sample(source[["point_id", "state", "longitude", "latitude"] + list(core.TERRAIN_FEATURES)])
    bundle = joblib.load(MODEL)
    features = list(bundle["features"])
    era5_features = [name for name in features if name.startswith("era5__")]
    modis_features = [name for name in features if name.startswith("modis_")]
    era5 = core.load_era5_wide().loc[lambda x: x.year.between(2000, 2025)]
    modis = predictor.load_modis()
    static = points[["latitude", "longitude"] + list(core.TERRAIN_FEATURES)].reset_index(drop=True)
    probability, days, tmin, coverage = [], [], [], []
    for year in YEARS:
        era5_year = era5.loc[era5.year.eq(year)].drop_duplicates(["source", "station_id"])
        modis_year = modis.loc[
            modis.year.eq(year)
            & modis.modis_lst_day_n_valid_days.fillna(0).ge(MIN_VALID_DAYS)
            & modis.modis_lst_night_n_valid_days.fillna(0).ge(MIN_VALID_DAYS)
        ].drop_duplicates(["source", "station_id"])
        era5_matrix = core.idw_lookup(era5_year, points, era5_features, k=4)
        modis_matrix = predictor.interpolate_or_missing(core, modis_year, points, modis_features)
        matrix = pd.concat([static, pd.DataFrame(era5_matrix, columns=era5_features),
                            pd.DataFrame(modis_matrix, columns=modis_features)], axis=1)
        matrix.insert(2, "year", year)
        matrix = matrix[features]
        probability.append(bundle["occurrence"].predict_proba(matrix)[:, 1].astype(np.float32))
        days.append(np.clip(bundle["frost_days"].predict(matrix), 0, None).astype(np.float32))
        tmin.append(bundle["seasonal_tmin"].predict(matrix).astype(np.float32))
        coverage.append({"year": year, "era5_locations": len(era5_year), "modis_locations": len(modis_year)})
        print(f"UPDATED_SMOKE_YEAR_OK={year}", flush=True)
    probability, days, tmin = map(np.stack, (probability, days, tmin))
    result = points.copy()
    result["annual_frost_probability_mean"] = probability.mean(axis=0)
    result["annual_frost_probability_p75"] = np.quantile(probability, 0.75, axis=0)
    result["expected_frost_days_mean"] = days.mean(axis=0)
    result["expected_frost_days_p75"] = np.quantile(days, 0.75, axis=0)
    result["event_minimum_temperature_mean_c"] = tmin.mean(axis=0)
    result["event_minimum_temperature_p25_c"] = np.quantile(tmin, 0.25, axis=0)
    result.to_parquet(TABLES / "UPDATED_HISTORICAL_RF_10000_PREDICTIONS.parquet", index=False)
    result.head(1000).to_csv(TABLES / "UPDATED_HISTORICAL_RF_10000_PREVIEW.csv", index=False)
    pd.DataFrame(coverage).to_csv(TABLES / "UPDATED_HISTORICAL_RF_10000_TEMPORAL_COVERAGE.csv", index=False)
    geo = gpd.GeoDataFrame(result, geometry=gpd.points_from_xy(result.longitude, result.latitude), crs=4326)
    paths = draw_maps(geo, core.load_boundaries())
    status = {
        "status": "UPDATED_HISTORICAL_RF_10000_SMOKE_OK", "completed_at": datetime.now(timezone.utc).isoformat(),
        "points": len(result), "points_per_state": result.groupby("state").size().astype(int).to_dict(),
        "years": [2000, 2025], "features": len(features), "era5_features": len(era5_features),
        "modis_features": len(modis_features), "terrain_hand_features": len(core.TERRAIN_FEATURES),
        "outputs": [str(path) for path in paths],
    }
    (OUT / "UPDATED_HISTORICAL_RF_10000_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (OUT / "UPDATED_HISTORICAL_RF_10000_SMOKE_OK").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
