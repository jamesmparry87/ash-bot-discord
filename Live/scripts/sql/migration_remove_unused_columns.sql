-- Database Quality Improvement: Remove Unused Columns
-- Date: 2025-12-26
-- Purpose: Clean up played_games table by removing unused tracking fields

-- IMPORTANT: Ensure you have a backup before running this migration!
-- Backup location: Live/scripts/backup_played_games_20251226_095844.json

-- Remove unused columns from played_games table
ALTER TABLE played_games 
DROP COLUMN IF EXISTS last_twitch_sync,
DROP COLUMN IF EXISTS twitch_watch_hours,
DROP COLUMN IF EXISTS twitch_views,
DROP COLUMN IF EXISTS igdb_last_validated,
DROP COLUMN IF EXISTS data_confidence,
DROP COLUMN IF EXISTS igdb_id,
DROP COLUMN IF EXISTS last_youtube_sync;

-- Verify the schema after migration
-- Run this to confirm columns were removed:
-- SELECT column_name, data_type 
-- FROM information_schema.columns 
-- WHERE table_name = 'played_games' 
-- ORDER BY ordinal_position;

-- Expected result: These columns should no longer appear in the output
