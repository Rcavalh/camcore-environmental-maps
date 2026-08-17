#!/usr/bin/env bash
#BSUB -J frostv22_preflight
#BSUB -q cnr
#BSUB -n 4
#BSUB -W 01:00
#BSUB -R "span[hosts=1] rusage[mem=8GB]"
#BSUB -o 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026/logs/lsf_preflight.%J.out
#BSUB -e 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026/logs/lsf_preflight.%J.err
set -euo pipefail
source 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026/hpc/runtime_env.sh
"$FROST_PYTHON_BIN" "$FROST_RUNROOT/scripts/prepare_runtime_config.py"
"$FROST_PYTHON_BIN" - <<'PY'
import json, os
from pathlib import Path
import joblib, pandas as pd, rasterio
run = Path(os.environ["FROST_RUNROOT"])
cfg = json.loads((run / "config/source_roots_hpc.json").read_text())
dem = Path(cfg["anadem_dem"])
hand = Path(cfg["anadem_hand_15000m"])
model = Path(os.environ["FROST_MODEL"])
enso_csv = Path(os.environ["FROST_ENSO_CSV"])
required = [dem, hand, model, enso_csv]
missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
inputs = Path(os.environ["FROST_DIRECT_INPUT"])
for year in range(2000, 2027):
    for label in ("PR_SC", "RS", "SP", "MS"):
        for kind in ("ERA5_CONTINUOUS", "ERA5_DISCRETE", "MODIS_CONTINUOUS", "MODIS_DISCRETE"):
            path = inputs / f"{kind}_{year}_{label}.tif"
            if not path.is_file() or path.stat().st_size == 0:
                missing.append(str(path))
if missing:
    raise SystemExit("Missing HAND15 production inputs (first 30):\n" + "\n".join(missing[:30]))
with rasterio.open(dem) as d, rasterio.open(hand) as h:
    if d.shape != h.shape or not d.transform.almost_equals(h.transform, precision=1e-8):
        raise RuntimeError("ANADEM and HAND15 are not aligned")
bundle = joblib.load(model)
if bundle.get("hand_flowpath_radius_m") != 15000:
    raise RuntimeError("Model was not trained with HAND 15 km")
if bundle.get("requested_period") != [2000, 2026]:
    raise RuntimeError("Model period is not rigidly 2000-2026")
if len(bundle["features"]) != 115 or set(bundle["models"]) != {"probability", "frost_days", "seasonal_tmin_c"}:
    raise RuntimeError("Unexpected HAND15 RF model contract")
enso = pd.read_csv(enso_csv)
if set(enso.year.astype(int)) != set(range(2000, 2027)):
    raise RuntimeError("ENSO table must classify every year from 2000 through 2026")
print("ARTICLE_V2_2_HAND15_2000_2026_PREFLIGHT_OK")
PY
