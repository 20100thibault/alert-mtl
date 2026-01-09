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


# ============================================================================
# API Routes - Subscription
# ============================================================================

@api_bp.route('/subscribe', methods=['POST'])
@limiter.limit("10 per minute")
def subscribe():
    """Subscribe an email to alerts for an address."""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    email = data.get('email', '').strip().lower()
    cote_rue_id = data.get('cote_rue_id')
    address_data = data.get('address', {})

    # Validate email
    if not email or not validate_email(email):
        return jsonify({'error': 'Valid email is required'}), 400

    # Validate address
    if not cote_rue_id:
        return jsonify({'error': 'cote_rue_id is required'}), 400

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

        # Check if this address already exists for subscriber
        existing = Address.query.filter_by(
            subscriber_id=subscriber.id,
            cote_rue_id=cote_rue_id
        ).first()

        if existing:
            return jsonify({
                'error': 'You are already subscribed to this address',
                'address_id': existing.id
            }), 409

        # Create new address
        address = Address(
            subscriber_id=subscriber.id,
            cote_rue_id=cote_rue_id,
            street_name=address_data.get('street_name', 'Unknown'),
            street_type=address_data.get('street_type'),
            civic_number=address_data.get('civic_number', 0),
            borough=address_data.get('borough'),
            cote=address_data.get('cote'),
            latitude=address_data.get('latitude'),
            longitude=address_data.get('longitude'),
            label=address_data.get('label', 'Home')
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
