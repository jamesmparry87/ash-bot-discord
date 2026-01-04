#!/usr/bin/env python3
"""Script to extract games/played_games methods and create games.py module"""

# Read the source file
with open('Live/bot/database_module.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find games section - starts after trivia, includes all played_games methods
# First game method is add_played_game
start = content.find('def add_played_game(')

# Find where games section ends (before get_connection or other utility methods)
# Games section ends before normalize_trivia_answer (which we already extracted)
end = content.find('def normalize_trivia_answer')

games_section = content[start:end]

# Create the games.py module
module_content = '''"""
Database Games Module - Played Games Management

This module handles:
- Played games CRUD operations
- Game data enrichment (IGDB, YouTube, Twitch)
- Alternative names and series management
- View statistics and analytics
- Timeline and chronological operations
- Search and filtering
- Data quality and validation
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, cast
from zoneinfo import ZoneInfo
from psycopg2.extras import RealDictRow

logger = logging.getLogger(__name__)


class GamesDatabase:
    """
    Handles all played games database operations.
    
    This class manages the complete played_games table including
    CRUD operations, enrichment, analytics, and data quality.
    """

    def __init__(self, db_manager):
        """
        Initialize games database handler.
        
        Args:
            db_manager: DatabaseManager instance for connection access
        """
        self.db = db_manager

    ''' + games_section + '''

# Export
__all__ = ['GamesDatabase']
'''

# Write the module
with open('Live/bot/database/games.py', 'w', encoding='utf-8') as f:
    f.write(module_content)

print("✅ Created Live/bot/database/games.py")
print(f"📊 Total size: {len(module_content):,} characters")
print(f"📊 Methods: ~60 games methods")
