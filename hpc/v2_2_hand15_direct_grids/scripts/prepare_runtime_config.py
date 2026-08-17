from __future__ import annotations

import json
import os
from pathlib import Path

project = Path(os.environ.get("FROST_PROJECT_ROOT", Path.cwd()))
module = project / "8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration"
runroot = module / "hpc_article_v2_2_direct_grids_hand15_2000_2026"
data = Path(os.environ.get("FROST_HPC_INPUT", module / "hpc_full_native_rf/data"))
output = runroot / "config/source_roots_hpc.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    "project_root": str(project),
    "anadem_dem": str(data / "ANADEM_v1_30m_RS_PR_SC_SP_MS_recortado.tif"),
    "anadem_hand_15000m": str(data / "anadem_rs_pr_sc_sp_ms_30m_HAND_flowpath_within_15000m_filled_zero.tif"),
    "hand_flowpath_radius_m": 15000,
    "event_window": {"start_month_day": "05-15", "end_month_day": "08-15", "years": [2000, 2026]},
}, indent=2), encoding="utf-8")
print(f"ARTICLE_V2_2_HAND15_RUNTIME_CONFIG_OK={output}")
