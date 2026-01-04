"""
Modular Database Package - Domain-Driven Architecture

This package provides a clean, modular interface to database operations
organized by domain: core, config, sessions, users, stats, trivia, and games.

Usage:
    from bot.database import get_database
    
    db = get_database()
    
    # Access domain modules:
    db.config.get_config_value('key')
    db.users.get_user_strikes(user_id)
    db.trivia.add_trivia_question(...)
    db.games.add_played_game(...)
    
Backward Compatibility:
    All existing DatabaseManager methods are still available for gradual migration.
"""

# Import core database manager
from .core import DatabaseManager

# Import domain modules
from .config import ConfigDatabase
from .sessions import SessionDatabase
from .users import UserDatabase
from .stats import StatsDatabase
from .trivia import TriviaDatabase
from .games import GamesDatabase

# Singleton instance
_db_instance = None


def get_database() -> DatabaseManager:
    """
    Get the singleton database manager instance.
    
    Returns:
        DatabaseManager: Fully initialized database manager with all domain modules
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance


# Create global db alias for backward compatibility
db = get_database()

# Export all classes and the singleton
__all__ = [
    'DatabaseManager',
    'ConfigDatabase',
    'SessionDatabase', 
    'UserDatabase',
    'StatsDatabase',
    'TriviaDatabase',
    'GamesDatabase',
    'get_database',
    'db'
]
