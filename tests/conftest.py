"""
Pytest Configuration and Fixtures
"""

import pytest
from app import create_app, db
from app.models import Subscriber, Address, AlertHistory, GeobaseCache


@pytest.fixture
def app():
    """Create and configure a test application instance."""
    app = create_app('testing')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create a test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture
def sample_subscriber(app):
    """Create a sample subscriber."""
    with app.app_context():
        subscriber = Subscriber(
            email='test@example.com',
            is_active=True
        )
        db.session.add(subscriber)
        db.session.commit()

        # Refresh to get the generated token
        db.session.refresh(subscriber)
        return subscriber


@pytest.fixture
def sample_address(app, sample_subscriber):
    """Create a sample address."""
    with app.app_context():
        # Re-query subscriber in this context
        subscriber = Subscriber.query.filter_by(email='test@example.com').first()

        address = Address(
            subscriber_id=subscriber.id,
            street_name='Saint-Denis',
            street_type='Rue',
            civic_number=1234,
            borough='Plateau-Mont-Royal',
            cote_rue_id=13811012,
            cote='Droit',
            latitude=45.5200,
            longitude=-73.5700
        )
        db.session.add(address)
        db.session.commit()

        db.session.refresh(address)
        return address


@pytest.fixture
def sample_geobase_entries(app):
    """Create sample Geobase cache entries."""
    with app.app_context():
        entries = [
            GeobaseCache(
                cote_rue_id=13811012,
                nom_voie='Saint-Denis',
                type_voie='Rue',
                debut_adresse=1200,
                fin_adresse=1300,
                cote='Droit',
                nom_ville='Montréal'
            ),
            GeobaseCache(
                cote_rue_id=13811013,
                nom_voie='Saint-Denis',
                type_voie='Rue',
                debut_adresse=1200,
                fin_adresse=1300,
                cote='Gauche',
                nom_ville='Montréal'
            ),
            GeobaseCache(
                cote_rue_id=14000001,
                nom_voie='Mont-Royal',
                type_voie='Avenue',
                debut_adresse=100,
                fin_adresse=500,
                cote='Droit',
                nom_ville='Montréal'
            ),
        ]

        for entry in entries:
            db.session.add(entry)
        db.session.commit()

        return entries


# Mock responses for external APIs
@pytest.fixture
def mock_planif_neige_response():
    """Sample Planif-Neige API response."""
    return {
        'etat': 'planifie',
        'date_debut': '2026-01-10T02:00:00',
        'date_fin': '2026-01-10T08:00:00',
        'date_maj': '2026-01-09T18:00:00'
    }


@pytest.fixture
def mock_waste_schedule():
    """Sample waste collection schedule."""
    return {
        'garbage': {
            'type': 'garbage',
            'name': 'Garbage',
            'name_fr': 'Ordures ménagères',
            'day_of_week': 'Tuesday',
            'frequency': 'weekly',
            'next_collection': '2026-01-14',
            'next_collection_display': 'Tuesday'
        },
        'recycling': {
            'type': 'recycling',
            'name': 'Recycling',
            'name_fr': 'Matières recyclables',
            'day_of_week': 'Tuesday',
            'frequency': 'bi-weekly',
            'next_collection': '2026-01-14',
            'next_collection_display': 'Tuesday'
        }
    }
