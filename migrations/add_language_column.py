"""
Migration script to add 'language' column to subscribers table.
Run this script once after deploying the i18n update.

Usage: python migrations/add_language_column.py
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from sqlalchemy import text


def migrate():
    """Add language column to subscribers table if it doesn't exist."""
    app = create_app()

    with app.app_context():
        # Check if column exists
        try:
            # Try to query the column - if it fails, column doesn't exist
            result = db.session.execute(text("SELECT language FROM subscriber LIMIT 1"))
            print("Column 'language' already exists in subscribers table.")
            return True
        except Exception:
            pass

        # Add the column
        try:
            db.session.execute(text(
                "ALTER TABLE subscriber ADD COLUMN language VARCHAR(2) DEFAULT 'en'"
            ))
            db.session.commit()
            print("Successfully added 'language' column to subscribers table.")
            return True
        except Exception as e:
            print(f"Error adding column: {e}")
            db.session.rollback()
            return False


if __name__ == '__main__':
    migrate()
