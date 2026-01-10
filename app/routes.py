import re
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for

from app import db, limiter, logger
from app.models import Subscriber, Address, AlertHistory, GeobaseCache, detect_city_from_postal

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
            'service': 'alert-quebec'
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
    """Get snow removal status for coordinates."""
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    city = request.args.get('city')

    if not (lat and lon):
        return jsonify({
            'error': 'Please provide coordinates (lat/lon)'
        }), 400

    try:
        from app.services import get_snow_status as service_get_snow_status

        # Auto-detect city from coordinates if not provided
        if not city:
            # Rough bounds: Montreal ~45.4-45.7, Quebec City ~46.7-47.0
            if 46.5 <= lat <= 47.5:
                city = 'quebec'
            else:
                city = 'montreal'

        status = service_get_snow_status(city=city, lat=lat, lon=lon)

        return jsonify({
            'city': city,
            'latitude': lat,
            'longitude': lon,
            'status': status
        })

    except Exception as e:
        logger.error(f"Error getting snow status: {e}")
        return jsonify({'error': 'Failed to get snow status'}), 500


@api_bp.route('/waste-schedule')
@limiter.limit("30 per minute")
def get_waste_schedule():
    """Get waste collection schedule for a location."""
    postal_code = request.args.get('postal_code', '').strip()
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    city = request.args.get('city')

    if not postal_code and not (lat and lon):
        return jsonify({'error': 'Please provide postal_code or lat/lon coordinates'}), 400

    try:
        from app.services import get_waste_schedule as service_get_waste_schedule

        schedule = service_get_waste_schedule(
            city=city,
            postal_code=postal_code if postal_code else None,
            lat=lat,
            lon=lon
        )

        if not schedule:
            return jsonify({'error': 'No waste schedule found for this location'}), 404

        return jsonify(schedule)

    except Exception as e:
        logger.error(f"Error getting waste schedule: {e}")
        return jsonify({'error': 'Failed to get waste schedule'}), 500


# ============================================================================
# API Routes - Geocoding
# ============================================================================

@api_bp.route('/geocode/postal-code')
@limiter.limit("30 per minute")
def geocode_postal_code_endpoint():
    """Convert postal code to coordinates. Supports both Montreal (H) and Quebec City (G)."""
    postal_code = request.args.get('postal_code', '').strip().upper()

    if not postal_code:
        return jsonify({'error': 'Postal code is required'}), 400

    # Validate Canadian postal code format
    postal_code = postal_code.replace(' ', '')
    if not re.match(r'^[A-Z]\d[A-Z]\d[A-Z]\d$', postal_code):
        return jsonify({'error': 'Invalid postal code format'}), 400

    formatted_postal = f"{postal_code[:3]} {postal_code[3:]}"

    # Detect city from postal code prefix
    try:
        city = detect_city_from_postal(postal_code)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    try:
        from app.services import geocode_postal_code as service_geocode

        result = service_geocode(postal_code)

        if not result:
            return jsonify({'error': 'Could not locate this postal code'}), 404

        return jsonify({
            'postal_code': formatted_postal,
            'city': city,
            'latitude': result['lat'],
            'longitude': result['lon'],
            'display_name': formatted_postal,
            'source': result.get('source', 'unknown')
        })

    except Exception as e:
        logger.error(f"Error geocoding postal code: {e}")
        return jsonify({'error': 'Failed to geocode postal code'}), 500


@api_bp.route('/geocode/reverse')
@limiter.limit("30 per minute")
def reverse_geocode():
    """Convert coordinates to nearest address."""
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)

    if not lat or not lon:
        return jsonify({'error': 'Please provide lat and lon coordinates'}), 400

    try:
        from app.services.montreal.geobase import lookup_by_coordinates
        result = lookup_by_coordinates(lat, lon)

        if not result:
            return jsonify({'error': 'No address found near these coordinates'}), 404

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in reverse geocoding: {e}")
        return jsonify({'error': 'Geocoding failed'}), 500


# ============================================================================
# API Routes - Quick Check
# ============================================================================

@api_bp.route('/quick-check/<postal_code>')
@limiter.limit("30 per minute")
def quick_check(postal_code):
    """Quick status check by postal code. Supports Montreal (H) and Quebec City (G)."""
    postal_code = postal_code.strip().upper().replace(' ', '')

    if not re.match(r'^[A-Z]\d[A-Z]\d[A-Z]\d$', postal_code):
        return jsonify({'error': 'Invalid postal code format'}), 400

    formatted_postal = f"{postal_code[:3]} {postal_code[3:]}"

    # Detect city from postal code prefix
    try:
        city = detect_city_from_postal(postal_code)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    try:
        from app.services import geocode_postal_code as service_geocode
        from app.services import get_snow_status as service_get_snow_status
        from app.services import get_waste_schedule as service_get_waste_schedule

        # Geocode the postal code
        location = service_geocode(postal_code)

        if not location:
            return jsonify({'error': 'Could not locate this postal code'}), 404

        lat, lon = location['lat'], location['lon']

        # Get snow status based on city
        snow_status = service_get_snow_status(city=city, lat=lat, lon=lon)

        # Get waste schedule
        waste_schedule = None
        try:
            waste_schedule = service_get_waste_schedule(city=city, postal_code=postal_code, lat=lat, lon=lon)
        except Exception as e:
            logger.warning(f"Could not get waste schedule: {e}")

        # Build city-specific location name
        if city == 'montreal':
            location_name = f"Montreal ({postal_code[:3]})"
        else:
            location_name = f"Quebec City ({postal_code[:3]})"

        return jsonify({
            'postal_code': formatted_postal,
            'city': city,
            'latitude': lat,
            'longitude': lon,
            'snow_status': snow_status or {'message': 'No data available'},
            'waste_schedule': waste_schedule,
            'location_name': location_name
        })

    except Exception as e:
        logger.error(f"Error in quick check: {e}")
        return jsonify({'error': 'Failed to check status'}), 500


# ============================================================================
# City-Specific Endpoints
# ============================================================================

@api_bp.route('/montreal/snow-status/<postal_code>')
@limiter.limit("30 per minute")
def montreal_snow_status(postal_code):
    """Get Montreal snow status for a postal code."""
    postal_code = postal_code.strip().upper().replace(' ', '')

    if not postal_code.startswith('H'):
        return jsonify({'error': 'Montreal postal codes start with H'}), 400

    try:
        from app.services import get_snow_status as service_get_snow_status
        from app.services import geocode_postal_code as service_geocode

        location = service_geocode(postal_code)
        if not location:
            return jsonify({'error': 'Could not locate postal code'}), 404

        status = service_get_snow_status(city='montreal', lat=location['lat'], lon=location['lon'])
        return jsonify(status)

    except Exception as e:
        logger.error(f"Error getting Montreal snow status: {e}")
        return jsonify({'error': 'Failed to get snow status'}), 500


@api_bp.route('/quebec/snow-status/<postal_code>')
@limiter.limit("30 per minute")
def quebec_snow_status(postal_code):
    """Get Quebec City snow status for a postal code."""
    postal_code = postal_code.strip().upper().replace(' ', '')

    if not postal_code.startswith('G'):
        return jsonify({'error': 'Quebec City postal codes start with G'}), 400

    try:
        from app.services import get_snow_status as service_get_snow_status
        from app.services import geocode_postal_code as service_geocode

        location = service_geocode(postal_code)
        if not location:
            return jsonify({'error': 'Could not locate postal code'}), 404

        status = service_get_snow_status(city='quebec', lat=location['lat'], lon=location['lon'])
        return jsonify(status)

    except Exception as e:
        logger.error(f"Error getting Quebec City snow status: {e}")
        return jsonify({'error': 'Failed to get snow status'}), 500


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
    city = data.get('city')  # Optional, will be auto-detected
    snow_alerts = data.get('snow_alerts', True)
    waste_alerts = data.get('waste_alerts', False)

    # Validate email
    if not email or not validate_email(email):
        return jsonify({'error': 'Valid email is required'}), 400

    # Validate postal code
    clean_postal = postal_code.replace(' ', '')
    if not re.match(r'^[A-Z]\d[A-Z]\d[A-Z]\d$', clean_postal):
        return jsonify({'error': 'Valid postal code is required'}), 400

    # Auto-detect city from postal code if not provided
    if not city:
        try:
            city = detect_city_from_postal(clean_postal)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

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

        # Create new address with city context
        address = Address(
            subscriber_id=subscriber.id,
            city=city,
            postal_code=formatted_postal,
            latitude=latitude,
            longitude=longitude,
            snow_alerts=snow_alerts,
            waste_alerts=waste_alerts,
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

        city_display = 'Montreal' if city == 'montreal' else 'Quebec City'

        return jsonify({
            'success': True,
            'message': f'Successfully subscribed to {city_display} alerts',
            'city': city,
            'subscriber_id': subscriber.id,
            'address_id': address.id,
            'unsubscribe_url': f"{current_app.config['APP_URL']}/unsubscribe/{subscriber.unsubscribe_token}"
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error subscribing: {e}")
        return jsonify({'error': 'Subscription failed'}), 500


@api_bp.route('/unsubscribe', methods=['POST'])
@limiter.limit("10 per minute")
def unsubscribe_api():
    """Unsubscribe an email from all alerts."""
    data = request.get_json()

    if not data or 'email' not in data:
        return jsonify({'error': 'Email is required'}), 400

    email = data['email'].strip().lower()

    subscriber = Subscriber.query.filter_by(email=email).first()

    if not subscriber:
        return jsonify({'error': 'Email not found'}), 404

    subscriber.is_active = False
    db.session.commit()

    logger.info(f"Subscriber {email} unsubscribed via API")
    return jsonify({'success': True, 'message': 'Successfully unsubscribed'})


# ============================================================================
# Admin Routes
# ============================================================================

@admin_bp.route('/trigger-snow-check')
@require_admin_token
def trigger_snow_check():
    """Manually trigger snow status check for all subscribers."""
    city = request.args.get('city')  # Optional: filter by city

    try:
        from app.services.alerts import check_all_snow_statuses
        result = check_all_snow_statuses(city=city)

        logger.info(f"Manual snow check triggered for {city or 'all cities'}: {result}")
        return jsonify({
            'success': True,
            'city': city or 'all',
            'result': result
        })

    except Exception as e:
        logger.error(f"Error in manual snow check: {e}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/trigger-waste-check')
@require_admin_token
def trigger_waste_check():
    """Manually trigger waste reminder check."""
    city = request.args.get('city')  # Optional: filter by city

    try:
        from app.services.alerts import send_waste_reminders
        result = send_waste_reminders(city=city)

        logger.info(f"Manual waste check triggered for {city or 'all cities'}: {result}")
        return jsonify({
            'success': True,
            'city': city or 'all',
            'result': result
        })

    except Exception as e:
        logger.error(f"Error in manual waste check: {e}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/refresh-geobase')
@require_admin_token
def refresh_geobase():
    """Manually refresh Montreal Geobase cache."""
    try:
        from app.services.montreal.geobase import refresh_cache
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

        # City breakdown
        montreal_addresses = Address.query.filter_by(city='montreal').count()
        quebec_addresses = Address.query.filter_by(city='quebec').count()

        alerts_today = AlertHistory.query.filter(
            AlertHistory.sent_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
        ).count()
        geobase_entries = GeobaseCache.query.count()

        return jsonify({
            'active_subscribers': active_subscribers,
            'total_addresses': total_addresses,
            'addresses_by_city': {
                'montreal': montreal_addresses,
                'quebec': quebec_addresses
            },
            'alerts_sent_today': alerts_today,
            'geobase_cache_entries': geobase_entries,
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500
