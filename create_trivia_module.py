#!/usr/bin/env python3
"""Script to extract trivia methods and create trivia.py module"""

# Read the source file
with open('Live/bot/database_module.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find trivia section boundaries
start = content.find('def normalize_trivia_answer')
end_marker = 'def cleanup_hanging_trivia_sessions'
end = content.find(end_marker)
# Find the end of cleanup_hanging_trivia_sessions method
end += content[end:].find('return {"error": str(e), "cleaned_sessions": 0}') + 60

trivia_section = content[start:end]

# Create the trivia.py module
module_content = '''"""
Database Trivia Module - Trivia System

This module handles:
- Trivia question management (add, get, update, reset)
- Trivia session lifecycle (create, start, submit answers, complete)
- Answer evaluation with fuzzy matching
- Dynamic question calculations
- Trivia statistics and leaderboards
- Question pool management
"""

import json
import logging
import re
import time
import difflib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, cast
from zoneinfo import ZoneInfo
from psycopg2.extras import RealDictRow

logger = logging.getLogger(__name__)


class TriviaDatabase:
    """
    Handles all trivia-related database operations.
    
    This class manages the complete trivia system including questions,
    sessions, answers, evaluation logic, and statistics tracking.
    """

    def __init__(self, db_manager):
        """
        Initialize trivia database handler.
        
        Args:
            db_manager: DatabaseManager instance for connection access
        """
        self.db = db_manager

    ''' + trivia_section + '''

# Export
__all__ = ['TriviaDatabase']
'''

# Write the module
with open('Live/bot/database/trivia.py', 'w', encoding='utf-8') as f:
    f.write(module_content)

print("✅ Created Live/bot/database/trivia.py")
print(f"📊 Total size: {len(module_content):,} characters")
print(f"📊 Methods: ~33 trivia methods")
