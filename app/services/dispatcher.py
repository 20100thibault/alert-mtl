"""
Unified Service Dispatcher

Routes service calls to the appropriate city-specific implementation
based on city parameter or postal code detection.
"""

import logging
from typing import Dict, Any, Optional

from app.models import detect_city_from_postal

logger = logging.getLogger(__name__)


def get_snow_status(city: str = None, postal_code: str = None, lat: float = None, lon: float = None) -> Dict[str, Any]:
    """
    Get snow removal status for a location.

    Auto-detects city from postal code if city not specified.

    Args:
        city: 'montreal' or 'quebec' (optional if postal_code provided)
        postal_code: Canadian postal code (used for city detection and geocoding)
        lat: Latitude (optional, for direct coordinate lookup)
        lon: Longitude (optional, for direct coordinate lookup)

    Returns:
        Dict with snow status information in unified format
    """
    # Detect city from postal code if not provided
    if not city and postal_code:
        try:
            city = detect_city_from_postal(postal_code)
        except ValueError as e:
            return {
                'error': str(e),
                'success': False
            }

    if not city:
        return {
            'error': 'City could not be determined. Please provide a valid postal code.',
            'success': False
        }

    # Route to appropriate service
    if city == 'montreal':
        return _get_montreal_snow_status(postal_code, lat, lon)
    elif city == 'quebec':
        return _get_quebec_snow_status(postal_code, lat, lon)
    else:
        return {
            'error': f'Unsupported city: {city}',
            'success': False
        }


def _get_montreal_snow_status(postal_code: str = None, lat: float = None, lon: float = None) -> Dict[str, Any]:
    """Get snow status from Montreal Planif-Neige service."""
    try:
        from app.services.montreal.planif_neige import get_status_for_street

        # If we have coordinates, try to find the cote_rue_id
        if lat and lon:
            # For Montreal, we need to find the street segment from coordinates
            # This is a simplified version - full implementation would use geobase
            cote_rue_id = lookup_cote_rue_id_from_coords(lat, lon)
            if cote_rue_id:
                status = get_status_for_street(cote_rue_id)
                status['city'] = 'montreal'
                return status

        # If we have postal code but no coordinates, try geocoding
        if postal_code and not (lat and lon):
            coords = _geocode_montreal_postal(postal_code)
            if coords:
                lat, lon = coords['lat'], coords['lon']

        # Default response if we can't get status
        return {
            'city': 'montreal',
            'etat': 'unknown',
            'etat_deneig': 0,
            'display': {
                'en': 'Unknown',
                'fr': 'Inconnu',
                'color': 'gray'
            },
            'parking_allowed': True,
            'message': 'Unable to determine snow status for this location.'
        }

    except Exception as e:
        logger.error(f"Montreal snow status error: {e}")
        return {
            'city': 'montreal',
            'error': str(e),
            'success': False
        }


def _get_quebec_snow_status(postal_code: str = None, lat: float = None, lon: float = None) -> Dict[str, Any]:
    """Get snow status from Quebec City ArcGIS service."""
    try:
        from app.services.quebec.snow_checker import (
            get_status_for_location,
            geocode_postal_code
        )

        # If we don't have coordinates, geocode the postal code
        if postal_code and not (lat and lon):
            location = geocode_postal_code(postal_code)
            if location:
                lat, lon = location['lat'], location['lon']
            else:
                return {
                    'city': 'quebec',
                    'error': f'Could not geocode postal code: {postal_code}',
                    'success': False
                }

        if lat and lon:
            status = get_status_for_location(lat, lon)
            status['city'] = 'quebec'
            return status

        return {
            'city': 'quebec',
            'error': 'No location provided',
            'success': False
        }

    except Exception as e:
        logger.error(f"Quebec snow status error: {e}")
        return {
            'city': 'quebec',
            'error': str(e),
            'success': False
        }


def get_waste_schedule(city: str = None, postal_code: str = None, lat: float = None, lon: float = None,
                       waste_zone_id: int = None) -> Optional[Dict[str, Any]]:
    """
    Get waste collection schedule for a location.

    Args:
        city: 'montreal' or 'quebec'
        postal_code: Canadian postal code
        lat: Latitude
        lon: Longitude
        waste_zone_id: Quebec City waste zone ID (optional)

    Returns:
        Dict with waste schedule information
    """
    # Detect city from postal code if not provided
    if not city and postal_code:
        try:
            city = detect_city_from_postal(postal_code)
        except ValueError:
            return None

    if city == 'montreal':
        return _get_montreal_waste_schedule(lat, lon)
    elif city == 'quebec':
        return _get_quebec_waste_schedule(waste_zone_id, postal_code, lat, lon)

    return None


def _get_montreal_waste_schedule(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Get waste schedule from Montreal GEOJSON service."""
    try:
        from app.services.montreal.waste import get_schedule_for_location

        if lat and lon:
            return get_schedule_for_location(lat, lon)

        return None

    except Exception as e:
        logger.error(f"Montreal waste schedule error: {e}")
        return None


def _get_quebec_waste_schedule(waste_zone_id: int = None, postal_code: str = None,
                                lat: float = None, lon: float = None) -> Optional[Dict[str, Any]]:
    """Get waste schedule from Quebec City zone-based system."""
    try:
        from app.services.quebec.waste import get_waste_schedule as qc_waste

        # If we have a waste_zone_id, use it directly
        if waste_zone_id:
            return qc_waste(waste_zone_id=waste_zone_id)

        # Try to determine zone from postal code FSA
        if postal_code:
            zone_code = _get_quebec_zone_from_postal(postal_code)
            if zone_code:
                schedule = qc_waste(zone_code=zone_code)
                if schedule:
                    return schedule

        # Fallback: return a default schedule based on typical Quebec City patterns
        return _get_quebec_default_schedule(postal_code)

    except Exception as e:
        logger.error(f"Quebec waste schedule error: {e}")
        # Fall back to default schedule on any error
        return _get_quebec_default_schedule(postal_code)


def _get_quebec_zone_from_postal(postal_code: str) -> Optional[str]:
    """
    Map Quebec City postal code FSA to waste zone.

    This is a simplified mapping - in production this would use
    actual Quebec City zone data.
    """
    if not postal_code:
        return None

    normalized = postal_code.upper().replace(' ', '')
    fsa = normalized[:3] if len(normalized) >= 3 else None

    if not fsa:
        return None

    # Map FSAs to zones (simplified mapping based on areas)
    QUEBEC_FSA_ZONES = {
        # Old Quebec / Downtown
        'G1K': 'QC-A', 'G1R': 'QC-A',
        # Saint-Roch / Saint-Sauveur
        'G1L': 'QC-B', 'G1N': 'QC-B',
        # Limoilou
        'G1M': 'QC-C', 'G1P': 'QC-C',
        # Sainte-Foy / Cap-Rouge
        'G1V': 'QC-D', 'G1W': 'QC-D', 'G1X': 'QC-D', 'G1Y': 'QC-D',
        # Charlesbourg / Beauport
        'G1B': 'QC-E', 'G1C': 'QC-E', 'G1E': 'QC-E', 'G1G': 'QC-E', 'G1H': 'QC-E',
        # Les Rivières
        'G2A': 'QC-B', 'G2B': 'QC-B', 'G2C': 'QC-E',
        # Haute-Saint-Charles
        'G3A': 'QC-C', 'G3B': 'QC-C', 'G3E': 'QC-D', 'G3G': 'QC-D',
    }

    return QUEBEC_FSA_ZONES.get(fsa)


def _get_quebec_default_schedule(postal_code: str = None) -> Dict[str, Any]:
    """
    Return a default Quebec City waste schedule.

    Used when zone data isn't available.
    """
    from datetime import datetime, timedelta

    today = datetime.now()
    current_week = today.isocalendar()[1]
    is_odd_week = current_week % 2 == 1

    # Default to Wednesday garbage, alternating recycling
    garbage_day = 2  # Wednesday
    days_until_garbage = (garbage_day - today.weekday()) % 7
    if days_until_garbage == 0:
        days_until_garbage = 7
    next_garbage = today + timedelta(days=days_until_garbage)

    # Recycling on same day but every other week
    days_until_recycling = days_until_garbage
    recycling_date = today + timedelta(days=days_until_recycling)
    recycling_week_parity = recycling_date.isocalendar()[1] % 2 == 1

    # If this week isn't a recycling week, add a week
    if recycling_week_parity != is_odd_week:
        days_until_recycling += 7

    next_recycling = today + timedelta(days=days_until_recycling)

    def format_date(d: datetime) -> str:
        days = (d.date() - today.date()).days
        if days == 0:
            return 'Today'
        elif days == 1:
            return 'Tomorrow'
        elif days < 7:
            return f"This {d.strftime('%A')}"
        else:
            return f"Next {d.strftime('%A')}"

    return {
        'zone_code': 'Default',
        'zone_description': 'Quebec City (estimated schedule)',
        'garbage': {
            'name': 'Garbage',
            'day_of_week': 'Wednesday',
            'next_collection': next_garbage.date().isoformat(),
            'next_collection_display': format_date(next_garbage),
            'is_tomorrow': days_until_garbage == 1
        },
        'recycling': {
            'name': 'Recycling',
            'day_of_week': 'Wednesday',
            'week_type': 'Odd' if is_odd_week else 'Even',
            'next_collection': next_recycling.date().isoformat(),
            'next_collection_display': format_date(next_recycling),
            'is_tomorrow': days_until_recycling == 1
        }
    }


def geocode_postal_code(postal_code: str) -> Optional[Dict[str, Any]]:
    """
    Geocode a postal code using the appropriate city service.

    Args:
        postal_code: Canadian postal code

    Returns:
        Dict with lat, lon, and city
    """
    try:
        city = detect_city_from_postal(postal_code)
    except ValueError:
        return None

    if city == 'montreal':
        return _geocode_montreal_postal(postal_code)
    elif city == 'quebec':
        return _geocode_quebec_postal(postal_code)

    return None


def _geocode_montreal_postal(postal_code: str) -> Optional[Dict[str, Any]]:
    """Geocode a Montreal postal code using FSA lookup or Nominatim."""
    # Import the FSA coordinates from routes (or define here)
    MONTREAL_FSA_COORDS = {
        'H1A': (45.6205, -73.6049), 'H1B': (45.6275, -73.5699),
        'H1C': (45.6358, -73.5499), 'H1E': (45.6175, -73.5499),
        'H1G': (45.5958, -73.5849), 'H1H': (45.5832, -73.5949),
        'H1J': (45.5872, -73.5449), 'H1K': (45.5732, -73.5549),
        'H1L': (45.5642, -73.5349), 'H1M': (45.5552, -73.5549),
        'H1N': (45.5462, -73.5749), 'H1P': (45.5372, -73.5649),
        'H1R': (45.5252, -73.5849), 'H1S': (45.5432, -73.5949),
        'H1T': (45.5552, -73.5849), 'H1V': (45.5492, -73.5549),
        'H1W': (45.5362, -73.5449), 'H1X': (45.5472, -73.5849),
        'H1Y': (45.5382, -73.5749), 'H1Z': (45.5292, -73.5649),
        'H2A': (45.5508, -73.5738), 'H2B': (45.5418, -73.5638),
        'H2C': (45.5328, -73.5538), 'H2E': (45.5438, -73.5838),
        'H2G': (45.5348, -73.5938), 'H2H': (45.5258, -73.5838),
        'H2J': (45.5268, -73.5638), 'H2K': (45.5178, -73.5538),
        'H2L': (45.5188, -73.5638), 'H2M': (45.5598, -73.6288),
        'H2N': (45.5688, -73.6388), 'H2P': (45.5388, -73.6088),
        'H2R': (45.5298, -73.6188), 'H2S': (45.5388, -73.5988),
        'H2T': (45.5198, -73.5888), 'H2V': (45.5188, -73.6084),
        'H2W': (45.5108, -73.5988), 'H2X': (45.5088, -73.5696),
        'H2Y': (45.5038, -73.5596), 'H2Z': (45.5048, -73.5646),
        'H3A': (45.5048, -73.5746), 'H3B': (45.5008, -73.5696),
        'H3C': (45.4958, -73.5546), 'H3E': (45.4708, -73.5196),
        'H3G': (45.4958, -73.5796), 'H3H': (45.4908, -73.5896),
        'H3J': (45.4858, -73.5746), 'H3K': (45.4808, -73.5546),
        'H3L': (45.5558, -73.6488), 'H3M': (45.5438, -73.6588),
        'H3N': (45.5348, -73.6288), 'H3P': (45.4948, -73.6396),
        'H3R': (45.5018, -73.6296), 'H3S': (45.5028, -73.6196),
        'H3T': (45.4988, -73.6346), 'H3V': (45.4918, -73.6196),
        'H3W': (45.4848, -73.6296), 'H3X': (45.4778, -73.6196),
        'H3Y': (45.4818, -73.5896), 'H3Z': (45.4788, -73.5996),
        'H4A': (45.4708, -73.6096), 'H4B': (45.4638, -73.6096),
        'H4C': (45.4708, -73.5846), 'H4E': (45.4638, -73.5746),
        'H4G': (45.4568, -73.5896), 'H4H': (45.4558, -73.6046),
        'H4J': (45.5048, -73.6546), 'H4K': (45.5118, -73.6646),
        'H4L': (45.5188, -73.6546), 'H4M': (45.5258, -73.6546),
        'H4N': (45.5128, -73.6846), 'H4P': (45.4958, -73.6546),
        'H4R': (45.4878, -73.6746), 'H4S': (45.4968, -73.6846),
        'H4T': (45.4888, -73.6646), 'H4V': (45.4688, -73.6246),
        'H4W': (45.4618, -73.6346), 'H4X': (45.4548, -73.6446),
        'H4Y': (45.4478, -73.6546), 'H4Z': (45.4408, -73.6646),
        'H5A': (45.5000, -73.5550), 'H5B': (45.4950, -73.5600),
        'H7A': (45.5620, -73.7390), 'H7B': (45.5555, -73.7490),
        'H7C': (45.5485, -73.7590), 'H7E': (45.5415, -73.7690),
        'H7G': (45.5345, -73.7790), 'H7H': (45.5600, -73.7290),
        'H7K': (45.5495, -73.7210), 'H7L': (45.5725, -73.7200),
        'H7M': (45.5795, -73.7300), 'H7N': (45.5865, -73.7400),
        'H7P': (45.5795, -73.7500), 'H7R': (45.5725, -73.7600),
        'H7S': (45.5655, -73.7700), 'H7T': (45.5585, -73.7100),
        'H7V': (45.5515, -73.7000), 'H7W': (45.5665, -73.7050),
        'H7X': (45.5735, -73.6950), 'H7Y': (45.5805, -73.6850),
        'H8N': (45.4378, -73.7196), 'H8P': (45.4308, -73.7296),
        'H8R': (45.4448, -73.7096), 'H8S': (45.4378, -73.6996),
        'H8T': (45.4518, -73.6896), 'H8Y': (45.4628, -73.7046),
        'H8Z': (45.4558, -73.7146), 'H9A': (45.4488, -73.7346),
        'H9B': (45.4418, -73.7446), 'H9C': (45.4348, -73.7546),
        'H9E': (45.4278, -73.7646), 'H9G': (45.4208, -73.7746),
        'H9H': (45.4468, -73.7746), 'H9J': (45.4538, -73.7846),
        'H9K': (45.4608, -73.7946), 'H9P': (45.4678, -73.8046),
        'H9R': (45.4618, -73.7696), 'H9S': (45.4548, -73.7596),
        'H9W': (45.4688, -73.7846), 'H9X': (45.4758, -73.7746),
    }

    normalized = postal_code.upper().replace(' ', '')
    fsa = normalized[:3]

    if fsa in MONTREAL_FSA_COORDS:
        lat, lon = MONTREAL_FSA_COORDS[fsa]
        return {
            'lat': lat,
            'lon': lon,
            'city': 'montreal',
            'source': 'fsa_lookup'
        }

    return None


def _geocode_quebec_postal(postal_code: str) -> Optional[Dict[str, Any]]:
    """Geocode a Quebec City postal code using ArcGIS."""
    try:
        from app.services.quebec.snow_checker import geocode_postal_code as qc_geocode

        result = qc_geocode(postal_code)
        if result:
            result['city'] = 'quebec'
            return result

    except Exception as e:
        logger.error(f"Quebec geocoding error: {e}")

    return None


def lookup_cote_rue_id_from_coords(lat: float, lon: float) -> Optional[int]:
    """
    Look up Montreal cote_rue_id from coordinates.

    This is a placeholder - full implementation would query the geobase.
    """
    # TODO: Implement proper coordinate-to-cote_rue_id lookup
    return None
