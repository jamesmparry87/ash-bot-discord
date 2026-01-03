# IGDB Enrichment Deployment Guide

## Overview
This guide provides step-by-step instructions for deploying the IGDB integration features and performing one-time bulk enrichment of existing game data.

## What Was Implemented

### 1. Automatic IGDB Integration in `!syncgames full`
- Every new game synced from YouTube/Twitch automatically queries IGDB
- Enriches missing fields: genre, release_year, series_name, alternative_names
- Cleans series names (removes "(Completed)" markers)
- Standardizes all genres to predefined list
- **Only applies to NEW content after deployment**

### 2. New Command: `!enrichallgames`
- One-time bulk enrichment of ALL existing games in database
- Processes ~200 games with IGDB validation
- Rate-limited to 4 seconds per game (prevents API throttling)
- Estimated runtime: ~13-15 minutes for 200 games
- Provides real-time progress updates every 10 games

## Pre-Deployment Checklist

Before deploying these changes, verify:

- [ ] IGDB API credentials are configured in environment variables
- [ ] Database backup has been taken (recommended for safety)
- [ ] Bot is not currently running scheduled tasks
- [ ] You have ~20 minutes available for the enrichment process

## Deployment Steps

### Step 1: Deploy Code Changes

**Action:** Merge and deploy the changes to production

**Files Modified:**
- `Live/bot/config.py` - Added STANDARD_GENRES mapping
- `Live/bot/tasks/scheduled.py` - Enhanced sync with IGDB integration
- `Live/bot/commands/games.py` - Added `!enrichallgames` command

**Commands:**
```bash
# From your deployment environment
git pull origin main
# Or your specific deployment process
```

**Verification:**
- [ ] Bot restarts successfully
- [ ] No error messages in logs
- [ ] Bot responds to `!ashstatus` command

---

### Step 2: Test Sync Functionality (Optional)

**Action:** Test the new sync process on NEW content

**Command:**
```
!syncgames full
```

**Expected Behavior:**
- Syncs content from last 5 years
- Logs show "✅ SYNC: IGDB integration available for data enrichment"
- Each game shows IGDB enrichment attempts in logs
- Series names automatically cleaned
- Genres standardized

**Verification:**
- [ ] Sync completes without errors
- [ ] Check a newly added game with `!gameinfo <game name>`
- [ ] Verify genre is standardized (e.g., "RPG" not "role-playing (rpg)")
- [ ] Verify series name is clean (no "(Completed)" markers)

---

### Step 3: Run One-Time Bulk Enrichment

**⚠️ IMPORTANT:** This is the critical step for cleaning existing data

**Action:** Run the bulk enrichment command

**Command:**
```
!enrichallgames
```

**What Happens:**
1. Command analyzes database (~1 second)
2. Reports total games found
3. Processes each game sequentially:
   - Queries IGDB for metadata
   - Cleans series name
   - Standardizes genre
   - Updates database if changes found
4. Progress updates every 10 games
5. Final comprehensive summary

**Expected Timeline:**
- **Initial scan:** <1 second
- **Processing:** ~4 seconds per game
- **200 games:** ~13 minutes
- **Progress updates:** Every 40 seconds

**Watch For:**
- Progress updates appearing every ~40 seconds
- No critical errors in bot logs
- Percentage completion increasing steadily

**Verification During Process:**
- [ ] Initial message shows correct game count
- [ ] Progress updates appear regularly
- [ ] No error spikes in bot logs
- [ ] Discord connection remains stable

---

### Step 4: Review Enrichment Results

**Action:** Check the final summary statistics

**What to Look For:**
```
✅ Bulk Enrichment Complete!

Statistics:
• Total games processed: 200
• Games enriched: 150 (example)
• IGDB matches found: 180 (example)
• Series names cleaned: 45 (example)
• Genres standardized: 120 (example)
• Alternative names added: 90 (example)
• Errors encountered: 5 (should be low)
• Skipped (missing data): 0 (should be 0)
```

**Good Indicators:**
- ✅ Errors encountered: <10
- ✅ Skipped: 0
- ✅ IGDB matches: >80% of total games
- ✅ Games enriched: >70% of total games

**Problem Indicators:**
- ❌ Errors encountered: >20
- ❌ Skipped: >10
- ❌ IGDB matches: <50% of total games

**Verification:**
- [ ] Error count is acceptable (<10)
- [ ] Most games were enriched
- [ ] IGDB match rate is high

---

### Step 5: Spot Check Sample Games

**Action:** Verify enrichment worked on specific games

**Commands:**
```
!gameinfo Hollow Knight
!gameinfo Dark Souls
!gameinfo The Last of Us
```

**What to Check:**
- [ ] **Series name** is clean (no "(Completed)" markers)
- [ ] **Genre** is standardized (e.g., "RPG", "Action", not lowercase variants)
- [ ] **Release year** is populated (if it wasn't before)
- [ ] **Alternative names** includes IGDB variants (if applicable)

**Example Before/After:**

**Before:**
```
Series: Dark Souls (Completed)
Genre: role-playing (rpg)
Release Year: [blank]
Alternative Names: [none]
```

**After:**
```
Series: Dark Souls
Genre: RPG
Release Year: 2011
Alternative Names: Dark Souls: Prepare to Die Edition, ダークソウル
```

---

### Step 6: Run Deduplication (Recommended)

**Action:** Clean up any duplicate entries that may exist

**Command:**
```
!deduplicategames
```

**Expected Behavior:**
- Analyzes database for duplicates
- Merges duplicate entries if found
- Reports number merged

**Verification:**
- [ ] Command completes successfully
- [ ] Check if any duplicates were found and merged
- [ ] Run `!listplayedgames` to verify clean list

---

## Post-Deployment Maintenance

### Future Syncs
After this one-time enrichment, future syncs will be automatic:

**Regular Sync (weekly/as needed):**
```
!syncgames
```
- Syncs only NEW content
- Automatically enriches with IGDB
- No manual enrichment needed

**Full Resync (if needed):**
```
!syncgames full
```
- Re-scans all content from last 5 years
- Useful if YouTube/Twitch data changed
- Automatically enriches all games found

### Do NOT Run `!enrichallgames` Again
After the initial bulk enrichment, you don't need to run this command again unless:
- You manually add many games without IGDB data
- You discover data quality issues requiring re-enrichment
- You reset/restore the database from an old backup

---

## Troubleshooting

### Issue: IGDB API Rate Limiting
**Symptoms:** Many "IGDB error" messages in logs
**Solution:** The 4-second delay should prevent this. If it occurs, wait 1 hour and retry.

### Issue: High Error Count (>20)
**Symptoms:** Many games showing errors in enrichment
**Solution:** 
1. Check specific error messages in logs
2. Verify IGDB API credentials are valid
3. Check if certain game names are causing issues
4. Re-run `!enrichallgames` - it's safe to run multiple times

### Issue: Bot Disconnects During Enrichment
**Symptoms:** Bot goes offline mid-enrichment
**Solution:**
1. Check bot hosting platform status
2. Restart bot
3. Re-run `!enrichallgames` - it will skip already-enriched games

### Issue: Progress Updates Stop
**Symptoms:** No Discord messages for >2 minutes
**Solution:**
1. Check bot logs - it may still be processing
2. IGDB queries can occasionally be slow
3. Wait up to 5 minutes before assuming failure
4. If truly stuck, restart bot and re-run command

---

## Summary: Command Execution Order

### First-Time Deployment (One-Time):
```
1. Deploy code changes
2. Verify bot restarts: !ashstatus
3. Run bulk enrichment: !enrichallgames
4. Wait ~13-15 minutes
5. Review final statistics
6. Spot check: !gameinfo <game>
7. Run deduplication: !deduplicategames
```

### Ongoing Maintenance (Weekly/As Needed):
```
1. Regular sync: !syncgames
   OR
2. Full resync: !syncgames full
```

### Never Run Again (Unless Necessary):
```
!enrichallgames (one-time only)
```

---

## Quick Reference Card

| Command | When to Use | Frequency |
|---------|-------------|-----------|
| `!syncgames` | Sync new content | Weekly or as needed |
| `!syncgames full` | Full rescan (5 years) | Monthly or when data issues suspected |
| `!enrichallgames` | **ONE-TIME ONLY** | After deployment, then never again |
| `!deduplicategames` | Clean duplicates | After enrichment, or when suspected |
| `!gameinfo <name>` | Check specific game | Anytime for verification |

---

## Success Criteria

After completing all steps, you should have:

✅ All existing games enriched with IGDB data  
✅ Series names cleaned (no completion markers)  
✅ Genres standardized to predefined list  
✅ Missing metadata populated  
✅ Alternative names added from IGDB  
✅ Future syncs automatically enriching new content  
✅ No manual enrichment needed going forward  

**Deployment Status: Complete** ✅
