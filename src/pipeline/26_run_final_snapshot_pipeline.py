from __future__ import annotations

import json
import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1]
SCRIPTS = MODULE / "scripts"
CHECKPOINTS = MODULE / "checkpoints/frozen_multisensor_modis_station_year"
LOGS = MODULE / "logs"
STATUS = MODULE / "outputs/FINAL_SNAPSHOT_PIPELINE_STATUS.json"


def write(stage: str, **extra) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    payload = {"status": stage, "updated_at": datetime.now(timezone.utc).isoformat(), **extra}
    STATUS.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload), flush=True)


def run(script: str, *args: str) -> None:
    command = [sys.executable, str(SCRIPTS / script), *args]
    print("RUNNING=" + " ".join(command), flush=True)
    subprocess.run(command, cwd=MODULE.parents[1], check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-after-fit", action="store_true")
    args = parser.parse_args()
    LOGS.mkdir(parents=True, exist_ok=True)
    if not args.resume_after_fit:
        while True:
            markers = len(list(CHECKPOINTS.glob("*.json")))
            write("WAITING_FOR_FROZEN_MODIS_PARTITIONS", partitions=markers, expected_partitions=104)
            if markers >= 104:
                break
            time.sleep(60)
        write("FINALIZING_FROZEN_MODIS")
        run("25_build_frozen_multisensor_modis_station_year.py", "--finalize-only")
        write("FITTING_FINAL_STATION_YEAR_MODELS")
        run("11_validate_historical_paired_models.py")
    write("RUNNING_STRATIFIED_10000_SMOKE")
    run("18_predict_updated_historical_10000_smoke.py")
    smoke_path = MODULE / "outputs/updated_historical_10000_smoke/UPDATED_HISTORICAL_RF_10000_STATUS.json"
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    if smoke.get("points") != 10000 or set(smoke.get("points_per_state", {}).values()) != {2000}:
        raise RuntimeError("Final smoke did not produce exactly 2,000 cells per state")
    if smoke.get("modis_features", 0) <= 9:
        raise RuntimeError("Final smoke did not incorporate the frozen multisensor MODIS features")
    write("TRAINING_FINAL_NATIVE_MODELS", smoke=smoke)
    run("20_train_full_native_climatology_rf.py")
    write("RUNNING_NATIVE_TILE_CONTRACT")
    run("21_predict_full_native_five_state_rf.py", "--tile-size", "512", "--max-tiles", "5")
    tile_status = json.loads((MODULE / "outputs/full_native_five_state_rf_final_snapshot_20260806/RUN_STATUS.json").read_text(encoding="utf-8"))
    audit = MODULE / "outputs/full_native_five_state_rf_final_snapshot_20260806/audit/tile_audit_this_run.csv"
    if not audit.exists():
        raise RuntimeError("Native tile contract produced no audit")
    write("FULL_NATIVE_PREDICTION_RUNNING", smoke=smoke, tile_contract=tile_status)
    run("21_predict_full_native_five_state_rf.py", "--tile-size", "512")
    write("FINAL_SNAPSHOT_PIPELINE_OK", outputs=str(MODULE / "outputs/full_native_five_state_rf_final_snapshot_20260806"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
