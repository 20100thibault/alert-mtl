"""
APScheduler Configuration

Handles scheduled background jobs for snow checks, waste reminders, etc.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

logger = logging.getLogger(__name__)

scheduler = None


def init_scheduler(app: Flask):
    """Initialize the scheduler with the Flask app."""
    global scheduler

    scheduler = BackgroundScheduler()

    # Add jobs
    add_scheduled_jobs(app)

    # Start scheduler
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def add_scheduled_jobs(app: Flask):
    """Add all scheduled jobs."""

    def snow_check_job():
        with app.app_context():
            try:
                from app.services.alerts import check_all_snow_statuses
                logger.info("Running scheduled snow check")
                result = check_all_snow_statuses()
                logger.info(f"Snow check complete: {result}")
            except Exception as e:
                logger.error(f"Snow check job failed: {e}")

    def waste_reminder_job():
        with app.app_context():
            try:
                from app.services.alerts import send_waste_reminders
                logger.info("Running scheduled waste reminders")
                result = send_waste_reminders()
                logger.info(f"Waste reminders complete: {result}")
            except Exception as e:
                logger.error(f"Waste reminder job failed: {e}")

    def geobase_refresh_job():
        with app.app_context():
            try:
                from app.services.geobase import refresh_cache
                logger.info("Running scheduled Geobase refresh")
                result = refresh_cache()
                logger.info(f"Geobase refresh complete: {result}")
            except Exception as e:
                logger.error(f"Geobase refresh job failed: {e}")

    # Add jobs using add_job method
    scheduler.add_job(snow_check_job, 'cron', minute='*/10', id='snow_check', replace_existing=True)
    scheduler.add_job(waste_reminder_job, 'cron', hour=18, minute=0, id='waste_reminder', replace_existing=True)
    scheduler.add_job(geobase_refresh_job, 'cron', day_of_week='sun', hour=3, id='geobase_refresh', replace_existing=True)

    logger.info("Scheduled jobs configured: snow_check (10min), waste_reminder (daily 6PM), geobase_refresh (weekly)")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shutdown")
