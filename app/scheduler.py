"""
APScheduler Configuration

Handles scheduled background jobs for snow checks, waste reminders, etc.
Supports both Montreal and Quebec City.
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
    """Add all scheduled jobs for both cities."""

    def snow_check_montreal_job():
        """Check snow status for Montreal subscribers."""
        with app.app_context():
            try:
                from app.services.alerts import check_all_snow_statuses
                logger.info("Running scheduled Montreal snow check")
                result = check_all_snow_statuses(city='montreal')
                logger.info(f"Montreal snow check complete: {result}")
            except Exception as e:
                logger.error(f"Montreal snow check job failed: {e}")

    def snow_check_quebec_job():
        """Check snow status for Quebec City subscribers."""
        with app.app_context():
            try:
                from app.services.alerts import check_all_snow_statuses
                logger.info("Running scheduled Quebec City snow check")
                result = check_all_snow_statuses(city='quebec')
                logger.info(f"Quebec City snow check complete: {result}")
            except Exception as e:
                logger.error(f"Quebec City snow check job failed: {e}")

    def waste_reminder_job():
        """Send waste reminders for both cities."""
        with app.app_context():
            try:
                from app.services.alerts import send_waste_reminders
                logger.info("Running scheduled waste reminders for both cities")
                result = send_waste_reminders()
                logger.info(f"Waste reminders complete: {result}")
            except Exception as e:
                logger.error(f"Waste reminder job failed: {e}")

    def geobase_refresh_job():
        """Refresh Montreal Geobase cache."""
        with app.app_context():
            try:
                from app.services.montreal.geobase import refresh_cache
                logger.info("Running scheduled Geobase refresh")
                result = refresh_cache()
                logger.info(f"Geobase refresh complete: {result}")
            except Exception as e:
                logger.error(f"Geobase refresh job failed: {e}")

    # Add jobs using add_job method
    # Snow checks every 10 minutes for both cities
    scheduler.add_job(snow_check_montreal_job, 'cron', minute='*/10', id='snow_check_montreal', replace_existing=True)
    scheduler.add_job(snow_check_quebec_job, 'cron', minute='*/10', id='snow_check_quebec', replace_existing=True)

    # Waste reminders at 6 PM for both cities
    scheduler.add_job(waste_reminder_job, 'cron', hour=18, minute=0, id='waste_reminder', replace_existing=True)

    # Montreal Geobase refresh weekly on Sunday at 3 AM
    scheduler.add_job(geobase_refresh_job, 'cron', day_of_week='sun', hour=3, id='geobase_refresh', replace_existing=True)

    logger.info("Scheduled jobs configured: snow_check_montreal (10min), snow_check_quebec (10min), waste_reminder (daily 6PM), geobase_refresh (weekly)")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shutdown")
