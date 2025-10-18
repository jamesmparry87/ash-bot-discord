-- Migration: Add youtube_views and last_youtube_sync columns
-- Date: 2025-10-18
-- Purpose: Support YouTube view tracking and sync timestamps

-- Add youtube_views column if it doesn't exist
ALTER TABLE played_games 
ADD COLUMN IF NOT EXISTS youtube_views INTEGER DEFAULT 0;

-- Add last_youtube_sync column if it doesn't exist
ALTER TABLE played_games 
ADD COLUMN IF NOT EXISTS last_youtube_sync TIMESTAMP;

-- Add index for better query performance
CREATE INDEX IF NOT EXISTS idx_played_games_youtube_views 
ON played_games(youtube_views DESC);

-- Verify the columns were added
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'played_games' 
        AND column_name = 'youtube_views'
    ) THEN
        RAISE NOTICE '✅ youtube_views column added successfully';
    ELSE
        RAISE EXCEPTION '❌ Failed to add youtube_views column';
    END IF;
    
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'played_games' 
        AND column_name = 'last_youtube_sync'
    ) THEN
        RAISE NOTICE '✅ last_youtube_sync column added successfully';
    ELSE
        RAISE EXCEPTION '❌ Failed to add last_youtube_sync column';
    END IF;
END $$;

-- Show summary
SELECT 
    COUNT(*) as total_games,
    COUNT(CASE WHEN youtube_views > 0 THEN 1 END) as games_with_views
FROM played_games;
