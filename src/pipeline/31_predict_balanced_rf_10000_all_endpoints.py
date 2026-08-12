from pathlib import Path
import importlib.util
import json
from datetime import datetime, timezone

import geopandas as gpd
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

MODULE = Path(__file__).resolve().parents[1]
PROJECT = MODULE.parent.parent
OUT = MODULE / "outputs/balanced_models_10000_temporal_enso"
TABLES = OUT / "tables"; FIGURES = OUT / "figures"
SOURCE = MODULE / "outputs/updated_historical_10000_smoke/tables/UPDATED_HISTORICAL_RF_10000_PREDICTIONS.parquet"
MODEL = OUT / "models/RF_BLOCK_BALANCED_ALL_ENDPOINTS.joblib"
ENSO = PROJECT / "4.Modelling/articles/tables/temporal_enso/NOAA_RONI_FROST_SEASON_2000_2025.csv"
YEARS = list(range(2000, 2026))

def load(name, filename):
    p = MODULE / "scripts" / filename
    s = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m

def plot(points, boundaries, columns, title, filename, endpoint, vmin, vmax, cmap):
    n = len(columns); cols = 3 if n > 3 else n; rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(6.0*cols, 5.5*rows), squeeze=False)
    for ax, (column, label) in zip(axes.ravel(), columns):
        art = ax.scatter(points.longitude, points.latitude, c=points[column], s=3.0,
                         cmap=cmap, vmin=vmin, vmax=vmax, linewidths=0, rasterized=True)
        boundaries.boundary.plot(ax=ax, color="#222222", linewidth=0.5)
        ax.set_title(label); ax.set_axis_off()
    for ax in axes.ravel()[n:]: ax.set_visible(False)
    bar = fig.colorbar(art, ax=axes.ravel().tolist(), fraction=0.018, pad=0.012, shrink=0.84)
    bar.set_label(endpoint)
    fig.suptitle(title, fontsize=15, y=0.995)
    fig.subplots_adjust(left=0.015, right=0.92, top=0.90, bottom=0.025, wspace=0.025, hspace=0.10)
    for suffix, dpi in [("LIGHT", 170), ("620DPI", 620)]:
        fig.savefig(FIGURES / f"{filename}_{suffix}.png", dpi=dpi, facecolor="white", bbox_inches="tight")
    fig.savefig(FIGURES / f"{filename}.pdf", facecolor="white", bbox_inches="tight")
    plt.close(fig)

core = load("balanced_endpoint_map_core", "08_run_five_state_50000_smoke.py")
predictor = load("balanced_endpoint_map_predictor", "12_predict_historical_paired_200000.py")
bundle = joblib.load(MODEL)
features = list(bundle["features"]); imputer = bundle["imputer"]
points = pd.read_parquet(SOURCE)[["point_id","state","longitude","latitude"] + list(core.TERRAIN_FEATURES)].copy()
era5_features = [x for x in features if x.startswith("era5__")]
modis_features = [x for x in features if x.startswith("modis_")]
era5 = core.load_era5_wide().loc[lambda d: d.year.between(2000, 2025)]
modis = predictor.load_modis().loc[lambda d: d.year.between(2000, 2025)]
static = points[["latitude","longitude"] + list(core.TERRAIN_FEATURES)].reset_index(drop=True)
cache = TABLES / "RF_BALANCED_ANNUAL_ALL_ENDPOINTS_2000_2025.npz"
if cache.exists():
    saved = np.load(cache)
    annual = {key: saved[key] for key in ["probability", "frost_days", "seasonal_tmin_c"]}
else:
    annual = {"probability": [], "frost_days": [], "seasonal_tmin_c": []}
    for year in YEARS:
        e = era5.loc[era5.year.eq(year)].drop_duplicates(["source","station_id"])
        m = modis.loc[modis.year.eq(year)].drop_duplicates(["source","station_id"])
        em = core.idw_lookup(e, points, era5_features, k=4)
        mm = predictor.interpolate_or_missing(core, m, points, modis_features)
        frame = pd.concat([static, pd.DataFrame(em, columns=era5_features), pd.DataFrame(mm, columns=modis_features)], axis=1)
        frame.insert(2, "year", year)
        x = imputer.transform(frame[features]).astype(np.float32)
        annual["probability"].append(bundle["models"]["probability"].predict_proba(x)[:,1].astype(np.float32))
        annual["frost_days"].append(np.clip(bundle["models"]["frost_days"].predict(x),0,None).astype(np.float32))
        annual["seasonal_tmin_c"].append(bundle["models"]["seasonal_tmin_c"].predict(x).astype(np.float32))
        print(f"BALANCED_ENDPOINT_10000_YEAR_OK={year}", flush=True)
    annual = {k: np.stack(v) for k,v in annual.items()}
    np.savez_compressed(cache, years=np.array(YEARS), **annual)

periods = {"2000–2005":range(2000,2006), "2006–2010":range(2006,2011), "2011–2015":range(2011,2016),
           "2016–2020":range(2016,2021), "2021–2025":range(2021,2026)}
enso = pd.read_csv(ENSO)
phases = {phase: enso.loc[enso.enso_phase.eq(phase),"year"].astype(int).tolist() for phase in ["El Niño","Neutral","La Niña"]}
boundaries = core.load_boundaries()
contracts = {
    "probability": ("Frost-occurrence probability (blue = higher risk)", 0, 1, "RdYlBu"),
    "frost_days": ("Expected frost days per season (blue = higher risk)", 0, float(np.quantile(annual["frost_days"],.99)), "RdYlBu"),
    "seasonal_tmin_c": ("Seasonal minimum temperature (°C; blue = colder)", float(np.quantile(annual["seasonal_tmin_c"],.01)), float(np.quantile(annual["seasonal_tmin_c"],.99)), "RdYlBu_r"),
}
for endpoint, (label,vmin,vmax,cmap) in contracts.items():
    period_cols=[]
    for name, years in periods.items():
        col=f"{endpoint}_period_{name}"; idx=[YEARS.index(y) for y in years]
        points[col]=annual[endpoint][idx].mean(axis=0); period_cols.append((col,name))
    plot(points,boundaries,period_cols,f"RF balanced — five-year periods — {label}",f"RF_BALANCED_PERIODS_{endpoint.upper()}_10000",label,vmin,vmax,cmap)
    enso_cols=[]
    for name, years in phases.items():
        idx=[YEARS.index(y) for y in years if y in YEARS]; col=f"{endpoint}_enso_{name}"
        points[col]=annual[endpoint][idx].mean(axis=0); enso_cols.append((col,f"{name} (n={len(idx)})"))
    plot(points,boundaries,enso_cols,f"RF balanced — ENSO phases — {label}",f"RF_BALANCED_ENSO_{endpoint.upper()}_10000",label,vmin,vmax,cmap)
points.to_parquet(TABLES / "RF_BALANCED_10000_ALL_ENDPOINTS_PERIOD_ENSO.parquet", index=False)
(OUT / "RF_BALANCED_10000_ALL_ENDPOINTS_OK").write_text("OK\n", encoding="utf-8")
print(json.dumps({"status":"RF_BALANCED_10000_ALL_ENDPOINTS_OK","completed_at":datetime.now(timezone.utc).isoformat()},indent=2))
