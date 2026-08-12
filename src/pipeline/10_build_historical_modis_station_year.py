from __future__ import annotations

import json
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJ_DATA = Path(sys.prefix) / "Lib/site-packages/rasterio/proj_data"
_GDAL_DATA = Path(sys.prefix) / "Lib/site-packages/rasterio/gdal_data"
if _PROJ_DATA.exists():
    os.environ["PROJ_DATA"] = str(_PROJ_DATA)
    os.environ["PROJ_LIB"] = str(_PROJ_DATA)
if _GDAL_DATA.exists():
    os.environ["GDAL_DATA"] = str(_GDAL_DATA)

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer


MODULE = Path(__file__).resolve().parents[1]
DB = MODULE / "database"
MANIFEST = DB / "AVAILABLE_ENVIRONMENTAL_ASSET_MANIFEST.parquet"
STATIONS = DB / "STATION_PHYSIOGRAPHIC_COVARIATES_ANADEM_30M.parquet"
PARTITIONS = DB / "modis_station_year_may15_aug15"
CHECKPOINTS = MODULE / "checkpoints/historical_modis_station_year"
INDEX = DB / "MODIS_STATION_YEAR_PARTITION_INDEX.csv"
AUDIT = DB / "MODIS_STATION_YEAR_TEMPORAL_COVERAGE.csv"
LOCK = CHECKPOINTS / "ACTIVE_EXTRACTION_LOCK"
YEARS = range(2000, 2026)
EXPECTED_DAYS = 93
STATE_GROUP = {"PR": "PR_SC", "SC": "PR_SC", "RS": "RS", "SP": "SP", "MS": "MS"}
FEATURES = [
    "modis_lst_day_mean_c",
    "modis_lst_day_min_c",
    "modis_lst_day_p05_c",
    "modis_lst_day_valid_fraction",
    "modis_lst_night_mean_c",
    "modis_lst_night_min_c",
    "modis_lst_night_p05_c",
    "modis_lst_night_valid_fraction",
    "modis_diurnal_range_mean_c",
]


def qc_ok(values: np.ndarray) -> np.ndarray:
    integer = np.nan_to_num(values, nan=255).astype(np.uint8)
    mandatory = integer & 0b11
    error_class = (integer >> 6) & 0b11
    return np.isin(mandatory, [0, 1]) & np.isin(error_class, [0, 1])


def sibling_qc(path: Path, period: str) -> Path:
    return path.with_name(path.name.replace(f"__LST_{period}_1km.tif", f"__QC_{period}.tif"))


def sample_file(path: Path, qc_path: Path, stations: pd.DataFrame) -> np.ndarray:
    result = np.full(len(stations), np.nan, dtype=np.float32)
    if not qc_path.exists():
        return result
    with rasterio.open(path) as src, rasterio.open(qc_path) as qc:
        transformer = Transformer.from_crs(4326, src.crs, always_xy=True)
        x, y = transformer.transform(stations.longitude.to_numpy(), stations.latitude.to_numpy())
        inside = (
            (x >= src.bounds.left)
            & (x <= src.bounds.right)
            & (y >= src.bounds.bottom)
            & (y <= src.bounds.top)
        )
        if not inside.any():
            return result
        positions = np.flatnonzero(inside)
        coordinates = list(zip(np.asarray(x)[inside], np.asarray(y)[inside]))
        raw = np.asarray([value[0] for value in src.sample(coordinates, indexes=1, masked=False)], dtype=float)
        quality = np.asarray([value[0] for value in qc.sample(coordinates, indexes=1, masked=False)], dtype=float)
        scale = float(src.tags().get("scale_factor", 0.02))
        temperature = raw * scale - 273.15
        valid = (
            np.isfinite(raw)
            & (raw > 0)
            & np.isfinite(quality)
            & qc_ok(quality)
            & (temperature >= -90)
            & (temperature <= 80)
        )
        result[positions[valid]] = temperature[valid].astype(np.float32)
    return result


def summarize(values: np.ndarray, prefix: str) -> dict[str, np.ndarray]:
    valid = np.isfinite(values)
    count = valid.sum(axis=0)
    mean = np.divide(
        np.nansum(values, axis=0),
        count,
        out=np.full(values.shape[1], np.nan, dtype=np.float32),
        where=count > 0,
    )
    safe = np.where(valid, values, np.inf)
    minimum = np.min(safe, axis=0)
    minimum[count == 0] = np.nan
    p05 = np.full(values.shape[1], np.nan, dtype=np.float32)
    for index in np.flatnonzero(count > 0):
        p05[index] = np.nanpercentile(values[:, index], 5)
    return {
        f"{prefix}_mean_c": mean.astype(np.float32),
        f"{prefix}_min_c": minimum.astype(np.float32),
        f"{prefix}_p05_c": p05,
        f"{prefix}_valid_fraction": (count / EXPECTED_DAYS).astype(np.float32),
        f"{prefix}_n_valid_days": count.astype(np.int16),
    }


def source_fingerprint(files: pd.DataFrame) -> str:
    """Return a stable signature for one state-group/year input partition."""
    if files.empty:
        return hashlib.sha256(b"EMPTY").hexdigest()
    columns = [name for name in ["path", "actual_bytes", "file_mtime"] if name in files]
    payload = files[columns].fillna("").astype(str).sort_values(columns).to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def process_partition(group: str, year: int, files: pd.DataFrame, stations: pd.DataFrame) -> dict:
    output = PARTITIONS / f"state_group={group}/year={year}/features.parquet"
    marker = CHECKPOINTS / f"{group}_{year}.json"
    fingerprint = source_fingerprint(files)
    if output.exists() and marker.exists():
        status = json.loads(marker.read_text(encoding="utf-8"))
        if status.get("status") == "COMPLETE" and status.get("source_fingerprint") == fingerprint:
            return status
    output.parent.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range(f"{year}-05-15", f"{year}-08-15", freq="D")
    day = np.full((EXPECTED_DAYS, len(stations)), np.nan, dtype=np.float32)
    night = np.full_like(day, np.nan)
    date_lookup = {date.date(): index for index, date in enumerate(dates)}
    file_reads = 0
    for period, destination in [("Day", day), ("Night", night)]:
        period_files = files.loc[files.asset.eq(f"LST_{period}_1km")]
        by_date_platform: dict[tuple[object, str], np.ndarray] = {}
        for row in period_files.itertuples(index=False):
            date = pd.Timestamp(row.acquisition_date).date()
            if date not in date_lookup:
                continue
            path = Path(row.path)
            platform = path.name[:3]
            key = (date, platform)
            sampled = sample_file(path, sibling_qc(path, period), stations)
            if key not in by_date_platform:
                by_date_platform[key] = sampled
            else:
                fill = np.isfinite(sampled)
                by_date_platform[key][fill] = sampled[fill]
            file_reads += 1
        for date in dates.date:
            platform_values = [
                by_date_platform[(date, platform)]
                for platform in ["MOD", "MYD"]
                if (date, platform) in by_date_platform
            ]
            if not platform_values:
                continue
            values = np.stack(platform_values)
            if period == "Day":
                count = np.isfinite(values).sum(axis=0)
                combined = np.divide(
                    np.nansum(values, axis=0),
                    count,
                    out=np.full(len(stations), np.nan, dtype=np.float32),
                    where=count > 0,
                )
            else:
                safe = np.where(np.isfinite(values), values, np.inf)
                combined = np.min(safe, axis=0)
                combined[~np.isfinite(values).any(axis=0)] = np.nan
            destination[date_lookup[date]] = combined

    summary = stations[["state", "source", "station_id", "latitude", "longitude"]].copy()
    for key, values in summarize(day, "modis_lst_day").items():
        summary[key] = values
    for key, values in summarize(night, "modis_lst_night").items():
        summary[key] = values
    diurnal = day - night
    count = np.isfinite(diurnal).sum(axis=0)
    summary["modis_diurnal_range_mean_c"] = np.divide(
        np.nansum(diurnal, axis=0),
        count,
        out=np.full(len(stations), np.nan, dtype=np.float32),
        where=count > 0,
    )
    summary["modis_diurnal_n_valid_days"] = count.astype(np.int16)
    summary["year"] = year
    summary.to_parquet(output, index=False)
    status = {
        "status": "COMPLETE",
        "state_group": group,
        "year": year,
        "stations": len(stations),
        "source_lst_files": int(len(files)),
        "source_fingerprint": fingerprint,
        "files_read": file_reads,
        "stations_with_day": int(summary.modis_lst_day_n_valid_days.gt(0).sum()),
        "stations_with_night": int(summary.modis_lst_night_n_valid_days.gt(0).sum()),
        "mean_day_valid_fraction": float(summary.modis_lst_day_valid_fraction.mean()),
        "mean_night_valid_fraction": float(summary.modis_lst_night_valid_fraction.mean()),
        "output": str(output),
    }
    marker.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"MODIS_STATION_YEAR_OK={group}/{year}", flush=True)
    return status


def main() -> int:
    PARTITIONS.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    # A long-running extractor was already started before this guard was added.
    # The lock prevents accidental duplicate launches while that process finishes.
    if LOCK.exists() and os.environ.get("FROST_MODIS_ALLOW_LOCKED", "0") != "1":
        print(f"MODIS_EXTRACTION_ALREADY_ACTIVE={LOCK}", flush=True)
        return 0
    stations = pd.read_parquet(STATIONS)
    stations = stations.loc[stations.source.eq("INMET")].copy()
    stations["state_group"] = stations.state.map(STATE_GROUP)
    manifest = pd.read_parquet(
        MANIFEST,
        columns=[
            "state_group", "source_type", "collection", "asset", "acquisition_date",
            "stable", "path", "actual_bytes", "file_mtime",
        ],
    )
    dates = pd.to_datetime(manifest.acquisition_date, errors="coerce")
    month_day = dates.dt.month * 100 + dates.dt.day
    manifest = manifest.loc[
        manifest.source_type.eq("MODIS")
        & manifest.collection.eq("modis-11A1-061")
        & manifest.asset.isin(["LST_Day_1km", "LST_Night_1km"])
        & manifest.stable.astype(bool)
        & dates.dt.year.between(2000, 2025)
        & month_day.between(515, 815)
    ].copy()
    manifest["year"] = dates.loc[manifest.index].dt.year.astype(int)
    statuses = []
    for group in ["PR_SC", "RS", "SP", "MS"]:
        group_stations = stations.loc[stations.state_group.eq(group)].reset_index(drop=True)
        for year in YEARS:
            files = manifest.loc[manifest.state_group.eq(group) & manifest.year.eq(year)]
            statuses.append(process_partition(group, year, files, group_stations))
    status_frame = pd.DataFrame(statuses)
    status_frame.to_csv(INDEX, index=False)
    coverage = status_frame.groupby("state_group", as_index=False).agg(
        first_year_with_files=("year", lambda x: int(status_frame.loc[x.index].loc[status_frame.loc[x.index, "source_lst_files"].gt(0), "year"].min()) if status_frame.loc[x.index, "source_lst_files"].gt(0).any() else np.nan),
        last_year_with_files=("year", lambda x: int(status_frame.loc[x.index].loc[status_frame.loc[x.index, "source_lst_files"].gt(0), "year"].max()) if status_frame.loc[x.index, "source_lst_files"].gt(0).any() else np.nan),
        years_with_files=("source_lst_files", lambda x: int((x > 0).sum())),
        source_lst_files=("source_lst_files", "sum"),
        mean_day_valid_fraction=("mean_day_valid_fraction", "mean"),
        mean_night_valid_fraction=("mean_night_valid_fraction", "mean"),
    )
    coverage.to_csv(AUDIT, index=False)
    marker = {
        "status": "HISTORICAL_MODIS_STATION_YEAR_OK",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "season": "15 May-15 August",
        "years": [2000, 2025],
        "inmet_stations": int(len(stations)),
        "partitions": len(status_frame),
        "source_lst_files": int(status_frame.source_lst_files.sum()),
        "features": FEATURES,
        "coverage_table": str(AUDIT),
    }
    (DB / "HISTORICAL_MODIS_STATION_YEAR_OK.json").write_text(json.dumps(marker, indent=2), encoding="utf-8")
    print(json.dumps(marker, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
