"""
Alert Dispatch Service

Handles checking statuses and dispatching alerts to subscribers.
Supports both Montreal and Quebec City.
"""

import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional

from app import db
from app.models import Subscriber, Address, AlertHistory

logger = logging.getLogger(__name__)


def should_send_alert(address_id: int, alert_type: str, reference_date: date = None) -> bool:
    """
    Check if we should send an alert (deduplication).

    For snow alerts: Prevents sending the same type within 24 hours.
    For waste alerts: Prevents sending duplicate for same collection date.
    """
    cutoff = datetime.utcnow() - timedelta(hours=24)

    query = AlertHistory.query.filter(
        AlertHistory.address_id == address_id,
        AlertHistory.alert_type == alert_type,
        AlertHistory.sent_at >= cutoff
    )

    if reference_date:
        query = query.filter(AlertHistory.reference_date == reference_date)

    return query.first() is None


def log_alert(address_id: int, city: str, alert_type: str, status: str,
              reference_date: date = None, delivered: bool = True, error: str = None):
    """Log an alert to history."""
    alert = AlertHistory(
        address_id=address_id,
        city=city,
        alert_type=alert_type,
        status=status,
        reference_date=reference_date,
        delivered=delivered,
        error_message=error
    )
    db.session.add(alert)
    db.session.commit()


def check_all_snow_statuses(city: str = None) -> Dict[str, Any]:
    """
    Check snow status for all subscribed addresses and send alerts.

    Args:
        city: Optional filter for 'montreal' or 'quebec' (None = both)

    Returns:
        Summary of checks and alerts sent.
    """
    # Get all active addresses with snow alerts enabled
    query = Address.query.join(Subscriber).filter(
        Subscriber.is_active == True,
        Address.snow_alerts == True
    )

    if city:
        query = query.filter(Address.city == city)

    addresses = query.all()

    results = {
        'addresses_checked': 0,
        'status_changes': 0,
        'alerts_sent': 0,
        'alerts_skipped': 0,
        'errors': 0,
        'by_city': {'montreal': 0, 'quebec': 0}
    }

    for address in addresses:
        try:
            results['addresses_checked'] += 1
            address_city = address.city or 'montreal'  # Default to montreal for legacy

            if address_city == 'montreal':
                check_result = _check_montreal_snow(address)
            else:
                check_result = _check_quebec_snow(address)

            if check_result.get('status_changed'):
                results['status_changes'] += 1

            if check_result.get('alert_sent'):
                results['alerts_sent'] += 1
                results['by_city'][address_city] += 1

            if check_result.get('alert_skipped'):
                results['alerts_skipped'] += 1

            if check_result.get('error'):
                results['errors'] += 1

        except Exception as e:
            logger.error(f"Error checking address {address.id}: {e}")
            results['errors'] += 1

    db.session.commit()

    logger.info(f"Snow status check complete: {results}")
    return results


def _check_montreal_snow(address: Address) -> Dict[str, Any]:
    """Check snow status for a Montreal address."""
    result = {'status_changed': False, 'alert_sent': False, 'alert_skipped': False}

    try:
        from app.services.montreal.planif_neige import get_status_for_street, detect_status_change
        from app.services.email import (
            send_snow_scheduled_alert,
            send_snow_urgent_alert,
            send_snow_cleared_alert
        )

        if not address.cote_rue_id:
            return result

        status = get_status_for_street(address.cote_rue_id)
        current_etat = status.get('etat', 'unknown')
        previous_etat = address.last_snow_status

        if previous_etat and previous_etat != current_etat:
            result['status_changed'] = True

            alert_type = detect_status_change(
                address.cote_rue_id,
                current_etat,
                previous_etat
            )

            if alert_type and should_send_alert(address.id, alert_type):
                subscriber = address.subscriber

                if alert_type == 'snow_scheduled':
                    email_result = send_snow_scheduled_alert(subscriber, address, status)
                elif alert_type == 'snow_urgent':
                    email_result = send_snow_urgent_alert(subscriber, address, status)
                elif alert_type == 'snow_cleared':
                    email_result = send_snow_cleared_alert(subscriber, address)
                else:
                    email_result = {'success': False}

                if email_result.get('success'):
                    result['alert_sent'] = True
                    log_alert(address.id, 'montreal', alert_type, current_etat, delivered=True)
                else:
                    result['error'] = email_result.get('error')
                    log_alert(address.id, 'montreal', alert_type, current_etat,
                              delivered=False, error=result['error'])
            elif alert_type:
                result['alert_skipped'] = True

        address.last_snow_status = current_etat
        address.last_snow_check = datetime.utcnow()

    except Exception as e:
        logger.error(f"Montreal snow check error for address {address.id}: {e}")
        result['error'] = str(e)

    return result


def _check_quebec_snow(address: Address) -> Dict[str, Any]:
    """Check snow status for a Quebec City address."""
    result = {'status_changed': False, 'alert_sent': False, 'alert_skipped': False}

    try:
        from app.services.quebec.snow_checker import get_status_for_location
        from app.services.email import send_snow_alert_quebec

        if not (address.latitude and address.longitude):
            return result

        status = get_status_for_location(address.latitude, address.longitude)
        has_operation = status.get('etat_deneig', 0) > 0
        current_etat = 'active' if has_operation else 'clear'
        previous_etat = address.last_snow_status

        if previous_etat and previous_etat != current_etat:
            result['status_changed'] = True

            if has_operation:
                alert_type = 'snow_active'

                if should_send_alert(address.id, alert_type):
                    subscriber = address.subscriber
                    email_result = send_snow_alert_quebec(subscriber, address, status)

                    if email_result.get('success'):
                        result['alert_sent'] = True
                        log_alert(address.id, 'quebec', alert_type, current_etat, delivered=True)
                    else:
                        result['error'] = email_result.get('error')
                        log_alert(address.id, 'quebec', alert_type, current_etat,
                                  delivered=False, error=result['error'])
                else:
                    result['alert_skipped'] = True

        address.last_snow_status = current_etat
        address.last_snow_check = datetime.utcnow()

    except Exception as e:
        logger.error(f"Quebec snow check error for address {address.id}: {e}")
        result['error'] = str(e)

    return result


def send_waste_reminders(city: str = None) -> Dict[str, Any]:
    """
    Send waste collection reminders for tomorrow's collections.

    Args:
        city: Optional filter for 'montreal' or 'quebec' (None = both)

    Returns:
        Summary of reminders sent.
    """
    # Get all active addresses with waste alerts enabled and coordinates
    query = Address.query.join(Subscriber).filter(
        Subscriber.is_active == True,
        Address.waste_alerts == True,
        Address.latitude.isnot(None),
        Address.longitude.isnot(None)
    )

    if city:
        query = query.filter(Address.city == city)

    addresses = query.all()

    results = {
        'addresses_checked': 0,
        'reminders_sent': 0,
        'no_collection': 0,
        'errors': 0,
        'by_city': {'montreal': 0, 'quebec': 0}
    }

    tomorrow = (datetime.utcnow() + timedelta(days=1)).date()

    for address in addresses:
        try:
            results['addresses_checked'] += 1
            address_city = address.city or 'montreal'

            if address_city == 'montreal':
                reminder_result = _send_montreal_waste_reminder(address, tomorrow)
            else:
                reminder_result = _send_quebec_waste_reminder(address, tomorrow)

            if reminder_result.get('no_collection'):
                results['no_collection'] += 1

            if reminder_result.get('reminder_sent'):
                results['reminders_sent'] += 1
                results['by_city'][address_city] += 1

            if reminder_result.get('error'):
                results['errors'] += 1

        except Exception as e:
            logger.error(f"Error sending waste reminder for address {address.id}: {e}")
            results['errors'] += 1

    logger.info(f"Waste reminders complete: {results}")
    return results


def _send_montreal_waste_reminder(address: Address, collection_date: date) -> Dict[str, Any]:
    """Send waste reminder for a Montreal address."""
    result = {'no_collection': False, 'reminder_sent': False}

    try:
        from app.services.montreal.waste import get_collections_for_tomorrow
        from app.services.email import send_waste_reminder

        collections = get_collections_for_tomorrow(address.latitude, address.longitude)

        if not collections:
            result['no_collection'] = True
            return result

        if not should_send_alert(address.id, 'waste_reminder', collection_date):
            return result

        subscriber = address.subscriber
        email_result = send_waste_reminder(subscriber, address, collections)

        if email_result.get('success'):
            result['reminder_sent'] = True
            log_alert(address.id, 'montreal', 'waste_reminder', 'tomorrow',
                      reference_date=collection_date, delivered=True)
        else:
            result['error'] = email_result.get('error')
            log_alert(address.id, 'montreal', 'waste_reminder', 'tomorrow',
                      reference_date=collection_date, delivered=False, error=result['error'])

    except Exception as e:
        logger.error(f"Montreal waste reminder error for address {address.id}: {e}")
        result['error'] = str(e)

    return result


def _send_quebec_waste_reminder(address: Address, collection_date: date) -> Dict[str, Any]:
    """Send waste reminder for a Quebec City address."""
    result = {'no_collection': False, 'reminder_sent': False}

    try:
        from app.services.quebec.waste import is_collection_tomorrow, get_waste_schedule
        from app.services.email import send_waste_reminder_quebec

        if not address.waste_zone_id:
            result['no_collection'] = True
            return result

        # Check if there's a collection tomorrow
        garbage_tomorrow = is_collection_tomorrow(address.waste_zone_id, 'garbage')
        recycling_tomorrow = is_collection_tomorrow(address.waste_zone_id, 'recycling')

        if not garbage_tomorrow and not recycling_tomorrow:
            result['no_collection'] = True
            return result

        if not should_send_alert(address.id, 'waste_reminder', collection_date):
            return result

        schedule = get_waste_schedule(waste_zone_id=address.waste_zone_id)
        subscriber = address.subscriber

        collections = []
        if garbage_tomorrow:
            collections.append('garbage')
        if recycling_tomorrow:
            collections.append('recycling')

        email_result = send_waste_reminder_quebec(subscriber, address, collections, schedule)

        if email_result.get('success'):
            result['reminder_sent'] = True
            log_alert(address.id, 'quebec', 'waste_reminder', 'tomorrow',
                      reference_date=collection_date, delivered=True)
        else:
            result['error'] = email_result.get('error')
            log_alert(address.id, 'quebec', 'waste_reminder', 'tomorrow',
                      reference_date=collection_date, delivered=False, error=result['error'])

    except Exception as e:
        logger.error(f"Quebec waste reminder error for address {address.id}: {e}")
        result['error'] = str(e)

    return result


def get_alert_summary(days: int = 7, city: str = None) -> Dict[str, Any]:
    """Get summary of alerts sent in the last N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    query = AlertHistory.query.filter(AlertHistory.sent_at >= cutoff)

    if city:
        query = query.filter(AlertHistory.city == city)

    alerts = query.all()

    by_type = {}
    by_day = {}
    by_city = {'montreal': 0, 'quebec': 0}
    success_count = 0
    failure_count = 0

    for alert in alerts:
        # By type
        alert_type = alert.alert_type
        by_type[alert_type] = by_type.get(alert_type, 0) + 1

        # By day
        day = alert.sent_at.strftime('%Y-%m-%d')
        by_day[day] = by_day.get(day, 0) + 1

        # By city
        alert_city = alert.city or 'montreal'
        by_city[alert_city] = by_city.get(alert_city, 0) + 1

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
        'by_city': by_city,
        'period_days': days
    }
