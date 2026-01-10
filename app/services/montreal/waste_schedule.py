"""
Montreal Waste Collection Schedule Service

FSA-based (Forward Sortation Area) waste collection schedule lookup.
Uses the first 3 characters of the postal code to determine collection day.

Schedule data is approximate and may vary by street.
For exact schedules, users should check: https://montreal.ca/en/services/collection-schedules
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# City website URLs
CITY_WEBSITE_EN = "https://montreal.ca/en/services/collection-schedules"
CITY_WEBSITE_FR = "https://montreal.ca/services/calendrier-des-collectes"

# Day name translations
DAY_NAMES_FR = {
    'Monday': 'Lundi',
    'Tuesday': 'Mardi',
    'Wednesday': 'Mercredi',
    'Thursday': 'Jeudi',
    'Friday': 'Vendredi',
}

# Montreal FSA to collection day mapping
# Based on borough/arrondissement typical collection patterns
# Format: FSA -> (day_name, weekday_number) where Monday=0
MONTREAL_FSA_DAYS = {
    # Plateau-Mont-Royal - Monday
    'H2J': ('Monday', 0),
    'H2T': ('Monday', 0),
    'H2W': ('Monday', 0),
    'H2L': ('Monday', 0),

    # Mile End / Outremont - Tuesday
    'H2V': ('Tuesday', 1),
    'H2S': ('Tuesday', 1),
    'H3N': ('Tuesday', 1),

    # Rosemont-La Petite-Patrie - Wednesday
    'H1X': ('Wednesday', 2),
    'H1Y': ('Wednesday', 2),
    'H2G': ('Wednesday', 2),
    'H2R': ('Wednesday', 2),

    # Villeray/Saint-Michel/Parc-Extension - Thursday
    'H2P': ('Thursday', 3),
    'H2M': ('Thursday', 3),
    'H2E': ('Thursday', 3),

    # Ahuntsic-Cartierville - Friday
    'H2N': ('Friday', 4),
    'H2C': ('Friday', 4),
    'H3L': ('Friday', 4),
    'H3M': ('Friday', 4),

    # Downtown/Ville-Marie - Monday
    'H3A': ('Monday', 0),
    'H3B': ('Monday', 0),
    'H3C': ('Monday', 0),
    'H3G': ('Monday', 0),
    'H3H': ('Monday', 0),

    # NDG/Côte-des-Neiges - Wednesday
    'H3S': ('Wednesday', 2),
    'H3T': ('Wednesday', 2),
    'H3V': ('Wednesday', 2),
    'H3W': ('Wednesday', 2),
    'H4A': ('Wednesday', 2),
    'H4B': ('Wednesday', 2),
    'H4V': ('Wednesday', 2),

    # Verdun/LaSalle - Thursday
    'H4G': ('Thursday', 3),
    'H4H': ('Thursday', 3),
    'H4E': ('Thursday', 3),
    'H8N': ('Thursday', 3),
    'H8P': ('Thursday', 3),

    # Mercier-Hochelaga-Maisonneuve - Tuesday
    'H1L': ('Tuesday', 1),
    'H1M': ('Tuesday', 1),
    'H1N': ('Tuesday', 1),
    'H1K': ('Tuesday', 1),
    'H1V': ('Tuesday', 1),
    'H1W': ('Tuesday', 1),

    # Anjou/Saint-Léonard - Friday
    'H1J': ('Friday', 4),
    'H1R': ('Friday', 4),
    'H1S': ('Friday', 4),
    'H1T': ('Friday', 4),

    # Montreal-Nord - Monday
    'H1G': ('Monday', 0),
    'H1H': ('Monday', 0),

    # Rivière-des-Prairies/Pointe-aux-Trembles - Tuesday
    'H1A': ('Tuesday', 1),
    'H1B': ('Tuesday', 1),
    'H1C': ('Tuesday', 1),
    'H1E': ('Tuesday', 1),

    # West Island - Wednesday
    'H9A': ('Wednesday', 2),
    'H9B': ('Wednesday', 2),
    'H9C': ('Wednesday', 2),
    'H9H': ('Wednesday', 2),
    'H9J': ('Wednesday', 2),
    'H9K': ('Wednesday', 2),
    'H9R': ('Wednesday', 2),
    'H9S': ('Wednesday', 2),
    'H9W': ('Wednesday', 2),
    'H9X': ('Wednesday', 2),

    # Lachine - Monday
    'H8R': ('Monday', 0),
    'H8S': ('Monday', 0),
    'H8T': ('Monday', 0),

    # Sud-Ouest - Tuesday
    'H3J': ('Tuesday', 1),
    'H3K': ('Tuesday', 1),
    'H4C': ('Tuesday', 1),
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


def get_schedule(postal_code: str) -> Dict[str, Any]:
    """
    Get waste collection schedule for a Montreal postal code.

    Args:
        postal_code: Canadian postal code (e.g., "H2V 1V5")

    Returns:
        Dict with schedule info or error response
    """
    # Extract FSA
    fsa = _extract_fsa(postal_code)

    if not fsa:
        return _error_response(
            "invalid_postal_code",
            "Please enter a valid Montreal postal code.",
            "Veuillez entrer un code postal montréalais valide."
        )

    # Check if it's a Montreal FSA (starts with H)
    if not fsa.startswith('H'):
        return _error_response(
            "not_montreal",
            "This postal code is not in Montreal.",
            "Ce code postal n'est pas à Montréal."
        )

    # Look up collection day
    if fsa not in MONTREAL_FSA_DAYS:
        return _error_response(
            "unknown_area",
            "We couldn't determine the collection schedule for this area.",
            "Nous n'avons pas pu déterminer l'horaire de collecte pour ce secteur."
        )

    day_name, day_num = MONTREAL_FSA_DAYS[fsa]
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
        "city": "montreal",
        "zone_code": fsa,
        "zone_description": f"Montreal ({fsa})",
        "disclaimer": "Schedule may vary by street. Check Info-Collectes for exact schedule.",
        "disclaimer_fr": "L'horaire peut varier selon la rue. Consultez Info-Collectes pour l'horaire exact.",
        "city_website": CITY_WEBSITE_EN,
        "city_website_fr": CITY_WEBSITE_FR,
        "garbage": {
            "type": "garbage",
            "name": "Garbage",
            "name_fr": "Ordures ménagères",
            "day_of_week": day_name,
            "day_of_week_fr": day_name_fr,
            "frequency": "weekly",
            "frequency_fr": "hebdomadaire",
            "next_collection": next_garbage.strftime('%Y-%m-%d'),
            "next_collection_display": _format_display(next_garbage, day_name),
            "next_collection_display_fr": _format_display_fr(next_garbage, day_name_fr)
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
            "next_collection_display": _format_display(next_recycling, day_name),
            "next_collection_display_fr": _format_display_fr(next_recycling, day_name_fr)
        }
    }


def _error_response(error_code: str, message: str, message_fr: str) -> Dict[str, Any]:
    """Create standardized error response."""
    return {
        "success": False,
        "city": "montreal",
        "error": error_code,
        "message": message,
        "message_fr": message_fr,
        "city_website": CITY_WEBSITE_EN,
        "city_website_fr": CITY_WEBSITE_FR,
        "city_website_label": "Check Montreal Info-Collectes",
        "city_website_label_fr": "Consultez Info-Collectes Montréal"
    }
