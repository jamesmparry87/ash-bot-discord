"""
Initialize Sync Staging Table

Run this script once to create the sync_staging table in the database.
This table is used for pre-approval workflow before committing games.
"""

import os
import sys

from bot.database import get_database

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def init_staging_table():
    """Initialize the sync_staging table"""
    print("[*] Initializing sync staging table...")

    db = get_database()
    if not db:
        print("[FAIL] Failed to connect to database")
        return False

    # Create the staging table
    success = db.games.create_staging_table_if_not_exists()

    if success:
        print("[OK] Sync staging table initialized successfully")
        print("\nTable structure:")
        print("  - id: Serial primary key")
        print("  - sync_session_id: UUID for grouping sync sessions")
        print("  - game_data: JSONB with complete game data")
        print("  - action_type: 'add' or 'update'")
        print("  - confidence_score: Extraction confidence (0.0-1.0)")
        print("  - source_platform: 'youtube' or 'twitch'")
        print("  - reviewed: Boolean flag for manual review status")
        print("  - approved: Boolean flag for approval status")
        print("  - edited: Boolean flag if data was manually corrected")
        print("\nIndexes created:")
        print("  - idx_sync_staging_session (sync_session_id)")
        print("  - idx_sync_staging_reviewed (sync_session_id, reviewed)")
        return True
    else:
        print("[FAIL] Failed to create sync staging table")
        return False


if __name__ == "__main__":
    init_staging_table()
