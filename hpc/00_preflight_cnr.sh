#!/usr/bin/env bash
#BSUB -J frost5_preflight
#BSUB -q cnr
#BSUB -n 4
#BSUB -W 00:30
#BSUB -R "span[hosts=1]"
#BSUB -R "rusage[mem=16GB]"
#BSUB -o 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/logs/lsf_preflight.%J.out
#BSUB -e 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/logs/lsf_preflight.%J.err
set -euo pipefail
source 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/hpc/runtime_env.sh
"$FROST_PYTHON_BIN" "$FROST_MODULE/hpc_full_native_rf/scripts/prepare_runtime_config.py"
hand_path="$FROST_HPC_INPUT/anadem_rs_pr_sc_sp_ms_30m_HAND_flowpath_within_2000m_filled_zero.tif"
expected_hand_sha256="3b45aa4535119916ba76a9c8b0d0145e02d700489d606bc970a5a55f29f9901c"
actual_hand_sha256="$(sha256sum "$hand_path" | awk '{print $1}')"
if [[ "$actual_hand_sha256" != "$expected_hand_sha256" ]]; then
  echo "HAND SHA-256 mismatch: expected=$expected_hand_sha256 actual=$actual_hand_sha256" >&2
  exit 1
fi
echo "HPC_HAND_SHA256_OK=$actual_hand_sha256"
"$FROST_PYTHON_BIN" - <<'PY'
import json
from pathlib import Path
import geopandas, joblib, matplotlib, numpy, pandas, pyarrow, rasterio, scipy, shapely, sklearn

module = Path("8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration").resolve()
config = json.loads((module / "hpc_full_native_rf/config/source_roots_hpc.json").read_text())
required = [
    Path(config["anadem_dem"]), Path(config["anadem_hand_2000m"]),
    module / "database/ERA5_STATION_YEAR_PARTITION_INDEX.csv",
    module / "database/MODIS_ALL_MODEL_READY_STATION_YEAR_2000_2025.parquet",
    module / "database/MODIS_ALL_MODEL_READY_STATION_YEAR_OK.json",
    module / "outputs/balanced_models_10000_temporal_enso/models/RF_BLOCK_BALANCED_ALL_ENDPOINTS.joblib",
    Path("4.Modelling/articles/tables/temporal_enso/NOAA_RONI_FROST_SEASON_2000_2025.csv"),
]
missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
parts = sorted((module / "database/era5_station_year_may15_aug15").rglob("features.parquet"))
if len(parts) != 108:
    missing.append(f"ERA5 partitions: expected 108, found {len(parts)}")
if missing:
    raise SystemExit("Missing HPC inputs:\n" + "\n".join(missing))
for raster in required[:2]:
    with rasterio.open(raster) as src:
        if src.width < 1 or src.height < 1 or src.crs is None:
            raise RuntimeError(f"Invalid raster: {raster}")
bundle = joblib.load(required[5])
if set(bundle["models"]) != {"probability", "frost_days", "seasonal_tmin_c"}:
    raise RuntimeError("Unexpected endpoint model bundle")
print("HPC_FULL_NATIVE_PREFLIGHT_OK")
print(f"features={len(bundle['features'])} era5_partitions={len(parts)}")
PY
