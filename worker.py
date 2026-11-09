from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timezone
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import Config
from logging_setup import configure_logging
from retention import run_cleanup
from storage import init_db, get_settings, update_worker_state

db_path = Config.DATABASE_PATH
logger = configure_logging(Config.LOG_PATH)
scheduler = BlockingScheduler(timezone=os.environ.get("TZ", "UTC"))

def cleanup_job():
    settings = get_settings(db_path)
    if not settings["worker_enabled"]:
        return
    result = run_cleanup(settings["target_paths"], settings["retention_months"],
                         settings["dry_run"], logger)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    update_worker_state(db_path, last_run=now, last_result=json.dumps(result))
    logger.info("Scheduled job result: %s", result)

def sync_schedule():
    settings = get_settings(db_path)
    update_worker_state(db_path, heartbeat=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    job = scheduler.get_job("retention-cleanup")
    if settings["worker_enabled"]:
        if job is None:
            scheduler.add_job(cleanup_job, IntervalTrigger(hours=settings["interval_hours"]),
                              id="retention-cleanup", replace_existing=True,
                              max_instances=1, coalesce=True, next_run_time=None)
            logger.info("Cleanup schedule enabled; interval=%s hours", settings["interval_hours"])
        elif job.trigger.interval.total_seconds() != settings["interval_hours"] * 3600:
            scheduler.reschedule_job("retention-cleanup",
                                     trigger=IntervalTrigger(hours=settings["interval_hours"]))
            logger.info("Cleanup schedule updated; interval=%s hours", settings["interval_hours"])
    elif job is not None:
        scheduler.remove_job("retention-cleanup")
        logger.info("Cleanup schedule disabled.")

def main():
    init_db(db_path)
    logger.info("Retention worker starting.")
    scheduler.add_job(sync_schedule, IntervalTrigger(seconds=max(2, Config.WORKER_POLL_SECONDS)),
                      id="settings-sync", max_instances=1, coalesce=True)
    sync_schedule()
    scheduler.start()

if __name__ == "__main__":
    main()
