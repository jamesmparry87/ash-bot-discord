"""
Database module for Ash Bot
Handles all database operations including strikes, games, played games, reminders, and trivia
"""

import sys
import os
from typing import Optional, Any

# Add the Live directory to the path to import the existing database module
live_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..')
if live_dir not in sys.path:
    sys.path.insert(0, live_dir)

# Import with proper error handling and type hints
DatabaseManager = None
db: Any = None

try:
    from database import DatabaseManager as _DatabaseManager
    DatabaseManager = _DatabaseManager
    # Create a shared database instance
    if DatabaseManager is not None:
        db = DatabaseManager()
except ImportError as e:
    print(f"Warning: Could not import DatabaseManager: {e}")
    DatabaseManager = None
    db = None
except Exception as e:
    print(f"Warning: Could not initialize database: {e}")
    db = None

__all__ = ['DatabaseManager', 'db']
