from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time


MODULE = Path(__file__).resolve().parents[1]
LOGS = MODULE / "logs"
LOCK = LOGS / "incremental_watch.pid"
STATUS = MODULE / "database" / "INCREMENTAL_WATCH_STATUS.json"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-seconds", type=int, default=3600)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def pid_is_active(pid: int) -> bool:
    try:
        import psutil

        return psutil.pid_exists(pid)
    except ImportError:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def acquire_lock():
    LOGS.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            prior = int(LOCK.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            prior = -1
        if prior > 0 and pid_is_active(prior):
            raise SystemExit(f"INCREMENTAL_WATCH_ALREADY_RUNNING pid={prior}")
        LOCK.unlink(missing_ok=True)
    LOCK.write_text(str(os.getpid()), encoding="utf-8")


def run_stage(script: str, *arguments: str) -> dict:
    started = datetime.now(timezone.utc)
    command = [sys.executable, str(MODULE / "scripts" / script), *arguments]
    print(f"RUNNING={script} started={started.isoformat()}", flush=True)
    result = subprocess.run(command, cwd=MODULE.parents[1], check=False)
    ended = datetime.now(timezone.utc)
    record = {
        "script": script,
        "exit_code": result.returncode,
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
    }
    print(json.dumps(record), flush=True)
    return record


def main():
    args = parse_args()
    acquire_lock()
    try:
        while True:
            cycle_started = datetime.now(timezone.utc)
            stages = [
                run_stage("01_update_asset_catalog.py"),
                run_stage("03_build_station_era5_window_features.py"),
            ]
            status = {
                "status": "FIVE_STATE_INCREMENTAL_WATCH_OK"
                if all(stage["exit_code"] == 0 for stage in stages)
                else "FIVE_STATE_INCREMENTAL_WATCH_WARNING",
                "pid": os.getpid(),
                "cycle_started_at": cycle_started.isoformat(),
                "cycle_finished_at": datetime.now(timezone.utc).isoformat(),
                "next_check_seconds": None if args.once else args.interval_seconds,
                "stages": stages,
            }
            STATUS.parent.mkdir(parents=True, exist_ok=True)
            STATUS.write_text(json.dumps(status, indent=2), encoding="utf-8")
            print(json.dumps(status, indent=2), flush=True)
            if args.once:
                return 0 if status["status"].endswith("_OK") else 1
            time.sleep(args.interval_seconds)
    finally:
        try:
            if LOCK.exists() and LOCK.read_text(encoding="utf-8").strip() == str(os.getpid()):
                LOCK.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
