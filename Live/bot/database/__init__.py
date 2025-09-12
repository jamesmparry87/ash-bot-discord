"""
Database module for Ash Bot
Handles all database operations including strikes, games, played games, reminders, and trivia
"""

import sys
import os
from typing import Optional, Any

# Import with robust path handling for both development and production
DatabaseManager = None
db: Any = None

def _import_database_manager():
    """Robustly import DatabaseManager with fallback strategies"""
    global DatabaseManager, db
    
    # Strategy 1: Try direct import (if in same directory)
    try:
        from database import DatabaseManager as _DatabaseManager
        DatabaseManager = _DatabaseManager
        db = DatabaseManager()
        print("✅ Database imported successfully via direct import")
        return True
    except ImportError:
        pass

    # Strategy 2: Try importing from Live directory (development)
    try:
        live_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..')
        live_dir = os.path.abspath(live_dir)  # Get absolute path
        if live_dir not in sys.path:
            sys.path.insert(0, live_dir)
        
        from database import DatabaseManager as _DatabaseManager
        DatabaseManager = _DatabaseManager
        db = DatabaseManager()
        print(f"✅ Database imported successfully from Live directory: {live_dir}")
        return True
    except ImportError as e:
        print(f"⚠️ Could not import from Live directory: {e}")

    # Strategy 3: Try importing from parent directories (production)
    current_dir = os.path.dirname(__file__)
    for i in range(3):  # Try up to 3 levels up
        try:
            parent_dir = os.path.abspath(os.path.join(current_dir, '../' * (i + 2)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from database import DatabaseManager as _DatabaseManager
            DatabaseManager = _DatabaseManager
            db = DatabaseManager()
            print(f"✅ Database imported successfully from parent directory: {parent_dir}")
            return True
        except ImportError:
            continue
    
    print("❌ Could not import DatabaseManager with any strategy")
    return False

# Attempt to import database on module load
try:
    success = _import_database_manager()
    if not success:
        print("❌ Database initialization failed - reminder and database features may not work")
        DatabaseManager = None
        db = None
except Exception as e:
    print(f"❌ Database initialization exception: {e}")
    DatabaseManager = None
    db = None

__all__ = ['DatabaseManager', 'db']
