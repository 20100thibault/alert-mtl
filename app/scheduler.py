"""
APScheduler Configuration

Handles scheduled background jobs for snow checks, waste reminders, etc.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from flask import Flask

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def init_scheduler(app: Flask):
    """Initialize the scheduler with the Flask app."""
    # Configure job store for persistence
    jobstores = {
        'default': SQLAlchemyJobStore(url=app.config.get('SQLALCHEMY_DATABASE_URI'))
    }

    scheduler.configure(jobstores=jobstores)

    # Add jobs
    add_scheduled_jobs(app)

    # Start scheduler
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def add_scheduled_jobs(app: Flask):
    """Add all scheduled jobs."""

    # Snow status check - every 10 minutes during winter months
    @scheduler.scheduled_job('cron', minute='*/10', id='snow_check', replace_existing=True)
    def snow_check_job():
        with app.app_context():
            try:
                from app.services.alerts import check_all_snow_statuses
                logger.info("Running scheduled snow check")
                result = check_all_snow_statuses()
                logger.info(f"Snow check complete: {result}")
            except Exception as e:
                logger.error(f"Snow check job failed: {e}")

    # Waste reminders - daily at 6 PM Eastern
    @scheduler.scheduled_job('cron', hour=18, minute=0, id='waste_reminder', replace_existing=True)
    def waste_reminder_job():
        with app.app_context():
            try:
                from app.services.alerts import send_waste_reminders
                logger.info("Running scheduled waste reminders")
                result = send_waste_reminders()
                logger.info(f"Waste reminders complete: {result}")
            except Exception as e:
                logger.error(f"Waste reminder job failed: {e}")

    # Geobase refresh - weekly on Sunday at 3 AM
    @scheduler.scheduled_job('cron', day_of_week='sun', hour=3, id='geobase_refresh', replace_existing=True)
    def geobase_refresh_job():
        with app.app_context():
            try:
                from app.services.geobase import refresh_cache
                logger.info("Running scheduled Geobase refresh")
                result = refresh_cache()
                logger.info(f"Geobase refresh complete: {result}")
            except Exception as e:
                logger.error(f"Geobase refresh job failed: {e}")

    logger.info("Scheduled jobs configured: snow_check (10min), waste_reminder (daily 6PM), geobase_refresh (weekly)")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shutdown")
