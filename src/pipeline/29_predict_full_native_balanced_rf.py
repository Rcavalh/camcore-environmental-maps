from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import gc
import importlib.util
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Parallelize at two levels: independent years and trees inside each forest.
# Defaults target the 24 physical cores of the local workstation (6 x 4).
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("GDAL_CACHEMAX", "1024")

import joblib
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window
from scipy.spatial import cKDTree


MODULE = Path(__file__).resolve().parents[1]
PROJECT = MODULE.parent.parent
CONFIG = Path(os.environ.get("FROST_CONFIG", MODULE / "config/source_roots.json"))
MODEL = Path(os.environ.get(
    "FROST_MODEL",
    MODULE / "outputs/balanced_models_10000_temporal_enso/models/RF_BLOCK_BALANCED_ALL_ENDPOINTS.joblib",
))
OUT = Path(os.environ.get(
    "FROST_OUTPUT",
    MODULE / "outputs/full_native_five_state_rf_balanced_all_endpoints_period_enso",
))
ENSO_PATH = Path(os.environ.get(
    "FROST_ENSO",
    PROJECT / "4.Modelling/articles/tables/temporal_enso/NOAA_RONI_FROST_SEASON_2000_2025.csv",
))
NODATA = np.float32(-9999.0)
YEARS = list(range(2000, 2026))
CHUNK = int(os.environ.get("FROST_PREDICTION_CHUNK", "45000"))
FLUSH_EVERY = int(os.environ.get("FROST_FLUSH_EVERY", "20"))
YEAR_WORKERS = int(os.environ.get("FROST_YEAR_WORKERS", "6"))
MODEL_WORKERS = int(os.environ.get("FROST_MODEL_WORKERS", "4"))
ZSTD_LEVEL = int(os.environ.get("FROST_ZSTD_LEVEL", "1"))
TMIN_AGGREGATION = os.environ.get("FROST_TMIN_AGGREGATION", "mean").strip().lower()
if TMIN_AGGREGATION not in {"mean", "p25"}:
    raise ValueError("FROST_TMIN_AGGREGATION must be mean or p25")
ENDPOINT_LABELS = {
    "probability": "FROST_PROBABILITY",
    "frost_days": "EXPECTED_FROST_DAYS",
    "seasonal_tmin_c": "SEASONAL_MINIMUM_TEMPERATURE_C",
}


def scenario_years() -> dict[str, list[int]]:
    scenario_set = os.environ.get("FROST_SCENARIO_SET", "all").strip().lower()
    if scenario_set in {"all_period_only", "all_2000_2025", "climatology"}:
        return {"ALL_2000_2025": YEARS}
    if scenario_set != "all":
        raise ValueError(
            "FROST_SCENARIO_SET must be 'all' or 'all_period_only'; "
            f"received {scenario_set!r}"
        )
    scenarios = {
        "ALL_2000_2025": YEARS,
        "PERIOD_2000_2005": list(range(2000, 2006)),
        "PERIOD_2006_2010": list(range(2006, 2011)),
        "PERIOD_2011_2015": list(range(2011, 2016)),
        "PERIOD_2016_2020": list(range(2016, 2021)),
        "PERIOD_2021_2025": list(range(2021, 2026)),
    }
    enso = pd.read_csv(ENSO_PATH)
    for phase, slug in [("El Niño", "ENSO_EL_NINO"), ("Neutral", "ENSO_NEUTRAL"), ("La Niña", "ENSO_LA_NINA")]:
        scenarios[slug] = enso.loc[enso.enso_phase.eq(phase), "year"].astype(int).loc[lambda s: s.between(2000, 2025)].tolist()
    return scenarios


def load_script(name: str, filename: str):
    path = MODULE / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_engine():
    path = MODULE.parents[1] / "4.Modelling/scripts/58_build_rf_50km_fold_test.py"
    spec = importlib.util.spec_from_file_location("balanced_full_terrain", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class AnnualIDW:
    def __init__(self, frame: pd.DataFrame, features: list[str], k: int = 4):
        self.features = features
        self.empty = frame.empty or not features
        if self.empty:
            return
        self.k = min(k, len(frame))
        self.tree = cKDTree(frame[["longitude", "latitude"]].to_numpy(float))
        self.values = frame[features].apply(pd.to_numeric, errors="coerce").to_numpy(np.float32)

    def query(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        if self.empty:
            return np.full((len(lon), len(self.features)), np.nan, np.float32)
        distance, index = self.tree.query(np.column_stack([lon, lat]), k=self.k)
        if self.k == 1:
            distance, index = distance[:, None], index[:, None]
        weights = 1.0 / np.maximum(distance, 1e-8) ** 2
        source = self.values[index]
        valid = np.isfinite(source)
        numerator = np.where(valid, source * weights[:, :, None], 0).sum(axis=1)
        denominator = np.where(valid, weights[:, :, None], 0).sum(axis=1)
        return np.divide(
            numerator,
            denominator,
            out=np.full_like(numerator, np.nan),
            where=denominator > 0,
        ).astype(np.float32, copy=False)


def grids_are_effectively_aligned(left, right, atol: float = 1e-9) -> bool:
    """Accept sub-floating-point header drift without resampling an identical grid."""
    return (
        left.width == right.width
        and left.height == right.height
        and left.crs == right.crs
        and np.allclose(tuple(left.transform), tuple(right.transform), rtol=0.0, atol=atol)
    )


def tile_windows(source, size: int):
    total = math.ceil(source.height / size) * math.ceil(source.width / size)
    number = 0
    for row in range(0, source.height, size):
        for col in range(0, source.width, size):
            number += 1
            yield number, total, Window(col, row, min(size, source.width-col), min(size, source.height-row))


def main(args) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    global_checkpoints = OUT / "checkpoints"; global_checkpoints.mkdir(exist_ok=True)
    run_out = (OUT if args.shard_count == 1 else
               OUT / f"shards_{args.tile_size}" /
               f"shard_{args.shard_index:02d}_of_{args.shard_count:02d}")
    run_out.mkdir(parents=True, exist_ok=True)
    checkpoints = run_out / "checkpoints"; checkpoints.mkdir(exist_ok=True)
    raster_dir = run_out / "rasters"; raster_dir.mkdir(exist_ok=True)
    core = load_script("balanced_full_core", "08_run_five_state_50000_smoke.py")
    predictor = load_script("balanced_full_predictor", "12_predict_historical_paired_200000.py")
    bundle = joblib.load(MODEL)
    features = list(bundle["features"])
    imputer, models = bundle["imputer"], bundle["models"]
    for estimator in models.values():
        if hasattr(estimator, "n_jobs"):
            estimator.n_jobs = MODEL_WORKERS
    terrain_features = list(core.TERRAIN_FEATURES)
    era5_features = [x for x in features if x.startswith("era5__")]
    modis_features = [x for x in features if x.startswith("modis_")]
    era5 = core.load_era5_wide().loc[lambda d: d.year.between(2000, 2025)]
    modis = predictor.load_modis().loc[lambda d: d.year.between(2000, 2025)]
    annual = {}
    for year in YEARS:
        annual[year] = (
            AnnualIDW(era5.loc[era5.year.eq(year)].drop_duplicates(["source", "station_id"]), era5_features),
            AnnualIDW(modis.loc[modis.year.eq(year)].drop_duplicates(["source", "station_id"]), modis_features),
        )
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    engine = load_engine(); engine.TEST_RESOLUTION_M = 30.0
    halo = int(math.ceil(2000 / 30.0)) + 5
    scenarios = scenario_years()
    memberships = {year: [name for name, members in scenarios.items() if year in members] for year in YEARS}
    dem_path, hand_path = Path(cfg["anadem_dem"]), Path(cfg["anadem_hand_2000m"])
    output_paths = {
        (endpoint, scenario): raster_dir / f"RF_BALANCED_{ENDPOINT_LABELS[endpoint]}_{scenario}_ANADEM30M.tif"
        for endpoint in ENDPOINT_LABELS for scenario in scenarios
    }
    if TMIN_AGGREGATION == "p25":
        for scenario in scenarios:
            output_paths[("seasonal_tmin_c", scenario)] = raster_dir / (
                f"RF_BALANCED_SEASONAL_MINIMUM_TEMPERATURE_C_P25_{scenario}_ANADEM30M.tif"
            )
    completed = 0
    completed_valid = 0
    with rasterio.open(dem_path) as dem_src, rasterio.open(hand_path) as hand_native:
        hand_is_aligned = grids_are_effectively_aligned(dem_src, hand_native)
        hand_context = (
            contextlib.nullcontext(hand_native)
            if hand_is_aligned
            else WarpedVRT(
                hand_native,
                crs=dem_src.crs,
                transform=dem_src.transform,
                width=dem_src.width,
                height=dem_src.height,
                resampling=Resampling.bilinear,
                nodata=hand_native.nodata,
            )
        )
        print(f"FROST_HAND_DIRECT_READ={int(hand_is_aligned)}", flush=True)
        with hand_context as hand_src:
            profile = dem_src.profile.copy()
            profile.update(driver="GTiff", dtype="float32", count=1, nodata=float(NODATA),
                           compress="ZSTD", predictor=3, tiled=True, blockxsize=512,
                           blockysize=512, BIGTIFF="YES", SPARSE_OK="TRUE",
                           zstd_level=ZSTD_LEVEL)
            for (endpoint, scenario), output_path in output_paths.items():
                if not output_path.exists():
                    with rasterio.open(output_path, "w", **profile) as dst:
                        dst.update_tags(model="block-balanced Random Forest endpoint model",
                                        features=f"{len(features)} ({len(era5_features)} ERA5, {len(modis_features)} MODIS, 16 terrain/HAND plus space/time)",
                                        endpoint=endpoint, scenario=scenario, years=",".join(map(str, scenarios[scenario])),
                                        aggregation=("25th percentile of annual predictions"
                                                     if endpoint == "seasonal_tmin_c" and TMIN_AGGREGATION == "p25"
                                                     else "mean of annual predictions"),
                                        smoothing="none")
            writers = {name: rasterio.open(path, "r+") for name, path in output_paths.items()}
            pending_markers = []
            try:
                for number, total, core_window in tile_windows(dem_src, args.tile_size):
                    if (number - 1) % args.shard_count != args.shard_index:
                        continue
                    marker = checkpoints / f"tile_r{int(core_window.row_off):06d}_c{int(core_window.col_off):06d}.json"
                    global_marker = global_checkpoints / marker.name
                    if marker.exists() or (args.shard_count > 1 and global_marker.exists()):
                        continue
                    tile_started = time.perf_counter()
                    row0, col0 = max(int(core_window.row_off)-halo, 0), max(int(core_window.col_off)-halo, 0)
                    row1 = min(int(core_window.row_off+core_window.height)+halo, dem_src.height)
                    col1 = min(int(core_window.col_off+core_window.width)+halo, dem_src.width)
                    expanded = Window(col0, row0, col1-col0, row1-row0)
                    dem = dem_src.read(1, window=expanded, masked=True).filled(np.nan).astype(np.float32)
                    raw_hand = hand_src.read(1, window=expanded, masked=True).filled(np.nan).astype(np.float32)
                    hand = np.where(np.isfinite(raw_hand) & (raw_hand != 0), raw_hand, np.nan).astype(np.float32)
                    lr0, lc0 = int(core_window.row_off)-row0, int(core_window.col_off)-col0
                    lr1, lc1 = lr0+int(core_window.height), lc0+int(core_window.width)
                    valid = np.isfinite(dem[lr0:lr1, lc0:lc1])
                    output = np.full(valid.shape, NODATA, np.float32)
                    n = int(valid.sum())
                    if n:
                        terrain_stack = engine.terrain_stack(dem, hand)
                        terrain = {name: terrain_stack[name][lr0:lr1, lc0:lc1] for name in terrain_features}
                        rows, cols = np.where(valid)
                        rr = rows + int(core_window.row_off); cc = cols + int(core_window.col_off)
                        lon, lat = rasterio.transform.xy(dem_src.transform, rr, cc, offset="center")
                        lon, lat = np.asarray(lon, np.float32), np.asarray(lat, np.float32)
                        sums = {
                            endpoint: {name: np.zeros(n, np.float32) for name in scenarios}
                            for endpoint in ENDPOINT_LABELS
                        }
                        annual_tmin = (
                            np.empty((len(YEARS), n), dtype=np.float32)
                            if TMIN_AGGREGATION == "p25" else None
                        )
                        def predict_year(year):
                            era_i, mod_i = annual[year]
                            result = {endpoint: np.empty(n, np.float32) for endpoint in ENDPOINT_LABELS}
                            for start in range(0, n, CHUNK):
                                stop = min(start + CHUNK, n)
                                frame = pd.DataFrame(index=np.arange(stop-start), columns=features, dtype=np.float32)
                                frame["latitude"] = lat[start:stop]; frame["longitude"] = lon[start:stop]; frame["year"] = year
                                for name in terrain_features:
                                    if name in frame:
                                        frame[name] = terrain[name][rows[start:stop], cols[start:stop]]
                                ev = era_i.query(lon[start:stop], lat[start:stop])
                                mv = mod_i.query(lon[start:stop], lat[start:stop])
                                for j, name in enumerate(era5_features): frame[name] = ev[:, j]
                                for j, name in enumerate(modis_features): frame[name] = mv[:, j]
                                x = imputer.transform(frame[features]).astype(np.float32)
                                annual_values = {
                                    "probability": models["probability"].predict_proba(x)[:, 1],
                                    "frost_days": np.clip(models["frost_days"].predict(x), 0, None),
                                    "seasonal_tmin_c": models["seasonal_tmin_c"].predict(x),
                                }
                                for endpoint, values in annual_values.items():
                                    result[endpoint][start:stop] = values
                            return year, result

                        with concurrent.futures.ThreadPoolExecutor(max_workers=YEAR_WORKERS) as pool:
                            futures = [pool.submit(predict_year, year) for year in YEARS]
                            for future in concurrent.futures.as_completed(futures):
                                year, annual_values = future.result()
                                if annual_tmin is not None:
                                    annual_tmin[year - YEARS[0], :] = annual_values["seasonal_tmin_c"]
                                for scenario in memberships[year]:
                                    for endpoint, values in annual_values.items():
                                        sums[endpoint][scenario] += values
                        scenario_values = {
                            (endpoint, scenario): (
                                np.clip(values / len(scenarios[scenario]), 0, 1).astype(np.float32)
                                if endpoint == "probability" else
                                np.clip(values / len(scenarios[scenario]), 0, None).astype(np.float32)
                                if endpoint == "frost_days" else
                                (values / len(scenarios[scenario])).astype(np.float32)
                            )
                            for endpoint, endpoint_sums in sums.items()
                            for scenario, values in endpoint_sums.items()
                        }
                        if annual_tmin is not None:
                            for scenario, members in scenarios.items():
                                indices = np.asarray([year - YEARS[0] for year in members], dtype=int)
                                scenario_values[("seasonal_tmin_c", scenario)] = np.percentile(
                                    annual_tmin[indices, :], 25, axis=0
                                ).astype(np.float32)
                        vmin = {name: float(values.min()) for name, values in scenario_values.items()}
                        vmax = {name: float(values.max()) for name, values in scenario_values.items()}
                    else:
                        scenario_values = {name: np.empty(0, np.float32) for name in output_paths}
                        vmin = {name: None for name in output_paths}; vmax = {name: None for name in output_paths}
                    for name, writer in writers.items():
                        output.fill(NODATA)
                        if n:
                            output[valid] = scenario_values[name]
                        writer.write(output, 1, window=core_window)
                    serial_min = {f"{a}__{b}": value for (a, b), value in vmin.items()}
                    serial_max = {f"{a}__{b}": value for (a, b), value in vmax.items()}
                    pending_markers.append((marker, {"tile": number, "total": total, "valid": n,
                                                     "min": serial_min, "max": serial_max}))
                    completed += 1
                    if n:
                        completed_valid += 1
                    tile_seconds = max(time.perf_counter() - tile_started, 1e-9)
                    print(
                        f"FULL_BALANCED_RF_TILE_OK={number}/{total} valid={n} run={completed} "
                        f"seconds={tile_seconds:.3f} valid_pixels_per_second={n/tile_seconds:.1f}",
                        flush=True,
                    )
                    del dem, raw_hand, hand, output
                    if n:
                        del terrain_stack, terrain, rows, cols, rr, cc, lon, lat, sums, scenario_values
                        if annual_tmin is not None:
                            del annual_tmin
                    gc.collect()
                    if completed % FLUSH_EVERY == 0:
                        for writer in writers.values(): writer.close()
                        for marker_path, record in pending_markers:
                            marker_path.write_text(json.dumps(record), encoding="utf-8")
                        pending_markers.clear()
                        writers = {name: rasterio.open(path, "r+") for name, path in output_paths.items()}
                        print(f"FULL_BALANCED_RF_FLUSH_OK={completed}", flush=True)
                    if args.max_tiles and completed >= args.max_tiles:
                        break
                    if args.max_valid_tiles and completed_valid >= args.max_valid_tiles:
                        break
            finally:
                for writer in writers.values():
                    writer.close()
                for marker_path, record in pending_markers:
                    marker_path.write_text(json.dumps(record), encoding="utf-8")
    partial_run = bool(args.max_tiles or args.max_valid_tiles)
    status = {"status": "FULL_NATIVE_BALANCED_RF_PARTIAL" if partial_run else "FULL_NATIVE_BALANCED_RF_OK",
              "updated_at": datetime.now(timezone.utc).isoformat(), "completed_tiles": len(list(checkpoints.glob("tile_*.json"))),
              "features": len(features), "era5_features": len(era5_features), "modis_features": len(modis_features),
              "years": [2000, 2025], "year_workers": YEAR_WORKERS,
              "model_workers": MODEL_WORKERS, "prediction_chunk": CHUNK,
              "tile_size": args.tile_size, "flush_every": FLUSH_EVERY,
              "zstd_level": ZSTD_LEVEL, "tmin_aggregation": TMIN_AGGREGATION,
              "scenarios": scenarios,
              "rasters": {f"{endpoint}__{scenario}": str(path)
                          for (endpoint, scenario), path in output_paths.items()}}
    status["shard_index"] = args.shard_index
    status["shard_count"] = args.shard_count
    (run_out / "RUN_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    if not partial_run:
        marker_name = ("FULL_NATIVE_BALANCED_RF_OK" if args.shard_count == 1 else
                       f"SHARD_{args.shard_index:02d}_OF_{args.shard_count:02d}_OK")
        (run_out / marker_name).write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tile-size", type=int, default=512)
    parser.add_argument("--max-tiles", type=int, default=0)
    parser.add_argument("--max-valid-tiles", type=int, default=0)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parsed = parser.parse_args()
    if parsed.shard_count < 1 or not 0 <= parsed.shard_index < parsed.shard_count:
        parser.error("--shard-index must be in [0, --shard-count)")
    raise SystemExit(main(parsed))
