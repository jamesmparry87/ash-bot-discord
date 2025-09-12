"""
Database Integration Module for Bot Components
Provides database access to modular components
"""

import os
import sys
from typing import TYPE_CHECKING, Optional

# Add the parent directory to sys.path to import the main database
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

if TYPE_CHECKING:
    from database import DatabaseManager
else:
    try:
        from database import DatabaseManager
    except ImportError:
        DatabaseManager = None

# Import the db instance
try:
    from database import db
    print("✅ Bot database integration loaded successfully")
except ImportError as e:
    print(f"❌ Failed to import main database manager: {e}")
    db = None
except Exception as e:
    print(f"❌ Database initialization error: {e}")
    db = None

__all__ = ['db', 'DatabaseManager']
