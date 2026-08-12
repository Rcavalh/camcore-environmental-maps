from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.windows import Window
from scipy.spatial import cKDTree


MODULE = Path(__file__).resolve().parents[1]
CONFIG = MODULE / "config/source_roots.json"
MODEL = MODULE / "outputs/full_native_climatology_model/models/FULL_NATIVE_CLIMATOLOGY_RF_MODELS.joblib"
OUT = MODULE / "outputs/full_native_five_state_rf_final_snapshot_20260806"
NODATA = np.float32(-9999.0)
DEFAULT_TILE_SIZE = 1024
PREDICTION_CHUNK = 60_000
OUTPUTS = {
    "observed_annual_frost_probability": "RF_ANNUAL_FROST_PROBABILITY_ANADEM30M_2000_2025.tif",
    "observed_expected_frost_days": "RF_EXPECTED_FROST_DAYS_ANADEM30M_2000_2025.tif",
    "observed_season_tmin_p25_c": "RF_SEASONAL_MINIMUM_TEMPERATURE_P25_ANADEM30M_2000_2025.tif",
}


def load_engine():
    path = MODULE.parents[1] / "4.Modelling/scripts/58_build_rf_50km_fold_test.py"
    spec = importlib.util.spec_from_file_location("five_state_full_native_terrain", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class StationClimateIDW:
    def __init__(self, stations: pd.DataFrame, features: list[str], k: int = 4):
        self.features = features
        self.k = min(k, len(stations))
        self.coordinates = stations[["longitude", "latitude"]].to_numpy(float)
        self.values = stations[features].apply(pd.to_numeric, errors="coerce").to_numpy(np.float32)
        self.tree = cKDTree(self.coordinates)

    def query(self, longitude: np.ndarray, latitude: np.ndarray) -> np.ndarray:
        distance, index = self.tree.query(np.column_stack([longitude, latitude]), k=self.k)
        if self.k == 1:
            distance, index = distance[:, None], index[:, None]
        weights = 1.0 / np.maximum(distance, 1e-8) ** 2
        source = self.values[index]
        valid = np.isfinite(source)
        weighted = np.where(valid, source * weights[:, :, None], 0).sum(axis=1)
        denominator = np.where(valid, weights[:, :, None], 0).sum(axis=1)
        return np.divide(weighted, denominator, out=np.full_like(weighted, np.nan), where=denominator > 0)


def windows(source: rasterio.DatasetReader, tile_size: int):
    total = math.ceil(source.height / tile_size) * math.ceil(source.width / tile_size)
    number = 0
    for row0 in range(0, source.height, tile_size):
        for col0 in range(0, source.width, tile_size):
            number += 1
            yield number, total, Window(col0, row0, min(tile_size, source.width-col0), min(tile_size, source.height-row0))


def create_rasters(source: rasterio.DatasetReader) -> tuple[dict[str, Path], dict[str, rasterio.DatasetWriter]]:
    raster_dir = OUT / "rasters"
    raster_dir.mkdir(parents=True, exist_ok=True)
    profile = source.profile.copy()
    profile.update(driver="GTiff", dtype="float32", count=1, nodata=float(NODATA), compress="ZSTD", predictor=3,
                   tiled=True, blockxsize=512, blockysize=512, BIGTIFF="YES", SPARSE_OK="TRUE")
    paths, writers = {}, {}
    for endpoint, filename in OUTPUTS.items():
        path = raster_dir / filename
        paths[endpoint] = path
        if not path.exists():
            with rasterio.open(path, "w", **profile) as target:
                target.update_tags(endpoint=endpoint, resolution="ANADEM native approximately 30 m",
                                   terrain="16 ANADEM/HAND covariates", climate="ERA5-Land and MODIS 2000-2025 climatology",
                                   smoothing="none")
        writers[endpoint] = rasterio.open(path, "r+")
    return paths, writers


def main(args: argparse.Namespace) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    checkpoint = OUT / "checkpoints"
    audit_dir = OUT / "audit"
    checkpoint.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    bundle = joblib.load(MODEL)
    terrain_features = list(bundle["terrain_features"])
    climate_features = list(bundle["climate_features"])
    features = list(bundle["features"])
    stations = bundle["station_climatology"].copy()
    climate = StationClimateIDW(stations, climate_features, k=4)
    engine = load_engine()
    audits, completed_this_run = [], 0
    dem_path, hand_path = Path(cfg["anadem_dem"]), Path(cfg["anadem_hand_2000m"])
    with rasterio.open(dem_path) as dem_source, rasterio.open(hand_path) as hand_native:
      # HAND and ANADEM cover the same five-state domain but can differ by a
      # sub-pixel origin/edge. Align HAND lazily to the ANADEM target grid;
      # this avoids a multi-hundred-GB intermediate and preserves 30 m output.
      with WarpedVRT(
          hand_native, crs=dem_source.crs, transform=dem_source.transform,
          width=dem_source.width, height=dem_source.height,
          resampling=Resampling.bilinear, nodata=hand_native.nodata,
      ) as hand_source:
        # The five-state mosaic is stored in geographic coordinates, while its
        # nominal source resolution is 30 m. Focal radii and derivatives are
        # therefore expressed with the documented 30 m ground resolution, not
        # with the transform's degree-sized pixel value.
        resolution_m = 30.0
        engine.TEST_RESOLUTION_M = resolution_m
        halo = int(math.ceil(2000 / resolution_m)) + 5
        paths, writers = create_rasters(dem_source)
        try:
            for tile_number, total_tiles, core in windows(dem_source, args.tile_size):
                marker = checkpoint / f"tile_r{int(core.row_off):06d}_c{int(core.col_off):06d}.json"
                if marker.exists():
                    continue
                row0, col0 = max(int(core.row_off)-halo, 0), max(int(core.col_off)-halo, 0)
                row1 = min(int(core.row_off+core.height)+halo, dem_source.height)
                col1 = min(int(core.col_off+core.width)+halo, dem_source.width)
                expanded = Window(col0, row0, col1-col0, row1-row0)
                dem = dem_source.read(1, window=expanded, masked=True).filled(np.nan).astype(np.float32)
                raw_hand = hand_source.read(1, window=expanded, masked=True).filled(np.nan).astype(np.float32)
                hand = np.where(np.isfinite(raw_hand) & (raw_hand != 0), raw_hand, np.nan).astype(np.float32)
                lr0, lc0 = int(core.row_off)-row0, int(core.col_off)-col0
                lr1, lc1 = lr0+int(core.height), lc0+int(core.width)
                core_dem = dem[lr0:lr1, lc0:lc1]
                valid = np.isfinite(core_dem) & (core_dem != dem_source.nodata)
                n_valid = int(valid.sum())
                output_arrays = {name: np.full(core_dem.shape, NODATA, dtype=np.float32) for name in OUTPUTS}
                record = {"tile": tile_number, "total_tiles": total_tiles, "row_off": int(core.row_off),
                          "col_off": int(core.col_off), "valid_pixels": n_valid}
                if n_valid:
                    terrain_stack = engine.terrain_stack(dem, hand)
                    terrain = {name: values[lr0:lr1, lc0:lc1] for name, values in terrain_stack.items()}
                    rows, cols = np.where(valid)
                    global_rows, global_cols = rows + int(core.row_off), cols + int(core.col_off)
                    longitude, latitude = rasterio.transform.xy(dem_source.transform, global_rows, global_cols, offset="center")
                    longitude, latitude = np.asarray(longitude, np.float32), np.asarray(latitude, np.float32)
                    flat = {name: np.empty(n_valid, np.float32) for name in OUTPUTS}
                    for start in range(0, n_valid, PREDICTION_CHUNK):
                        stop = min(start + PREDICTION_CHUNK, n_valid)
                        climate_values = climate.query(longitude[start:stop], latitude[start:stop])
                        matrix = pd.DataFrame(index=np.arange(stop-start), columns=features, dtype=np.float32)
                        matrix["longitude"], matrix["latitude"] = longitude[start:stop], latitude[start:stop]
                        for name in terrain_features:
                            matrix[name] = terrain[name][rows[start:stop], cols[start:stop]]
                        for index, name in enumerate(climate_features):
                            matrix[name] = climate_values[:, index]
                        for endpoint, estimator in bundle["models"].items():
                            values = estimator.predict(matrix[features]).astype(np.float32)
                            if endpoint == "observed_annual_frost_probability":
                                values = np.clip(values, 0, 1)
                            elif endpoint == "observed_expected_frost_days":
                                values = np.clip(values, 0, None)
                            flat[endpoint][start:stop] = values
                    for endpoint, values in flat.items():
                        output_arrays[endpoint][valid] = values
                        record[endpoint+"_min"], record[endpoint+"_max"] = float(values.min()), float(values.max())
                for endpoint, writer in writers.items():
                    writer.write(output_arrays[endpoint], 1, window=core)
                record["status"] = "done"
                marker.write_text(json.dumps(record), encoding="utf-8")
                audits.append(record)
                completed_this_run += 1
                print(f"FULL_NATIVE_TILE_OK={tile_number}/{total_tiles} valid={n_valid} run={completed_this_run}", flush=True)
                del dem, raw_hand, hand, output_arrays
                gc.collect()
                if args.max_tiles and completed_this_run >= args.max_tiles and any(a.get("valid_pixels", 0) > 0 for a in audits):
                    break
        finally:
            for writer in writers.values():
                writer.close()
    if audits:
        pd.DataFrame(audits).to_csv(audit_dir / "tile_audit_this_run.csv", index=False)
    total_markers = len(list(checkpoint.glob("tile_*.json")))
    partial = bool(args.max_tiles)
    status = {
        "status": "FIVE_STATE_FULL_NATIVE_RF_PARTIAL" if partial else "FIVE_STATE_FULL_NATIVE_RF_OK",
        "updated_at": datetime.now(timezone.utc).isoformat(), "completed_tiles": total_markers,
        "tile_size": args.tile_size, "model_features": len(features), "terrain_hand_features": len(terrain_features),
        "selected_climate_features": len(climate_features), "rasters": {key: str(path) for key, path in paths.items()},
    }
    (OUT / "RUN_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    if not partial:
        (OUT / "FIVE_STATE_FULL_NATIVE_RF_OK").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tile-size", type=int, default=DEFAULT_TILE_SIZE)
    parser.add_argument("--max-tiles", type=int, default=0)
    raise SystemExit(main(parser.parse_args()))
