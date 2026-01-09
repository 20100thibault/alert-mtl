"""
Waste Collection Integration Service

Handles downloading, caching, and querying Montreal's waste collection schedules.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import requests
from flask import current_app

logger = logging.getLogger(__name__)

# Montreal waste collection dataset URLs
WASTE_DATASETS = {
    'garbage': {
        'name': 'Garbage',
        'name_fr': 'Ordures ménagères',
        'url': 'https://donnees.montreal.ca/dataset/2df0fa28-7a7b-46c6-912f-93b215bd201e/resource/garbage.geojson'
    },
    'recycling': {
        'name': 'Recycling',
        'name_fr': 'Matières recyclables',
        'url': 'https://donnees.montreal.ca/dataset/2df0fa28-7a7b-46c6-912f-93b215bd201e/resource/recycling.geojson'
    },
    'organic': {
        'name': 'Organic/Food Waste',
        'name_fr': 'Résidus alimentaires',
        'url': 'https://donnees.montreal.ca/dataset/2df0fa28-7a7b-46c6-912f-93b215bd201e/resource/organic.geojson'
    },
    'green': {
        'name': 'Green Waste',
        'name_fr': 'Résidus verts',
        'url': 'https://donnees.montreal.ca/dataset/2df0fa28-7a7b-46c6-912f-93b215bd201e/resource/green.geojson'
    }
}

# Quebec statutory holidays (dates may shift year to year)
HOLIDAYS_2026 = [
    datetime(2026, 1, 1),   # New Year's Day
    datetime(2026, 4, 3),   # Good Friday
    datetime(2026, 4, 6),   # Easter Monday
    datetime(2026, 5, 18),  # Victoria Day
    datetime(2026, 6, 24),  # Saint-Jean-Baptiste
    datetime(2026, 7, 1),   # Canada Day
    datetime(2026, 9, 7),   # Labour Day
    datetime(2026, 10, 12), # Thanksgiving
    datetime(2026, 12, 25), # Christmas
    datetime(2026, 12, 26), # Boxing Day
]

# In-memory cache for waste data
_waste_cache = {
    'data': None,
    'fetched_at': None
}


def point_in_polygon(point: tuple, polygon: List[List[float]]) -> bool:
    """
    Ray casting algorithm to determine if point is inside polygon.

    Args:
        point: (lon, lat) tuple
        polygon: List of [lon, lat] coordinates forming the polygon

    Returns:
        True if point is inside polygon
    """
    x, y = point
    n = len(polygon)
    inside = False

    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y

    return inside


def fetch_waste_geojson(collection_type: str) -> Optional[Dict]:
    """Fetch waste collection GEOJSON data."""
    dataset = WASTE_DATASETS.get(collection_type)
    if not dataset:
        logger.error(f"Unknown collection type: {collection_type}")
        return None

    try:
        # Note: The actual URLs need to be confirmed from Montreal's open data portal
        # For now, using placeholder structure
        response = requests.get(dataset['url'], timeout=60)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch {collection_type} GEOJSON: {e}")
        return None


def load_all_waste_data() -> Dict[str, Any]:
    """Load all waste collection data."""
    global _waste_cache

    # Check cache
    cache_hours = current_app.config.get('WASTE_CACHE_HOURS', 24)
    if _waste_cache['data'] and _waste_cache['fetched_at']:
        age = (datetime.utcnow() - _waste_cache['fetched_at']).total_seconds() / 3600
        if age < cache_hours:
            return _waste_cache['data']

    # Fetch all datasets
    data = {}
    for collection_type in WASTE_DATASETS:
        geojson = fetch_waste_geojson(collection_type)
        if geojson:
            data[collection_type] = geojson

    if data:
        _waste_cache['data'] = data
        _waste_cache['fetched_at'] = datetime.utcnow()

    return data


def find_sector_for_point(lon: float, lat: float, geojson: Dict) -> Optional[Dict]:
    """Find which sector contains the given point."""
    if not geojson or 'features' not in geojson:
        return None

    point = (lon, lat)

    for feature in geojson['features']:
        geometry = feature.get('geometry', {})
        geom_type = geometry.get('type')
        coords = geometry.get('coordinates', [])

        if geom_type == 'Polygon':
            # Single polygon
            if coords and point_in_polygon(point, coords[0]):
                return feature.get('properties', {})

        elif geom_type == 'MultiPolygon':
            # Multiple polygons
            for polygon in coords:
                if polygon and point_in_polygon(point, polygon[0]):
                    return feature.get('properties', {})

    return None


def parse_collection_schedule(properties: Dict) -> Dict[str, Any]:
    """Parse collection schedule from sector properties."""
    # Properties structure depends on actual GEOJSON format
    # This is a simplified example

    schedule = {
        'day_of_week': properties.get('JOUR_COLLECTE'),
        'frequency': properties.get('FREQUENCE', 'weekly'),
        'start_time': properties.get('HEURE_DEBUT'),
        'notes': properties.get('NOTES', '')
    }

    return schedule


def get_next_collection_date(day_name: str, from_date: datetime = None) -> datetime:
    """Calculate the next occurrence of a collection day."""
    if from_date is None:
        from_date = datetime.now()

    # Map day names to weekday numbers (Monday=0)
    day_map = {
        'lundi': 0, 'monday': 0,
        'mardi': 1, 'tuesday': 1,
        'mercredi': 2, 'wednesday': 2,
        'jeudi': 3, 'thursday': 3,
        'vendredi': 4, 'friday': 4,
        'samedi': 5, 'saturday': 5,
        'dimanche': 6, 'sunday': 6,
    }

    target_day = day_map.get(day_name.lower(), 0)
    current_day = from_date.weekday()

    days_ahead = target_day - current_day
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7

    next_date = from_date + timedelta(days=days_ahead)

    # Adjust for holidays
    next_date = adjust_for_holiday(next_date)

    return next_date


def adjust_for_holiday(collection_date: datetime) -> datetime:
    """Adjust collection date if it falls on a holiday."""
    # Check if date is a holiday
    for holiday in HOLIDAYS_2026:
        if collection_date.date() == holiday.date():
            # Move to next day
            return collection_date + timedelta(days=1)

    return collection_date


def get_schedule_for_location(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Get complete waste collection schedule for a location."""
    waste_data = load_all_waste_data()

    if not waste_data:
        # Return mock data for testing when real data isn't available
        logger.warning("Using mock waste schedule data")
        return get_mock_schedule()

    schedule = {}

    for collection_type, geojson in waste_data.items():
        sector = find_sector_for_point(lon, lat, geojson)

        if sector:
            parsed = parse_collection_schedule(sector)

            # Calculate next collection date
            if parsed.get('day_of_week'):
                next_date = get_next_collection_date(parsed['day_of_week'])
                parsed['next_collection'] = next_date.strftime('%Y-%m-%d')
                parsed['next_collection_display'] = format_date_display(next_date)

            dataset_info = WASTE_DATASETS[collection_type]
            parsed['type'] = collection_type
            parsed['name'] = dataset_info['name']
            parsed['name_fr'] = dataset_info['name_fr']

            schedule[collection_type] = parsed

    return schedule if schedule else None


def get_mock_schedule() -> Dict[str, Any]:
    """Return mock schedule data for testing."""
    today = datetime.now()

    return {
        'garbage': {
            'type': 'garbage',
            'name': 'Garbage',
            'name_fr': 'Ordures ménagères',
            'day_of_week': 'Tuesday',
            'frequency': 'weekly',
            'next_collection': (today + timedelta(days=(1 - today.weekday() + 7) % 7 or 7)).strftime('%Y-%m-%d'),
            'next_collection_display': 'Tuesday'
        },
        'recycling': {
            'type': 'recycling',
            'name': 'Recycling',
            'name_fr': 'Matières recyclables',
            'day_of_week': 'Tuesday',
            'frequency': 'bi-weekly',
            'next_collection': (today + timedelta(days=(1 - today.weekday() + 7) % 7 or 7)).strftime('%Y-%m-%d'),
            'next_collection_display': 'Tuesday'
        },
        'organic': {
            'type': 'organic',
            'name': 'Organic/Food Waste',
            'name_fr': 'Résidus alimentaires',
            'day_of_week': 'Friday',
            'frequency': 'weekly',
            'next_collection': (today + timedelta(days=(4 - today.weekday() + 7) % 7 or 7)).strftime('%Y-%m-%d'),
            'next_collection_display': 'Friday'
        }
    }


def format_date_display(date: datetime) -> str:
    """Format date for display."""
    today = datetime.now().date()
    target = date.date()

    if target == today:
        return 'Today'
    elif target == today + timedelta(days=1):
        return 'Tomorrow'
    else:
        return date.strftime('%A, %B %d')


def get_collections_for_tomorrow(lat: float, lon: float) -> List[Dict[str, Any]]:
    """Get list of collections happening tomorrow (for reminders)."""
    schedule = get_schedule_for_location(lat, lon)

    if not schedule:
        return []

    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    collections = []

    for collection_type, info in schedule.items():
        if info.get('next_collection') == tomorrow:
            collections.append(info)

    return collections
