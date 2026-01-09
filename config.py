import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///alert_mtl.db')
    # Handle Render's postgres:// vs postgresql://
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)

    # Email (Resend)
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY')
    SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'alerts@alertmtl.com')

    # External APIs
    PLANIF_NEIGE_WSDL = os.environ.get(
        'PLANIF_NEIGE_WSDL',
        'https://servicesenligne2.ville.montreal.qc.ca/api/infoneige/InfoneigeWebService?WSDL'
    )
    GEOBASE_CSV_URL = os.environ.get(
        'GEOBASE_CSV_URL',
        'https://donnees.montreal.ca/dataset/geobase-double/resource/csv'
    )

    # App Settings
    APP_URL = os.environ.get('APP_URL', 'http://localhost:5000')
    ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'dev-admin-token')

    # Cache Settings (in appropriate units)
    GEOBASE_CACHE_DAYS = int(os.environ.get('GEOBASE_CACHE_DAYS', 7))
    PLANIF_NEIGE_CACHE_SECONDS = int(os.environ.get('PLANIF_NEIGE_CACHE_SECONDS', 300))
    WASTE_CACHE_HOURS = int(os.environ.get('WASTE_CACHE_HOURS', 24))


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///alert_mtl_dev.db')


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
