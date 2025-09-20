"""
Database Integration Module for Bot Components
Provides database access to modular components
"""

import os
import sys
from typing import TYPE_CHECKING, Any, Optional

# Add the parent directory to sys.path to import the main database
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Import the enhanced database module with trivia methods
try:
    from bot.database_module import DatabaseManager, db, get_database  # type: ignore
    print("✅ Bot database integration loaded successfully")
except ImportError as e:
    print(f"❌ Failed to import enhanced database manager: {e}")
    # Fallback to old database if enhanced version fails
    try:
        from database import DatabaseManager, db, get_database  # type: ignore
        print("⚠️ Using fallback database (enhanced trivia features may not be available)")
    except ImportError as e2:
        print(f"❌ Failed to import fallback database manager: {e2}")
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
