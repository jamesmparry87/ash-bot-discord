-- Migration: Clean up bad sync data from failed extraction
-- Date: 2025-10-18
-- Purpose: Remove duplicate/malformed game entries created by broken extraction function

-- BACKUP RECOMMENDATION: Always backup before running this cleanup!
-- pg_dump -h <host> -U <user> -d <database> -t played_games > backup_played_games.sql

-- Step 1: Show what will be deleted (REVIEW FIRST)
SELECT 
    'PREVIEW' as action,
    id,
    canonical_name,
    total_episodes,
    created_at,
    notes
FROM played_games
WHERE notes LIKE '%Auto-discovered from content sync%'
AND created_at >= '2025-10-18'::date
ORDER BY created_at DESC;

-- Step 2: Count affected records
SELECT 
    COUNT(*) as records_to_delete,
    MIN(created_at) as earliest,
    MAX(created_at) as latest
FROM played_games
WHERE notes LIKE '%Auto-discovered from content sync%'
AND created_at >= '2025-10-18'::date;

-- Step 3: Delete bad sync data (UNCOMMENT TO EXECUTE)
-- WARNING: This will permanently delete the malformed entries
/*
BEGIN;

DELETE FROM played_games
WHERE notes LIKE '%Auto-discovered from content sync%'
AND created_at >= '2025-10-18'::date;

-- Show how many were deleted
SELECT 'DELETED' as status, COUNT(*) as count FROM played_games WHERE FALSE;

COMMIT;
*/

-- Step 4: After cleanup, verify database state
SELECT 
    COUNT(*) as total_games,
    COUNT(CASE WHEN notes LIKE '%Auto-discovered%' THEN 1 END) as auto_discovered,
    COUNT(CASE WHEN notes LIKE '%Auto-imported%' THEN 1 END) as auto_imported,
    COUNT(CASE WHEN notes NOT LIKE '%Auto-%' THEN 1 END) as manually_added
FROM played_games;

-- Step 5: Show sample of remaining games
SELECT 
    id,
    canonical_name,
    total_episodes,
    total_playtime_minutes,
    LEFT(notes, 50) as notes_preview
FROM played_games
ORDER BY created_at DESC
LIMIT 10;
