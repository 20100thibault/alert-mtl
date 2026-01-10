"""
Quebec City Waste Collection Schedule Service

FSA-based (Forward Sortation Area) waste collection schedule lookup.
Uses the first 3 characters of the postal code to determine collection day.

Schedule data is approximate and may vary by street.
For exact schedules, users should check: https://www.ville.quebec.qc.ca/services/info-collecte/
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# City website URL (same for EN/FR)
CITY_WEBSITE = "https://www.ville.quebec.qc.ca/services/info-collecte/"

# Day name translations
DAY_NAMES_FR = {
    'Monday': 'Lundi',
    'Tuesday': 'Mardi',
    'Wednesday': 'Mercredi',
    'Thursday': 'Jeudi',
    'Friday': 'Vendredi',
}

# Quebec City FSA to collection day mapping
# Based on arrondissement typical collection patterns
# Format: FSA -> (day_name, weekday_number) where Monday=0
QUEBEC_FSA_DAYS = {
    # La Cité-Limoilou (dense areas) - Monday
    'G1K': ('Monday', 0),
    'G1L': ('Monday', 0),
    'G1R': ('Monday', 0),

    # La Cité-Limoilou (semi-dense) - Tuesday
    'G1M': ('Tuesday', 1),
    'G1N': ('Tuesday', 1),

    # Sainte-Foy-Sillery-Cap-Rouge - Thursday
    'G1V': ('Thursday', 3),
    'G1W': ('Thursday', 3),
    'G1X': ('Thursday', 3),
    'G1Y': ('Thursday', 3),

    # Les Rivières - Wednesday
    'G1E': ('Wednesday', 2),
    'G2B': ('Wednesday', 2),
    'G2E': ('Wednesday', 2),

    # Charlesbourg - Friday
    'G1G': ('Friday', 4),
    'G1H': ('Friday', 4),
    'G2N': ('Friday', 4),

    # Beauport - Wednesday
    'G1B': ('Wednesday', 2),
    'G1C': ('Wednesday', 2),

    # La Haute-Saint-Charles - Thursday
    'G2A': ('Thursday', 3),
    'G2C': ('Thursday', 3),
    'G3A': ('Thursday', 3),
    'G3B': ('Thursday', 3),
    'G3E': ('Thursday', 3),
    'G3G': ('Thursday', 3),
    'G3J': ('Thursday', 3),
    'G3K': ('Thursday', 3),

    # Additional areas
    'G1J': ('Tuesday', 1),
    'G1P': ('Wednesday', 2),
    'G1S': ('Thursday', 3),
    'G1T': ('Thursday', 3),
    'G2G': ('Friday', 4),
    'G2J': ('Wednesday', 2),
    'G2K': ('Wednesday', 2),
    'G2L': ('Thursday', 3),
    'G2M': ('Thursday', 3),
}


def _extract_fsa(postal_code: str) -> Optional[str]:
    """Extract FSA (first 3 characters) from postal code."""
    if not postal_code:
        return None

    # Clean and normalize
    clean = postal_code.upper().replace(' ', '').replace('-', '')

    if len(clean) < 3:
        return None

    fsa = clean[:3]

    # Validate format (letter-digit-letter for Canadian FSA)
    if not (fsa[0].isalpha() and fsa[1].isdigit() and fsa[2].isalpha()):
        return None

    return fsa


def _calculate_next_collection(day_num: int, from_date: datetime = None) -> datetime:
    """Calculate the next occurrence of a collection day."""
    if from_date is None:
        from_date = datetime.now()

    days_until = (day_num - from_date.weekday()) % 7
    if days_until == 0:
        days_until = 7  # If today is collection day, show next week

    return from_date + timedelta(days=days_until)


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


def get_schedule(postal_code: str) -> Dict[str, Any]:
    """
    Get waste collection schedule for a Quebec City postal code.

    Args:
        postal_code: Canadian postal code (e.g., "G1V 1J8")

    Returns:
        Dict with schedule info or error response
    """
    # Extract FSA
    fsa = _extract_fsa(postal_code)

    if not fsa:
        return _error_response(
            "invalid_postal_code",
            "Please enter a valid Quebec City postal code.",
            "Veuillez entrer un code postal de la ville de Québec valide."
        )

    # Check if it's a Quebec City FSA (starts with G)
    if not fsa.startswith('G'):
        return _error_response(
            "not_quebec_city",
            "This postal code is not in Quebec City.",
            "Ce code postal n'est pas dans la ville de Québec."
        )

    # Look up collection day
    if fsa not in QUEBEC_FSA_DAYS:
        return _error_response(
            "unknown_area",
            "We couldn't determine the collection schedule for this area.",
            "Nous n'avons pas pu déterminer l'horaire de collecte pour ce secteur."
        )

    day_name, day_num = QUEBEC_FSA_DAYS[fsa]
    day_name_fr = DAY_NAMES_FR[day_name]

    # Calculate next collection dates
    now = datetime.now()
    next_garbage = _calculate_next_collection(day_num, now)

    # Recycling is bi-weekly - determine based on week number
    week_num = next_garbage.isocalendar()[1]
    if week_num % 2 == 0:
        next_recycling = next_garbage
    else:
        next_recycling = next_garbage + timedelta(days=7)

    return {
        "success": True,
        "city": "quebec",
        "zone_code": fsa,
        "zone_description": f"Quebec City ({fsa})",
        "disclaimer": "Schedule may vary by street. Check Info-Collecte for exact schedule.",
        "disclaimer_fr": "L'horaire peut varier selon la rue. Consultez Info-Collecte pour l'horaire exact.",
        "city_website": CITY_WEBSITE,
        "city_website_fr": CITY_WEBSITE,
        "garbage": {
            "type": "garbage",
            "name": "Garbage",
            "name_fr": "Ordures ménagères",
            "day_of_week": day_name,
            "day_of_week_fr": day_name_fr,
            "frequency": "weekly",
            "frequency_fr": "hebdomadaire",
            "next_collection": next_garbage.strftime('%Y-%m-%d'),
            "next_collection_display": _format_display(next_garbage, day_name)
        },
        "recycling": {
            "type": "recycling",
            "name": "Recycling",
            "name_fr": "Matières recyclables",
            "day_of_week": day_name,
            "day_of_week_fr": day_name_fr,
            "frequency": "bi-weekly",
            "frequency_fr": "aux deux semaines",
            "next_collection": next_recycling.strftime('%Y-%m-%d'),
            "next_collection_display": _format_display(next_recycling, day_name)
        }
    }


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
