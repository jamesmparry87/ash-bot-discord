"""
Database wrapper to handle import path issues
"""
import os
import sys

from database import DatabaseManager, get_database

# Add the Live directory to Python path for database import
live_dir = os.path.join(os.path.dirname(__file__), '..')
if live_dir not in sys.path:
    sys.path.insert(0, live_dir)


# Re-export for easy importing
__all__ = ['get_database', 'DatabaseManager']
