"""
Quebec City Snow Removal Checker Service

Checks Quebec City's ArcGIS API for snow removal operations (flashing lights).
"""

import logging
import math
import requests
from typing import Optional, Dict, Any, List, Tuple
from flask import current_app

logger = logging.getLogger(__name__)

# Headers to avoid rate limiting
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}

# Quebec City FSA (Forward Sortation Area) coordinates
# Used as fallback when geocoding fails
QUEBEC_FSA_COORDS = {
    'G1A': (46.8139, -71.2080),
    'G1B': (46.8625, -71.1978),
    'G1C': (46.8758, -71.1678),
    'G1E': (46.8572, -71.2281),
    'G1G': (46.8247, -71.2589),
    'G1H': (46.7989, -71.2378),
    'G1J': (46.8208, -71.2089),
    'G1K': (46.8125, -71.2189),
    'G1L': (46.8064, -71.2289),
    'G1M': (46.7939, -71.2489),
    'G1N': (46.7814, -71.2589),
    'G1P': (46.7689, -71.2789),
    'G1R': (46.8094, -71.2189),
    'G1S': (46.7564, -71.2889),
    'G1T': (46.7439, -71.2989),
    'G1V': (46.7814, -71.2789),
    'G1W': (46.7689, -71.2889),
    'G1X': (46.7564, -71.3089),
    'G1Y': (46.7439, -71.3189),
    'G2A': (46.8375, -71.2580),
    'G2B': (46.8500, -71.2680),
    'G2C': (46.8625, -71.2780),
    'G2E': (46.8750, -71.2880),
    'G2G': (46.8875, -71.2980),
    'G2J': (46.9000, -71.3080),
    'G2K': (46.9125, -71.3180),
    'G2L': (46.9250, -71.3280),
    'G2M': (46.9375, -71.3380),
    'G2N': (46.9500, -71.3480),
    'G3A': (46.8439, -71.1678),
    'G3B': (46.8572, -71.1578),
    'G3C': (46.8705, -71.1478),
    'G3E': (46.8838, -71.1378),
    'G3G': (46.8971, -71.1278),
    'G3H': (46.9104, -71.1178),
    'G3J': (46.9237, -71.1078),
    'G3K': (46.9370, -71.0978),
    'G3L': (46.9503, -71.0878),
    'G3M': (46.9636, -71.0778),
    'G3N': (46.9769, -71.0678),
}

# Status display mapping (consistent with Montreal service)
STATUS_DISPLAY = {
    'en_fonction': {'en': 'Active', 'fr': 'En fonction', 'color': 'red', 'priority': 4},
    'hors_service': {'en': 'Inactive', 'fr': 'Hors service', 'color': 'green', 'priority': 0},
    'unknown': {'en': 'Unknown', 'fr': 'Inconnu', 'color': 'gray', 'priority': 0},
}


def geocode_postal_code(postal_code: str) -> Optional[Dict[str, Any]]:
    """
    Convert a Quebec postal code to latitude/longitude coordinates.
    Uses ArcGIS World Geocoder with FSA fallback.
    """
    # Normalize postal code
    normalized = postal_code.upper().replace(' ', '')
    formatted = f"{normalized[:3]} {normalized[3:]}"  # Format as "G1R 2K8"
    fsa = normalized[:3]

    # Try ArcGIS geocoder first
    url = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
    params = {
        "SingleLine": f"{formatted}, Quebec, Canada",
        "f": "json",
        "outFields": "*"
    }

    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        candidates = data.get('candidates', [])
        if candidates:
            best = candidates[0]
            return {
                "lat": best['location']['y'],
                "lon": best['location']['x'],
                "source": "arcgis"
            }
    except Exception as e:
        logger.warning(f"ArcGIS geocoding failed: {e}")

    # Fall back to FSA lookup
    if fsa in QUEBEC_FSA_COORDS:
        lat, lon = QUEBEC_FSA_COORDS[fsa]
        logger.info(f"Using FSA fallback for {fsa}: ({lat}, {lon})")
        return {
            "lat": lat,
            "lon": lon,
            "source": "fsa_fallback"
        }

    logger.error(f"Could not geocode postal code: {postal_code}")
    return None


def reverse_geocode(lat: float, lon: float) -> str:
    """
    Get street name from coordinates using ArcGIS reverse geocoding.
    """
    url = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/reverseGeocode"
    params = {
        "location": f"{lon},{lat}",
        "f": "json",
        "outSR": "4326"
    }

    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=5)
        response.raise_for_status()
        data = response.json()

        address = data.get('address', {})
        street = address.get('Address', '')
        if street:
            return street
        street = address.get('Match_addr', '')
        if street:
            return street.split(',')[0]
        return 'Unknown'

    except Exception:
        return 'Unknown'


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two coordinates using Haversine formula."""
    R = 6371000  # Earth radius in meters

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c


def check_snow_removal(lat: float, lon: float, buffer_meters: int = 200) -> Dict[str, Any]:
    """
    Check snow removal status for a location using Quebec City's ArcGIS API.

    Args:
        lat: Latitude of the location
        lon: Longitude of the location
        buffer_meters: Search radius in meters

    Returns:
        Dict with status information including nearby flashing lights
    """
    base_url = "https://carte.ville.quebec.qc.ca/arcgis/rest/services/CI/Deneigement/MapServer/2/query"

    # Try with initial buffer, expand if nothing found
    search_radius = buffer_meters
    max_radius = 500

    while search_radius <= max_radius:
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "distance": search_radius,
            "units": "esriSRUnit_Meter",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json"
        }

        try:
            response = requests.get(base_url, params=params, headers=HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()

            if 'error' in data:
                return {
                    "success": False,
                    "error": data['error'].get('message', 'Unknown API error')
                }

            features = data.get('features', [])

            if not features:
                if search_radius < max_radius:
                    search_radius += 100
                    continue
                return {
                    "success": True,
                    "found": False,
                    "search_radius": search_radius,
                    "has_active_operation": False,
                    "lights": [],
                    "message": f"No flashing lights found within {search_radius}m."
                }

            # Analyze the flashing lights found
            results = []
            has_active_operation = False

            for feature in features:
                attrs = feature.get('attributes', {})
                geom = feature.get('geometry', {})

                status = attrs.get('STATUT', 'Unknown')
                station = attrs.get('STATION_NO', 'Unknown')

                # Get station coordinates
                station_lon = geom.get('x')
                station_lat = geom.get('y')

                # Calculate distance from search location
                distance = None
                if station_lat and station_lon:
                    distance = calculate_distance(lat, lon, station_lat, station_lon)

                # Reverse geocode to get street name
                street = 'Unknown'
                if station_lat and station_lon:
                    street = reverse_geocode(station_lat, station_lon)

                if status == "En fonction":
                    has_active_operation = True

                results.append({
                    "station": station,
                    "status": status,
                    "street": street,
                    "distance": distance
                })

            # Sort by distance
            results.sort(key=lambda x: x.get('distance') or 9999)

            return {
                "success": True,
                "found": True,
                "search_radius": search_radius,
                "has_active_operation": has_active_operation,
                "lights": results,
                "lights_nearby": len([l for l in results if l.get('status') == 'En fonction'])
            }

        except requests.RequestException as e:
            logger.error(f"Quebec API request error: {e}")
            return {
                "success": False,
                "error": f"Network error: {e}"
            }
        except ValueError as e:
            logger.error(f"Quebec API parse error: {e}")
            return {
                "success": False,
                "error": f"Error parsing response: {e}"
            }

    return {
        "success": True,
        "found": False,
        "search_radius": max_radius,
        "has_active_operation": False,
        "lights": [],
        "message": f"No flashing lights found within {max_radius}m."
    }


def get_status_for_location(lat: float, lon: float) -> Dict[str, Any]:
    """
    Get snow removal status formatted consistently with Montreal service.

    Returns dict with display info compatible with unified response format.
    """
    result = check_snow_removal(lat, lon)

    if not result.get('success'):
        return {
            'etat': 'unknown',
            'etat_deneig': 0,
            'display': STATUS_DISPLAY['unknown'],
            'parking_allowed': True,
            'message': result.get('error', 'Unable to retrieve status')
        }

    has_operation = result.get('has_active_operation', False)

    if has_operation:
        etat = 'en_fonction'
        display = STATUS_DISPLAY['en_fonction']
        lights_nearby = result.get('lights_nearby', 0)
        nearest_light = result.get('lights', [{}])[0] if result.get('lights') else {}
        message = f"Snow removal in progress! {lights_nearby} flashing lights nearby."
        if nearest_light.get('street') != 'Unknown':
            message += f" Nearest: {nearest_light['street']} ({int(nearest_light.get('distance', 0))}m)"
    else:
        etat = 'hors_service'
        display = STATUS_DISPLAY['hors_service']
        message = 'No active snow removal operations nearby.'

    return {
        'etat': etat,
        'etat_deneig': 1 if has_operation else 0,
        'display': display,
        'parking_allowed': not has_operation,
        'message': message,
        'lights': result.get('lights', []),
        'lights_nearby': result.get('lights_nearby', 0),
        'search_radius': result.get('search_radius')
    }


def check_postal_code(postal_code: str) -> Tuple[bool, List[str]]:
    """
    Check if there's a snow removal operation for a Quebec City postal code.

    Args:
        postal_code: Quebec City postal code (G prefix)

    Returns:
        Tuple of (has_operation: bool, streets_affected: list of street names)
    """
    # Geocode the postal code
    location = geocode_postal_code(postal_code)
    if not location:
        return (False, [])

    # Check snow removal status
    result = check_snow_removal(location['lat'], location['lon'])

    if not result.get('success') or not result.get('found'):
        return (False, [])

    has_operation = result.get('has_active_operation', False)

    # Get list of affected streets (only those with active operations)
    streets = []
    if has_operation:
        for light in result.get('lights', []):
            if light.get('status') == 'En fonction':
                streets.append(light.get('street', 'Unknown'))

    return (has_operation, streets)
