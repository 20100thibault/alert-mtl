"""
Quebec City Waste Collection Service

Handles waste collection schedule lookups for Quebec City.
Quebec City uses a zone-based system with:
- Garbage collection on specific weekdays
- Recycling collection on odd or even weeks
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from app import db
from app.models import WasteZone

logger = logging.getLogger(__name__)

# Day name to number mapping
DAY_NAMES = {
    'monday': 0,
    'tuesday': 1,
    'wednesday': 2,
    'thursday': 3,
    'friday': 4,
    'saturday': 5,
    'sunday': 6
}

DAY_DISPLAY = {
    0: {'en': 'Monday', 'fr': 'Lundi'},
    1: {'en': 'Tuesday', 'fr': 'Mardi'},
    2: {'en': 'Wednesday', 'fr': 'Mercredi'},
    3: {'en': 'Thursday', 'fr': 'Jeudi'},
    4: {'en': 'Friday', 'fr': 'Vendredi'},
    5: {'en': 'Saturday', 'fr': 'Samedi'},
    6: {'en': 'Sunday', 'fr': 'Dimanche'},
}


def get_week_parity(date: datetime = None) -> str:
    """
    Determine if a date falls in an odd or even week.

    Quebec City uses ISO week numbers for recycling schedules.

    Returns:
        'odd' or 'even'
    """
    if date is None:
        date = datetime.now()

    # ISO week number (1-53)
    week_number = date.isocalendar()[1]

    return 'odd' if week_number % 2 == 1 else 'even'


def get_next_collection_date(collection_day: str, reference_date: datetime = None) -> datetime:
    """
    Calculate the next collection date for a given day of the week.

    Args:
        collection_day: Day name (e.g., 'monday', 'tuesday')
        reference_date: Date to calculate from (default: today)

    Returns:
        Next date that falls on the collection day
    """
    if reference_date is None:
        reference_date = datetime.now()

    target_weekday = DAY_NAMES.get(collection_day.lower())
    if target_weekday is None:
        logger.error(f"Invalid collection day: {collection_day}")
        return reference_date

    current_weekday = reference_date.weekday()
    days_ahead = target_weekday - current_weekday

    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7

    return reference_date + timedelta(days=days_ahead)


def get_next_recycling_date(collection_day: str, recycling_week: str, reference_date: datetime = None) -> datetime:
    """
    Calculate the next recycling collection date.

    Args:
        collection_day: Day name for recycling collection
        recycling_week: 'odd' or 'even' for the collection week
        reference_date: Date to calculate from

    Returns:
        Next recycling collection date
    """
    if reference_date is None:
        reference_date = datetime.now()

    # First, find the next occurrence of the collection day
    next_date = get_next_collection_date(collection_day, reference_date)

    # Check if this date matches the recycling week parity
    current_parity = get_week_parity(next_date)

    if current_parity != recycling_week.lower():
        # Need to go to the following week
        next_date += timedelta(days=7)

    return next_date


def get_waste_zone(zone_code: str) -> Optional[WasteZone]:
    """
    Get waste zone information by zone code.

    Args:
        zone_code: Quebec City waste zone code

    Returns:
        WasteZone model instance or None
    """
    return WasteZone.query.filter_by(zone_code=zone_code).first()


def get_waste_zone_by_id(zone_id: int) -> Optional[WasteZone]:
    """
    Get waste zone information by ID.

    Args:
        zone_id: Database ID of the waste zone

    Returns:
        WasteZone model instance or None
    """
    return WasteZone.query.get(zone_id)


def get_waste_schedule(waste_zone_id: int = None, zone_code: str = None) -> Optional[Dict[str, Any]]:
    """
    Get waste collection schedule for a Quebec City zone.

    Args:
        waste_zone_id: Database ID of the waste zone
        zone_code: Alternative lookup by zone code

    Returns:
        Dict with garbage and recycling schedule information
    """
    zone = None

    if waste_zone_id:
        zone = get_waste_zone_by_id(waste_zone_id)
    elif zone_code:
        zone = get_waste_zone(zone_code)

    if not zone:
        logger.warning(f"Waste zone not found: id={waste_zone_id}, code={zone_code}")
        return None

    today = datetime.now()
    garbage_day = zone.garbage_day.lower() if zone.garbage_day else None
    recycling_week = zone.recycling_week.lower() if zone.recycling_week else None

    result = {
        'zone_code': zone.zone_code,
        'zone_description': zone.description
    }

    # Calculate garbage schedule
    if garbage_day:
        next_garbage = get_next_collection_date(garbage_day, today)
        is_garbage_tomorrow = (next_garbage.date() - today.date()).days == 1

        result['garbage'] = {
            'name': 'Garbage',
            'day_of_week': DAY_DISPLAY.get(DAY_NAMES.get(garbage_day), {}).get('en', garbage_day.capitalize()),
            'next_collection': next_garbage.date().isoformat(),
            'next_collection_display': format_collection_date(next_garbage, today),
            'is_tomorrow': is_garbage_tomorrow
        }

    # Calculate recycling schedule
    if garbage_day and recycling_week:
        # Recycling typically on same day as garbage but alternate weeks
        next_recycling = get_next_recycling_date(garbage_day, recycling_week, today)
        is_recycling_tomorrow = (next_recycling.date() - today.date()).days == 1

        result['recycling'] = {
            'name': 'Recycling',
            'day_of_week': DAY_DISPLAY.get(DAY_NAMES.get(garbage_day), {}).get('en', garbage_day.capitalize()),
            'week_type': recycling_week.capitalize(),
            'next_collection': next_recycling.date().isoformat(),
            'next_collection_display': format_collection_date(next_recycling, today),
            'is_tomorrow': is_recycling_tomorrow
        }

    return result


def format_collection_date(collection_date: datetime, reference_date: datetime = None) -> str:
    """
    Format a collection date in a human-readable way.

    Returns strings like 'Tomorrow', 'This Wednesday', 'Next Friday'
    """
    if reference_date is None:
        reference_date = datetime.now()

    days_until = (collection_date.date() - reference_date.date()).days

    if days_until == 0:
        return 'Today'
    elif days_until == 1:
        return 'Tomorrow'
    elif days_until < 7:
        return f"This {collection_date.strftime('%A')}"
    elif days_until < 14:
        return f"Next {collection_date.strftime('%A')}"
    else:
        return collection_date.strftime('%B %d')


def is_collection_tomorrow(waste_zone_id: int, collection_type: str = 'garbage') -> bool:
    """
    Check if there's a collection tomorrow for a zone.

    Args:
        waste_zone_id: Database ID of the waste zone
        collection_type: 'garbage' or 'recycling'

    Returns:
        True if collection is tomorrow
    """
    schedule = get_waste_schedule(waste_zone_id=waste_zone_id)

    if not schedule:
        return False

    if collection_type == 'garbage':
        return schedule.get('garbage', {}).get('is_tomorrow', False)
    elif collection_type == 'recycling':
        return schedule.get('recycling', {}).get('is_tomorrow', False)

    return False


def seed_default_zones():
    """
    Seed default Quebec City waste zones.

    This creates a basic set of zones that can be expanded based on
    actual Quebec City waste zone data.
    """
    default_zones = [
        {'zone_code': 'QC-A', 'garbage_day': 'monday', 'recycling_week': 'odd', 'description': 'Zone A - Vieux-Quebec'},
        {'zone_code': 'QC-B', 'garbage_day': 'tuesday', 'recycling_week': 'even', 'description': 'Zone B - Saint-Roch'},
        {'zone_code': 'QC-C', 'garbage_day': 'wednesday', 'recycling_week': 'odd', 'description': 'Zone C - Limoilou'},
        {'zone_code': 'QC-D', 'garbage_day': 'thursday', 'recycling_week': 'even', 'description': 'Zone D - Sainte-Foy'},
        {'zone_code': 'QC-E', 'garbage_day': 'friday', 'recycling_week': 'odd', 'description': 'Zone E - Charlesbourg'},
    ]

    for zone_data in default_zones:
        existing = WasteZone.query.filter_by(zone_code=zone_data['zone_code']).first()
        if not existing:
            zone = WasteZone(**zone_data)
            db.session.add(zone)
            logger.info(f"Created waste zone: {zone_data['zone_code']}")

    db.session.commit()
    logger.info("Quebec City waste zones seeded")
