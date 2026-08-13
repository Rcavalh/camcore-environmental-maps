#!/usr/bin/env python3
"""Build lightweight, value-preserving web previews for monthly P95 Tmax."""
from __future__ import annotations

import argparse, base64, json, math, zlib
from pathlib import Path
import numpy as np
import rasterio
from rasterio.enums import Resampling
from PIL import Image

MONTHS=("JANUARY","FEBRUARY","MARCH","OCTOBER","NOVEMBER","DECEMBER")
V_MIN,V_MAX=22.0,42.0
STOPS=np.array([[49,54,149],[69,117,180],[171,217,233],[255,255,191],[253,174,97],[215,48,39]],dtype=float)

def colorize(values:np.ndarray)->Image.Image:
    norm=np.nan_to_num(np.clip((values-V_MIN)/(V_MAX-V_MIN),0,1),nan=0.0)
    pos=norm*(len(STOPS)-1); lo=np.floor(pos).astype(int); hi=np.minimum(lo+1,len(STOPS)-1); frac=(pos-lo)[...,None]
    rgb=STOPS[lo]*(1-frac)+STOPS[hi]*frac; alpha=np.where(np.isfinite(values),245,0).astype(np.uint8)
    rgb[~np.isfinite(values)]=0
    return Image.fromarray(np.dstack([rgb.astype(np.uint8),alpha]),'RGBA')

def grid_payload(grid_id:str,values:np.ndarray,bounds:list[list[float]])->dict:
    finite=np.isfinite(values); q=np.full(values.shape,65535,dtype='<u2')
    q[finite]=np.rint(np.clip((values[finite]-V_MIN)/(V_MAX-V_MIN),0,1)*65534).astype('<u2')
    raw=zlib.compress(q.tobytes(),9)
    return {'id':grid_id,'width':values.shape[1],'height':values.shape[0],'bounds':bounds,'minimum':V_MIN,'maximum':V_MAX,'quantizedMaximum':65534,'nodata':65535,'encoding':'zlib-base64-uint16-le','data':base64.b64encode(raw).decode('ascii')}

def main()->int:
    parser=argparse.ArgumentParser(); parser.add_argument('--source',type=Path,default=Path(r'Z:\ENVIROMICS\Camcore26\Articles\8.Frost_Risk_\tmax\maps\display_rasters')); parser.add_argument('--web',type=Path,required=True); args=parser.parse_args()
    preview=args.web/'assets'/'heat'; analysis=args.web/'assets'/'heat-analysis'; preview.mkdir(parents=True,exist_ok=True); analysis.mkdir(parents=True,exist_ok=True)
    layers=[]; manifest={}
    for month in MONTHS:
        candidates=sorted(args.source.glob(f'TMAX_P95_{month}_display_*.tif'))
        if not candidates: print(f'HEAT_MONTH_MISSING={month}'); continue
        path=candidates[0]
        with rasterio.open(path) as src:
            values=src.read(1,masked=True,resampling=Resampling.bilinear).filled(np.nan).astype(np.float32)
            bounds=[[float(src.bounds.bottom),float(src.bounds.left)],[float(src.bounds.top),float(src.bounds.right)]]
        valid=values[np.isfinite(values)]; slug=month.lower(); image_name=f'tmax_p95_{slug}_2000_2025.webp'; colorize(values).save(preview/image_name,'WEBP',lossless=True,method=6)
        grid_values=values[::2,::2]; grid_id=f'tmax_p95_{slug}'; js_name=f'{grid_id}.generated.js'; payload=grid_payload(grid_id,grid_values,bounds)
        (analysis/js_name).write_text("window.HEAT_ANALYSIS_GRIDS=window.HEAT_ANALYSIS_GRIDS||{};\n"+f"window.HEAT_ANALYSIS_GRIDS[{json.dumps(grid_id)}]={json.dumps(payload,separators=(',',':'))};\n",encoding='utf-8')
        manifest[grid_id]={'url':f'assets/heat-analysis/{js_name}'}
        layers.append({'id':grid_id,'month':month.title(),'monthPt':{'JANUARY':'Janeiro','FEBRUARY':'Fevereiro','MARCH':'Março','OCTOBER':'Outubro','NOVEMBER':'Novembro','DECEMBER':'Dezembro'}[month],'image':f'assets/heat/{image_name}','gridId':grid_id,'bounds':bounds,'minimum':float(valid.min()),'mean':float(valid.mean()),'maximum':float(valid.max()),'displayMinimum':V_MIN,'displayMaximum':V_MAX,'units':'°C','period':'2000–2025'})
    result={'layers':layers,'analysisManifest':manifest,'domain':'RS, PR, SC, SP and MS','period':'2000–2025','displayMinimum':V_MIN,'displayMaximum':V_MAX}
    (args.web/'heat.generated.js').write_text('window.HEAT_MAPS='+json.dumps(result,ensure_ascii=False,indent=2)+';\n',encoding='utf-8')
    print(f'HEAT_WEB_LAYERS_OK={len(layers)}')
    return 0
if __name__=='__main__': raise SystemExit(main())
