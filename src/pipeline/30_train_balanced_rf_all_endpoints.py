from pathlib import Path
import importlib.util
import json
from datetime import datetime, timezone

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor

MODULE = Path(__file__).resolve().parents[1]
BASE = MODULE / "outputs/balanced_models_10000_temporal_enso/models/RF_XGBOOST_BLOCK_BALANCED_FINAL.joblib"
TARGET = MODULE / "outputs/balanced_models_10000_temporal_enso/models/RF_BLOCK_BALANCED_ALL_ENDPOINTS.joblib"

def load(name, filename):
    p = MODULE / "scripts" / filename
    s = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m

core = load("balanced_endpoints_core", "08_run_five_state_50000_smoke.py")
validation = load("balanced_endpoints_validation", "11_validate_historical_paired_models.py")
table, _, _ = validation.build_table(core)
bundle = joblib.load(BASE)
features = list(bundle["features"]); imputer = bundle["imputer"]

models = {"probability": bundle["rf"]}
targets = {"frost_days": ("frost_days", True), "seasonal_tmin_c": ("observed_season_tmin_c", False)}
for key, (target, poisson) in targets.items():
    work = table.loc[table[target].notna()].reset_index(drop=True)
    x = imputer.transform(work[features]).astype(np.float32)
    y = work[target].to_numpy(float)
    model = RandomForestRegressor(
        n_estimators=700, criterion="poisson" if poisson else "squared_error",
        min_samples_leaf=4, max_features=0.45, n_jobs=-1,
        random_state=20260807 + len(models),
    ).fit(x, y)
    models[key] = model
    print(f"BALANCED_RF_ENDPOINT_OK={key} n={len(work)}", flush=True)

bundle.update({"models": models, "terrain_features": list(core.TERRAIN_FEATURES),
               "trained_at": datetime.now(timezone.utc).isoformat(),
               "target_contract": {"probability": "frost_any", "frost_days": "frost_days",
                                   "seasonal_tmin_c": "observed_season_tmin_c"}})
joblib.dump(bundle, TARGET)
(TARGET.with_suffix(".json")).write_text(json.dumps({
    "status": "RF_BLOCK_BALANCED_ALL_ENDPOINTS_OK", "features": len(features),
    "endpoints": list(models), "output": str(TARGET)
}, indent=2), encoding="utf-8")
print(TARGET)
