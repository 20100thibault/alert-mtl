# PRD: Waste Collection Schedule Rearchitecture

## Overview

Complete rearchitecture of the waste collection schedule system for Montreal and Quebec City. Each city will have its own independent service module with FSA-based (Forward Sortation Area - first 3 characters of postal code) schedule lookups.

---

## 1. Goals

1. **Complete Separation**: Each city has its own standalone module with zero shared dependencies
2. **FSA-Based Lookup**: Use postal code prefix to determine collection day (neighborhood-level accuracy)
3. **Reliable Fallback**: Clear error handling with "check city website" messages
4. **Standard Output Contract**: Both services return identical JSON structure for frontend consistency
5. **Testable**: Include test postal codes with expected results in each module

---

## 2. Architecture

### 2.1 File Structure

```
app/services/
├── montreal/
│   └── waste_schedule.py    # NEW - Montreal-specific waste schedule
├── quebec/
│   └── waste_schedule.py    # NEW - Quebec City-specific waste schedule
└── dispatcher.py            # UPDATE - Route to city-specific services
```

### 2.2 Standard Output Contract

Both city services must return this exact structure:

```python
{
    "success": True,
    "city": "montreal" | "quebec",
    "zone_code": "H2V",  # FSA code
    "zone_description": "Mile End / Outremont area",
    "disclaimer": "Schedule may vary by street. Check info-collectes for exact schedule.",
    "city_website": "https://montreal.ca/en/services/collection-schedules",
    "garbage": {
        "type": "garbage",
        "name": "Garbage",
        "name_fr": "Ordures ménagères",
        "day_of_week": "Tuesday",
        "day_of_week_fr": "Mardi",
        "frequency": "weekly",
        "frequency_fr": "hebdomadaire",
        "next_collection": "2026-01-14",
        "next_collection_display": "This Tuesday"
    },
    "recycling": {
        "type": "recycling",
        "name": "Recycling",
        "name_fr": "Matières recyclables",
        "day_of_week": "Tuesday",
        "day_of_week_fr": "Mardi",
        "frequency": "bi-weekly",
        "frequency_fr": "aux deux semaines",
        "next_collection": "2026-01-14",
        "next_collection_display": "This Tuesday"
    }
}
```

Error response:
```python
{
    "success": False,
    "city": "montreal" | "quebec",
    "error": "unknown_postal_code",
    "message": "We couldn't determine your collection schedule.",
    "message_fr": "Nous n'avons pas pu déterminer votre horaire de collecte.",
    "city_website": "https://montreal.ca/en/services/collection-schedules",
    "city_website_label": "Check Montreal Info-Collectes",
    "city_website_label_fr": "Consultez Info-Collectes Montréal"
}
```

---

## 3. Montreal Waste Schedule Service

### 3.1 FSA to Collection Day Mapping

Based on Montreal borough organization:

| Borough/Area | FSA Codes | Garbage Day | Recycling Day |
|--------------|-----------|-------------|---------------|
| Plateau-Mont-Royal | H2J, H2T, H2W, H2L | Monday | Monday |
| Mile End / Outremont | H2V, H2S, H3N | Tuesday | Tuesday |
| Rosemont-La Petite-Patrie | H1X, H1Y, H2G, H2R | Wednesday | Wednesday |
| Villeray/Saint-Michel/Parc-Ex | H2P, H2M, H2E, H2R | Thursday | Thursday |
| Ahuntsic-Cartierville | H2N, H2C, H3L, H3M | Friday | Friday |
| Downtown/Ville-Marie | H3A, H3B, H3C, H3G, H3H | Monday | Monday |
| NDG/Côte-des-Neiges | H3S, H3T, H3V, H3W, H4A, H4B, H4V | Wednesday | Wednesday |
| Verdun/LaSalle | H4G, H4H, H4E, H8N, H8P | Thursday | Thursday |
| Mercier-Hochelaga-Maisonneuve | H1L, H1M, H1N, H1K, H1V, H1W | Tuesday | Tuesday |
| Anjou/Saint-Léonard | H1J, H1R, H1S, H1T | Friday | Friday |
| Montreal-Nord | H1G, H1H | Monday | Monday |
| RDP/Pointe-aux-Trembles | H1A, H1B, H1C, H1E | Tuesday | Tuesday |
| West Island | H9A, H9B, H9C, H9H, H9J, H9K, H9R, H9S, H9W, H9X | Wednesday | Wednesday |
| Lachine | H8R, H8S, H8T | Monday | Monday |
| Sud-Ouest | H3J, H3K, H4C | Tuesday | Tuesday |

### 3.2 Test Cases

| Postal Code | Expected Garbage Day | Expected Recycling Day | Area |
|-------------|---------------------|------------------------|------|
| H2V 1V5 | Tuesday | Tuesday | Mile End |
| H2J 1A1 | Monday | Monday | Plateau |
| H1X 1A1 | Wednesday | Wednesday | Rosemont |
| H4A 1A1 | Wednesday | Wednesday | NDG |
| H3B 1A1 | Monday | Monday | Downtown |
| H1G 1A1 | Monday | Monday | Montreal-Nord |

---

## 4. Quebec City Waste Schedule Service

### 4.1 FSA to Collection Day Mapping

Based on Quebec City arrondissement organization:

| Arrondissement/Area | FSA Codes | Garbage Day | Recycling Day |
|---------------------|-----------|-------------|---------------|
| La Cité-Limoilou (dense) | G1K, G1L, G1R | Monday | Monday |
| La Cité-Limoilou (semi-dense) | G1M, G1N | Tuesday | Tuesday |
| Sainte-Foy-Sillery-Cap-Rouge | G1V, G1W, G1X, G1Y | Thursday | Thursday |
| Les Rivières | G1E, G2B, G2E | Wednesday | Wednesday |
| Charlesbourg | G1G, G1H, G2N | Friday | Friday |
| Beauport | G1B, G1C, G1E | Wednesday | Wednesday |
| La Haute-Saint-Charles | G2A, G2C, G3A, G3B, G3E, G3G, G3J, G3K | Thursday | Thursday |

### 4.2 Test Cases

| Postal Code | Expected Garbage Day | Expected Recycling Day | Area |
|-------------|---------------------|------------------------|------|
| G1V 1J8 | Thursday | Thursday | Sainte-Foy |
| G1K 1A1 | Monday | Monday | Cité-Limoilou |
| G1G 1A1 | Friday | Friday | Charlesbourg |
| G2B 1A1 | Wednesday | Wednesday | Les Rivières |
| G1B 1A1 | Wednesday | Wednesday | Beauport |

---

## 5. Dispatcher Integration

### 5.1 Updated get_waste_schedule Function

```python
def get_waste_schedule(city: str = None, postal_code: str = None, **kwargs) -> Dict[str, Any]:
    """
    Get waste schedule by routing to city-specific service.

    Args:
        city: 'montreal' or 'quebec'
        postal_code: Canadian postal code

    Returns:
        Standardized waste schedule dict
    """
    # Detect city from postal code if not provided
    if not city and postal_code:
        city = detect_city_from_postal(postal_code)

    if city == 'montreal':
        from app.services.montreal.waste_schedule import get_schedule
        return get_schedule(postal_code)
    elif city == 'quebec':
        from app.services.quebec.waste_schedule import get_schedule
        return get_schedule(postal_code)
    else:
        return _get_unknown_city_error()
```

---

## 6. Frontend Updates

### 6.1 Display Disclaimer

When displaying waste schedule, show the disclaimer:
```html
<p class="schedule-disclaimer">
    Schedule may vary by street.
    <a href="{city_website}" target="_blank">Check official schedule</a>
</p>
```

### 6.2 Handle Error State

When `success: false`:
```html
<div class="schedule-error">
    <p>{message}</p>
    <a href="{city_website}" class="btn">{city_website_label}</a>
</div>
```

---

## 7. Tasks Breakdown

### Phase 1: Montreal Service (Independent)
1. Create `app/services/montreal/waste_schedule.py`
2. Implement FSA mapping dictionary
3. Implement `get_schedule(postal_code)` function
4. Implement date calculation helpers
5. Add unit tests with test postal codes
6. Manual verification with API

### Phase 2: Quebec City Service (Independent)
1. Create `app/services/quebec/waste_schedule.py`
2. Implement FSA mapping dictionary
3. Implement `get_schedule(postal_code)` function
4. Implement date calculation helpers
5. Add unit tests with test postal codes
6. Manual verification with API

### Phase 3: Integration
1. Update dispatcher to use new services
2. Remove old waste schedule code
3. Update frontend to show disclaimer
4. Update frontend to handle error state
5. End-to-end testing
6. Deploy and verify

---

## 8. Success Criteria

1. Different Montreal postal codes return different collection days
2. Different Quebec City postal codes return different collection days
3. Unknown postal codes return error with city website link
4. Frontend displays disclaimer on all schedules
5. All test cases pass
6. No cross-contamination between city services

---

## 9. City Website URLs

- **Montreal**: https://montreal.ca/en/services/collection-schedules
- **Montreal (FR)**: https://montreal.ca/services/calendrier-des-collectes
- **Quebec City**: https://www.ville.quebec.qc.ca/services/info-collecte/
- **Quebec City (FR)**: https://www.ville.quebec.qc.ca/services/info-collecte/
