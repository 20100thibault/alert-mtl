import uuid
from datetime import datetime
from app import db


def generate_token():
    """Generate a unique unsubscribe token."""
    return str(uuid.uuid4())


def detect_city_from_postal(postal_code: str) -> str:
    """Detect city from postal code prefix.

    Args:
        postal_code: Canadian postal code (e.g., 'H2V 1V5' or 'G1R 4P5')

    Returns:
        'montreal' for H prefix, 'quebec' for G prefix

    Raises:
        ValueError: If postal code prefix is not supported
    """
    if not postal_code:
        raise ValueError("Postal code is required")

    prefix = postal_code.strip().upper()[0]
    if prefix == 'H':
        return 'montreal'
    elif prefix == 'G':
        return 'quebec'
    else:
        raise ValueError(f"Unsupported postal code prefix: {prefix}. Only H (Montreal) and G (Quebec City) are supported.")


class Subscriber(db.Model):
    """Subscriber model for email alert recipients."""
    __tablename__ = 'subscribers'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    unsubscribe_token = db.Column(db.String(36), unique=True, default=generate_token)

    # Relationships
    addresses = db.relationship('Address', backref='subscriber', lazy='dynamic',
                                cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Subscriber {self.email}>'

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'created_at': self.created_at.isoformat(),
            'is_active': self.is_active,
            'address_count': self.addresses.count()
        }


class Address(db.Model):
    """Address model for tracked locations."""
    __tablename__ = 'addresses'

    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('subscribers.id'), nullable=False)

    # City identifier (montreal or quebec)
    city = db.Column(db.String(20), nullable=False, default='montreal', index=True)

    # Postal code (primary identifier)
    postal_code = db.Column(db.String(10), index=True)

    # Address components (optional)
    street_name = db.Column(db.String(255))
    street_type = db.Column(db.String(50))  # Rue, Avenue, Boulevard, etc.
    civic_number = db.Column(db.Integer)
    borough = db.Column(db.String(100))

    # Montreal-specific identifiers
    cote_rue_id = db.Column(db.Integer, index=True)
    cote = db.Column(db.String(10))  # "Droit" or "Gauche"

    # Quebec City-specific identifiers
    waste_zone_id = db.Column(db.Integer, db.ForeignKey('waste_zones.id'), nullable=True)

    # Coordinates for waste collection lookup
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    # Status tracking
    last_snow_status = db.Column(db.String(50))
    last_snow_check = db.Column(db.DateTime)

    # Alert preferences (per address)
    snow_alerts = db.Column(db.Boolean, default=True)
    waste_alerts = db.Column(db.Boolean, default=False)

    # Metadata
    label = db.Column(db.String(50))  # "Home", "Work", etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    alert_history = db.relationship('AlertHistory', backref='address', lazy='dynamic',
                                    cascade='all, delete-orphan')
    waste_zone = db.relationship('WasteZone', backref='addresses')

    def __repr__(self):
        city_label = f"[{self.city}]" if self.city else ""
        if self.postal_code:
            return f'<Address {city_label} {self.postal_code}>'
        return f'<Address {city_label} {self.civic_number} {self.street_name}>'

    def full_address(self):
        """Return formatted full address."""
        if self.postal_code and not self.street_name:
            return self.postal_code
        parts = []
        if self.civic_number:
            parts.append(str(self.civic_number))
        if self.street_type:
            parts.append(self.street_type)
        if self.street_name:
            parts.append(self.street_name)
        if self.borough:
            parts.append(f", {self.borough}")
        return ' '.join(parts) if parts else self.postal_code or 'Unknown'

    def city_display_name(self):
        """Return human-readable city name."""
        return 'Montreal' if self.city == 'montreal' else 'Quebec City'

    def to_dict(self):
        return {
            'id': self.id,
            'city': self.city,
            'city_display': self.city_display_name(),
            'full_address': self.full_address(),
            'postal_code': self.postal_code,
            'street_name': self.street_name,
            'street_type': self.street_type,
            'civic_number': self.civic_number,
            'borough': self.borough,
            'cote_rue_id': self.cote_rue_id,
            'cote': self.cote,
            'waste_zone_id': self.waste_zone_id,
            'snow_alerts': self.snow_alerts,
            'waste_alerts': self.waste_alerts,
            'label': self.label,
            'last_snow_status': self.last_snow_status,
            'last_snow_check': self.last_snow_check.isoformat() if self.last_snow_check else None
        }


class WasteZone(db.Model):
    """Quebec City waste collection zones."""
    __tablename__ = 'waste_zones'

    id = db.Column(db.Integer, primary_key=True)
    zone_code = db.Column(db.String(20), unique=True, nullable=False, index=True)

    # Schedule information
    garbage_day = db.Column(db.String(20))  # 'monday', 'tuesday', etc.
    recycling_week = db.Column(db.String(10))  # 'odd' or 'even'

    # Zone boundaries (optional, for lookup)
    description = db.Column(db.String(255))

    def __repr__(self):
        return f'<WasteZone {self.zone_code}: {self.garbage_day}, recycling {self.recycling_week}>'

    def to_dict(self):
        return {
            'id': self.id,
            'zone_code': self.zone_code,
            'garbage_day': self.garbage_day,
            'recycling_week': self.recycling_week,
            'description': self.description
        }


class AlertHistory(db.Model):
    """Track all sent alerts for deduplication and analytics."""
    __tablename__ = 'alert_history'

    id = db.Column(db.Integer, primary_key=True)
    address_id = db.Column(db.Integer, db.ForeignKey('addresses.id'), nullable=False)

    # City for easier querying
    city = db.Column(db.String(20), index=True)

    # Alert details
    alert_type = db.Column(db.String(50), nullable=False)  # 'snow_scheduled', 'snow_urgent', 'snow_cleared', 'waste_reminder'
    status = db.Column(db.String(50))  # The status that triggered the alert
    message = db.Column(db.Text)

    # Reference date for deduplication (e.g., waste collection date)
    reference_date = db.Column(db.Date)

    # Delivery tracking
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text)

    # Composite index for deduplication
    __table_args__ = (
        db.Index('idx_alert_dedup', 'address_id', 'city', 'alert_type', 'reference_date'),
    )

    def __repr__(self):
        return f'<AlertHistory {self.alert_type} for address {self.address_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'address_id': self.address_id,
            'city': self.city,
            'alert_type': self.alert_type,
            'status': self.status,
            'reference_date': self.reference_date.isoformat() if self.reference_date else None,
            'sent_at': self.sent_at.isoformat(),
            'delivered': self.delivered
        }


class GeobaseCache(db.Model):
    """Cache for Geobase Double data (address to COTE_RUE_ID mapping)."""
    __tablename__ = 'geobase_cache'

    id = db.Column(db.Integer, primary_key=True)
    cote_rue_id = db.Column(db.Integer, unique=True, nullable=False, index=True)

    # Street information
    nom_voie = db.Column(db.String(255), nullable=False, index=True)
    type_voie = db.Column(db.String(50))  # Rue, Avenue, etc.

    # Address range
    debut_adresse = db.Column(db.Integer)
    fin_adresse = db.Column(db.Integer)

    # Side of street
    cote = db.Column(db.String(10))  # "Droit" or "Gauche"

    # Location
    nom_ville = db.Column(db.String(100))

    # Metadata
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<GeobaseCache {self.nom_voie} ({self.debut_adresse}-{self.fin_adresse})>'


class SnowStatusCache(db.Model):
    """Cache for Planif-Neige API responses."""
    __tablename__ = 'snow_status_cache'

    id = db.Column(db.Integer, primary_key=True)
    cote_rue_id = db.Column(db.Integer, nullable=False, index=True)

    # Status information
    etat = db.Column(db.String(50))  # enneige, planifie, en_cours, deneige, etc.
    date_debut = db.Column(db.DateTime)
    date_fin = db.Column(db.DateTime)

    # Cache metadata
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<SnowStatusCache {self.cote_rue_id}: {self.etat}>'

    def is_expired(self, max_age_seconds=300):
        """Check if cache entry is expired (default 5 minutes)."""
        if not self.fetched_at:
            return True
        age = (datetime.utcnow() - self.fetched_at).total_seconds()
        return age > max_age_seconds
