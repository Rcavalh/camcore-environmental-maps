from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap


MODULE = Path(__file__).resolve().parents[1]
MODEL = MODULE / "outputs/balanced_models_10000_temporal_enso/models/RF_BLOCK_BALANCED_ALL_ENDPOINTS.joblib"
OUT = MODULE / "articles/images/variable_importance"
TABLES = MODULE / "articles/tables/variable_importance"
SEED = 20260807
MAX_OBSERVATIONS = 2000


def load(name: str, filename: str):
    path = MODULE / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def formal_label(name: str) -> str:
    explicit = {
        "latitude": "Latitude",
        "longitude": "Longitude",
        "year": "Year",
        "elevation": "Elevation",
        "slope_deg": "Terrain slope",
        "eastness": "Terrain eastness",
        "northness": "Terrain northness",
        "TPI_native": "Topographic position index",
        "TRI_native": "Terrain ruggedness index",
        "roughness_native": "Terrain surface roughness",
        "plan_curvature": "Plan curvature",
        "profile_curvature": "Profile curvature",
        "surface_curvature_laplacian": "Laplacian terrain curvature",
        "cold_air_pooling_2000m": "Cold-air pooling index",
        "elevation_above_local_min_2000m": "Relative elevation above local minimum",
        "elevation_below_local_max_2000m": "Relative elevation below local maximum",
        "local_relief_2000m": "Local topographic relief",
        "local_sd_2000m": "Local elevation variability",
        "HAND_selected_m": "HAND",
    }
    if name in explicit:
        return explicit[name]
    label = name
    if label.startswith("era5__"):
        variable, statistic = label.removeprefix("era5__").split("__", 1)
        label = f"ERA5-Land {variable.replace('_', ' ')} ({statistic.replace('_', ' ')})"
    elif label.startswith("modis_"):
        label = "MODIS " + label.removeprefix("modis_").replace("_", " ")
    label = re.sub(r"\b2000m\b", "", label).strip()
    return label[0].upper() + label[1:]


def block(name: str) -> str:
    if name.startswith("era5__"):
        return "ERA5-Land"
    if name.startswith("modis_"):
        return "MODIS"
    return "Terrain + HAND + space/time"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    core = load("shap_balanced_core", "08_run_five_state_50000_smoke.py")
    validation = load("shap_balanced_validation", "11_validate_historical_paired_models.py")
    table, _, _ = validation.build_table(core)
    bundle = joblib.load(MODEL)
    features = list(bundle["features"])
    model = bundle["models"]["probability"]
    imputer = bundle["imputer"]
    work = table.loc[table.frost_any.notna()].copy()
    if len(work) > MAX_OBSERVATIONS:
        work = work.sample(MAX_OBSERVATIONS, random_state=SEED)
    x = imputer.transform(work[features]).astype(np.float32)

    explainer = shap.TreeExplainer(model, feature_perturbation="tree_path_dependent")
    values = np.asarray(explainer.shap_values(x, check_additivity=False))
    if values.ndim == 3:
        values = values[:, :, 1] if values.shape[-1] == 2 else values[1]
    if values.shape != x.shape:
        raise RuntimeError(f"Unexpected SHAP shape {values.shape}; expected {x.shape}")

    importance = pd.DataFrame({
        "feature": features,
        "display_name": [formal_label(name) for name in features],
        "block": [block(name) for name in features],
        "mean_abs_shap": np.abs(values).mean(axis=0),
        "mean_shap": values.mean(axis=0),
    }).sort_values("mean_abs_shap", ascending=False)
    importance["rank"] = np.arange(1, len(importance) + 1)
    importance.to_csv(TABLES / "SHAP_BALANCED_RF_FEATURE_IMPORTANCE.csv", index=False)
    blocks = importance.groupby("block", as_index=False).mean_abs_shap.sum().sort_values("mean_abs_shap", ascending=False)
    blocks["relative_importance_percent"] = 100 * blocks.mean_abs_shap / blocks.mean_abs_shap.sum()
    blocks.to_csv(TABLES / "SHAP_BALANCED_RF_BLOCK_IMPORTANCE.csv", index=False)

    display = [formal_label(name) for name in features]
    explanation = shap.Explanation(values=values, data=x, feature_names=display)
    for suffix, dpi in [("620DPI", 620), ("LIGHT", 180)]:
        plt.figure(figsize=(10.2, 10.8))
        shap.plots.beeswarm(explanation, max_display=20, show=False, plot_size=None)
        plt.xlabel("SHAP contribution to predicted frost probability", fontsize=13)
        plt.ylabel("")
        plt.xticks(fontsize=11)
        plt.yticks(fontsize=12)
        plt.tight_layout()
        plt.savefig(OUT / f"REDUCED_BALANCED_RF_SHAP_WASP_{suffix}.png", dpi=dpi, bbox_inches="tight")
        if suffix == "620DPI":
            plt.savefig(OUT / "REDUCED_BALANCED_RF_SHAP_WASP.pdf", bbox_inches="tight")
        plt.close()

    colors = {"Terrain + HAND + space/time": "#31688e", "ERA5-Land": "#35b779", "MODIS": "#fde725"}
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ordered = blocks.sort_values("relative_importance_percent")
    ax.barh(ordered.block, ordered.relative_importance_percent, color=[colors[x] for x in ordered.block])
    for y, value in enumerate(ordered.relative_importance_percent):
        ax.text(value + 0.6, y, f"{value:.1f}%", va="center", fontsize=12)
    ax.set_xlabel("Aggregated mean absolute SHAP contribution (%)", fontsize=12)
    ax.set_ylabel("")
    ax.tick_params(labelsize=12)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "REDUCED_BALANCED_RF_SHAP_BLOCKS_620DPI.png", dpi=620, bbox_inches="tight")
    fig.savefig(OUT / "REDUCED_BALANCED_RF_SHAP_BLOCKS.pdf", bbox_inches="tight")
    fig.savefig(OUT / "REDUCED_BALANCED_RF_SHAP_BLOCKS_LIGHT.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    status = {
        "status": "REDUCED_BALANCED_RF_SHAP_OK",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "model": str(MODEL),
        "observations": len(work),
        "features": len(features),
        "era5_features": sum(name.startswith("era5__") for name in features),
        "modis_features": sum(name.startswith("modis_") for name in features),
        "other_features": sum(not (name.startswith("era5__") or name.startswith("modis_")) for name in features),
    }
    (OUT / "REDUCED_BALANCED_RF_SHAP_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
