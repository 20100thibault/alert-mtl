"""
Planif-Neige API Integration Service

Handles SOAP/WSDL communication with Montreal's snow removal API.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from functools import lru_cache
import threading

from flask import current_app

from app import db
from app.models import SnowStatusCache

logger = logging.getLogger(__name__)

# Thread lock for rate limiting
_api_lock = threading.Lock()
_last_api_call = None

# Status code mappings
STATUS_DISPLAY = {
    'enneige': {'en': 'Snowy', 'fr': 'Enneigé', 'color': 'blue', 'priority': 1},
    'planifie': {'en': 'Scheduled', 'fr': 'Planifié', 'color': 'orange', 'priority': 3},
    'replanifie': {'en': 'Rescheduled', 'fr': 'Replanifié', 'color': 'orange', 'priority': 3},
    'en_cours': {'en': 'In Progress', 'fr': 'En cours', 'color': 'purple', 'priority': 4},
    'deneige': {'en': 'Cleared', 'fr': 'Déneigé', 'color': 'green', 'priority': 0},
    'sera_replanifie': {'en': 'To be Rescheduled', 'fr': 'Sera replanifié', 'color': 'orange', 'priority': 2},
    'degage': {'en': 'Clear', 'fr': 'Dégagé', 'color': 'green', 'priority': 0},
}

# Alert-worthy status transitions (current status -> triggers alert)
ALERT_TRANSITIONS = {
    'planifie': 'snow_scheduled',
    'replanifie': 'snow_scheduled',
    'en_cours': 'snow_urgent',
    'deneige': 'snow_cleared',
}


def get_soap_client():
    """Initialize and return SOAP client for Planif-Neige API."""
    try:
        from zeep import Client
        from zeep.transports import Transport
        from requests import Session

        wsdl_url = current_app.config.get('PLANIF_NEIGE_WSDL')

        session = Session()
        session.timeout = 30

        transport = Transport(session=session)
        client = Client(wsdl=wsdl_url, transport=transport)

        logger.debug("SOAP client initialized")
        return client

    except Exception as e:
        logger.error(f"Failed to initialize SOAP client: {e}")
        raise


def respect_rate_limit():
    """Ensure we respect the API rate limit (1 request per 5 minutes)."""
    global _last_api_call

    with _api_lock:
        if _last_api_call:
            elapsed = (datetime.utcnow() - _last_api_call).total_seconds()
            min_interval = current_app.config.get('PLANIF_NEIGE_CACHE_SECONDS', 300)

            if elapsed < min_interval:
                logger.debug(f"Rate limit: {min_interval - elapsed:.0f}s until next API call allowed")
                return False

        _last_api_call = datetime.utcnow()
        return True


def get_cached_status(cote_rue_id: int) -> Optional[Dict[str, Any]]:
    """Get status from cache if available and fresh."""
    cache_seconds = current_app.config.get('PLANIF_NEIGE_CACHE_SECONDS', 300)

    cached = SnowStatusCache.query.filter_by(cote_rue_id=cote_rue_id).first()

    if cached and not cached.is_expired(cache_seconds):
        return {
            'etat': cached.etat,
            'date_debut': cached.date_debut.isoformat() if cached.date_debut else None,
            'date_fin': cached.date_fin.isoformat() if cached.date_fin else None,
            'cached': True,
            'fetched_at': cached.fetched_at.isoformat()
        }

    return None


def update_cache(cote_rue_id: int, status_data: Dict[str, Any]):
    """Update status cache."""
    cached = SnowStatusCache.query.filter_by(cote_rue_id=cote_rue_id).first()

    if cached:
        cached.etat = status_data.get('etat')
        cached.date_debut = status_data.get('date_debut')
        cached.date_fin = status_data.get('date_fin')
        cached.fetched_at = datetime.utcnow()
    else:
        cached = SnowStatusCache(
            cote_rue_id=cote_rue_id,
            etat=status_data.get('etat'),
            date_debut=status_data.get('date_debut'),
            date_fin=status_data.get('date_fin'),
            fetched_at=datetime.utcnow()
        )
        db.session.add(cached)

    db.session.commit()


def fetch_status_from_api(cote_rue_id: int) -> Optional[Dict[str, Any]]:
    """Fetch status directly from Planif-Neige API."""
    if not respect_rate_limit():
        logger.warning("Rate limit exceeded, using cache only")
        return get_cached_status(cote_rue_id)

    try:
        client = get_soap_client()

        # Get today's date
        today = datetime.now().strftime('%Y-%m-%d')

        # Call the API
        # Note: Actual method names depend on WSDL - adjust as needed
        response = client.service.GetPlanificationsForDate(date=today)

        # Parse response - structure depends on actual WSDL
        # This is a simplified example
        if response:
            for item in response:
                if hasattr(item, 'COTE_RUE_ID') and item.COTE_RUE_ID == cote_rue_id:
                    return {
                        'etat': getattr(item, 'ETAT', 'unknown'),
                        'date_debut': getattr(item, 'DATE_DEBUT', None),
                        'date_fin': getattr(item, 'DATE_FIN', None),
                        'cached': False
                    }

        return None

    except Exception as e:
        logger.error(f"API call failed: {e}")
        # Fall back to cache
        return get_cached_status(cote_rue_id)


def get_status_for_street(cote_rue_id: int) -> Dict[str, Any]:
    """
    Get snow removal status for a street.

    Returns formatted status with display information.
    """
    # Try cache first
    status = get_cached_status(cote_rue_id)

    if not status:
        # Fetch from API
        status = fetch_status_from_api(cote_rue_id)

        if status:
            update_cache(cote_rue_id, status)

    if not status:
        return {
            'etat': 'unknown',
            'display': {
                'en': 'Unknown',
                'fr': 'Inconnu',
                'color': 'gray'
            },
            'parking_allowed': None,
            'message': 'Unable to retrieve status'
        }

    # Enrich with display info
    etat = status.get('etat', 'unknown').lower()
    display_info = STATUS_DISPLAY.get(etat, {
        'en': etat.capitalize(),
        'fr': etat.capitalize(),
        'color': 'gray',
        'priority': 0
    })

    # Determine parking status
    parking_prohibited = etat in ['en_cours', 'planifie', 'replanifie']

    result = {
        'etat': etat,
        'display': display_info,
        'parking_allowed': not parking_prohibited,
        'cached': status.get('cached', False)
    }

    # Add dates if available
    if status.get('date_debut'):
        result['scheduled_start'] = status['date_debut']
    if status.get('date_fin'):
        result['scheduled_end'] = status['date_fin']

    # Add message based on status
    if etat == 'planifie':
        result['message'] = 'Snow removal is scheduled. Move your vehicle before the operation begins.'
    elif etat == 'en_cours':
        result['message'] = 'Snow removal in progress! Parking is prohibited.'
    elif etat == 'deneige':
        result['message'] = 'Street has been cleared. Parking is allowed.'
    elif etat == 'enneige':
        result['message'] = 'Street is snowy. Monitor for scheduled removal.'

    return result


def get_all_statuses_for_date(date: datetime = None) -> List[Dict[str, Any]]:
    """Get all planned operations for a date."""
    if date is None:
        date = datetime.now()

    if not respect_rate_limit():
        logger.warning("Rate limit exceeded")
        return []

    try:
        client = get_soap_client()
        date_str = date.strftime('%Y-%m-%d')

        response = client.service.GetPlanificationsForDate(date=date_str)

        results = []
        if response:
            for item in response:
                results.append({
                    'cote_rue_id': getattr(item, 'COTE_RUE_ID', 0),
                    'etat': getattr(item, 'ETAT', 'unknown'),
                    'date_debut': getattr(item, 'DATE_DEBUT', None),
                    'date_fin': getattr(item, 'DATE_FIN', None),
                })

        return results

    except Exception as e:
        logger.error(f"Failed to get all statuses: {e}")
        return []


def detect_status_change(cote_rue_id: int, new_status: str, previous_status: str) -> Optional[str]:
    """
    Detect if a status change warrants an alert.

    Returns alert type or None.
    """
    if new_status == previous_status:
        return None

    # Check if new status triggers an alert
    alert_type = ALERT_TRANSITIONS.get(new_status)

    if alert_type:
        logger.info(f"Status change detected for {cote_rue_id}: {previous_status} -> {new_status}")
        return alert_type

    return None


def get_status_priority(etat: str) -> int:
    """Get priority level for a status (higher = more urgent)."""
    return STATUS_DISPLAY.get(etat, {}).get('priority', 0)
