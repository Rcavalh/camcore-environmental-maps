from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import time


MODULE = Path(__file__).resolve().parents[1]
READY = MODULE / "checkpoints/updated_historical_10000_smoke/UPDATED_HISTORICAL_PIPELINE_10000_OK.json"
LOCK = MODULE / "checkpoints/full_native_tile_smoke/ACTIVE.json"
OK = MODULE / "checkpoints/full_native_tile_smoke/FULL_NATIVE_TILE_SMOKE_OK.json"
LOGS = MODULE / "logs"


def run(script: str, stem: str, *arguments: str) -> None:
    with (LOGS / f"{stem}.out").open("w", encoding="utf-8") as out, (LOGS / f"{stem}.err").open("w", encoding="utf-8") as err:
        result = subprocess.run([sys.executable, str(MODULE / "scripts" / script), *arguments], cwd=MODULE.parents[1],
                                stdout=out, stderr=err, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"{script} failed with exit code {result.returncode}")


def main() -> int:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if OK.exists():
        print("FULL_NATIVE_TILE_SMOKE_ALREADY_OK", flush=True)
        return 0
    LOCK.write_text(json.dumps({"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    try:
        while not READY.exists():
            print("WAITING_FOR_UPDATED_HISTORICAL_10000_SMOKE", flush=True)
            time.sleep(300)
        run("20_train_full_native_climatology_rf.py", "full_native_climatology_model")
        run("21_predict_full_native_five_state_rf.py", "full_native_tile_smoke", "--max-tiles", "5")
        status = {"status": "FULL_NATIVE_TILE_SMOKE_OK", "completed_at": datetime.now(timezone.utc).isoformat(),
                  "model": str(MODULE / "outputs/full_native_climatology_model/FULL_NATIVE_CLIMATOLOGY_RF_MODEL_STATUS.json"),
                  "tile_smoke": str(MODULE / "outputs/full_native_five_state_rf_2000_2025/RUN_STATUS.json")}
        OK.write_text(json.dumps(status, indent=2), encoding="utf-8")
        print(json.dumps(status, indent=2), flush=True)
        return 0
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
