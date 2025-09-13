"""
Database Integration Module for Bot Components
Provides database access to modular components
"""

import os
import sys
from typing import TYPE_CHECKING, Any, Optional

# Add the parent directory to sys.path to import the main database
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Import the db instance and get_database function
try:
    from database import DatabaseManager, db, get_database  # type: ignore
    print("✅ Bot database integration loaded successfully")
except ImportError as e:
    print(f"❌ Failed to import main database manager: {e}")
    db = None
    DatabaseManager = None
    # Create a stub function to avoid callable errors

    def get_database():
        raise RuntimeError("Database not available - import failed")
except Exception as e:
    print(f"❌ Database initialization error: {e}")
    db = None
    DatabaseManager = None
    # Create a stub function to avoid callable errors

    def get_database():
        raise RuntimeError("Database not available - initialization failed")

__all__ = ['db', 'get_database', 'DatabaseManager']
