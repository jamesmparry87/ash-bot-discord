# Content Sync System Fixes - October 2025

## 🚨 Issues Identified

### 1. **Missing Database Columns**
- `youtube_views` column missing from `played_games` table
- `last_youtube_sync` timestamp column missing
- **Impact:** Database INSERT errors, sync failures

### 2. **Broken Game Name Extraction**
- `extract_game_name_from_title()` function not actually extracting game names
- Returning full video titles instead of game names
- **Impact:** 989 "games" created (one per video instead of grouping by game)

### 3. **Massive Data Duplication**
- Each video created as separate "game" entry
- Examples:
  - `"First Time Playing: Resident Evil 8 Village Road to Resi 9"` → Should be `"Resident Evil 8 Village"`
  - `"*DROPS* Samurai School Dropout - Ghost of Yotei Thanks @playstation"` → Should be `"Ghost of Yotei"`

## ✅ Fixes Applied

### Fix 1: Enhanced Game Name Extraction (`youtube.py`)
**New Logic:**
```python
# Removes prefixes: *DROPS*, First Time Playing:, etc.
# Removes suffixes: Road to X, Thanks @sponsor, #ad, etc.
# Preserves game subtitles: "Resident Evil 4: Separate Ways"
# Validates output: rejects generic terms, requires substance
```

**Test Cases:**
| Input | Output |
|-------|--------|
| `"First Time Playing: Resident Evil 8 Village Road to Resi 9"` | `"Resident Evil 8 Village"` |
| `"*DROPS* Ghost of Yotei Thanks @playstation #ad"` | `"Ghost of Yotei"` |
| `"Horror + Monsters = Cronos: A New Dawn Thanks @blooberteam"` | `"Cronos: A New Dawn"` |

### Fix 2: Database Schema Update
- Added `youtube_views INTEGER DEFAULT 0`
- Added `last_youtube_sync TIMESTAMP`
- Added performance index on `youtube_views`

### Fix 3: Data Cleanup Scripts
- Preview script to see what will be deleted
- Safe deletion with backup recommendation
- Verification queries

## 📋 Implementation Steps

### Step 1: Apply Database Migration (Required)

```bash
# Connect to your database
psql -h <host> -U <user> -d <database>

# Run the migration
\i Live/database_migrations/001_add_youtube_columns.sql
```

**Expected Output:**
```
NOTICE: ✅ youtube_views column added successfully
NOTICE: ✅ last_youtube_sync column added successfully
```

### Step 2: Review Bad Data (Before Cleanup)

```bash
# Preview what will be deleted
psql -h <host> -U <user> -d <database> -f Live/database_migrations/002_cleanup_bad_sync_data.sql
```

This shows:
- How many records will be deleted
- Preview of records to be deleted
- Date range of bad data

### Step 3: Clean Up Bad Data (Optional but Recommended)

**⚠️ IMPORTANT: Backup first!**

```bash
# Backup the table
pg_dump -h <host> -U <user> -d <database> -t played_games > backup_played_games_$(date +%Y%m%d).sql
```

Then uncomment the DELETE section in `002_cleanup_bad_sync_data.sql` and run:

```sql
BEGIN;

DELETE FROM played_games
WHERE notes LIKE '%Auto-discovered from content sync%'
AND created_at >= '2025-10-18'::date;

COMMIT;
```

### Step 4: Verify Fixes

The extraction function is already fixed in the code. Test it:

```python
# In Python console or bot
from Live.bot.integrations.youtube import extract_game_name_from_title

# Test cases
test_titles = [
    "First Time Playing: Resident Evil 8 Village Road to Resi 9",
    "*DROPS* Samurai School Dropout - Ghost of Yotei Thanks @playstation #ad/gift",
    "Horror + Monsters + Space = Cronos: A New Dawn Thanks @blooberteam"
]

for title in test_titles:
    result = extract_game_name_from_title(title)
    print(f"{title}\n  → {result}\n")
```

**Expected Output:**
```
First Time Playing: Resident Evil 8 Village Road to Resi 9
  → Resident Evil 8 Village

*DROPS* Samurai School Dropout - Ghost of Yotei Thanks @playstation #ad/gift
  → Ghost of Yotei

Horror + Monsters + Space = Cronos: A New Dawn Thanks @blooberteam
  → Cronos: A New Dawn
```

### Step 5: Re-run Sync

After applying all fixes:

```
# In Discord
!syncgames full
```

**Expected Behavior:**
- Properly extracts game names
- Groups episodes by game
- No database errors
- Reports like: "Added 15 new games, updated 30 existing games"

## 🔍 Verification Checklist

- [ ] Database columns added (`youtube_views`, `last_youtube_sync`)
- [ ] Bad sync data cleaned up
- [ ] Extraction function tested with sample titles
- [ ] Re-run sync completes without errors
- [ ] Games properly grouped (not 989+ individual entries)
- [ ] Deduplication runs after sync
- [ ] Database shows reasonable game count

## 📊 Before/After Comparison

### Before Fixes:
```
✅ SYNC: Added new game 'First Time Playing: Resident Evil 8 Village Road to Resi 9'
✅ SYNC: Added new game 'First Time Playing: Resident Evil 8 Village End Game?'
✅ SYNC: Added new game '*DROPS* Samurai School Dropout - Ghost of Yotei'
Total: 989 "games" created
```

### After Fixes:
```
✅ SYNC: Added new game 'Resident Evil 8 Village' with 1560 mins.
✅ SYNC: Updated 'Resident Evil 8 Village' with 275 mins. (7 episodes total)
✅ SYNC: Added new game 'Ghost of Yotei' with 281 mins.
Total: 15 games properly grouped
```

## 🛡️ Safety Features

1. **SQL Migration Uses `IF NOT EXISTS`**
   - Safe to run multiple times
   - Won't break if columns already exist

2. **Cleanup Script Has Preview Mode**
   - Shows what will be deleted before executing
   - Requires manual uncomment to execute DELETE

3. **Backup Reminders**
   - Scripts remind to backup before cleanup
   - Provides exact backup commands

4. **Validation Queries**
   - Verify columns were added
   - Show counts before/after cleanup
   - Sample remaining data

## 📝 Notes

- The extraction function now handles complex patterns intelligently
- Deduplication runs automatically after each sync
- The sync system is safe to run on existing data (won't corrupt good entries)
- YouTube views are now tracked for analytics

## 🆘 Troubleshooting

**Q: Still seeing database errors after migration?**
- Verify columns were added: `\d played_games` in psql
- Check for typos in column names
- Ensure you have ALTER TABLE permissions

**Q: Extraction still returning full titles?**
- Restart the bot to reload the code
- Test extraction function manually (see Step 4)
- Check that youtube.py was actually updated

**Q: Worried about deleting data?**
- Run preview query first (Step 2)
- Always backup before cleanup (provided command)
- Cleanup only targets auto-discovered entries from today

**Q: How do I restore if something goes wrong?**
```bash
# Restore from backup
psql -h <host> -U <user> -d <database> < backup_played_games_YYYYMMDD.sql
```

## 📞 Support

If issues persist after applying all fixes:
1. Check bot logs for specific error messages
2. Verify all files were saved correctly
3. Confirm database migration completed successfully
4. Test extraction function manually
