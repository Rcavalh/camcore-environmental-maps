from pathlib import Path
import importlib.util
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODULE = Path(__file__).resolve().parents[1]
OUT = MODULE / "outputs/balanced_models_10000_temporal_enso"
SOURCE = MODULE / "outputs/updated_historical_10000_smoke/tables/UPDATED_HISTORICAL_RF_10000_PREDICTIONS.parquet"

spec = importlib.util.spec_from_file_location("partial_core", MODULE / "scripts/08_run_five_state_50000_smoke.py")
core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
data = np.load(OUT / "tables/ANNUAL_PREDICTIONS_PARTIAL.npz")
years = data["years"].astype(int)
points = pd.read_parquet(SOURCE, columns=["state", "longitude", "latitude"])
panels = [
    ("rf", "Random Forest balanced"),
    ("xgb", "XGBoost tuned"),
    ("tabpfn_classifier", "TabPFN classifier"),
    ("tabpfn_regressor", "TabPFN regressor"),
]
fig, axes = plt.subplots(2, 2, figsize=(11.5, 11.0))
boundaries = core.load_boundaries()
for ax, (key, title) in zip(axes.ravel(), panels):
    values = data[key].mean(axis=0)
    artist = ax.scatter(points.longitude, points.latitude, c=values, s=3.2, linewidths=0,
                        cmap="RdYlBu", vmin=0, vmax=1, rasterized=True)
    boundaries.boundary.plot(ax=ax, color="#222222", linewidth=0.55)
    ax.set_title(title, fontsize=12)
    ax.set_axis_off()
bar = fig.colorbar(artist, ax=axes.ravel().tolist(), fraction=0.024, pad=0.012, shrink=0.84)
bar.set_label("Frost-occurrence probability (blue = higher)")
fig.suptitle(f"Partial smoke preview — {years.min()}–{years.max()} ({len(years)} annual layers)", fontsize=15)
fig.text(0.5, 0.018, "10,000 fixed cells: 2,000 per state. Preliminary visualization; processing continues through 2025.",
         ha="center", fontsize=9)
fig.subplots_adjust(left=0.02, right=0.91, top=0.94, bottom=0.05, wspace=0.03, hspace=0.07)
target = OUT / "figures/BALANCED_MODELS_10000_PARTIAL_PREVIEW.png"
target.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(target, dpi=190, facecolor="white", bbox_inches="tight")
plt.close(fig)
print(target)
