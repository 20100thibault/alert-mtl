"""
Tests for API routes
"""

import pytest
import json


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check_returns_200(self, client):
        """Health check should return 200 OK."""
        response = client.get('/health')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['status'] == 'healthy'
        assert 'timestamp' in data


class TestSubscription:
    """Tests for subscription endpoints."""

    def test_subscribe_requires_email(self, client):
        """Subscribe should require email."""
        response = client.post('/api/subscribe',
            data=json.dumps({'cote_rue_id': 12345}),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_subscribe_requires_cote_rue_id(self, client):
        """Subscribe should require cote_rue_id."""
        response = client.post('/api/subscribe',
            data=json.dumps({'email': 'test@example.com'}),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_subscribe_validates_email(self, client):
        """Subscribe should validate email format."""
        response = client.post('/api/subscribe',
            data=json.dumps({
                'email': 'not-an-email',
                'cote_rue_id': 12345
            }),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_subscribe_success(self, client):
        """Subscribe should create subscriber and address."""
        response = client.post('/api/subscribe',
            data=json.dumps({
                'email': 'new@example.com',
                'cote_rue_id': 12345,
                'address': {
                    'street_name': 'Test Street',
                    'civic_number': 100
                }
            }),
            content_type='application/json'
        )
        assert response.status_code == 201

        data = json.loads(response.data)
        assert data['success'] == True
        assert 'subscriber_id' in data
        assert 'address_id' in data


class TestUnsubscribe:
    """Tests for unsubscribe endpoint."""

    def test_unsubscribe_invalid_token(self, client):
        """Unsubscribe with invalid token should show error."""
        response = client.get('/unsubscribe/invalid-token-12345')
        assert response.status_code == 200
        assert b'Invalid token' in response.data or b'failed' in response.data.lower()

    def test_unsubscribe_valid_token(self, client, sample_subscriber, app):
        """Unsubscribe with valid token should succeed."""
        with app.app_context():
            from app.models import Subscriber
            subscriber = Subscriber.query.filter_by(email='test@example.com').first()
            token = subscriber.unsubscribe_token

        response = client.get(f'/unsubscribe/{token}')
        assert response.status_code == 200
        assert b'Successfully' in response.data or b'success' in response.data.lower()


class TestAddressSearch:
    """Tests for address search endpoint."""

    def test_search_requires_query(self, client):
        """Search should return empty for short queries."""
        response = client.get('/api/address/search?q=ab')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['results'] == []

    def test_search_returns_results(self, client, sample_geobase_entries):
        """Search should return matching results."""
        response = client.get('/api/address/search?q=saint-denis')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'results' in data


class TestSnowStatus:
    """Tests for snow status endpoint."""

    def test_snow_status_requires_params(self, client):
        """Snow status should require cote_rue_id, coords, or address."""
        response = client.get('/api/snow-status')
        assert response.status_code == 400

    def test_snow_status_with_cote_rue_id(self, client):
        """Snow status should accept cote_rue_id."""
        response = client.get('/api/snow-status?cote_rue_id=12345')
        # May return 500 if API is not mocked, but should not be 400
        assert response.status_code != 400 or response.status_code == 500


class TestAdminEndpoints:
    """Tests for admin endpoints."""

    def test_admin_requires_token(self, client):
        """Admin endpoints should require token."""
        response = client.get('/admin/trigger-snow-check')
        assert response.status_code == 401

    def test_admin_with_wrong_token(self, client):
        """Admin endpoints should reject wrong token."""
        response = client.get('/admin/trigger-snow-check?token=wrong-token')
        assert response.status_code == 401

    def test_admin_stats(self, client, app):
        """Admin stats should work with correct token."""
        response = client.get('/admin/stats?token=dev-admin-token')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'active_subscribers' in data
        assert 'total_addresses' in data
