from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1]
MODIS_MARKER = MODULE / "database/HISTORICAL_MODIS_STATION_YEAR_OK.json"
RESULT_MARKER = MODULE / "outputs/historical_paired_model_statistics/HISTORICAL_PAIRED_RF_STATISTICS_OK"
ACTIVE_MARKER = MODULE / "checkpoints/HISTORICAL_STATISTICS_ORCHESTRATOR_ACTIVE.json"
VALIDATION_SCRIPT = MODULE / "scripts/11_validate_historical_paired_models.py"
LOG_DIR = MODULE / "logs"


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if RESULT_MARKER.exists():
        return 0
    ACTIVE_MARKER.write_text(
        json.dumps({"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()}, indent=2),
        encoding="utf-8",
    )
    try:
        while not MODIS_MARKER.exists():
            time.sleep(15)
        with (LOG_DIR / "historical_paired_statistics.out").open("w", encoding="utf-8") as stdout, (
            LOG_DIR / "historical_paired_statistics.err"
        ).open("w", encoding="utf-8") as stderr:
            completed = subprocess.run(
                [sys.executable, str(VALIDATION_SCRIPT)],
                cwd=str(MODULE.parent.parent),
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
        return completed.returncode
    finally:
        ACTIVE_MARKER.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
