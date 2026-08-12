from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.transform import rowcol
from rasterio.windows import Window


MODULE = Path(__file__).resolve().parents[1]
MODEL = Path(os.environ.get(
    "FROST_MODEL",
    MODULE / "outputs/balanced_models_10000_temporal_enso/models/RF_BLOCK_BALANCED_ALL_ENDPOINTS.joblib",
))
SOURCE = MODULE / "outputs/updated_historical_10000_smoke/tables/UPDATED_HISTORICAL_RF_10000_PREDICTIONS.parquet"
OUT = Path(os.environ.get("FROST_SMOKE_OUTPUT", MODULE / "outputs/hpc_rf_reduced_10000_smoke"))
YEARS = list(range(2000, 2026))
NODATA = np.float32(-9999.0)
BLOCK = 512


def load_script(name: str, filename: str):
    path = MODULE / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_sparse_point_raster(
    dem_path: Path,
    points: pd.DataFrame,
    values: np.ndarray,
    output: Path,
    tags: dict[str, str],
) -> None:
    with rasterio.open(dem_path) as dem:
        transformer = Transformer.from_crs("EPSG:4326", dem.crs, always_xy=True)
        x, y = transformer.transform(points.longitude.to_numpy(), points.latitude.to_numpy())
        rows, cols = rowcol(dem.transform, x, y)
        locations = pd.DataFrame({"row": rows, "col": cols, "value": values})
        locations = locations.loc[
            locations.row.between(0, dem.height - 1)
            & locations.col.between(0, dem.width - 1)
            & np.isfinite(locations.value)
        ].copy()
        locations = locations.groupby(["row", "col"], as_index=False).value.mean()
        locations["block_row"] = locations.row // BLOCK
        locations["block_col"] = locations.col // BLOCK
        profile = dem.profile.copy()
        profile.update(
            driver="GTiff", dtype="float32", count=1, nodata=float(NODATA),
            compress="ZSTD", predictor=3, tiled=True, blockxsize=BLOCK,
            blockysize=BLOCK, BIGTIFF="YES", SPARSE_OK="TRUE",
        )
        with rasterio.open(output, "w", **profile) as dst:
            dst.update_tags(**tags, sample_points=len(points), unique_cells=len(locations))
            for (br, bc), group in locations.groupby(["block_row", "block_col"]):
                row0, col0 = int(br) * BLOCK, int(bc) * BLOCK
                height = min(BLOCK, dem.height - row0)
                width = min(BLOCK, dem.width - col0)
                array = np.full((height, width), NODATA, np.float32)
                rr = group.row.to_numpy(int) - row0
                cc = group.col.to_numpy(int) - col0
                array[rr, cc] = group.value.to_numpy(np.float32)
                dst.write(array, 1, window=Window(col0, row0, width, height))


def plot_maps(points: pd.DataFrame, boundaries, contracts: list[tuple[str, str, str, float, float]]) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(18, 7.2))
    for ax, (column, title, cmap, vmin, vmax) in zip(axes, contracts):
        art = ax.scatter(
            points.longitude, points.latitude, c=points[column], s=4.5,
            cmap=cmap, vmin=vmin, vmax=vmax, linewidths=0, rasterized=True,
        )
        boundaries.boundary.plot(ax=ax, color="#202020", linewidth=0.55)
        ax.set_title(title, fontsize=12)
        ax.set_axis_off()
        bar = fig.colorbar(art, ax=ax, fraction=0.035, pad=0.012, shrink=0.78)
        bar.ax.tick_params(labelsize=8)
    fig.suptitle(
        "Reduced Random Forest smoke test — 2,000 points per state — 2000–2025",
        fontsize=15, y=0.98,
    )
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.02, top=0.90, wspace=0.08)
    fig.savefig(OUT / "RF_REDUCED_THREE_ENDPOINTS_10000_LIGHT.png", dpi=170, facecolor="white")
    fig.savefig(OUT / "RF_REDUCED_THREE_ENDPOINTS_10000_620DPI.png", dpi=620, facecolor="white")
    fig.savefig(OUT / "RF_REDUCED_THREE_ENDPOINTS_10000.pdf", facecolor="white")
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    core = load_script("rf_reduced_smoke_core", "08_run_five_state_50000_smoke.py")
    predictor = load_script("rf_reduced_smoke_predictor", "12_predict_historical_paired_200000.py")
    bundle = joblib.load(MODEL)
    features = list(bundle["features"])
    imputer = bundle["imputer"]
    models = bundle["models"]
    for estimator in models.values():
        if hasattr(estimator, "n_jobs"):
            estimator.n_jobs = -1

    points = pd.read_parquet(SOURCE)
    counts = points.groupby("state").size().to_dict()
    if len(points) != 10_000 or counts != {state: 2_000 for state in ["MS", "PR", "RS", "SC", "SP"]}:
        raise RuntimeError(f"Expected 2,000 points per state; obtained {counts}")
    keep = ["point_id", "state", "longitude", "latitude"] + list(core.TERRAIN_FEATURES)
    points = points[keep].copy().reset_index(drop=True)

    terrain_features = list(core.TERRAIN_FEATURES)
    era5_features = [name for name in features if name.startswith("era5__")]
    modis_features = [name for name in features if name.startswith("modis_")]
    era5 = core.load_era5_wide().loc[lambda frame: frame.year.between(2000, 2025)]
    modis = predictor.load_modis().loc[lambda frame: frame.year.between(2000, 2025)]
    static = points[["latitude", "longitude"] + terrain_features].copy()
    sums = {name: np.zeros(len(points), np.float64) for name in models}

    for year in YEARS:
        e = era5.loc[era5.year.eq(year)].drop_duplicates(["source", "station_id"])
        m = modis.loc[modis.year.eq(year)].drop_duplicates(["source", "station_id"])
        em = core.idw_lookup(e, points, era5_features, k=4)
        mm = predictor.interpolate_or_missing(core, m, points, modis_features)
        frame = pd.concat([
            static,
            pd.DataFrame(em, columns=era5_features),
            pd.DataFrame(mm, columns=modis_features),
        ], axis=1)
        frame.insert(2, "year", year)
        matrix = imputer.transform(frame[features]).astype(np.float32)
        sums["probability"] += models["probability"].predict_proba(matrix)[:, 1]
        sums["frost_days"] += np.clip(models["frost_days"].predict(matrix), 0, None)
        sums["seasonal_tmin_c"] += models["seasonal_tmin_c"].predict(matrix)
        print(f"RF_REDUCED_10000_YEAR_OK={year}", flush=True)

    for endpoint, values in sums.items():
        points[endpoint] = (values / len(YEARS)).astype(np.float32)
    points["probability"] = points.probability.clip(0, 1)
    points["frost_days"] = points.frost_days.clip(lower=0)

    config = json.loads(Path(os.environ["FROST_CONFIG"]).read_text(encoding="utf-8"))
    dem_path = Path(config["anadem_dem"])
    outputs = {
        "probability": OUT / "RF_REDUCED_FROST_PROBABILITY_ALL_2000_2025_10000_SAMPLE.tif",
        "frost_days": OUT / "RF_REDUCED_EXPECTED_FROST_DAYS_ALL_2000_2025_10000_SAMPLE.tif",
        "seasonal_tmin_c": OUT / "RF_REDUCED_SEASONAL_MINIMUM_TEMPERATURE_C_ALL_2000_2025_10000_SAMPLE.tif",
    }
    for endpoint, output in outputs.items():
        write_sparse_point_raster(
            dem_path, points, points[endpoint].to_numpy(), output,
            {"model": "reduced Random Forest", "endpoint": endpoint,
             "years": "2000-2025", "aggregation": "mean annual prediction",
             "smoothing": "none", "purpose": "distributed 10000-point HPC smoke test"},
        )

    points.to_parquet(OUT / "RF_REDUCED_THREE_ENDPOINTS_10000.parquet", index=False)
    summary = pd.DataFrame([
        {"endpoint": endpoint, "n": len(points), "minimum": float(points[endpoint].min()),
         "mean": float(points[endpoint].mean()), "maximum": float(points[endpoint].max()),
         "output": str(outputs[endpoint])}
        for endpoint in outputs
    ])
    summary.to_csv(OUT / "RF_REDUCED_THREE_ENDPOINTS_10000_SUMMARY.csv", index=False)
    frost_vmax = float(points.frost_days.quantile(0.99))
    tmin_lo, tmin_hi = map(float, points.seasonal_tmin_c.quantile([0.01, 0.99]))
    plot_maps(points, core.load_boundaries(), [
        ("probability", "Frost-occurrence probability", "RdYlBu", 0.0, 1.0),
        ("frost_days", "Expected frost days per season", "RdYlBu", 0.0, frost_vmax),
        ("seasonal_tmin_c", "Seasonal minimum temperature (°C)", "RdYlBu_r", tmin_lo, tmin_hi),
    ])
    status = {
        "status": "HPC_RF_REDUCED_10000_SMOKE_OK",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "points": len(points), "points_per_state": counts,
        "features": len(features), "era5_features": len(era5_features),
        "modis_features": len(modis_features), "years": [2000, 2025],
        "endpoints": list(outputs), "outputs": {key: str(value) for key, value in outputs.items()},
    }
    (OUT / "RUN_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (OUT / "HPC_RF_REDUCED_10000_SMOKE_OK").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
