from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys


MODULE = Path(__file__).resolve().parents[1]
LOGS = MODULE / "logs"
CHECKPOINT = MODULE / "checkpoints/updated_historical_10000_smoke"
LOCK = CHECKPOINT / "ACTIVE_ORCHESTRATOR.json"
MODIS_LOCK = MODULE / "checkpoints/historical_modis_station_year/ACTIVE_EXTRACTION_LOCK"


def process_active(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, check=False,
        )
        return str(pid) in result.stdout
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, SystemError):
            return False


def pid_from_text(path: Path) -> int | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("active_process="):
            try:
                return int(line.split("=", 1)[1])
            except ValueError:
                return None
    return None


def run_stage(script: str, stem: str, *arguments: str) -> None:
    stdout = LOGS / f"{stem}.out"
    stderr = LOGS / f"{stem}.err"
    with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
        result = subprocess.run([sys.executable, str(MODULE / "scripts" / script), *arguments], cwd=MODULE.parents[1],
                                stdout=out, stderr=err, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"{script} failed with exit code {result.returncode}; see {stderr}")


def main() -> int:
    CHECKPOINT.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        prior = json.loads(LOCK.read_text(encoding="utf-8"))
        if process_active(int(prior.get("pid", -1))):
            raise SystemExit(f"UPDATED_SMOKE_ORCHESTRATOR_ALREADY_ACTIVE={prior['pid']}")
    LOCK.write_text(json.dumps({"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    try:
        modis_pid = pid_from_text(MODIS_LOCK)
        if modis_pid is not None and process_active(modis_pid):
            raise RuntimeError(f"A separate MODIS extractor is already active: {modis_pid}")
        MODIS_LOCK.unlink(missing_ok=True)
        run_stage("10_build_historical_modis_station_year.py", "historical_modis_refresh")
        run_stage("11_validate_historical_paired_models.py", "updated_historical_model_statistics")
        run_stage("18_predict_updated_historical_10000_smoke.py", "updated_historical_10000_smoke")
        status = {
            "status": "UPDATED_HISTORICAL_PIPELINE_10000_OK",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "model_status": str(MODULE / "outputs/historical_paired_model_statistics/HISTORICAL_PAIRED_RF_STATISTICS_STATUS.json"),
            "smoke_status": str(MODULE / "outputs/updated_historical_10000_smoke/UPDATED_HISTORICAL_RF_10000_STATUS.json"),
        }
        (CHECKPOINT / "UPDATED_HISTORICAL_PIPELINE_10000_OK.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        print(json.dumps(status, indent=2), flush=True)
        return 0
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
