"""
Tests for database models
"""

import pytest
from datetime import datetime
from app import db
from app.models import Subscriber, Address, AlertHistory, GeobaseCache, SnowStatusCache


class TestSubscriberModel:
    """Tests for Subscriber model."""

    def test_create_subscriber(self, app):
        """Should create subscriber with required fields."""
        with app.app_context():
            subscriber = Subscriber(email='test@example.com')
            db.session.add(subscriber)
            db.session.commit()

            assert subscriber.id is not None
            assert subscriber.email == 'test@example.com'
            assert subscriber.is_active == True
            assert subscriber.unsubscribe_token is not None
            assert len(subscriber.unsubscribe_token) == 36  # UUID format

    def test_subscriber_email_unique(self, app):
        """Should enforce unique email constraint."""
        with app.app_context():
            sub1 = Subscriber(email='duplicate@example.com')
            db.session.add(sub1)
            db.session.commit()

            sub2 = Subscriber(email='duplicate@example.com')
            db.session.add(sub2)

            with pytest.raises(Exception):  # IntegrityError
                db.session.commit()

    def test_subscriber_to_dict(self, app):
        """Should serialize to dictionary."""
        with app.app_context():
            subscriber = Subscriber(email='test@example.com')
            db.session.add(subscriber)
            db.session.commit()

            data = subscriber.to_dict()
            assert data['email'] == 'test@example.com'
            assert data['is_active'] == True
            assert 'created_at' in data


class TestAddressModel:
    """Tests for Address model."""

    def test_create_address(self, app, sample_subscriber):
        """Should create address with required fields."""
        with app.app_context():
            subscriber = Subscriber.query.filter_by(email='test@example.com').first()

            address = Address(
                subscriber_id=subscriber.id,
                street_name='Saint-Denis',
                civic_number=1234,
                cote_rue_id=13811012
            )
            db.session.add(address)
            db.session.commit()

            assert address.id is not None
            assert address.subscriber_id == subscriber.id

    def test_address_full_address(self, app, sample_address):
        """Should format full address correctly."""
        with app.app_context():
            address = Address.query.first()
            full = address.full_address()

            assert '1234' in full
            assert 'Saint-Denis' in full

    def test_address_subscriber_relationship(self, app, sample_address):
        """Should have subscriber relationship."""
        with app.app_context():
            address = Address.query.first()
            assert address.subscriber is not None
            assert address.subscriber.email == 'test@example.com'


class TestAlertHistoryModel:
    """Tests for AlertHistory model."""

    def test_create_alert_history(self, app, sample_address):
        """Should create alert history."""
        with app.app_context():
            address = Address.query.first()

            alert = AlertHistory(
                address_id=address.id,
                alert_type='snow_scheduled',
                status='planifie'
            )
            db.session.add(alert)
            db.session.commit()

            assert alert.id is not None
            assert alert.sent_at is not None
            assert alert.delivered == True


class TestGeobaseCacheModel:
    """Tests for GeobaseCache model."""

    def test_create_geobase_entry(self, app):
        """Should create geobase cache entry."""
        with app.app_context():
            entry = GeobaseCache(
                cote_rue_id=12345678,
                nom_voie='Test Street',
                debut_adresse=100,
                fin_adresse=200,
                cote='Droit'
            )
            db.session.add(entry)
            db.session.commit()

            assert entry.id is not None


class TestSnowStatusCacheModel:
    """Tests for SnowStatusCache model."""

    def test_create_snow_status_cache(self, app):
        """Should create snow status cache entry."""
        with app.app_context():
            cache = SnowStatusCache(
                cote_rue_id=12345678,
                etat='planifie'
            )
            db.session.add(cache)
            db.session.commit()

            assert cache.id is not None

    def test_cache_is_expired(self, app):
        """Should correctly detect expired cache."""
        with app.app_context():
            from datetime import timedelta

            cache = SnowStatusCache(
                cote_rue_id=12345678,
                etat='planifie'
            )
            db.session.add(cache)
            db.session.commit()

            # Fresh cache should not be expired
            assert cache.is_expired(max_age_seconds=300) == False

            # Manually set old timestamp
            cache.fetched_at = datetime.utcnow() - timedelta(minutes=10)
            db.session.commit()

            # Old cache should be expired
            assert cache.is_expired(max_age_seconds=300) == True
