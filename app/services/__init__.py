# Alert Quebec Services
# Unified service layer with city-specific implementations

from .dispatcher import (
    get_snow_status,
    get_waste_schedule,
    geocode_postal_code
)

# City-specific modules available via:
# - app.services.montreal
# - app.services.quebec

__all__ = [
    'get_snow_status',
    'get_waste_schedule',
    'geocode_postal_code',
]
