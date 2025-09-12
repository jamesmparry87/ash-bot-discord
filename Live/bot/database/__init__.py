"""
Database Integration Module for Bot Components
Provides database access to modular components
"""

import os
import sys

# Add the parent directory to sys.path to import the main database
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from database import db
    print("✅ Bot database integration loaded successfully")
except ImportError as e:
    print(f"❌ Failed to import main database manager: {e}")
    db = None
except Exception as e:
    print(f"❌ Database initialization error: {e}")
    db = None

# Export the database instance
__all__ = ['db']
