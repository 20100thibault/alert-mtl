"""
Quebec City Waste Collection Schedule Service

Real-time scraping from Quebec City's Info-Collecte website.
Fetches actual collection schedules based on postal code.

Data source: https://www.ville.quebec.qc.ca/services/info-collecte/
"""

import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from functools import lru_cache
import time

logger = logging.getLogger(__name__)

# City website URL
CITY_WEBSITE = "https://www.ville.quebec.qc.ca/services/info-collecte/"
INFO_COLLECTE_URL = "https://www.ville.quebec.qc.ca/services/info-collecte/index.aspx"

# Day name mappings
DAY_NAMES_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
DAY_NAMES_FR = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

# French month names
MONTH_MAP = {
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
}

# Simple in-memory cache with TTL
_cache: Dict[str, tuple] = {}  # postal_code -> (result, timestamp)
CACHE_TTL_SECONDS = 86400  # 24 hours


def _get_cached(postal_code: str) -> Optional[Dict[str, Any]]:
    """Get cached result if still valid."""
    normalized = postal_code.upper().replace(' ', '').replace('-', '')
    if normalized in _cache:
        result, timestamp = _cache[normalized]
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            logger.debug(f"Cache hit for {normalized}")
            return result
        else:
            del _cache[normalized]
    return None


def _set_cached(postal_code: str, result: Dict[str, Any]):
    """Cache a result."""
    normalized = postal_code.upper().replace(' ', '').replace('-', '')
    _cache[normalized] = (result, time.time())


def _extract_fsa(postal_code: str) -> Optional[str]:
    """Extract FSA (first 3 characters) from postal code."""
    if not postal_code:
        return None
    clean = postal_code.upper().replace(' ', '').replace('-', '')
    if len(clean) < 3:
        return None
    fsa = clean[:3]
    if not (fsa[0].isalpha() and fsa[1].isdigit() and fsa[2].isalpha()):
        return None
    return fsa


def _format_display(collection_date: datetime, day_name: str) -> str:
    """Format the next collection date for display."""
    today = datetime.now().date()
    target = collection_date.date()
    days_diff = (target - today).days

    if days_diff == 0:
        return "Today"
    elif days_diff == 1:
        return "Tomorrow"
    elif days_diff <= 7:
        return f"This {day_name}"
    else:
        return f"Next {day_name}"


def _scrape_schedule(postal_code: str) -> Dict[str, Any]:
    """
    Scrape the actual schedule from Quebec City's Info-Collecte website.

    Returns dict with collection days or error.
    """
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'fr-CA,fr;q=0.9,en;q=0.8',
        })

        # Step 1: GET initial page to get ASP.NET tokens
        response = session.get(INFO_COLLECTE_URL, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        hidden_fields = {}
        for inp in soup.find_all('input', {'type': 'hidden'}):
            name = inp.get('name')
            value = inp.get('value', '')
            if name:
                hidden_fields[name] = value

        # Step 2: Search by postal code to get address
        form_data = hidden_fields.copy()
        form_data['ctl00$ctl00$contenu$texte_page$ucInfoCollecteRechercheAdresse$RechercheAdresse$txtCodePostal'] = postal_code
        form_data['ctl00$ctl00$contenu$texte_page$ucInfoCollecteRechercheAdresse$RechercheAdresse$BtnCodePostal'] = 'Rechercher'

        response2 = session.post(INFO_COLLECTE_URL, data=form_data, timeout=30)
        response2.raise_for_status()
        soup2 = BeautifulSoup(response2.text, 'html.parser')

        # Get address from dropdown
        select = soup2.find('select', {'id': lambda x: x and 'ddChoix' in str(x)})
        if not select:
            return None  # No addresses found

        select_name = select.get('name')
        first_option = select.find('option')
        if not first_option:
            return None

        option_value = first_option.get('value', '')
        address_text = first_option.text.strip()
        logger.debug(f"Found address for {postal_code}: {address_text} (value={option_value})")

        # Step 3: Get new hidden fields
        hidden_fields2 = {}
        for inp in soup2.find_all('input', {'type': 'hidden'}):
            name = inp.get('name')
            value = inp.get('value', '')
            if name:
                hidden_fields2[name] = value

        # Step 4: Select address from dropdown and click Poursuivre
        form_data2 = hidden_fields2.copy()
        form_data2[select_name] = option_value
        form_data2['ctl00$ctl00$contenu$texte_page$ucInfoCollecteRechercheAdresse$RechercheAdresse$btnChoix'] = 'Poursuivre'

        response3 = session.post(INFO_COLLECTE_URL, data=form_data2, timeout=30)
        response3.raise_for_status()
        soup3 = BeautifulSoup(response3.text, 'html.parser')

        # Parse calendars
        calendars = soup3.find_all('table', class_='calendrier')
        if not calendars:
            return None

        # Extract collection dates
        garbage_dates = []
        recycling_dates = []

        for cal in calendars:
            caption = cal.find('caption')
            if not caption:
                continue

            # Parse month/year from caption (e.g., "Janvier 2026")
            caption_text = caption.text.strip().lower()
            parts = caption_text.split()
            month_num = MONTH_MAP.get(parts[0], 1)
            year = int(parts[1]) if len(parts) > 1 else datetime.now().year

            # Find collection days
            for cell in cal.find_all('td'):
                date_elem = cell.find(class_='date')
                img_elem = cell.find('img')
                if date_elem and img_elem:
                    try:
                        day = int(date_elem.text.strip())
                        collection_type = img_elem.get('alt', img_elem.get('title', '')).lower()

                        date_obj = datetime(year, month_num, day)
                        weekday = date_obj.weekday()  # 0=Monday

                        if 'ordures' in collection_type:
                            garbage_dates.append((date_obj, weekday))
                        elif 'recyclage' in collection_type:
                            recycling_dates.append((date_obj, weekday))
                    except (ValueError, TypeError):
                        continue

        if not garbage_dates and not recycling_dates:
            return None

        # Determine collection day (should be consistent)
        garbage_weekday = garbage_dates[0][1] if garbage_dates else None
        recycling_weekday = recycling_dates[0][1] if recycling_dates else None

        return {
            'address': address_text,
            'garbage_weekday': garbage_weekday,
            'recycling_weekday': recycling_weekday,
            'garbage_dates': [d[0] for d in garbage_dates],
            'recycling_dates': [d[0] for d in recycling_dates],
        }

    except requests.RequestException as e:
        logger.error(f"Request error scraping Quebec schedule: {e}")
        return None
    except Exception as e:
        logger.error(f"Error scraping Quebec schedule: {e}")
        return None


def get_schedule(postal_code: str) -> Dict[str, Any]:
    """
    Get waste collection schedule for a Quebec City postal code.

    Uses real-time scraping from Info-Collecte with caching.

    Args:
        postal_code: Canadian postal code (e.g., "G1T 1M9")

    Returns:
        Dict with schedule info or error response
    """
    # Validate postal code
    fsa = _extract_fsa(postal_code)
    if not fsa:
        return _error_response(
            "invalid_postal_code",
            "Please enter a valid Quebec City postal code.",
            "Veuillez entrer un code postal de la ville de Québec valide."
        )

    if not fsa.startswith('G'):
        return _error_response(
            "not_quebec_city",
            "This postal code is not in Quebec City.",
            "Ce code postal n'est pas dans la ville de Québec."
        )

    # Check cache first
    cached = _get_cached(postal_code)
    if cached:
        return cached

    # Scrape the actual schedule
    scraped = _scrape_schedule(postal_code)

    if not scraped:
        return _error_response(
            "scrape_failed",
            "Could not retrieve schedule. Please check the city website.",
            "Impossible de récupérer l'horaire. Veuillez consulter le site de la ville."
        )

    # Build response
    now = datetime.now()

    # Garbage info
    garbage_weekday = scraped['garbage_weekday']
    garbage_day_en = DAY_NAMES_EN[garbage_weekday] if garbage_weekday is not None else 'Unknown'
    garbage_day_fr = DAY_NAMES_FR[garbage_weekday] if garbage_weekday is not None else 'Inconnu'

    # Find next garbage collection
    next_garbage = None
    for d in scraped.get('garbage_dates', []):
        if d.date() >= now.date():
            next_garbage = d
            break

    # Recycling info
    recycling_weekday = scraped['recycling_weekday']
    recycling_day_en = DAY_NAMES_EN[recycling_weekday] if recycling_weekday is not None else 'Unknown'
    recycling_day_fr = DAY_NAMES_FR[recycling_weekday] if recycling_weekday is not None else 'Inconnu'

    # Find next recycling collection
    next_recycling = None
    for d in scraped.get('recycling_dates', []):
        if d.date() >= now.date():
            next_recycling = d
            break

    result = {
        "success": True,
        "city": "quebec",
        "zone_code": fsa,
        "zone_description": f"Quebec City - {scraped.get('address', fsa)}",
        "disclaimer": "Schedule from Info-Collecte. May vary for holidays.",
        "disclaimer_fr": "Horaire provenant d'Info-Collecte. Peut varier lors des jours fériés.",
        "city_website": CITY_WEBSITE,
        "city_website_fr": CITY_WEBSITE,
        "garbage": {
            "type": "garbage",
            "name": "Garbage",
            "name_fr": "Ordures ménagères",
            "day_of_week": garbage_day_en,
            "day_of_week_fr": garbage_day_fr,
            "frequency": "bi-weekly",
            "frequency_fr": "aux deux semaines",
            "next_collection": next_garbage.strftime('%Y-%m-%d') if next_garbage else None,
            "next_collection_display": _format_display(next_garbage, garbage_day_en) if next_garbage else garbage_day_en
        },
        "recycling": {
            "type": "recycling",
            "name": "Recycling",
            "name_fr": "Matières recyclables",
            "day_of_week": recycling_day_en,
            "day_of_week_fr": recycling_day_fr,
            "frequency": "bi-weekly",
            "frequency_fr": "aux deux semaines",
            "next_collection": next_recycling.strftime('%Y-%m-%d') if next_recycling else None,
            "next_collection_display": _format_display(next_recycling, recycling_day_en) if next_recycling else recycling_day_en
        }
    }

    # Cache the result
    _set_cached(postal_code, result)

    return result


def _error_response(error_code: str, message: str, message_fr: str) -> Dict[str, Any]:
    """Create standardized error response."""
    return {
        "success": False,
        "city": "quebec",
        "error": error_code,
        "message": message,
        "message_fr": message_fr,
        "city_website": CITY_WEBSITE,
        "city_website_fr": CITY_WEBSITE,
        "city_website_label": "Check Quebec Info-Collecte",
        "city_website_label_fr": "Consultez Info-Collecte Québec"
    }
