"""
Alert Dispatch Service

Handles checking statuses and dispatching alerts to subscribers.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from app import db
from app.models import Subscriber, Address, AlertHistory

logger = logging.getLogger(__name__)


def should_send_alert(address_id: int, alert_type: str) -> bool:
    """
    Check if we should send an alert (deduplication).

    Prevents sending the same type of alert within 24 hours.
    """
    cutoff = datetime.utcnow() - timedelta(hours=24)

    existing = AlertHistory.query.filter(
        AlertHistory.address_id == address_id,
        AlertHistory.alert_type == alert_type,
        AlertHistory.sent_at >= cutoff
    ).first()

    return existing is None


def log_alert(address_id: int, alert_type: str, status: str, delivered: bool = True, error: str = None):
    """Log an alert to history."""
    alert = AlertHistory(
        address_id=address_id,
        alert_type=alert_type,
        status=status,
        delivered=delivered,
        error_message=error
    )
    db.session.add(alert)
    db.session.commit()


def check_all_snow_statuses() -> Dict[str, Any]:
    """
    Check snow status for all subscribed addresses and send alerts.

    Returns summary of checks and alerts sent.
    """
    from app.services.planif_neige import get_status_for_street, detect_status_change
    from app.services.email import (
        send_snow_scheduled_alert,
        send_snow_urgent_alert,
        send_snow_cleared_alert
    )

    # Get all active addresses
    addresses = Address.query.join(Subscriber).filter(
        Subscriber.is_active == True
    ).all()

    results = {
        'addresses_checked': 0,
        'status_changes': 0,
        'alerts_sent': 0,
        'alerts_skipped': 0,
        'errors': 0
    }

    for address in addresses:
        try:
            results['addresses_checked'] += 1

            # Get current status
            status = get_status_for_street(address.cote_rue_id)
            current_etat = status.get('etat', 'unknown')

            # Check for status change
            previous_etat = address.last_snow_status

            if previous_etat and previous_etat != current_etat:
                results['status_changes'] += 1

                # Determine alert type
                alert_type = detect_status_change(
                    address.cote_rue_id,
                    current_etat,
                    previous_etat
                )

                if alert_type and should_send_alert(address.id, alert_type):
                    # Get subscriber
                    subscriber = address.subscriber

                    # Send appropriate alert
                    if alert_type == 'snow_scheduled':
                        result = send_snow_scheduled_alert(subscriber, address, status)
                    elif alert_type == 'snow_urgent':
                        result = send_snow_urgent_alert(subscriber, address, status)
                    elif alert_type == 'snow_cleared':
                        result = send_snow_cleared_alert(subscriber, address)
                    else:
                        result = {'success': False, 'error': 'Unknown alert type'}

                    if result.get('success'):
                        results['alerts_sent'] += 1
                        log_alert(address.id, alert_type, current_etat, True)
                    else:
                        results['errors'] += 1
                        log_alert(address.id, alert_type, current_etat, False, result.get('error'))

                elif alert_type:
                    results['alerts_skipped'] += 1

            # Update address with current status
            address.last_snow_status = current_etat
            address.last_snow_check = datetime.utcnow()

        except Exception as e:
            logger.error(f"Error checking address {address.id}: {e}")
            results['errors'] += 1

    db.session.commit()

    logger.info(f"Snow status check complete: {results}")
    return results


def send_waste_reminders() -> Dict[str, Any]:
    """
    Send waste collection reminders for tomorrow's collections.

    Returns summary of reminders sent.
    """
    from app.services.waste import get_collections_for_tomorrow
    from app.services.email import send_waste_reminder

    # Get all active addresses with coordinates
    addresses = Address.query.join(Subscriber).filter(
        Subscriber.is_active == True,
        Address.latitude.isnot(None),
        Address.longitude.isnot(None)
    ).all()

    results = {
        'addresses_checked': 0,
        'reminders_sent': 0,
        'no_collection': 0,
        'errors': 0
    }

    for address in addresses:
        try:
            results['addresses_checked'] += 1

            # Get tomorrow's collections
            collections = get_collections_for_tomorrow(
                address.latitude,
                address.longitude
            )

            if not collections:
                results['no_collection'] += 1
                continue

            # Check deduplication
            if not should_send_alert(address.id, 'waste_reminder'):
                continue

            # Send reminder
            subscriber = address.subscriber
            result = send_waste_reminder(subscriber, address, collections)

            if result.get('success'):
                results['reminders_sent'] += 1
                log_alert(address.id, 'waste_reminder', 'tomorrow', True)
            else:
                results['errors'] += 1
                log_alert(address.id, 'waste_reminder', 'tomorrow', False, result.get('error'))

        except Exception as e:
            logger.error(f"Error sending waste reminder for address {address.id}: {e}")
            results['errors'] += 1

    logger.info(f"Waste reminders complete: {results}")
    return results


def get_alert_summary(days: int = 7) -> Dict[str, Any]:
    """Get summary of alerts sent in the last N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Count by type
    alerts = AlertHistory.query.filter(
        AlertHistory.sent_at >= cutoff
    ).all()

    by_type = {}
    by_day = {}
    success_count = 0
    failure_count = 0

    for alert in alerts:
        # By type
        alert_type = alert.alert_type
        by_type[alert_type] = by_type.get(alert_type, 0) + 1

        # By day
        day = alert.sent_at.strftime('%Y-%m-%d')
        by_day[day] = by_day.get(day, 0) + 1

        # Success/failure
        if alert.delivered:
            success_count += 1
        else:
            failure_count += 1

    return {
        'total': len(alerts),
        'success': success_count,
        'failure': failure_count,
        'by_type': by_type,
        'by_day': by_day,
        'period_days': days
    }
