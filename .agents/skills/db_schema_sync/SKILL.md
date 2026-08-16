---
name: db_schema_sync
description: Safely add and sync new columns or data types to the PostgreSQL database schema.
---
# Database Schema Synchronizer

When asked to add a new column, track new metadata, or alter the schema:

1. **Database Schema Setup:**
   - Open `bot/database/games.py` and add the `ALTER TABLE` execution block inside the database initialization function.
   - Add the new parameter (e.g. `youtube_playlist_url: Optional[str] = None`) to `PLAYED_GAMES_COLUMNS` and function signatures.

2. **Upsert Logic Injection:**
   - Carefully trace the logic inside `bulk_import_played_games`.
   - Ensure the new column is handled during the duplicate merge resolution phase (e.g. prioritize preserving existing non-null data).
   - Ensure the new column is correctly added to the `INSERT INTO` and `ON CONFLICT DO UPDATE` blocks in the SQL strings.

3. **Validation:**
   - Modify or create a corresponding test in `test_database.py` that verifies the new schema parameter can be written and read without triggering a Postgres mapping error.
