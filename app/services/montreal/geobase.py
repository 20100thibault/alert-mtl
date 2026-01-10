"""
Geobase Double Integration Service

Handles downloading, caching, and querying Montreal's Geobase Double dataset
for address to COTE_RUE_ID mapping.
"""

import re
import csv
import io
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import requests
from flask import current_app

from app import db
from app.models import GeobaseCache

logger = logging.getLogger(__name__)

# Street type variations for normalization
STREET_TYPES = {
    'rue': ['rue', 'r.', 'r'],
    'avenue': ['avenue', 'ave', 'av.', 'av'],
    'boulevard': ['boulevard', 'boul', 'blvd', 'bl.', 'bl'],
    'chemin': ['chemin', 'ch.', 'ch'],
    'place': ['place', 'pl.', 'pl'],
    'cote': ['cote', 'côte'],
    'rang': ['rang', 'rg'],
    'route': ['route', 'rte'],
    'terrasse': ['terrasse', 'tsse'],
    'allee': ['allee', 'allée'],
    'passage': ['passage', 'pass'],
    'square': ['square', 'sq'],
    'croissant': ['croissant', 'crois'],
    'impasse': ['impasse', 'imp'],
}

# Common abbreviation mappings
ABBREVIATIONS = {
    'st': 'saint',
    'st-': 'saint-',
    'ste': 'sainte',
    'ste-': 'sainte-',
    'mt': 'mont',
    'mt-': 'mont-',
}


def normalize_street_name(name: str) -> str:
    """Normalize street name for matching."""
    if not name:
        return ''

    # Convert to lowercase
    normalized = name.lower().strip()

    # Remove accents (simple version)
    accent_map = {
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'à': 'a', 'â': 'a', 'ä': 'a',
        'ù': 'u', 'û': 'u', 'ü': 'u',
        'ô': 'o', 'ö': 'o',
        'î': 'i', 'ï': 'i',
        'ç': 'c',
    }
    for accented, plain in accent_map.items():
        normalized = normalized.replace(accented, plain)

    # Expand abbreviations
    for abbrev, full in ABBREVIATIONS.items():
        if normalized.startswith(abbrev):
            normalized = full + normalized[len(abbrev):]

    # Remove common prefixes like "rue", "avenue" etc.
    for type_name, variations in STREET_TYPES.items():
        for var in variations:
            if normalized.startswith(var + ' '):
                normalized = normalized[len(var) + 1:]
                break

    return normalized


def parse_address(address: str) -> Dict[str, Any]:
    """Parse address string into components."""
    if not address:
        return {}

    address = address.strip()

    # Try to extract civic number from start
    match = re.match(r'^(\d+)\s*[-,]?\s*(.+)$', address)

    if match:
        civic_number = int(match.group(1))
        street_part = match.group(2).strip()
    else:
        # Maybe street name first, then number
        match = re.match(r'^(.+?)\s+(\d+)$', address)
        if match:
            street_part = match.group(1).strip()
            civic_number = int(match.group(2))
        else:
            return {'street_name': address, 'civic_number': None}

    # Try to extract street type
    street_type = None
    street_name = street_part

    for type_name, variations in STREET_TYPES.items():
        for var in variations:
            pattern = rf'^({var})\s+(.+)$'
            type_match = re.match(pattern, street_part, re.IGNORECASE)
            if type_match:
                street_type = type_name.capitalize()
                street_name = type_match.group(2)
                break
        if street_type:
            break

    return {
        'civic_number': civic_number,
        'street_type': street_type,
        'street_name': street_name,
        'normalized_name': normalize_street_name(street_name)
    }


def download_geobase_csv() -> str:
    """Download Geobase Double CSV data from Montreal open data portal."""
    # The actual CSV URL from donnees.montreal.ca
    csv_url = (
        "https://donnees.montreal.ca/dataset/"
        "984f7a68-ab34-4092-9204-4bdfcca767c5/resource/"
        "9d3d60d8-4e7f-493e-b7a6-6e89c19aee93/download/geobase-double.csv"
    )

    logger.info(f"Downloading Geobase CSV from {csv_url}")

    try:
        response = requests.get(csv_url, timeout=120)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Failed to download Geobase CSV: {e}")
        raise


def refresh_cache() -> Dict[str, Any]:
    """Download and cache Geobase data."""
    start_time = datetime.utcnow()

    try:
        csv_data = download_geobase_csv()
    except Exception as e:
        return {'success': False, 'error': str(e)}

    # Clear existing cache
    GeobaseCache.query.delete()

    # Parse CSV and insert into cache
    reader = csv.DictReader(io.StringIO(csv_data))
    count = 0
    batch = []

    for row in reader:
        try:
            entry = GeobaseCache(
                cote_rue_id=int(row.get('COTE_RUE_ID', 0)),
                nom_voie=row.get('NOM_VOIE', ''),
                type_voie=row.get('TYPE_F', ''),
                debut_adresse=int(row.get('DEBUT_ADRESSE', 0) or 0),
                fin_adresse=int(row.get('FIN_ADRESSE', 0) or 0),
                cote=row.get('COTE', ''),
                nom_ville=row.get('NOM_VILLE', 'Montréal'),
                last_updated=datetime.utcnow()
            )
            batch.append(entry)
            count += 1

            # Batch insert every 1000 records
            if len(batch) >= 1000:
                db.session.bulk_save_objects(batch)
                db.session.commit()
                batch = []

        except (ValueError, KeyError) as e:
            logger.warning(f"Skipping invalid row: {e}")
            continue

    # Insert remaining
    if batch:
        db.session.bulk_save_objects(batch)
        db.session.commit()

    duration = (datetime.utcnow() - start_time).total_seconds()

    logger.info(f"Geobase cache refreshed: {count} entries in {duration:.2f}s")

    return {
        'success': True,
        'entries': count,
        'duration_seconds': duration
    }


def is_cache_stale() -> bool:
    """Check if cache needs refresh."""
    latest = GeobaseCache.query.order_by(GeobaseCache.last_updated.desc()).first()

    if not latest:
        return True

    cache_age = datetime.utcnow() - latest.last_updated
    max_age = timedelta(days=current_app.config.get('GEOBASE_CACHE_DAYS', 7))

    return cache_age > max_age


def ensure_cache() -> None:
    """Ensure cache is populated and fresh."""
    if is_cache_stale():
        refresh_cache()


def lookup_address(address: str) -> Optional[Dict[str, Any]]:
    """Look up COTE_RUE_ID for an address string."""
    parsed = parse_address(address)

    if not parsed.get('normalized_name'):
        return None

    civic_number = parsed.get('civic_number')
    normalized = parsed['normalized_name']

    # Build query
    query = GeobaseCache.query.filter(
        GeobaseCache.nom_voie.ilike(f'%{normalized}%')
    )

    # If we have a civic number, filter by range
    if civic_number:
        query = query.filter(
            GeobaseCache.debut_adresse <= civic_number,
            GeobaseCache.fin_adresse >= civic_number
        )

    results = query.limit(10).all()

    if not results:
        # Try broader search
        query = GeobaseCache.query.filter(
            GeobaseCache.nom_voie.ilike(f'%{normalized[:4]}%')
        )
        if civic_number:
            query = query.filter(
                GeobaseCache.debut_adresse <= civic_number,
                GeobaseCache.fin_adresse >= civic_number
            )
        results = query.limit(10).all()

    if not results:
        return None

    # Score and sort results
    best_match = results[0]

    return {
        'cote_rue_id': best_match.cote_rue_id,
        'street_name': best_match.nom_voie,
        'street_type': best_match.type_voie,
        'civic_number': civic_number or best_match.debut_adresse,
        'cote': best_match.cote,
        'borough': best_match.nom_ville,
        'address_range': f"{best_match.debut_adresse}-{best_match.fin_adresse}"
    }


def search_addresses(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search for addresses matching a query (for autocomplete)."""
    if not query or len(query) < 3:
        return []

    parsed = parse_address(query)
    search_term = parsed.get('normalized_name', query)

    # Search by street name
    results = GeobaseCache.query.filter(
        GeobaseCache.nom_voie.ilike(f'%{search_term}%')
    ).limit(limit * 2).all()

    # Group by street name to avoid duplicates
    seen = set()
    unique_results = []

    for r in results:
        key = (r.nom_voie, r.cote)
        if key not in seen:
            seen.add(key)
            unique_results.append({
                'cote_rue_id': r.cote_rue_id,
                'display': f"{r.type_voie} {r.nom_voie}" if r.type_voie else r.nom_voie,
                'street_name': r.nom_voie,
                'street_type': r.type_voie,
                'cote': r.cote,
                'address_range': f"{r.debut_adresse}-{r.fin_adresse}",
                'borough': r.nom_ville
            })

            if len(unique_results) >= limit:
                break

    return unique_results


def lookup_by_coordinates(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """
    Find the nearest street to given coordinates.

    Note: This is a simplified implementation. For production,
    you'd want to use PostGIS or a proper spatial index.
    """
    # For now, just return a sample result based on approximate location
    # In production, this would use the Geobase geometry data

    # Check if coordinates are within Montreal bounds (approximate)
    if not (45.4 <= lat <= 45.7 and -73.9 <= lon <= -73.4):
        return None

    # Get any cached entry as fallback
    # In production, use spatial query
    entry = GeobaseCache.query.first()

    if not entry:
        return None

    return {
        'cote_rue_id': entry.cote_rue_id,
        'street_name': entry.nom_voie,
        'street_type': entry.type_voie,
        'civic_number': entry.debut_adresse,
        'cote': entry.cote,
        'borough': entry.nom_ville,
        'latitude': lat,
        'longitude': lon,
        'note': 'Approximate match - please verify address'
    }
