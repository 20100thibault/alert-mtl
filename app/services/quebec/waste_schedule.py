"""
Quebec City Waste Collection Schedule Service

Real-time scraping from Quebec City's Info-Collecte website.
Fetches actual collection schedules based on postal code.

Data source: https://www.ville.quebec.qc.ca/services/info-collecte/
"""

import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Dict, Any, Optional
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


def _normalize_postal_code(postal_code: str) -> str:
    """Normalize postal code to uppercase without spaces or dashes."""
    return postal_code.upper().replace(' ', '').replace('-', '')


def _get_cached(postal_code: str) -> Optional[Dict[str, Any]]:
    """Get cached result if still valid."""
    normalized = _normalize_postal_code(postal_code)
    if normalized not in _cache:
        return None

    result, timestamp = _cache[normalized]
    if time.time() - timestamp < CACHE_TTL_SECONDS:
        logger.debug(f"Cache hit for {normalized}")
        return result

    del _cache[normalized]
    return None


def _set_cached(postal_code: str, result: Dict[str, Any]) -> None:
    """Cache a result."""
    normalized = _normalize_postal_code(postal_code)
    _cache[normalized] = (result, time.time())


def _extract_fsa(postal_code: str) -> Optional[str]:
    """Extract FSA (first 3 characters) from postal code."""
    if not postal_code:
        return None

    clean = _normalize_postal_code(postal_code)
    if len(clean) < 3:
        return None

    fsa = clean[:3]
    if not (fsa[0].isalpha() and fsa[1].isdigit() and fsa[2].isalpha()):
        return None

    return fsa


def _format_display(collection_date: datetime, day_name: str) -> str:
    """Format the next collection date for display (English)."""
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


def _format_display_fr(collection_date: datetime, day_name_fr: str) -> str:
    """Format the next collection date for display (French)."""
    today = datetime.now().date()
    target = collection_date.date()
    days_diff = (target - today).days

    if days_diff == 0:
        return "Aujourd'hui"
    elif days_diff == 1:
        return "Demain"
    elif days_diff <= 7:
        return f"Ce {day_name_fr}"
    else:
        return f"{day_name_fr} prochain"


def _extract_hidden_fields(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract ASP.NET hidden form fields from a page."""
    fields = {}
    for inp in soup.find_all('input', {'type': 'hidden'}):
        name = inp.get('name')
        if name:
            fields[name] = inp.get('value', '')
    return fields


def _parse_calendar_dates(calendars) -> tuple:
    """Parse garbage and recycling dates from calendar tables."""
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

        for cell in cal.find_all('td'):
            date_elem = cell.find(class_='date')
            img_elem = cell.find('img')
            if not (date_elem and img_elem):
                continue

            try:
                day = int(date_elem.text.strip())
                collection_type = img_elem.get('alt', img_elem.get('title', '')).lower()
                date_obj = datetime(year, month_num, day)
                weekday = date_obj.weekday()

                if 'ordures' in collection_type:
                    garbage_dates.append((date_obj, weekday))
                elif 'recyclage' in collection_type:
                    recycling_dates.append((date_obj, weekday))
            except (ValueError, TypeError):
                continue

    return garbage_dates, recycling_dates


def _scrape_schedule(postal_code: str) -> Optional[Dict[str, Any]]:
    """
    Scrape the actual schedule from Quebec City's Info-Collecte website.

    Returns dict with collection days or None on failure.
    """
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'fr-CA,fr;q=0.9,en;q=0.8',
        })

        # Step 1: GET initial page to get ASP.NET tokens
        response = session.get(INFO_COLLECTE_URL, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Step 2: Search by postal code
        form_data = _extract_hidden_fields(soup)
        form_data['ctl00$ctl00$contenu$texte_page$ucInfoCollecteRechercheAdresse$RechercheAdresse$txtCodePostal'] = postal_code
        form_data['ctl00$ctl00$contenu$texte_page$ucInfoCollecteRechercheAdresse$RechercheAdresse$BtnCodePostal'] = 'Rechercher'

        response2 = session.post(INFO_COLLECTE_URL, data=form_data, timeout=30)
        response2.raise_for_status()
        soup2 = BeautifulSoup(response2.text, 'html.parser')

        # Step 3: Get address from dropdown
        select = soup2.find('select', {'id': lambda x: x and 'ddChoix' in str(x)})
        if not select:
            return None

        first_option = select.find('option')
        if not first_option:
            return None

        address_text = first_option.text.strip()
        logger.debug(f"Found address for {postal_code}: {address_text}")

        # Step 4: Select address and submit
        form_data2 = _extract_hidden_fields(soup2)
        form_data2[select.get('name')] = first_option.get('value', '')
        form_data2['ctl00$ctl00$contenu$texte_page$ucInfoCollecteRechercheAdresse$RechercheAdresse$btnChoix'] = 'Poursuivre'

        response3 = session.post(INFO_COLLECTE_URL, data=form_data2, timeout=30)
        response3.raise_for_status()
        soup3 = BeautifulSoup(response3.text, 'html.parser')

        # Step 5: Parse calendar data
        calendars = soup3.find_all('table', class_='calendrier')
        if not calendars:
            return None

        garbage_dates, recycling_dates = _parse_calendar_dates(calendars)

        if not garbage_dates and not recycling_dates:
            return None

        return {
            'address': address_text,
            'garbage_weekday': garbage_dates[0][1] if garbage_dates else None,
            'recycling_weekday': recycling_dates[0][1] if recycling_dates else None,
            'garbage_dates': [d[0] for d in garbage_dates],
            'recycling_dates': [d[0] for d in recycling_dates],
        }

    except requests.RequestException as e:
        logger.error(f"Request error scraping Quebec schedule: {e}")
        return None
    except Exception as e:
        logger.error(f"Error scraping Quebec schedule: {e}")
        return None


def _find_next_collection(dates: list, today: datetime.date) -> Optional[datetime]:
    """Find the next collection date on or after today."""
    for d in dates:
        if d.date() >= today:
            return d
    return None


def _get_day_names(weekday: Optional[int]) -> tuple:
    """Get English and French day names for a weekday number."""
    if weekday is None:
        return 'Unknown', 'Inconnu'
    return DAY_NAMES_EN[weekday], DAY_NAMES_FR[weekday]


def _build_collection_info(
    collection_type: str,
    name: str,
    name_fr: str,
    weekday: Optional[int],
    next_date: Optional[datetime]
) -> Dict[str, Any]:
    """Build a collection info dict for garbage or recycling."""
    day_en, day_fr = _get_day_names(weekday)

    return {
        "type": collection_type,
        "name": name,
        "name_fr": name_fr,
        "day_of_week": day_en,
        "day_of_week_fr": day_fr,
        "frequency": "bi-weekly",
        "frequency_fr": "aux deux semaines",
        "next_collection": next_date.strftime('%Y-%m-%d') if next_date else None,
        "next_collection_display": _format_display(next_date, day_en) if next_date else day_en,
        "next_collection_display_fr": _format_display_fr(next_date, day_fr) if next_date else day_fr
    }


def get_schedule(postal_code: str) -> Dict[str, Any]:
    """
    Get waste collection schedule for a Quebec City postal code.

    Uses real-time scraping from Info-Collecte with caching.

    Args:
        postal_code: Canadian postal code (e.g., "G1T 1M9")

    Returns:
        Dict with schedule info or error response
    """
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

    cached = _get_cached(postal_code)
    if cached:
        return cached

    scraped = _scrape_schedule(postal_code)
    if not scraped:
        return _error_response(
            "scrape_failed",
            "Could not retrieve schedule. Please check the city website.",
            "Impossible de récupérer l'horaire. Veuillez consulter le site de la ville."
        )

    today = datetime.now().date()
    next_garbage = _find_next_collection(scraped.get('garbage_dates', []), today)
    next_recycling = _find_next_collection(scraped.get('recycling_dates', []), today)

    result = {
        "success": True,
        "city": "quebec",
        "zone_code": fsa,
        "zone_description": f"Quebec City - {scraped.get('address', fsa)}",
        "disclaimer": "Schedule from Info-Collecte. May vary for holidays.",
        "disclaimer_fr": "Horaire provenant d'Info-Collecte. Peut varier lors des jours fériés.",
        "city_website": CITY_WEBSITE,
        "city_website_fr": CITY_WEBSITE,
        "garbage": _build_collection_info(
            "garbage", "Garbage", "Ordures ménagères",
            scraped['garbage_weekday'], next_garbage
        ),
        "recycling": _build_collection_info(
            "recycling", "Recycling", "Matières recyclables",
            scraped['recycling_weekday'], next_recycling
        )
    }

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
