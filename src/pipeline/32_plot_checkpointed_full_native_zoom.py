from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window, bounds as window_bounds

MODULE = Path(__file__).resolve().parents[1]
RUN = MODULE / "outputs/full_native_five_state_rf_balanced_all_endpoints_period_enso"
RASTER = RUN / "rasters/RF_BALANCED_FROST_PROBABILITY_ALL_2000_2025_ANADEM30M.tif"
records=[]
for marker in (RUN/"checkpoints").glob("tile_*.json"):
    try:
        item=json.loads(marker.read_text())
        if item.get("valid",0)>0:
            parts=marker.stem.split("_")
            records.append((int(parts[1][1:]),int(parts[2][1:])))
    except Exception:
        pass
if not records:
    raise RuntimeError("No flushed valid tiles yet")
row0=min(x[0] for x in records); col0=min(x[1] for x in records)
row1=max(x[0] for x in records)+512; col1=max(x[1] for x in records)+512
with rasterio.open(RASTER) as src:
    row1=min(row1,src.height); col1=min(col1,src.width)
    win=Window(col0,row0,col1-col0,row1-row0)
    scale=max(win.width/2200,win.height/1400,1)
    data=src.read(1,window=win,out_shape=(max(1,round(win.height/scale)),max(1,round(win.width/scale))),
                  masked=True,resampling=Resampling.average)
    b=window_bounds(win,src.transform)
extent=[b[0],b[2],b[1],b[3]]
fig,axes=plt.subplots(2,1,figsize=(13,6.5),sharex=True,sharey=True)
im=axes[0].imshow(data,extent=extent,origin="upper",cmap="RdYlBu",vmin=0,vmax=1,aspect="auto")
axes[0].set_title("Flushed probability pixels — zoom on the currently processed strip")
coverage=~np.ma.getmaskarray(data)
axes[1].imshow(np.where(coverage,1,np.nan),extent=extent,origin="upper",cmap="Blues",vmin=0,vmax=1,aspect="auto")
axes[1].set_title("Persisted tile coverage")
for ax in axes: ax.set_ylabel("Latitude"); ax.grid(alpha=.15)
axes[1].set_xlabel("Longitude")
bar=fig.colorbar(im,ax=axes[0],fraction=.025,pad=.012); bar.set_label("Frost-occurrence probability")
fig.suptitle(f"Recoverable full-native checkpoint preview — {len(list((RUN/'checkpoints').glob('tile_*.json'))):,}/12,342 tiles")
fig.tight_layout(rect=[0,0,1,.95])
target=RUN/"figures/RF_BALANCED_CHECKPOINTED_TILE_ZOOM_LIGHT.png"; target.parent.mkdir(parents=True,exist_ok=True)
fig.savefig(target,dpi=190,facecolor="white",bbox_inches="tight"); plt.close(fig)
print(target)
