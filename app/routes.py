import re
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for

from app import db, limiter, logger
from app.models import Subscriber, Address, AlertHistory, GeobaseCache

# Create blueprints
main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)
admin_bp = Blueprint('admin', __name__)


# ============================================================================
# Helper Functions
# ============================================================================

def validate_email(email):
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def require_admin_token(f):
    """Decorator to require admin token for protected endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-Admin-Token') or request.args.get('token')
        if token != current_app.config.get('ADMIN_TOKEN'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# Main Routes (Web Pages)
# ============================================================================

@main_bp.route('/')
def index():
    """Home page with status check and subscription form."""
    return render_template('index.html')


@main_bp.route('/unsubscribe/<token>')
def unsubscribe(token):
    """One-click unsubscribe via email link."""
    subscriber = Subscriber.query.filter_by(unsubscribe_token=token).first()

    if not subscriber:
        return render_template('unsubscribe.html', success=False, error='Invalid token')

    subscriber.is_active = False
    db.session.commit()

    logger.info(f"Subscriber {subscriber.email} unsubscribed")
    return render_template('unsubscribe.html', success=True, email=subscriber.email)


@main_bp.route('/health')
def health_check():
    """Health check endpoint for monitoring."""
    try:
        # Test database connection
        db.session.execute(db.text('SELECT 1'))
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'service': 'alert-mtl'
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


# ============================================================================
# API Routes - Status Check
# ============================================================================

@api_bp.route('/snow-status')
@limiter.limit("30 per minute")
def get_snow_status():
    """Get snow removal status for an address or coordinates."""
    # Get parameters
    cote_rue_id = request.args.get('cote_rue_id', type=int)
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    address = request.args.get('address')

    if not cote_rue_id and not (lat and lon) and not address:
        return jsonify({
            'error': 'Please provide cote_rue_id, coordinates (lat/lon), or address'
        }), 400

    try:
        from app.services.planif_neige import get_status_for_street

        # If we have an address, look up the COTE_RUE_ID
        if address and not cote_rue_id:
            from app.services.geobase import lookup_address
            result = lookup_address(address)
            if not result:
                return jsonify({'error': 'Address not found in Montreal'}), 404
            cote_rue_id = result['cote_rue_id']

        # If we have coordinates, find nearest street
        elif lat and lon and not cote_rue_id:
            from app.services.geobase import lookup_by_coordinates
            result = lookup_by_coordinates(lat, lon)
            if not result:
                return jsonify({'error': 'No street found near these coordinates'}), 404
            cote_rue_id = result['cote_rue_id']

        # Get the snow status
        status = get_status_for_street(cote_rue_id)

        return jsonify({
            'cote_rue_id': cote_rue_id,
            'status': status
        })

    except Exception as e:
        logger.error(f"Error getting snow status: {e}")
        return jsonify({'error': 'Failed to get snow status'}), 500


@api_bp.route('/waste-schedule')
@limiter.limit("30 per minute")
def get_waste_schedule():
    """Get waste collection schedule for coordinates."""
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)

    if not lat or not lon:
        return jsonify({'error': 'Please provide lat and lon coordinates'}), 400

    try:
        from app.services.waste import get_schedule_for_location
        schedule = get_schedule_for_location(lat, lon)

        if not schedule:
            return jsonify({'error': 'No waste schedule found for this location'}), 404

        return jsonify(schedule)

    except Exception as e:
        logger.error(f"Error getting waste schedule: {e}")
        return jsonify({'error': 'Failed to get waste schedule'}), 500


# ============================================================================
# API Routes - Address Lookup
# ============================================================================

@api_bp.route('/address/search')
@limiter.limit("60 per minute")
def search_address():
    """Search for addresses matching a query (autocomplete)."""
    query = request.args.get('q', '').strip()

    if len(query) < 3:
        return jsonify({'results': []})

    try:
        from app.services.geobase import search_addresses
        results = search_addresses(query, limit=10)
        return jsonify({'results': results})

    except Exception as e:
        logger.error(f"Error searching addresses: {e}")
        return jsonify({'error': 'Search failed'}), 500


@api_bp.route('/address/validate', methods=['POST'])
@limiter.limit("30 per minute")
def validate_address():
    """Validate an address and return COTE_RUE_ID."""
    data = request.get_json()

    if not data or 'address' not in data:
        return jsonify({'error': 'Address is required'}), 400

    try:
        from app.services.geobase import lookup_address
        result = lookup_address(data['address'])

        if not result:
            return jsonify({
                'valid': False,
                'error': 'Address not found in Montreal'
            }), 404

        return jsonify({
            'valid': True,
            'cote_rue_id': result['cote_rue_id'],
            'street_name': result['street_name'],
            'civic_number': result['civic_number'],
            'cote': result['cote'],
            'borough': result.get('borough')
        })

    except Exception as e:
        logger.error(f"Error validating address: {e}")
        return jsonify({'error': 'Validation failed'}), 500


@api_bp.route('/geocode/reverse')
@limiter.limit("30 per minute")
def reverse_geocode():
    """Convert coordinates to nearest Montreal address."""
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)

    if not lat or not lon:
        return jsonify({'error': 'Please provide lat and lon coordinates'}), 400

    try:
        from app.services.geobase import lookup_by_coordinates
        result = lookup_by_coordinates(lat, lon)

        if not result:
            return jsonify({'error': 'No address found near these coordinates'}), 404

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in reverse geocoding: {e}")
        return jsonify({'error': 'Geocoding failed'}), 500


@api_bp.route('/geocode/postal-code')
@limiter.limit("30 per minute")
def geocode_postal_code_endpoint():
    """Convert postal code to coordinates."""
    postal_code = request.args.get('postal_code', '').strip().upper()

    if not postal_code:
        return jsonify({'error': 'Postal code is required'}), 400

    # Validate Canadian postal code format
    postal_code = postal_code.replace(' ', '')
    if not re.match(r'^[A-Z]\d[A-Z]\d[A-Z]\d$', postal_code):
        return jsonify({'error': 'Invalid postal code format'}), 400

    # Check if it's a Montreal postal code
    if not postal_code.startswith('H'):
        return jsonify({'error': 'This postal code is not in Montreal (must start with H)'}), 400

    formatted_postal = f"{postal_code[:3]} {postal_code[3:]}"
    fsa = postal_code[:3]

    try:
        lat, lon, location_name = None, None, None

        # Try Nominatim first
        lat, lon, location_name = geocode_postal_code_nominatim(postal_code)

        # Fallback to FSA lookup table
        if lat is None and fsa in MONTREAL_FSA_COORDS:
            lat, lon = MONTREAL_FSA_COORDS[fsa]
            location_name = f"Montreal ({fsa})"

        if lat is None:
            return jsonify({'error': 'Could not locate this postal code'}), 404

        return jsonify({
            'postal_code': formatted_postal,
            'latitude': lat,
            'longitude': lon,
            'display_name': location_name or formatted_postal
        })

    except Exception as e:
        logger.error(f"Error geocoding postal code: {e}")
        return jsonify({'error': 'Failed to geocode postal code'}), 500


def geocode_postal_code_nominatim(postal_code):
    """Try to geocode a Canadian postal code using Nominatim."""
    import requests as req

    formatted_postal = f"{postal_code[:3]} {postal_code[3:]}"
    headers = {'User-Agent': 'AlertMTL/1.0 (Montreal snow/waste alerts)'}

    # Try 1: Full postal code with city context
    try:
        response = req.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                'q': f"{formatted_postal}, Montreal, Quebec, Canada",
                'format': 'json',
                'limit': 1
            },
            headers=headers,
            timeout=10
        )
        results = response.json()
        if results:
            return float(results[0]['lat']), float(results[0]['lon']), results[0].get('display_name', formatted_postal)
    except:
        pass

    # Try 2: Just postal code with country
    try:
        response = req.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                'postalcode': formatted_postal,
                'country': 'Canada',
                'format': 'json',
                'limit': 1
            },
            headers=headers,
            timeout=10
        )
        results = response.json()
        if results:
            return float(results[0]['lat']), float(results[0]['lon']), results[0].get('display_name', formatted_postal)
    except:
        pass

    # Try 3: FSA only (first 3 chars) - broader area
    fsa = postal_code[:3]
    try:
        response = req.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                'q': f"{fsa}, Montreal, Quebec, Canada",
                'format': 'json',
                'limit': 1
            },
            headers=headers,
            timeout=10
        )
        results = response.json()
        if results:
            return float(results[0]['lat']), float(results[0]['lon']), f"Montreal ({fsa})"
    except:
        pass

    return None, None, None


# Montreal FSA (Forward Sortation Area) approximate coordinates
# These are the first 3 characters of Montreal postal codes
MONTREAL_FSA_COORDS = {
    'H1A': (45.6205, -73.6049), 'H1B': (45.6275, -73.5699), 'H1C': (45.6153, -73.5486),
    'H1E': (45.6359, -73.5879), 'H1G': (45.5902, -73.6139), 'H1H': (45.5753, -73.6249),
    'H1J': (45.6051, -73.5651), 'H1K': (45.5909, -73.5761), 'H1L': (45.5826, -73.5498),
    'H1M': (45.5648, -73.5624), 'H1N': (45.5527, -73.5471), 'H1P': (45.5958, -73.6365),
    'H1R': (45.5775, -73.6531), 'H1S': (45.5635, -73.6272), 'H1T': (45.5594, -73.6050),
    'H1V': (45.5524, -73.5682), 'H1W': (45.5413, -73.5482), 'H1X': (45.5524, -73.5941),
    'H1Y': (45.5405, -73.5772), 'H1Z': (45.5493, -73.6152),
    'H2A': (45.5361, -73.6049), 'H2B': (45.5362, -73.6329), 'H2C': (45.5367, -73.6531),
    'H2E': (45.5330, -73.5989), 'H2G': (45.5260, -73.5917), 'H2H': (45.5166, -73.5808),
    'H2J': (45.5245, -73.5690), 'H2K': (45.5328, -73.5536), 'H2L': (45.5187, -73.5614),
    'H2M': (45.5369, -73.6501), 'H2N': (45.5325, -73.6696), 'H2P': (45.5306, -73.6213),
    'H2R': (45.5257, -73.6167), 'H2S': (45.5232, -73.6056), 'H2T': (45.5188, -73.5918),
    'H2V': (45.5188, -73.6084), 'H2W': (45.5131, -73.5790), 'H2X': (45.5088, -73.5696),
    'H2Y': (45.5047, -73.5556), 'H2Z': (45.5044, -73.5621),
    'H3A': (45.5029, -73.5793), 'H3B': (45.4999, -73.5704), 'H3C': (45.4928, -73.5544),
    'H3E': (45.4666, -73.5312), 'H3G': (45.4970, -73.5806), 'H3H': (45.4854, -73.5896),
    'H3J': (45.4816, -73.5695), 'H3K': (45.4722, -73.5609), 'H3L': (45.5264, -73.6509),
    'H3M': (45.5091, -73.6845), 'H3N': (45.5188, -73.6294), 'H3P': (45.5001, -73.6448),
    'H3R': (45.4902, -73.6344), 'H3S': (45.4987, -73.6193), 'H3T': (45.5000, -73.6049),
    'H3V': (45.4870, -73.6169), 'H3W': (45.4781, -73.6259), 'H3X': (45.4702, -73.6436),
    'H3Y': (45.4811, -73.5923), 'H3Z': (45.4867, -73.5857),
    'H4A': (45.4621, -73.6234), 'H4B': (45.4581, -73.6400), 'H4C': (45.4648, -73.5998),
    'H4E': (45.4554, -73.5808), 'H4G': (45.4627, -73.5655), 'H4H': (45.4623, -73.5519),
    'H4J': (45.5057, -73.6644), 'H4K': (45.5151, -73.6783), 'H4L': (45.5217, -73.6942),
    'H4M': (45.5134, -73.7121), 'H4N': (45.5014, -73.6783), 'H4P': (45.4919, -73.6609),
    'H4R': (45.4873, -73.6917), 'H4S': (45.4730, -73.6894), 'H4T': (45.4868, -73.6681),
    'H4V': (45.4589, -73.6190), 'H4W': (45.4494, -73.6408), 'H4X': (45.4414, -73.6329),
    'H4Y': (45.4567, -73.6600), 'H4Z': (45.5011, -73.5686),
    'H5A': (45.5004, -73.5632), 'H5B': (45.5054, -73.5587),
    'H8N': (45.4384, -73.6131), 'H8P': (45.4290, -73.6255), 'H8R': (45.4327, -73.6506),
    'H8S': (45.4449, -73.6565), 'H8T': (45.4508, -73.6772), 'H8Y': (45.4628, -73.6843),
    'H8Z': (45.4536, -73.6986), 'H9A': (45.4649, -73.7313), 'H9B': (45.4579, -73.7501),
    'H9C': (45.4430, -73.7419), 'H9E': (45.4318, -73.7089), 'H9G': (45.4332, -73.7342),
    'H9H': (45.4529, -73.7655), 'H9J': (45.4427, -73.7620), 'H9K': (45.4340, -73.7554),
    'H9P': (45.4663, -73.7495), 'H9R': (45.4761, -73.7667), 'H9S': (45.4869, -73.7720),
    'H9W': (45.4283, -73.7731), 'H9X': (45.4155, -73.8002),
}


@api_bp.route('/quick-check/<postal_code>')
@limiter.limit("30 per minute")
def quick_check(postal_code):
    """Quick status check by postal code."""
    postal_code = postal_code.strip().upper().replace(' ', '')

    if not re.match(r'^[A-Z]\d[A-Z]\d[A-Z]\d$', postal_code):
        return jsonify({'error': 'Invalid postal code format'}), 400

    formatted_postal = f"{postal_code[:3]} {postal_code[3:]}"
    fsa = postal_code[:3]

    # Check if it's a Montreal postal code (starts with H)
    if not postal_code.startswith('H'):
        return jsonify({'error': 'This postal code is not in Montreal (must start with H)'}), 400

    try:
        lat, lon, location_name = None, None, None

        # Try Nominatim first
        lat, lon, location_name = geocode_postal_code_nominatim(postal_code)

        # Fallback to FSA lookup table
        if lat is None and fsa in MONTREAL_FSA_COORDS:
            lat, lon = MONTREAL_FSA_COORDS[fsa]
            location_name = f"Montreal ({fsa})"

        if lat is None:
            return jsonify({'error': 'Could not locate this postal code'}), 404

        # Check Montreal bounds (expanded)
        if not (45.3 <= lat <= 45.8 and -74.0 <= lon <= -73.3):
            return jsonify({'error': 'This postal code is not in Montreal area'}), 400

        # Get snow status
        from app.services.planif_neige import get_status_for_street
        from app.models import GeobaseCache

        entry = GeobaseCache.query.first()
        snow_status = None

        if entry:
            try:
                snow_status = get_status_for_street(entry.cote_rue_id)
            except:
                pass

        # Get waste schedule
        waste_schedule = None
        try:
            from app.services.waste import get_schedule_for_location
            waste_schedule = get_schedule_for_location(lat, lon)
        except:
            pass

        return jsonify({
            'postal_code': formatted_postal,
            'latitude': lat,
            'longitude': lon,
            'snow_status': snow_status or {'message': 'No data available'},
            'waste_schedule': waste_schedule,
            'location_name': location_name or formatted_postal
        })

    except Exception as e:
        logger.error(f"Error in quick check: {e}")
        return jsonify({'error': 'Failed to check status'}), 500


# ============================================================================
# API Routes - Subscription
# ============================================================================

@api_bp.route('/subscribe', methods=['POST'])
@limiter.limit("10 per minute")
def subscribe():
    """Subscribe an email to alerts for a postal code."""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    email = data.get('email', '').strip().lower()
    postal_code = data.get('postal_code', '').strip().upper()
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    # Validate email
    if not email or not validate_email(email):
        return jsonify({'error': 'Valid email is required'}), 400

    # Validate postal code
    clean_postal = postal_code.replace(' ', '')
    if not re.match(r'^[A-Z]\d[A-Z]\d[A-Z]\d$', clean_postal):
        return jsonify({'error': 'Valid Montreal postal code is required'}), 400

    try:
        # Find or create subscriber
        subscriber = Subscriber.query.filter_by(email=email).first()

        if subscriber:
            if not subscriber.is_active:
                subscriber.is_active = True
                logger.info(f"Reactivated subscriber: {email}")
        else:
            subscriber = Subscriber(email=email)
            db.session.add(subscriber)
            db.session.flush()
            logger.info(f"New subscriber: {email}")

        # Check address limit (max 5 per subscriber)
        if subscriber.addresses.count() >= 5:
            return jsonify({
                'error': 'Maximum 5 addresses per subscriber'
            }), 400

        # Check if this postal code already exists for subscriber
        formatted_postal = f"{clean_postal[:3]} {clean_postal[3:]}"
        existing = Address.query.filter_by(
            subscriber_id=subscriber.id,
            postal_code=formatted_postal
        ).first()

        if existing:
            return jsonify({
                'error': 'You are already subscribed to this postal code',
                'address_id': existing.id
            }), 409

        # Create new address with postal code
        address = Address(
            subscriber_id=subscriber.id,
            postal_code=formatted_postal,
            latitude=latitude,
            longitude=longitude,
            label='Home'
        )
        db.session.add(address)
        db.session.commit()

        # Send confirmation email
        try:
            from app.services.email import send_confirmation_email
            send_confirmation_email(subscriber, address)
        except Exception as e:
            logger.warning(f"Failed to send confirmation email: {e}")

        return jsonify({
            'success': True,
            'message': 'Successfully subscribed to alerts',
            'subscriber_id': subscriber.id,
            'address_id': address.id,
            'unsubscribe_url': f"{current_app.config['APP_URL']}/unsubscribe/{subscriber.unsubscribe_token}"
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error subscribing: {e}")
        return jsonify({'error': 'Subscription failed'}), 500


# ============================================================================
# Admin Routes
# ============================================================================

@admin_bp.route('/trigger-snow-check')
@require_admin_token
def trigger_snow_check():
    """Manually trigger snow status check for all subscribers."""
    try:
        from app.services.alerts import check_all_snow_statuses
        result = check_all_snow_statuses()

        logger.info(f"Manual snow check triggered: {result}")
        return jsonify({
            'success': True,
            'result': result
        })

    except Exception as e:
        logger.error(f"Error in manual snow check: {e}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/trigger-waste-check')
@require_admin_token
def trigger_waste_check():
    """Manually trigger waste reminder check."""
    try:
        from app.services.alerts import send_waste_reminders
        result = send_waste_reminders()

        logger.info(f"Manual waste check triggered: {result}")
        return jsonify({
            'success': True,
            'result': result
        })

    except Exception as e:
        logger.error(f"Error in manual waste check: {e}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/refresh-geobase')
@require_admin_token
def refresh_geobase():
    """Manually refresh Geobase cache."""
    try:
        from app.services.geobase import refresh_cache
        result = refresh_cache()

        logger.info(f"Geobase cache refreshed: {result}")
        return jsonify({
            'success': True,
            'result': result
        })

    except Exception as e:
        logger.error(f"Error refreshing Geobase: {e}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/stats')
@require_admin_token
def get_stats():
    """Get application statistics."""
    try:
        active_subscribers = Subscriber.query.filter_by(is_active=True).count()
        total_addresses = Address.query.count()
        alerts_today = AlertHistory.query.filter(
            AlertHistory.sent_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
        ).count()
        geobase_entries = GeobaseCache.query.count()

        return jsonify({
            'active_subscribers': active_subscribers,
            'total_addresses': total_addresses,
            'alerts_sent_today': alerts_today,
            'geobase_cache_entries': geobase_entries,
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500
