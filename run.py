#!/usr/bin/env python3
"""
Alert MTL - Application Entry Point

Run with: python run.py
Or with gunicorn: gunicorn run:app
"""

import os
from app import create_app, db
from app.scheduler import init_scheduler, shutdown_scheduler

# Create app
app = create_app()

# Initialize scheduler for background jobs
# Only in production or when explicitly enabled
if os.environ.get('ENABLE_SCHEDULER', 'false').lower() == 'true':
    with app.app_context():
        init_scheduler(app)


@app.teardown_appcontext
def shutdown(exception=None):
    """Cleanup on app shutdown."""
    pass


if __name__ == '__main__':
    # Development server
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'

    app.run(host='0.0.0.0', port=port, debug=debug)
