from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# The workstation also has an older PostGIS PROJ database on PATH. Force this
# run to use the projection databases bundled with the selected Python env.
_PROJ_DATA = Path(sys.prefix) / "Lib/site-packages/rasterio/proj_data"
_GDAL_DATA = Path(sys.prefix) / "Lib/site-packages/rasterio/gdal_data"
if _PROJ_DATA.exists():
    os.environ["PROJ_DATA"] = str(_PROJ_DATA)
    os.environ["PROJ_LIB"] = str(_PROJ_DATA)
if _GDAL_DATA.exists():
    os.environ["GDAL_DATA"] = str(_GDAL_DATA)

import geopandas as gpd
import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin, rowcol
from rasterio.warp import reproject
from scipy.spatial import cKDTree
from shapely import contains_xy
from sklearn.base import clone
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline


MODULE = Path(__file__).resolve().parents[1]
PROJECT = MODULE.parent.parent
DB = MODULE / "database"
TOTAL_POINTS = int(os.environ.get("FROST_TOTAL_POINTS", "50000"))
if TOTAL_POINTS <= 0 or TOTAL_POINTS % 5:
    raise ValueError("FROST_TOTAL_POINTS must be a positive multiple of five")
RUN_KIND = "smoke" if TOTAL_POINTS == 50_000 else "complete"
RUN_SLUG = f"five_state_{TOTAL_POINTS}_{RUN_KIND}"
OUTPUT_PREFIX = f"FIVE_STATE_RF_{TOTAL_POINTS}_{RUN_KIND.upper()}"
OUT = MODULE / "outputs" / RUN_SLUG
CHECKPOINT = MODULE / "checkpoints" / RUN_SLUG
ENVIRONMENT_CHECKPOINT = MODULE / "checkpoints" / "five_state_50000_smoke"
TABLE = OUT / "tables"
FIG = OUT / "figures"
MODEL = OUT / "models"
REPORT = OUT / "reports"

CONFIG = MODULE / "config" / "source_roots.json"
ERA5_INDEX = DB / "ERA5_STATION_YEAR_PARTITION_INDEX.csv"
TERRAIN_STATIONS = DB / "STATION_PHYSIOGRAPHIC_COVARIATES_ANADEM_30M.parquet"
DAILY = PROJECT / "8.Dados_Meteorologicos_Publicos/07_RS_SP_MS_Extension/database/PUBLIC_DAILY_METEOROLOGICAL_OBSERVATIONS_2000_2026.parquet"
FROST_FILES = [
    PROJECT / "8.Dados_Meteorologicos_Publicos/01_INMET/frost_occurrences/inmet_frost_occurrences_PR_SC_2000_present.csv",
    PROJECT / "8.Dados_Meteorologicos_Publicos/07_RS_SP_MS_Extension/01_INMET/frost_occurrences/inmet_frost_occurrences_RS_SP_MS_2000_present.csv",
]
CONTRACT = PROJECT / "8.Dados_Meteorologicos_Publicos/06_Frost_Occurrence_RF_Pipeline/outputs/SMOKE_MODEL_CONTRACT.json"
ENGINE = PROJECT / "4.Modelling/scripts/58_build_rf_50km_fold_test.py"

SEED = 20260806
SEASON_START = 515
SEASON_END = 815
N_POINTS_PER_STATE = TOTAL_POINTS // 5
TERRAIN_SMOKE_RESOLUTION_M = 250.0
MODIS_GRID_DEGREES = 0.025
MODIS_ANCHOR_YEARS = [2024, 2025]
MODIS_ANCHOR_STEP_DAYS = 8

STATE_GROUP = {"PR": "PR_SC", "SC": "PR_SC", "RS": "RS", "SP": "SP", "MS": "MS"}
TERRAIN_FEATURES = [
    "elevation", "slope_deg", "eastness", "northness", "TPI_native",
    "TRI_native", "roughness_native", "plan_curvature", "profile_curvature",
    "surface_curvature_laplacian", "cold_air_pooling_2000m",
    "elevation_above_local_min_2000m", "elevation_below_local_max_2000m",
    "local_relief_2000m", "local_sd_2000m", "HAND_selected_m",
]
MODIS_FEATURES = [
    "modis_lst_day_mean_c", "modis_lst_day_min_c", "modis_lst_day_p05_c",
    "modis_lst_day_valid_fraction", "modis_lst_night_mean_c",
    "modis_lst_night_min_c", "modis_lst_night_p05_c",
    "modis_lst_night_valid_fraction", "modis_diurnal_range_mean_c",
]


def ensure_dirs() -> None:
    for path in (OUT, CHECKPOINT, ENVIRONMENT_CHECKPOINT, TABLE, FIG, MODEL, REPORT):
        path.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def load_engine():
    spec = importlib.util.spec_from_file_location("five_state_smoke_terrain_engine", ENGINE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import terrain engine: {ENGINE}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ENGINE.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def boundary_paths() -> dict[str, Path]:
    root = PROJECT / "8.Dados_Meteorologicos_Publicos"
    ext = root / "07_RS_SP_MS_Extension/boundaries"
    return {
        "PR": root / "boundaries/ibge_PR_minimum.geojson",
        "SC": root / "boundaries/ibge_SC_minimum.geojson",
        "RS": ext / "ibge_RS_minimum.geojson",
        "SP": ext / "ibge_SP_minimum.geojson",
        "MS": ext / "ibge_MS_minimum.geojson",
    }


def load_boundaries() -> gpd.GeoDataFrame:
    pieces = []
    for state, path in boundary_paths().items():
        frame = gpd.read_file(path).to_crs(4326)
        pieces.append(gpd.GeoDataFrame({"state": [state]}, geometry=[frame.geometry.union_all()], crs=4326))
    return gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), geometry="geometry", crs=4326)


def generate_points(boundaries: gpd.GeoDataFrame, dem_path: Path) -> pd.DataFrame:
    cache = CHECKPOINT / f"{OUTPUT_PREFIX}_POINTS.csv"
    if cache.exists():
        frame = pd.read_csv(cache)
        if len(frame) == 5 * N_POINTS_PER_STATE:
            return frame
    rng = np.random.default_rng(SEED)
    records = []
    with rasterio.open(dem_path) as dem:
        transformer = Transformer.from_crs(4326, dem.crs, always_xy=True)
        for state in ["MS", "SP", "PR", "SC", "RS"]:
            geometry = boundaries.loc[boundaries.state.eq(state), "geometry"].iloc[0]
            xmin, ymin, xmax, ymax = geometry.bounds
            accepted_x, accepted_y = [], []
            while sum(len(x) for x in accepted_x) < N_POINTS_PER_STATE:
                n = max(8_000, 2 * (N_POINTS_PER_STATE - sum(len(x) for x in accepted_x)))
                xx = rng.uniform(xmin, xmax, n)
                yy = rng.uniform(ymin, ymax, n)
                inside = contains_xy(geometry, xx, yy)
                xx, yy = xx[inside], yy[inside]
                if not len(xx):
                    continue
                dx, dy = transformer.transform(xx, yy)
                values = np.asarray([v[0] for v in dem.sample(zip(dx, dy), indexes=1, masked=True)], dtype=float)
                valid = np.isfinite(values) & (values != dem.nodata)
                accepted_x.append(xx[valid])
                accepted_y.append(yy[valid])
            lon = np.concatenate(accepted_x)[:N_POINTS_PER_STATE]
            lat = np.concatenate(accepted_y)[:N_POINTS_PER_STATE]
            records.append(pd.DataFrame({"state": state, "longitude": lon, "latitude": lat}))
    points = pd.concat(records, ignore_index=True)
    points.insert(0, "point_id", [f"P{i:06d}" for i in range(1, len(points) + 1)])
    points.to_csv(cache, index=False)
    return points


def terrain_for_points(points: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    cache = CHECKPOINT / f"{OUTPUT_PREFIX}_TERRAIN_FEATURES.parquet"
    if cache.exists():
        frame = pd.read_parquet(cache)
        if len(frame) == len(points):
            return frame
    dem_path = Path(cfg["anadem_dem"])
    hand_path = Path(cfg["anadem_hand_2000m"])
    with rasterio.open(dem_path) as dem_src:
        factor = TERRAIN_SMOKE_RESOLUTION_M / 30.0
        out_height = max(1, round(dem_src.height / factor))
        out_width = max(1, round(dem_src.width / factor))
        transform = dem_src.transform * dem_src.transform.scale(
            dem_src.width / out_width, dem_src.height / out_height
        )
        dem = dem_src.read(
            1, out_shape=(out_height, out_width), masked=True,
            resampling=Resampling.bilinear,
        ).filled(np.nan).astype(np.float32)
    with rasterio.open(hand_path) as hand_src:
        hand_raw = hand_src.read(
            1, out_shape=(out_height, out_width), masked=True,
            resampling=Resampling.nearest,
        ).filled(np.nan).astype(np.float32)
    hand = np.where(np.isfinite(hand_raw) & (hand_raw != 0), hand_raw, np.nan).astype(np.float32)
    engine = load_engine()
    engine.TEST_RESOLUTION_M = TERRAIN_SMOKE_RESOLUTION_M
    stack = engine.terrain_stack(dem, hand)
    rows, cols = rowcol(transform, points.longitude.to_numpy(), points.latitude.to_numpy())
    rows, cols = np.asarray(rows), np.asarray(cols)
    valid = (rows >= 0) & (rows < out_height) & (cols >= 0) & (cols < out_width)
    result = points[["point_id", "state", "longitude", "latitude"]].copy()
    for feature in TERRAIN_FEATURES:
        values = np.full(len(points), np.nan, dtype=np.float32)
        values[valid] = stack[feature][rows[valid], cols[valid]]
        result[feature] = values
    result.to_parquet(cache, index=False)
    audit = {
        "status": "SMOKE_TERRAIN_OK",
        "smoke_resolution_m": TERRAIN_SMOKE_RESOLUTION_M,
        "final_prediction_resolution_m": 30,
        "points": len(result),
        "hand_zero_policy": "source zeros masked as NA",
        "hand_missing_points": int(result.HAND_selected_m.isna().sum()),
    }
    (CHECKPOINT / f"{OUTPUT_PREFIX}_TERRAIN_AUDIT.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    del stack, dem, hand, hand_raw
    return result


def qc_relaxed(qc: np.ndarray) -> np.ndarray:
    integer = np.nan_to_num(qc, nan=255).astype(np.uint8)
    mandatory = integer & 0b11
    error_class = (integer >> 6) & 0b11
    return np.isin(mandatory, [0, 1]) & np.isin(error_class, [0, 1])


def warp_lst(path: Path, target_shape, target_transform) -> np.ndarray:
    period = "Day" if "__LST_Day_1km" in path.name else "Night"
    qc_path = path.with_name(path.name.replace(f"__LST_{period}_1km.tif", f"__QC_{period}.tif"))
    if not qc_path.exists():
        return np.full(target_shape, np.nan, dtype=np.float32)
    raw = np.full(target_shape, np.nan, dtype=np.float32)
    quality = np.full(target_shape, np.nan, dtype=np.float32)
    with rasterio.open(path) as src, rasterio.open(qc_path) as qc:
        reproject(
            rasterio.band(src, 1), raw,
            src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
            dst_transform=target_transform, dst_crs="EPSG:4326", dst_nodata=np.nan,
            resampling=Resampling.nearest,
        )
        reproject(
            rasterio.band(qc, 1), quality,
            src_transform=qc.transform, src_crs=qc.crs, src_nodata=qc.nodata,
            dst_transform=target_transform, dst_crs="EPSG:4326", dst_nodata=np.nan,
            resampling=Resampling.nearest,
        )
        scale = float(src.tags().get("scale_factor", 0.02))
    values = raw * scale - 273.15
    valid = (
        np.isfinite(raw)
        & (raw > 0)
        & np.isfinite(quality)
        & qc_relaxed(quality)
        & (values >= -90)
        & (values <= 80)
    )
    return np.where(valid, values, np.nan).astype(np.float32)


def nan_combine(arrays: list[np.ndarray], reducer: str, shape) -> np.ndarray:
    if not arrays:
        return np.full(shape, np.nan, dtype=np.float32)
    values = np.stack(arrays)
    valid = np.isfinite(values)
    if reducer == "mean":
        count = valid.sum(axis=0)
        return np.divide(np.nansum(values, axis=0), count, out=np.full(shape, np.nan, dtype=np.float32), where=count > 0)
    safe = np.where(valid, values, np.inf)
    result = np.min(safe, axis=0)
    result[~valid.any(axis=0)] = np.nan
    return result.astype(np.float32)


def modis_group_grid(group: str, states_geometry, modis_root: Path) -> tuple[dict[str, np.ndarray], dict]:
    cache = ENVIRONMENT_CHECKPOINT / f"MODIS_THERMAL_ANCHOR_{group}.npz"
    audit_path = ENVIRONMENT_CHECKPOINT / f"MODIS_THERMAL_ANCHOR_{group}_AUDIT.json"
    if cache.exists() and audit_path.exists():
        z = np.load(cache)
        return {name: z[name] for name in z.files if name not in {"transform_values"}}, json.loads(audit_path.read_text(encoding="utf-8"))
    xmin, ymin, xmax, ymax = states_geometry.bounds
    width = math.ceil((xmax - xmin) / MODIS_GRID_DEGREES)
    height = math.ceil((ymax - ymin) / MODIS_GRID_DEGREES)
    transform = from_origin(xmin, ymax, MODIS_GRID_DEGREES, MODIS_GRID_DEGREES)
    shape = (height, width)
    day_stack, night_stack, diurnal_stack = [], [], []
    used_dates = []
    source_files = 0
    for year in MODIS_ANCHOR_YEARS:
        for date in pd.date_range(f"{year}-05-15", f"{year}-08-15", freq=f"{MODIS_ANCHOR_STEP_DAYS}D"):
            directory = modis_root / "modis-11A1-061" / str(year) / date.strftime("%Y-%m-%d")
            if not directory.exists():
                continue
            period_daily = {}
            for period, reducer in (("Day", "mean"), ("Night", "min")):
                platform_arrays = []
                for platform in ("MOD", "MYD"):
                    tile_arrays = []
                    for path in directory.glob(f"{platform}*__LST_{period}_1km.tif"):
                        tile_arrays.append(warp_lst(path, shape, transform))
                        source_files += 1
                    if tile_arrays:
                        # Tiles are spatially complementary; first finite value wins.
                        mosaic = np.full(shape, np.nan, dtype=np.float32)
                        for tile in tile_arrays:
                            fill = np.isfinite(tile)
                            mosaic[fill] = tile[fill]
                        platform_arrays.append(mosaic)
                period_daily[period] = nan_combine(platform_arrays, reducer, shape)
            if np.isfinite(period_daily["Day"]).any() or np.isfinite(period_daily["Night"]).any():
                day_stack.append(period_daily["Day"])
                night_stack.append(period_daily["Night"])
                diurnal_stack.append(period_daily["Day"] - period_daily["Night"])
                used_dates.append(str(date.date()))
    def summaries(stack: list[np.ndarray], prefix: str) -> dict[str, np.ndarray]:
        if not stack:
            blank = np.full(shape, np.nan, dtype=np.float32)
            return {f"{prefix}_mean_c": blank, f"{prefix}_min_c": blank.copy(), f"{prefix}_p05_c": blank.copy(), f"{prefix}_valid_fraction": np.zeros(shape, dtype=np.float32)}
        values = np.stack(stack)
        valid = np.isfinite(values)
        count = valid.sum(axis=0)
        mean = np.divide(np.nansum(values, axis=0), count, out=np.full(shape, np.nan, dtype=np.float32), where=count > 0)
        safe = np.where(valid, values, np.inf)
        minimum = np.min(safe, axis=0); minimum[~valid.any(axis=0)] = np.nan
        with np.errstate(all="ignore"):
            p05 = np.nanpercentile(values, 5, axis=0).astype(np.float32)
        return {f"{prefix}_mean_c": mean.astype(np.float32), f"{prefix}_min_c": minimum.astype(np.float32), f"{prefix}_p05_c": p05, f"{prefix}_valid_fraction": (count / max(len(stack), 1)).astype(np.float32)}
    arrays = {}
    arrays.update(summaries(day_stack, "modis_lst_day"))
    arrays.update(summaries(night_stack, "modis_lst_night"))
    if diurnal_stack:
        values = np.stack(diurnal_stack)
        count = np.isfinite(values).sum(axis=0)
        arrays["modis_diurnal_range_mean_c"] = np.divide(np.nansum(values, axis=0), count, out=np.full(shape, np.nan, dtype=np.float32), where=count > 0)
    else:
        arrays["modis_diurnal_range_mean_c"] = np.full(shape, np.nan, dtype=np.float32)
    arrays["transform_values"] = np.array(tuple(transform), dtype=np.float64)
    np.savez_compressed(cache, **arrays)
    arrays.pop("transform_values")
    audit = {
        "state_group": group, "status": "MODIS_THERMAL_ANCHOR_OK", "years": MODIS_ANCHOR_YEARS,
        "anchor_step_days": MODIS_ANCHOR_STEP_DAYS, "dates_used": used_dates,
        "n_dates_used": len(used_dates), "source_lst_files": source_files,
        "grid_shape": list(shape), "grid_resolution_degrees": MODIS_GRID_DEGREES,
        "transform": tuple(transform), "source": str(modis_root),
        "limitation": "Smoke-test temporal subsample; final run must use every stable observation in the common coverage period",
    }
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return arrays, audit


def build_modis_grids(boundaries: gpd.GeoDataFrame, cfg: dict):
    grids, audits = {}, []
    for group in ["PR_SC", "RS", "SP", "MS"]:
        codes = cfg["states"][group]["state_codes"]
        geometry = boundaries.loc[boundaries.state.isin(codes)].geometry.union_all()
        arrays, audit = modis_group_grid(group, geometry, PROJECT / cfg["states"][group]["modis"])
        grids[group] = (arrays, rasterio.Affine(*audit["transform"]))
        audits.append(audit)
    pd.DataFrame(audits).to_json(TABLE / f"{OUTPUT_PREFIX}_MODIS_THERMAL_COVERAGE.json", orient="records", indent=2)
    return grids


def sample_modis(frame: pd.DataFrame, grids) -> pd.DataFrame:
    result = frame.copy()
    for feature in MODIS_FEATURES:
        result[feature] = np.nan
    for group in ["PR_SC", "RS", "SP", "MS"]:
        mask = result.state.map(STATE_GROUP).eq(group).to_numpy()
        if not mask.any():
            continue
        arrays, transform = grids[group]
        rr, cc = rowcol(transform, result.loc[mask, "longitude"].to_numpy(), result.loc[mask, "latitude"].to_numpy())
        rr, cc = np.asarray(rr), np.asarray(cc)
        shape = next(iter(arrays.values())).shape
        valid = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
        target_index = result.index[mask].to_numpy()
        for feature in MODIS_FEATURES:
            values = np.full(mask.sum(), np.nan, dtype=np.float32)
            values[valid] = arrays[feature][rr[valid], cc[valid]]
            result.loc[target_index, feature] = values
    return result


def load_era5_wide() -> pd.DataFrame:
    index = pd.read_csv(ERA5_INDEX)
    keep = [
        "state", "source", "station_id", "latitude", "longitude", "year", "source_variable",
        "mean", "minimum", "p05", "p25", "p50", "p75", "p95", "maximum",
        "days_le_0c", "days_le_2c", "days_le_5c",
    ]
    frames = []
    for row in index.loc[index.status.eq("COMPLETE")].itertuples(index=False):
        # The index may have been created on Windows and therefore contain a
        # drive-letter or UNC path that is not meaningful on Linux. Prefer the
        # portable package-relative partition before inspecting the recorded
        # source path. Path.is_file() is guarded because a Windows UNC string
        # can raise ENAMETOOLONG on Linux rather than simply returning False.
        local_path = (
            DB / "era5_station_year_may15_aug15" /
            f"state_group={row.state_group}" / f"year={int(row.year)}" / "features.parquet"
        )
        path = local_path
        if not local_path.is_file():
            recorded_path = Path(str(row.output))
            try:
                recorded_available = recorded_path.is_file()
            except OSError:
                recorded_available = False
            if recorded_available:
                path = recorded_path
        if not path.is_file():
            raise FileNotFoundError(f"ERA5 station-year partition is missing: {path}")
        frames.append(pd.read_parquet(path, columns=keep))
    long = pd.concat(frames, ignore_index=True)
    ids = ["state", "source", "station_id", "latitude", "longitude", "year"]
    pieces = []
    for statistic in [c for c in keep if c not in ids + ["source_variable"]]:
        pivot = long.pivot(index=ids, columns="source_variable", values=statistic)
        pivot.columns = [f"era5__{column}__{statistic}" for column in pivot.columns]
        pieces.append(pivot)
    wide = pd.concat(pieces, axis=1).reset_index()
    wide.columns.name = None
    return wide


def load_targets() -> pd.DataFrame:
    daily = pd.read_parquet(DAILY, columns=["date", "state", "source", "station_id", "tmin_c"])
    daily["date"] = pd.to_datetime(daily.date)
    md = daily.date.dt.month * 100 + daily.date.dt.day
    daily = daily.loc[daily.source.eq("INMET") & daily.tmin_c.notna() & md.between(SEASON_START, SEASON_END)].copy()
    daily["year"] = daily.date.dt.year
    coverage = daily.drop_duplicates(["station_id", "date"]).groupby(["state", "station_id", "year"], as_index=False).agg(
        observed_days=("date", "size"), observed_season_tmin_c=("tmin_c", "min")
    )
    coverage = coverage.loc[coverage.observed_days.ge(65) & coverage.year.le(2025)].copy()
    occurrence = []
    for path in FROST_FILES:
        frame = pd.read_csv(path)
        frame = frame.loc[frame.station_type.eq("automatica")].copy()
        frame["date"] = pd.to_datetime(frame.DT_MEDICAO)
        md = frame.date.dt.month * 100 + frame.date.dt.day
        frame = frame.loc[md.between(SEASON_START, SEASON_END)]
        frame["year"] = frame.date.dt.year
        occurrence.append(frame.rename(columns={"CODIGO": "station_id", "UF": "state"})[["state", "station_id", "year", "date"]])
    events = pd.concat(occurrence, ignore_index=True).drop_duplicates(["state", "station_id", "year", "date"])
    events = events.groupby(["state", "station_id", "year"], as_index=False).agg(frost_days=("date", "size"))
    target = coverage.merge(events, on=["state", "station_id", "year"], how="left")
    target["frost_days"] = target.frost_days.fillna(0).astype(int)
    target["frost_any"] = target.frost_days.gt(0).astype(int)
    return target


def idw_lookup(source: pd.DataFrame, target: pd.DataFrame, features: list[str], k: int = 4) -> np.ndarray:
    lat0 = math.radians(float(source.latitude.mean()))
    src_xy = np.column_stack([source.longitude.to_numpy() * math.cos(lat0), source.latitude.to_numpy()])
    dst_xy = np.column_stack([target.longitude.to_numpy() * math.cos(lat0), target.latitude.to_numpy()])
    tree = cKDTree(src_xy)
    distances, indices = tree.query(dst_xy, k=min(k, len(source)))
    if distances.ndim == 1:
        distances, indices = distances[:, None], indices[:, None]
    weights = 1.0 / np.maximum(distances, 1e-6) ** 2
    weights /= weights.sum(axis=1, keepdims=True)
    source_values = source[features].to_numpy(dtype=np.float32)
    output = np.empty((len(target), len(features)), dtype=np.float32)
    for start in range(0, len(target), 2_500):
        stop = min(start + 2_500, len(target))
        values = source_values[indices[start:stop]]
        w = weights[start:stop, :, None]
        finite = np.isfinite(values)
        denominator = np.sum(w * finite, axis=1)
        output[start:stop] = np.divide(
            np.nansum(values * w, axis=1), denominator,
            out=np.full((stop - start, len(features)), np.nan, dtype=np.float32),
            where=denominator > 0,
        )
    return output


def classifier() -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("rf", RandomForestClassifier(
            n_estimators=420, max_depth=18, min_samples_leaf=5, max_features="sqrt",
            class_weight="balanced_subsample", n_jobs=-1, random_state=SEED,
        )),
    ])


def regressor(seed: int, poisson: bool = False) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("rf", RandomForestRegressor(
            n_estimators=420, criterion="poisson" if poisson else "squared_error",
            min_samples_leaf=4, max_features=0.45, n_jobs=-1, random_state=seed,
        )),
    ])


def grouped_oof(model, frame: pd.DataFrame, features: list[str], target: str, kind: str):
    work = frame.loc[frame[target].notna()].copy().reset_index(drop=True)
    y = work[target].to_numpy()
    groups = work.station_id.astype(str).to_numpy()
    folds = GroupKFold(n_splits=5)
    prediction = np.full(len(work), np.nan)
    for train, test in folds.split(work[features], y, groups):
        fitted = clone(model)
        fitted.fit(work.iloc[train][features], y[train])
        prediction[test] = fitted.predict_proba(work.iloc[test][features])[:, 1] if kind == "classifier" else fitted.predict(work.iloc[test][features])
    if kind == "classifier":
        binary = (prediction >= 0.5).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, binary, labels=[0, 1]).ravel()
        metrics = {
            "endpoint": target, "validation": "five-fold station-held-out", "n": len(work),
            "roc_auc": roc_auc_score(y, prediction), "pr_auc": average_precision_score(y, prediction),
            "brier": brier_score_loss(y, prediction), "balanced_accuracy": balanced_accuracy_score(y, binary),
            "sensitivity": tp / (tp + fn), "specificity": tn / (tn + fp),
            "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        }
    else:
        metrics = {
            "endpoint": target, "validation": "five-fold station-held-out", "n": len(work),
            "r2": r2_score(y, prediction), "rmse": mean_squared_error(y, prediction) ** 0.5,
            "mae": mean_absolute_error(y, prediction), "bias": float(np.mean(prediction - y)),
        }
    final = clone(model).fit(work[features], y)
    return final, metrics


def plot_maps(points: gpd.GeoDataFrame, boundaries: gpd.GeoDataFrame) -> tuple[Path, Path, Path]:
    panels = [
        ("annual_frost_probability_mean", "(a) Mean annual frost probability", "Probability", "RdYlBu", 0, 1),
        ("annual_frost_probability_p75", "(b) P75 annual frost probability", "Probability", "RdYlBu", 0, 1),
        ("expected_frost_days_mean", "(c) Expected frost days per season", "Days", "RdYlBu", 0, None),
        ("event_minimum_temperature_mean_c", "(d) Predicted seasonal minimum temperature", "Temperature (°C)", "RdYlBu_r", None, None),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(12.4, 13.0))
    for ax, (column, title, label, cmap, vmin, vmax) in zip(axes.ravel(), panels):
        sc = ax.scatter(points.longitude, points.latitude, c=points[column], s=1.35, cmap=cmap, vmin=vmin, vmax=vmax, linewidths=0, rasterized=True)
        boundaries.boundary.plot(ax=ax, color="#222222", linewidth=0.55)
        ax.set_title(title, fontsize=12)
        ax.set_axis_off()
        cb = fig.colorbar(sc, ax=ax, fraction=0.035, pad=0.015, shrink=0.78)
        cb.set_label(label, fontsize=9)
    fig.suptitle(f"Five-state frost-risk {RUN_KIND} run — {TOTAL_POINTS:,} spatial samples", fontsize=16, y=0.985)
    fig.text(
        0.5, 0.012,
        "RF models fitted to INMET station-year endpoints; predictors: ANADEM physiography, HAND, ERA5-Land (2000–2025), and a current common-period MODIS thermal anchor sample.",
        ha="center", fontsize=8.5,
    )
    fig.subplots_adjust(left=0.025, right=0.98, top=0.955, bottom=0.04, wspace=0.08, hspace=0.08)
    light = FIG / f"{OUTPUT_PREFIX}_LIGHT.png"
    hd = FIG / f"{OUTPUT_PREFIX}_620DPI.png"
    pdf = FIG / f"{OUTPUT_PREFIX}.pdf"
    fig.savefig(light, dpi=160, facecolor="white", bbox_inches="tight")
    fig.savefig(hd, dpi=620, facecolor="white", bbox_inches="tight")
    fig.savefig(pdf, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return light, hd, pdf


def main() -> int:
    ensure_dirs()
    cfg = load_config()
    boundaries = load_boundaries()
    points = generate_points(boundaries, Path(cfg["anadem_dem"]))
    terrain_points = terrain_for_points(points, cfg)
    modis_grids = build_modis_grids(boundaries, cfg)
    terrain_points = sample_modis(terrain_points, modis_grids)

    era5 = load_era5_wide()
    era5 = era5.loc[era5.year.between(2000, 2025)].copy()
    era5_features = [column for column in era5.columns if column.startswith("era5__")]
    targets = load_targets()
    terrain_stations = pd.read_parquet(TERRAIN_STATIONS)
    station_static = terrain_stations[["state", "source", "station_id", "latitude", "longitude"] + TERRAIN_FEATURES].drop_duplicates(["source", "station_id"])
    station_static = sample_modis(station_static, modis_grids)
    training = era5.loc[era5.source.eq("INMET")].merge(targets, on=["state", "station_id", "year"], how="inner", validate="one_to_one")
    training = training.merge(
        station_static.drop(columns=["latitude", "longitude"]),
        on=["state", "source", "station_id"], how="left", validate="many_to_one",
    )
    features = ["latitude", "longitude", "year"] + TERRAIN_FEATURES + era5_features + MODIS_FEATURES
    features = [feature for feature in features if training[feature].notna().any()]
    era5_features_used = [feature for feature in era5_features if feature in features]

    models, metrics = {}, []
    models["frost_any"], metric = grouped_oof(classifier(), training, features, "frost_any", "classifier")
    metrics.append(metric)
    models["frost_days"], metric = grouped_oof(regressor(SEED + 1, poisson=True), training, features, "frost_days", "regressor")
    metrics.append(metric)
    models["observed_season_tmin_c"], metric = grouped_oof(regressor(SEED + 2), training, features, "observed_season_tmin_c", "regressor")
    metrics.append(metric)
    pd.DataFrame(metrics).to_csv(TABLE / f"{OUTPUT_PREFIX}_VALIDATION_METRICS.csv", index=False)

    static_features = ["latitude", "longitude"] + TERRAIN_FEATURES + MODIS_FEATURES
    static_matrix = terrain_points[static_features].copy()
    annual_probability = []
    annual_days = []
    annual_tmin = []
    for year in range(2000, 2026):
        source_year = era5.loc[era5.year.eq(year)].drop_duplicates(["source", "station_id"])
        if source_year.empty:
            continue
        climate_matrix = idw_lookup(source_year, terrain_points, era5_features, k=4)
        prediction = pd.concat(
            [
                static_matrix.reset_index(drop=True),
                pd.DataFrame(climate_matrix, columns=era5_features),
            ],
            axis=1,
        )
        prediction.insert(2, "year", year)
        prediction = prediction[features]
        annual_probability.append(models["frost_any"].predict_proba(prediction)[:, 1].astype(np.float32))
        annual_days.append(np.clip(models["frost_days"].predict(prediction), 0, None).astype(np.float32))
        annual_tmin.append(models["observed_season_tmin_c"].predict(prediction).astype(np.float32))
        print(f"PREDICT_YEAR_OK={year}", flush=True)
    probability_stack = np.stack(annual_probability)
    days_stack = np.stack(annual_days)
    tmin_stack = np.stack(annual_tmin)
    result = terrain_points.copy()
    result["annual_frost_probability_mean"] = probability_stack.mean(axis=0)
    result["annual_frost_probability_p75"] = np.quantile(probability_stack, 0.75, axis=0)
    result["expected_frost_days_mean"] = days_stack.mean(axis=0)
    result["expected_frost_days_p75"] = np.quantile(days_stack, 0.75, axis=0)
    result["event_minimum_temperature_mean_c"] = tmin_stack.mean(axis=0)
    result["event_minimum_temperature_p25_c"] = np.quantile(tmin_stack, 0.25, axis=0)
    result.to_parquet(TABLE / f"{OUTPUT_PREFIX}_PREDICTIONS.parquet", index=False)
    result.head(1000).to_csv(TABLE / f"{OUTPUT_PREFIX}_PREDICTIONS_PREVIEW.csv", index=False)
    geo = gpd.GeoDataFrame(result, geometry=gpd.points_from_xy(result.longitude, result.latitude), crs=4326)
    geo[["point_id", "state", "annual_frost_probability_mean", "annual_frost_probability_p75", "expected_frost_days_mean", "event_minimum_temperature_mean_c", "geometry"]].to_file(
        OUT / f"{OUTPUT_PREFIX}_PREDICTIONS.gpkg", driver="GPKG"
    )
    light, hd, pdf = plot_maps(geo, boundaries)
    joblib.dump({
        "models": models, "features": features, "era5_features": era5_features_used,
        "terrain_features": TERRAIN_FEATURES, "modis_features": MODIS_FEATURES,
        "years": [2000, 2025], "season": "15 May-15 August",
        "modis_anchor": {"years": MODIS_ANCHOR_YEARS, "step_days": MODIS_ANCHOR_STEP_DAYS},
    }, MODEL / f"{OUTPUT_PREFIX}_BUNDLE.joblib")
    feature_registry = pd.DataFrame(
        ([{"feature": f, "block": "Terrain/HAND"} for f in ["latitude", "longitude"] + TERRAIN_FEATURES]
         + [{"feature": "year", "block": "Time"}]
         + [{"feature": f, "block": "ERA5-Land"} for f in era5_features_used]
         + [{"feature": f, "block": "MODIS thermal"} for f in MODIS_FEATURES])
    )
    feature_registry.to_csv(TABLE / f"{OUTPUT_PREFIX}_FEATURE_REGISTRY.csv", index=False)
    status = {
        "status": f"{OUTPUT_PREFIX}_OK",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "points": len(result), "points_per_state": result.groupby("state").size().to_dict(),
        "training_station_years": len(training), "training_stations": int(training.station_id.nunique()),
        "features": len(features), "era5_features_used": len(era5_features_used),
        "era5_features_catalogued": len(era5_features),
        "terrain_features": len(TERRAIN_FEATURES), "modis_features": len(MODIS_FEATURES),
        "climate_years": [2000, 2025], "season": "15 May-15 August",
        "modis_smoke_anchor_years": MODIS_ANCHOR_YEARS,
        "modis_smoke_temporal_sampling_days": MODIS_ANCHOR_STEP_DAYS,
        "terrain_smoke_resolution_m": TERRAIN_SMOKE_RESOLUTION_M,
        "final_native_resolution_m": 30,
        "metrics": metrics,
        "light_map": str(light), "hd_map": str(hd), "pdf_map": str(pdf),
    }
    (OUT / f"{OUTPUT_PREFIX}_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (OUT / f"{OUTPUT_PREFIX}_OK").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
