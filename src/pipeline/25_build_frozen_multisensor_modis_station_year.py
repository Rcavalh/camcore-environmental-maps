from __future__ import annotations

import hashlib
import argparse
import json
import os
import sys
from collections import defaultdict
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
MANIFEST = DB / "snapshots/final_environmental_snapshot_20260806/AVAILABLE_ENVIRONMENTAL_ASSET_MANIFEST_FROZEN.parquet"
STATIONS = DB / "STATION_PHYSIOGRAPHIC_COVARIATES_ANADEM_30M.parquet"
PARTITIONS = DB / "modis_multisensor_station_year_may15_aug15_frozen"
CHECKPOINTS = MODULE / "checkpoints/frozen_multisensor_modis_station_year"
INDEX = DB / "MODIS_MULTISENSOR_STATION_YEAR_PARTITION_INDEX.csv"
COVERAGE = DB / "MODIS_MULTISENSOR_STATION_YEAR_TEMPORAL_COVERAGE.csv"
UNIFIED = DB / "MODIS_ALL_MODEL_READY_STATION_YEAR_2000_2025.parquet"
STATE_GROUP = {"PR": "PR_SC", "SC": "PR_SC", "RS": "RS", "SP": "SP", "MS": "MS"}
YEARS = range(2000, 2026)

PRODUCTS = {
    "evi": dict(collection="modis-13Q1-061", assets=["250m_16_days_EVI"], qa="250m_16_days_VI_Quality", scale=0.0001, valid=(-2000, 10000), qa_rule="vi"),
    "lai": dict(collection="modis-15A3H-061", assets=["Lai_500m"], qa="FparLai_QC", scale=0.1, valid=(0, 100), qa_rule="modland"),
    "fpar": dict(collection="modis-15A3H-061", assets=["Fpar_500m"], qa="FparLai_QC", scale=0.01, valid=(0, 100), qa_rule="modland"),
    "gpp": dict(collection="modis-17A2HGF-061", assets=["Gpp_500m"], qa="Psn_QC_500m", scale=0.0001, valid=(0, 30000), qa_rule="modland"),
}


def granule_prefix(path: Path) -> str:
    return path.name.rsplit("__", 1)[0]


def sibling(path: Path, asset: str) -> Path:
    return path.with_name(granule_prefix(path) + "__" + asset + ".tif")


def qa_mask(values: np.ndarray, rule: str) -> np.ndarray:
    integer = np.nan_to_num(values, nan=65535).astype(np.uint16)
    if rule == "modland":
        return (integer & 0b11) <= 1
    if rule == "surface":
        cloud = integer & 0b11
        shadow = (integer >> 2) & 1
        internal_cloud = (integer >> 10) & 1
        return (cloud == 0) & (shadow == 0) & (internal_cloud == 0)
    if rule == "vi":
        modland = integer & 0b11
        usefulness = (integer >> 2) & 0b1111
        snow = (integer >> 14) & 1
        shadow = (integer >> 15) & 1
        return (modland <= 1) & (usefulness <= 10) & (snow == 0) & (shadow == 0)
    if rule == "mandatory":
        return integer == 0
    raise ValueError(rule)


def sample_pair(path: Path, qa_asset: str, stations: pd.DataFrame, scale: float, limits: tuple[float, float], rule: str) -> np.ndarray:
    result = np.full(len(stations), np.nan, dtype=np.float32)
    qa_path = sibling(path, qa_asset)
    if not qa_path.exists():
        return result
    with rasterio.open(path) as src, rasterio.open(qa_path) as qa:
        transformer = Transformer.from_crs(4326, src.crs, always_xy=True)
        x, y = transformer.transform(stations.longitude.to_numpy(), stations.latitude.to_numpy())
        inside = (x >= src.bounds.left) & (x <= src.bounds.right) & (y >= src.bounds.bottom) & (y <= src.bounds.top)
        if not inside.any():
            return result
        pos = np.flatnonzero(inside)
        coords = list(zip(np.asarray(x)[inside], np.asarray(y)[inside]))
        raw = np.asarray([v[0] for v in src.sample(coords, indexes=1, masked=False)], dtype=float)
        quality = np.asarray([v[0] for v in qa.sample(coords, indexes=1, masked=False)], dtype=float)
        valid = np.isfinite(raw) & (raw >= limits[0]) & (raw <= limits[1]) & np.isfinite(quality) & qa_mask(quality, rule)
        result[pos[valid]] = (raw[valid] * scale).astype(np.float32)
    return result


def mosaic_date(rows: pd.DataFrame, stations: pd.DataFrame, spec: dict) -> np.ndarray:
    by_platform: dict[str, np.ndarray] = {}
    for row in rows.itertuples(index=False):
        path = Path(row.path)
        platform = path.name[:3]
        values = sample_pair(path, spec["qa"], stations, spec["scale"], spec["valid"], spec["qa_rule"])
        if platform not in by_platform:
            by_platform[platform] = values
        else:
            fill = np.isfinite(values)
            by_platform[platform][fill] = values[fill]
    if not by_platform:
        return np.full(len(stations), np.nan, np.float32)
    stack = np.stack(list(by_platform.values()))
    count = np.isfinite(stack).sum(axis=0)
    return np.divide(np.nansum(stack, axis=0), count, out=np.full(len(stations), np.nan, np.float32), where=count > 0)


def reflectance_indices(files: pd.DataFrame, stations: pd.DataFrame, collection: str, bands: dict[str, str], qa: str, rule: str) -> dict[str, list[np.ndarray]]:
    subset = files.loc[files.collection.eq(collection) & files.asset.isin(list(bands.values()))]
    observations: dict[str, list[np.ndarray]] = defaultdict(list)
    for date, date_rows in subset.groupby("acquisition_date"):
        sampled = {}
        for key, asset in bands.items():
            rows = date_rows.loc[date_rows.asset.eq(asset)]
            if rows.empty:
                break
            spec = dict(qa=qa, scale=0.0001, valid=(-100, 32766), qa_rule=rule)
            sampled[key] = mosaic_date(rows, stations, spec)
        if len(sampled) != len(bands):
            continue
        red, nir, swir1, swir2 = sampled["red"], sampled["nir"], sampled["swir1"], sampled["swir2"]
        with np.errstate(divide="ignore", invalid="ignore"):
            values = {
                "ndmi": (nir - swir1) / (nir + swir1),
                "nbr": (nir - swir2) / (nir + swir2),
                "savi": 1.5 * (nir - red) / (nir + red + 0.5),
            }
        for name, vector in values.items():
            vector[~np.isfinite(vector) | (np.abs(vector) > 1.5)] = np.nan
            observations[name].append(vector.astype(np.float32))
    return observations


def summarize(vectors: list[np.ndarray], prefix: str, n: int) -> dict[str, np.ndarray]:
    if not vectors:
        blank = np.full(n, np.nan, np.float32)
        return {f"modis_{prefix}_{s}": blank.copy() for s in ["mean", "min", "p05", "max", "sd", "valid_fraction"]} | {f"modis_{prefix}_n_valid_observations": np.zeros(n, np.int16)}
    x = np.stack(vectors).astype(np.float32)
    count = np.isfinite(x).sum(axis=0)
    out = {}
    with np.errstate(all="ignore"):
        out[f"modis_{prefix}_mean"] = np.nanmean(x, axis=0).astype(np.float32)
        out[f"modis_{prefix}_min"] = np.nanmin(x, axis=0).astype(np.float32)
        out[f"modis_{prefix}_p05"] = np.nanpercentile(x, 5, axis=0).astype(np.float32)
        out[f"modis_{prefix}_max"] = np.nanmax(x, axis=0).astype(np.float32)
        out[f"modis_{prefix}_sd"] = np.nanstd(x, axis=0).astype(np.float32)
    out[f"modis_{prefix}_valid_fraction"] = (count / max(len(vectors), 1)).astype(np.float32)
    out[f"modis_{prefix}_n_valid_observations"] = count.astype(np.int16)
    return out


def fingerprint(files: pd.DataFrame) -> str:
    cols = [c for c in ["path", "actual_bytes", "file_mtime"] if c in files]
    payload = files[cols].fillna("").astype(str).sort_values(cols).to_csv(index=False).encode()
    return hashlib.sha256(payload).hexdigest()


def process(group: str, year: int, files: pd.DataFrame, stations: pd.DataFrame) -> dict:
    output = PARTITIONS / f"state_group={group}/year={year}/features.parquet"
    marker = CHECKPOINTS / f"{group}_{year}.json"
    sig = fingerprint(files)
    if output.exists() and marker.exists():
        old = json.loads(marker.read_text(encoding="utf-8"))
        if old.get("source_fingerprint") == sig:
            return old
    observations: dict[str, list[np.ndarray]] = defaultdict(list)
    for name, spec in PRODUCTS.items():
        rows = files.loc[files.collection.eq(spec["collection"]) & files.asset.isin(spec["assets"])]
        for _, date_rows in rows.groupby("acquisition_date"):
            observations[name].append(mosaic_date(date_rows, stations, spec))
    surface = reflectance_indices(files, stations, "modis-09A1-061", {"red":"sur_refl_b01","nir":"sur_refl_b02","swir1":"sur_refl_b06","swir2":"sur_refl_b07"}, "sur_refl_state_500m", "surface")
    nbar = reflectance_indices(files, stations, "modis-43A4-061", {"red":"Nadir_Reflectance_Band1","nir":"Nadir_Reflectance_Band2","swir1":"Nadir_Reflectance_Band6","swir2":"Nadir_Reflectance_Band7"}, "BRDF_Albedo_Band_Mandatory_Quality_Band1", "mandatory")
    for name, vectors in surface.items(): observations[name].extend(vectors)
    for name, vectors in nbar.items(): observations[f"nbar_{name}"].extend(vectors)
    result = stations[["state","source","station_id","latitude","longitude"]].copy()
    for name in ["evi","lai","fpar","gpp","ndmi","nbr","savi","nbar_ndmi","nbar_nbr","nbar_savi"]:
        for column, values in summarize(observations[name], name, len(stations)).items():
            result[column] = values
    result["year"] = year
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output, index=False)
    status = {"status":"COMPLETE","state_group":group,"year":year,"stations":len(stations),"source_files":int(len(files)),"source_fingerprint":sig,"output":str(output),**{f"{k}_observations":len(v) for k,v in observations.items()}}
    marker.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"MODIS_MULTISENSOR_STATION_YEAR_OK={group}/{year}", flush=True)
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--groups", nargs="+", choices=["PR_SC", "RS", "SP", "MS"], default=["PR_SC", "RS", "SP", "MS"])
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--finalize-only", action="store_true")
    args = parser.parse_args()
    PARTITIONS.mkdir(parents=True, exist_ok=True); CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    stations = pd.read_parquet(STATIONS)
    stations = stations.loc[stations.source.eq("INMET")].copy()
    stations["state_group"] = stations.state.map(STATE_GROUP)
    manifest = pd.read_parquet(MANIFEST)
    dates = pd.to_datetime(manifest.acquisition_date, errors="coerce")
    md = dates.dt.month * 100 + dates.dt.day
    manifest = manifest.loc[manifest.source_type.eq("MODIS") & dates.dt.year.between(2000, 2025) & md.between(515,815)].copy()
    manifest["year"] = dates.loc[manifest.index].dt.year.astype(int)
    if not args.finalize_only:
        statuses=[]
        for group in args.groups:
            st=stations.loc[stations.state_group.eq(group)].reset_index(drop=True)
            for year in range(args.start_year, args.end_year + 1):
                statuses.append(process(group, year, manifest.loc[manifest.state_group.eq(group)&manifest.year.eq(year)], st))
        if set(args.groups) != {"PR_SC", "RS", "SP", "MS"}:
            print(f"MODIS_MULTISENSOR_GROUP_EXTRACTION_OK={','.join(args.groups)}", flush=True)
            return 0
    statuses=[]
    for group in ["PR_SC","RS","SP","MS"]:
        for year in YEARS:
            marker=CHECKPOINTS/f"{group}_{year}.json"
            if not marker.exists():
                raise RuntimeError(f"Missing frozen multisensor partition marker: {group}/{year}")
            statuses.append(json.loads(marker.read_text(encoding="utf-8")))
    index=pd.DataFrame(statuses); index.to_csv(INDEX,index=False)
    coverage=index.groupby("state_group",as_index=False).agg(years_with_files=("source_files",lambda x:int((x>0).sum())),source_files=("source_files","sum"))
    coverage.to_csv(COVERAGE,index=False)
    frames=[pd.read_parquet(p) for p in index.output]
    multi=pd.concat(frames,ignore_index=True)
    lst_index=pd.read_csv(DB/"MODIS_STATION_YEAR_PARTITION_INDEX.csv")
    lst=pd.concat([pd.read_parquet(p) for p in lst_index.loc[lst_index.status.eq("COMPLETE"),"output"]],ignore_index=True)
    keys=["state","source","station_id","latitude","longitude","year"]
    unified=lst.merge(multi,on=keys,how="outer",validate="one_to_one")
    unified.to_parquet(UNIFIED,index=False)
    contract={"status":"MODIS_ALL_MODEL_READY_STATION_YEAR_OK","completed_at":datetime.now(timezone.utc).isoformat(),"rows":len(unified),"stations":int(unified.station_id.nunique()),"years":[int(unified.year.min()),int(unified.year.max())],"model_ready_features":len([c for c in unified if c.startswith('modis_')]),"ndvi_excluded":True,"output":str(UNIFIED)}
    (DB/"MODIS_ALL_MODEL_READY_STATION_YEAR_OK.json").write_text(json.dumps(contract,indent=2),encoding="utf-8")
    print(json.dumps(contract,indent=2),flush=True)
    return 0


if __name__ == "__main__": raise SystemExit(main())
