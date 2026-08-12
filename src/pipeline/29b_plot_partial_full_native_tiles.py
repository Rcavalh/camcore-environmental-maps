from pathlib import Path
import importlib.util
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import rasterio
from rasterio.enums import Resampling

MODULE = Path(__file__).resolve().parents[1]
RUN = MODULE / "outputs/full_native_five_state_rf_balanced_period_enso"
RASTER = RUN / "rasters/RF_BALANCED_FROST_PROBABILITY_ALL_2000_2025_ANADEM30M.tif"
FIG = RUN / "figures"
FIG.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("partial_native_core", MODULE / "scripts/08_run_five_state_50000_smoke.py")
core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
boundaries = core.load_boundaries()

with rasterio.open(RASTER) as src:
    scale = max(src.width / 2400, src.height / 2400, 1)
    width, height = max(1, round(src.width / scale)), max(1, round(src.height / scale))
    values = src.read(1, out_shape=(height, width), masked=True, resampling=Resampling.average)
    bounds = src.bounds
    crs = src.crs

if crs:
    boundaries = boundaries.to_crs(crs)
extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
fig, axes = plt.subplots(1, 2, figsize=(13.5, 7.8))
im = axes[0].imshow(values, extent=extent, origin="upper", cmap="RdYlBu", vmin=0, vmax=1)
boundaries.boundary.plot(ax=axes[0], color="#222222", linewidth=0.65)
axes[0].set_title("Partial RF balanced probability")
axes[0].set_axis_off()
coverage = np.ma.getmaskarray(values) == 0
axes[1].imshow(np.where(coverage, 1.0, np.nan), extent=extent, origin="upper", cmap="Blues", vmin=0, vmax=1)
boundaries.boundary.plot(ax=axes[1], color="#222222", linewidth=0.65)
axes[1].set_title("Tiles currently populated")
axes[1].set_axis_off()
bar = fig.colorbar(im, ax=axes[0], fraction=0.035, pad=0.015, shrink=0.82)
bar.set_label("Frost-occurrence probability (blue = higher)")
n_tiles = len(list((RUN / "checkpoints").glob("tile_*.json")))
fig.suptitle(f"Full-native processing snapshot — {n_tiles:,} of 12,342 tiles", fontsize=15)
fig.text(0.5, 0.018, "Incomplete raster preview. Unprocessed cells are transparent and must not be interpreted as zero risk.", ha="center", fontsize=9)
fig.subplots_adjust(left=0.02, right=0.98, top=0.92, bottom=0.06, wspace=0.04)
light = FIG / "RF_BALANCED_FULL_NATIVE_PARTIAL_TILE_PREVIEW_LIGHT.png"
hd = FIG / "RF_BALANCED_FULL_NATIVE_PARTIAL_TILE_PREVIEW_620DPI.png"
fig.savefig(light, dpi=180, facecolor="white", bbox_inches="tight")
fig.savefig(hd, dpi=620, facecolor="white", bbox_inches="tight")
plt.close(fig)
print(light)
