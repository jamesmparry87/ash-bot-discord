# Played Games Database - Comprehensive Data Quality Fix Plan

**Date:** December 6, 2025  
**Status:** Planning Complete - Ready for Implementation  
**Severity:** High - Affects Monday morning summaries, trivia questions, and database integrity  
**Scope:** Both YouTube AND Twitch data quality issues

---

## Executive Summary

The played games database has significant data quality issues affecting **BOTH YouTube and Twitch entries**:

### Critical Issues Affecting All Sources:
1. **Alternative names** - Mixed languages, untidy syntax, nested arrays
2. **Missing timestamps** - `last_youtube_sync` never populated for ANY entry
3. **Poor organization** - Entries not grouped by series alphabetically/chronologically
4. **IGDB integration gaps** - Not used consistently across YouTube and Twitch sync

### Twitch-Specific Issues:
1. Inaccurate game name extraction
2. VOD URLs never stored
3. Missing engagement metrics (views, watch time)
4. Multi-game stream handling

### YouTube-Specific Issues:
1. Timestamp not updated after sync
2. Alternative names from YouTube sync also have language issues

**Impact:** Incorrect trivia answers, skewed statistics in Monday summaries, missing historical data, poor database maintainability.

---

## Identified Issues

### Critical Issues (Immediate Fix Required)

#### 1. **Twitch Game Name Extraction Failures**
- **Example:** "Certified Zombie Pest Control Specialist - Zombie Army 4 (day7)" → extracted as "Certified Zombie Pest Control Specialist" (WRONG)
- **Root Cause:** Monday sync uses basic `extract_game_from_twitch()` instead of smart extraction
- **Impact:** Wrong game names → wrong database entries → incorrect trivia → bad statistics

#### 2. **IGDB Integration Not Used in Monday Sync**
- **Root Cause:** `perform_full_content_sync()` doesn't call `smart_extract_with_validation()`
- **Impact:** No IGDB validation → no genre/release year → no alternative names → poor data quality

#### 3. **Twitch VOD URLs Never Stored**
- **Root Cause:** Monday sync creates/updates games but never populates `twitch_vod_urls` column
- **Impact:** Column exists but stays empty → no historical record → statistics only reflect 3-month VOD window

#### 4. **No Twitch Engagement Metrics**
- **Root Cause:** Missing database columns for Twitch-specific metrics
- **Impact:** Monday summaries can't report Twitch views/watch time → incomplete engagement reporting

### High Priority Issues

#### 5. **Alternative Names Data Quality**
- **Current:** Mixed languages and messy syntax: `{"Halo CE HD","Halo: El Combate ha Evolucionado","Halo HD"}`
- **Root Cause:** IGDB returns all languages; no English-only filtering
- **Impact:** Confusing database entries, harder for users to search

#### 6. **Missing Metadata Across Board**
- No release year for Twitch entries
- No genre for Twitch entries
- No series name inference
- Completion status always "unknown" for Twitch
- `last_youtube_sync` never populated

#### 7. **Title Parsing Priority Issues**
- **Current:** Tries "before dash" first, then "after dash"
- **Problem:** For "Description - Game Name (dayX)" format, it picks description
- **Impact:** Consistent extraction failures for this common pattern

### Medium Priority Issues

#### 8. **Multi-Game Stream Handling**
- **Current:** Treats each VOD as single game
- **Problem:** Can't split streams covering multiple games
- **Impact:** Playtime/episodes attributed to wrong game or not tracked

#### 9. **Database Organization**
- **Current:** Entries not grouped by series
- **Problem:** No alphabetical/chronological series organization
- **Impact:** Harder to browse, maintain, and analyze data

#### 10. **Historical Data Loss**
- **Current:** Only reflects 3-month Twitch VOD window
- **Problem:** Older streams not counted in statistics
- **Impact:** Incomplete historical record (e.g., Elden Ring Twitch playtime missing)

---

## Root Cause Analysis

### Technical Root Causes

1. **Wrong Function Called**
   - `scheduled.py` calls `extract_game_from_twitch()` (basic)
   - Should call `smart_extract_with_validation()` (IGDB-validated)

2. **Missing Data Flow**
   ```
   VOD fetched → Game extracted → Database updated
                                   ↓
                                   twitch_vod_urls NEVER SET
   ```

3. **No Language Filtering**
   - IGDB API returns all languages
   - No post-processing to filter English-only

4. **Schema Gaps**
   - Missing: `twitch_views`, `twitch_watch_hours`
   - Unused: `last_youtube_sync` (exists but never updated)

5. **Parsing Priority**
   - Algorithm prioritizes wrong part of title
   - Doesn't adapt to common streaming conventions

---

## Multi-Phase Implementation Plan

### **Phase 1: Foundation Fixes** (IMMEDIATE - Days 1-2)
*Goal: Stop bad data from entering the system*

#### 1.1 IGDB Integration - English-Only Filtering
**File:** `Live/bot/integrations/igdb.py`  
**Changes:**
- Add `filter_english_names()` function
- Filter alternative names to ASCII + Latin Extended-A
- Remove CJK characters (Chinese, Japanese, Korean)
- Update `validate_and_enrich()` to apply filter

**Code Addition:**
```python
def filter_english_names(names: List[str]) -> List[str]:
    """Filter to English-only names (ASCII + common European chars)"""
    import re
    english_names = []
    for name in names:
        # Allow ASCII + common accented characters (é, ñ, ö, etc.)
        if all(ord(c) < 592 for c in name):  # Basic Latin + Latin Extended-A
            # Skip if contains CJK characters
            if not re.match(r'^[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+$', name):
                english_names.append(name)
    return english_names
```

**Testing:**
- Verify "Halo" returns only English names
- Test with known multi-language games

---

#### 1.2 Monday Sync - Use Smart Extraction
**File:** `Live/bot/tasks/scheduled.py`  
**Function:** `perform_full_content_sync()` (around line 1500)  
**Changes:**

**BEFORE:**
```python
for vod in twitch_vods:
    title = vod['title']
    game_name = extract_game_from_twitch(title)  # ❌ Basic extraction
```

**AFTER:**
```python
for vod in twitch_vods:
    title = vod['title']
    
    # Use smart extraction with IGDB validation
    from ..integrations.twitch import smart_extract_with_validation
    extracted_name, confidence = await smart_extract_with_validation(title)
    
    if not extracted_name or confidence < 0.5:
        print(f"⚠️ SYNC: Low confidence ({confidence:.2f}) for '{title}'")
        # Flag for manual review
        continue
    
    print(f"✅ SYNC: Extracted '{extracted_name}' with {confidence:.2f} confidence")
```

**Testing:**
- Test with "Certified Zombie Pest Control Specialist - Zombie Army 4 (day7)"
- Verify it extracts "Zombie Army 4" with high confidence
- Check IGDB enrichment happens

---

#### 1.3 Store VOD URLs During Sync
**File:** `Live/bot/tasks/scheduled.py`  
**Function:** `perform_full_content_sync()` (Twitch processing section)  
**Changes:**

Add after game name extraction:
```python
# Store VOD URL
vod_url = vod.get('url')
if vod_url:
    if existing_game:
        # Get existing VOD URLs (handle both list and text formats)
        existing_vods = existing_game.get('twitch_vod_urls', [])
        if isinstance(existing_vods, str):
            # Parse comma-separated string
            existing_vods = [v.strip() for v in existing_vods.split(',') if v.strip()]
        elif not isinstance(existing_vods, list):
            existing_vods = []
        
        # Add new VOD if not already present
        if vod_url not in existing_vods:
            existing_vods.append(vod_url)
            # Keep only last 10 VODs to avoid bloat
            existing_vods = existing_vods[-10:]
        
        update_params['twitch_vod_urls'] = existing_vods
    else:
        # New game - start with first VOD
        game_data['twitch_vod_urls'] = [vod_url]
```

**Testing:**
- Verify VODs appear in database after sync
- Test with existing game (should append)
- Test with new game (should create list)

---

#### 1.4 Database Schema - Add Twitch Metrics
**File:** `Live/bot/database_module.py`  
**Function:** `init_database()` (around line 200)  
**Changes:**

Add after existing `played_games` table setup:
```python
# Add Twitch engagement tracking columns
cur.execute("""
    ALTER TABLE played_games
    ADD COLUMN IF NOT EXISTS twitch_views INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS twitch_watch_hours FLOAT DEFAULT 0.0
""")
print("✅ Added Twitch engagement tracking columns")
```

**Note:** Twitch API may not provide view counts - need to verify what data is available.

**Testing:**
- Run bot to trigger migration
- Verify columns exist: `SELECT column_name FROM information_schema.columns WHERE table_name='played_games'`

---

#### 1.5 Fix Timestamp Updates
**File:** `Live/bot/tasks/scheduled.py`  
**Function:** `perform_full_content_sync()`  
**Changes:**

Verify this code exists and works (should be near end of function):
```python
# Update last sync timestamp
try:
    sync_completion_time = datetime.now(ZoneInfo("Europe/London"))
    db.update_last_sync_timestamp(sync_completion_time)
    print(f"✅ SYNC: Updated last sync timestamp to {sync_completion_time.strftime('%Y-%m-%d %H:%M:%S')}")
except Exception as timestamp_error:
    print(f"⚠️ SYNC: Failed to update last sync timestamp: {timestamp_error}")
```

If missing, add it. Also ensure `last_youtube_sync` is set per-game during updates.

**Testing:**
- Run sync manually
- Check `last_youtube_sync` column has timestamps

---

### **Phase 2: Enhanced Extraction** (PRIORITY - Days 3-4)
*Goal: Handle edge cases and improve accuracy*

#### 2.1 Title Parsing - Prioritize "After Dash"
**File:** `Live/bot/integrations/twitch.py`  
**Function:** `smart_extract_with_validation()` (around line 50)  
**Changes:**

Reorder Strategy 2 to try "after dash" FIRST:

**CURRENT ORDER:**
1. Try part BEFORE dash
2. Try part AFTER dash

**NEW ORDER:**
1. Try part AFTER dash (often the game name)
2. Try part BEFORE dash (fallback)

**Rationale:** Stream titles often follow "Description - Game Name (day X)" format.

**Code Change:**
```python
# Strategy 2: Try extracting part AFTER the dash first (for "Description - Game Name" format)
if ' - ' in title or ' | ' in title:
    separator = ' - ' if ' - ' in title else ' | '
    parts = title.split(separator)
    
    # NEW: Try AFTER dash FIRST
    if len(parts) > 1:
        after_dash = parts[1].strip()
        # Remove day/episode markers
        after_dash = re.sub(r'\s*\((?:day|part|episode|ep)\s+\d+[^)]*\)', '', after_dash, flags=re.IGNORECASE)
        after_dash = cleanup_game_name(after_dash)
        
        if len(after_dash) >= 3 and not is_generic_term(after_dash):
            igdb_result = await igdb.validate_and_enrich(after_dash)
            confidence = igdb_result.get('confidence', 0.0)
            print(f"  Trying part after dash: '{after_dash}' → confidence: {confidence:.2f}")
            
            if confidence >= 0.8:  # High confidence threshold
                return after_dash, confidence
            
            # Store for comparison
            if confidence > best_confidence:
                best_name = after_dash
                best_confidence = confidence
    
    # THEN try before dash as fallback
    if len(parts) > 1:
        before_dash = parts[0].strip()
        # ... existing logic ...
```

**Testing:**
- Test "Certified Zombie Pest Control Specialist - Zombie Army 4 (day7)"
- Verify it tries "Zombie Army 4" first and finds high confidence
- Test "Zombie Army 4 - Stream Description" to ensure it still works

---

#### 2.2 Multi-Game Stream Detection
**File:** `Live/bot/tasks/scheduled.py`  
**Function:** `perform_full_content_sync()` (new helper function)  
**Changes:**

Add helper function:
```python
def detect_multiple_games_in_title(title: str) -> List[str]:
    """
    Detect if a stream title mentions multiple games.
    Returns list of potential game names.
    """
    import re
    
    # Common patterns:
    # "Game A + Game B"
    # "Game A & Game B"
    # "Game A and Game B"
    # "Game A, Game B, Game C"
    
    potential_games = []
    
    # Split on common separators
    separators = [' + ', ' & ', ' and ', ', ']
    for sep in separators:
        if sep in title:
            parts = title.split(sep)
            if len(parts) >= 2:
                potential_games = [p.strip() for p in parts]
                break
    
    return potential_games
```

Then in sync loop:
```python
# Check for multi-game streams
potential_games = detect_multiple_games_in_title(title)
if len(potential_games) > 1:
    print(f"🔍 SYNC: Multi-game stream detected: {potential_games}")
    # Process each game separately
    for game_name in potential_games:
        extracted_name, confidence = await smart_extract_with_validation(game_name)
        if extracted_name and confidence >= 0.7:
            # Add as separate entry with fractional playtime
            fractional_duration = duration_minutes / len(potential_games)
            # ... process game ...
```

**Testing:**
- Test with "Elden Ring + Dark Souls 3" title
- Verify both games are detected and created
- Check playtime is split appropriately

---

### **Phase 3: Data Cleanup** (MAINTENANCE - Days 5-6)
*Goal: Clean up existing bad data*

#### 3.1 Alternative Names Cleanup Script
**File:** `Live/bot/utils/data_quality.py` (create if needed)  
**Changes:**

Create cleanup function:
```python
def cleanup_alternative_names_format(db):
    """Clean up alternative names to simple comma-separated format"""
    games = db.get_all_played_games()
    
    for game in games:
        alt_names = game.get('alternative_names', [])
        if alt_names:
            # Parse if string
            if isinstance(alt_names, str):
                # Handle nested array syntax
                alt_names = parse_complex_array_syntax(alt_names)
            
            # Filter English-only
            from ..integrations.igdb import filter_english_names
            english_only = filter_english_names(alt_names)
            
            # Deduplicate
            unique_names = list(set(english_only))
            
            # Update database
            db.update_played_game(game['id'], alternative_names=unique_names)
            print(f"✅ Cleaned {game['canonical_name']}: {len(alt_names)} → {len(unique_names)} names")
```

**Testing:**
- Run on test database first
- Verify "Halo" entry is cleaned
- Check no English names are lost

---

#### 3.2 Series Name Organization
**File:** `Live/bot/database_module.py`  
**Changes:**

Add query helper:
```python
def get_games_by_series_organized(self) -> Dict[str, List[Dict[str, Any]]]:
    """Get all games organized by series with chronological sorting"""
    conn = self.get_connection()
    if not conn:
        return {}
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM played_games
                WHERE series_name IS NOT NULL AND series_name != ''
                ORDER BY 
                    series_name ASC,
                    release_year ASC NULLS LAST,
                    canonical_name ASC
            """)
            results = cur.fetchall()
            
            # Group by series
            series_dict = {}
            for row in results:
                game = dict(row)
                series = game['series_name']
                if series not in series_dict:
                    series_dict[series] = []
                series_dict[series].append(game)
            
            return series_dict
    except Exception as e:
        print(f"Error getting organized series: {e}")
        return {}
```

**Testing:**
- Query games by series
- Verify chronological order
- Check alphabetical series sorting

---

### **Phase 4: Validation & Review** (QUALITY - Days 7-8)
*Goal: Ensure quality and catch edge cases*

#### 4.1 Low-Confidence Match Review Workflow
**File:** `Live/bot/handlers/conversation_handler.py`  
**Changes:**

Enhance existing review system:
```python
async def start_game_review_approval(review_data: Dict[str, Any]):
    """Send low-confidence game match for manual review"""
    # Already exists - ensure it's being called from sync
    
    # Enhancement: Add batch review option
    # Instead of one-by-one, allow reviewing multiple at once
```

**Integration Point:**
In `scheduled.py::perform_full_content_sync()`:
```python
if confidence < 0.75 and confidence >= 0.5:
    # Flag for manual review
    await start_game_review_approval({
        'original_title': title,
        'extracted_name': extracted_name,
        'confidence': confidence,
        'source': 'twitch_sync',
        # ... other data
    })
```

**Testing:**
- Generate low-confidence match
- Verify review message sent
- Test approval workflow

---

#### 4.2 Data Quality Validation Tests
**File:** `Live/tests/test_twitch_data_quality.py` (new)  
**Changes:**

Create comprehensive test suite:
```python
import pytest
from bot.integrations.igdb import filter_english_names, validate_and_enrich
from bot.integrations.twitch import smart_extract_with_validation

class TestTwitchDataQuality:
    @pytest.mark.asyncio
    async def test_game_extraction_accuracy(self):
        """Test game name extraction from various title formats"""
        test_cases = [
            ("Certified Zombie... - Zombie Army 4 (day7)", "Zombie Army 4"),
            ("Stream Title - Elden Ring - Part 5", "Elden Ring"),
            ("NEW GAME! Dead Space Remake", "Dead Space"),
        ]
        
        for title, expected in test_cases:
            extracted, confidence = await smart_extract_with_validation(title)
            assert extracted.lower() in expected.lower()
            assert confidence >= 0.7
    
    def test_english_name_filtering(self):
        """Test alternative names are English-only"""
        names = ["Halo", "Halo: El Combate", "ハロー", "Halo CE"]
        filtered = filter_english_names(names)
        assert "Halo" in filtered
        assert "ハロー" not in filtered
    
    @pytest.mark.asyncio
    async def test_igdb_confidence_scoring(self):
        """Test IGDB confidence scores are reasonable"""
        test_games = ["Halo", "Elden Ring", "God of War"]
        for game in test_games:
            result = await validate_and_enrich(game)
            assert result['confidence'] >= 0.9  # Should be high for known games
```

**Testing:**
- Run pytest suite
- Verify all tests pass
- Add more edge cases as discovered

---

### **Phase 5: Historical Backfill** (OPTIONAL - Future)
*Goal: Recover historical data where possible*

#### 5.1 Historical VOD Analysis
**Challenges:**
- Twitch VODs are only stored 3 months
- No API access to older data
- Manual records may not exist

**Possible Approaches:**
1. **YouTube Sync:** Use YouTube videos to backfill Twitch playtime
   - Match YouTube playlists to Twitch content
   - Estimate Twitch hours from YouTube episodes
   
2. **Manual Entry:** Provide admin command to add historical data
   ```
   !addhistoricalgame "Elden Ring" --twitch-hours 40 --notes "Played on Twitch 2023"
   ```

3. **Archive Mining:** If stream archives exist elsewhere, parse those

**Status:** Deprioritized - accept 3-month limitation as technical constraint.

---

## Testing Strategy

### Unit Tests
- IGDB English filtering
- Title parsing logic
- Multi-game detection
- Confidence scoring

### Integration Tests
- Full Monday sync with test VODs
- Database updates verified
- VOD URL storage confirmed
- Timestamp updates working

### Manual Testing
- Run sync with real Twitch account
- Verify data quality improvements
- Check Monday summary accuracy
- Test trivia questions with new data

### Regression Testing
- Ensure YouTube sync still works
- Verify existing games not broken
- Check alternative names preserved (where English)

---

## Success Metrics

### Quantitative Metrics
1. **Extraction Accuracy:** >90% of Twitch VODs extract correct game name
2. **IGDB Match Rate:** >80% of extractions have IGDB confidence >0.75
3. **Data Completeness:**
   - 100% of Twitch games have VOD URLs
   - >80% have genre
   - >70% have release year
4. **Alternative Names Quality:** 0% non-English names in new entries

### Qualitative Metrics
1. Monday summaries report accurate Twitch statistics
2. Trivia questions based on Twitch data are correct
3. Database is human-readable and maintainable
4. Manual intervention required <5% of time

---

## Rollout Plan

### Pre-Rollout
- [x] Complete planning document
- [ ] Review with team
- [ ] Set up test environment
- [ ] Backup production database

### Phase 1 Rollout (Days 1-2)
- [ ] Implement IGDB English filtering
- [ ] Update Monday sync to use smart extraction
- [ ] Add VOD URL storage
- [ ] Add database columns
- [ ] Test on staging
- [ ] Deploy to production

### Phase 2 Rollout (Days 3-4)
- [ ] Implement enhanced title parsing
- [ ] Add multi-game detection
- [ ] Test edge cases
- [ ] Deploy to production

### Phase 3 Rollout (Days 5-6)
- [ ] Run cleanup scripts
- [ ] Organize database entries
- [ ] Verify data quality
- [ ] Document changes

### Phase 4 Rollout (Days 7-8)
- [ ] Deploy review workflow enhancements
- [ ] Run validation tests
- [ ] Monitor for issues
- [ ] Iterate on feedback

### Post-Rollout
- [ ] Monitor first Monday sync
- [ ] Validate data quality metrics
- [ ] Document any issues
- [ ] Plan Phase 5 if needed

---

## Risk Assessment

### High Risk
- **Breaking Monday Sync:** If extraction fails completely
  - *Mitigation:* Keep fallback to basic extraction
  - *Testing:* Thorough integration tests

### Medium Risk
- **IGDB Rate Limiting:** Exceeding 4 req/sec during large sync
  - *Mitigation:* Existing rate limiting in `igdb.py`
  - *Monitoring:* Add rate limit logging

### Low Risk
- **Data Loss:** Cleanup scripts removing valid data
  - *Mitigation:* Backup before cleanup
  - *Testing:* Test on copy first

---

## Maintenance Plan

### Weekly
- Review low-confidence matches flagged for manual review
- Check data quality metrics dashboard (if created)

### Monthly
- Run data quality validation tests
- Review and update extraction patterns as needed
- Clean up old VOD URLs (keep only last 10)

### Quarterly
- Evaluate need for historical backfill
- Review IGDB alternative names for quality
- Update title parsing patterns based on trends

---

## Dependencies

### External APIs
- **IGDB API:** Requires Twitch OAuth credentials
- **Twitch API:** For VOD fetching

### Environment Variables Required
```bash
TWITCH_CLIENT_ID=<required>
TWITCH_CLIENT_SECRET=<required>
IGDB_CLIENT_ID=<optional, falls back to TWITCH_CLIENT_ID>
IGDB_CLIENT_SECRET=<optional, falls back to TWITCH_CLIENT_SECRET>
```

### Database Schema
- PostgreSQL with `played_games` table
- Required columns exist (verified in Phase 1)

---

## Implementation Checklist

### Phase 1: Foundation Fixes
- [ ] 1.1: IGDB English-only filtering
- [ ] 1.2: Monday sync smart extraction
- [ ] 1.3: VOD URL storage
- [ ] 1.4: Database schema additions
- [ ] 1.5: Timestamp fixes

### Phase 2: Enhanced Extraction
- [ ] 2.1: Title parsing priority
- [ ] 2.2: Multi-game detection

### Phase 3: Data Cleanup
- [ ] 3.1: Alternative names cleanup
- [ ] 3.2: Series organization

### Phase 4: Validation
- [ ] 4.1: Review workflow
- [ ] 4.2: Quality tests

### Phase 5: Historical Backfill
- [ ] 5.1: Evaluate feasibility
- [ ] 5.2: Implement if needed

---

## Appendix A: Code File Changes Summary

| File | Changes | Priority |
|------|---------|----------|
| `Live/bot/integrations/igdb.py` | Add English filtering | P1 |
| `Live/bot/integrations/twitch.py` | Fix title parsing priority | P2 |
| `Live/bot/tasks/scheduled.py` | Use smart extraction, store VODs | P1 |
| `Live/bot/database_module.py` | Add Twitch metrics columns | P1 |
| `Live/bot/utils/data_quality.py` | Cleanup scripts | P3 |
| `Live/bot/handlers/conversation_handler.py` | Enhanced review | P4 |
| `Live/tests/test_twitch_data_quality.py` | New test suite | P4 |

---

## Appendix B: Database Schema Changes

```sql
-- Add Twitch engagement tracking
ALTER TABLE played_games
ADD COLUMN IF NOT EXISTS twitch_views INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS twitch_watch_hours FLOAT DEFAULT 0.0;

-- Existing columns to utilize:
-- - twitch_vod_urls (TEXT) - currently empty, will be populated
-- - last_youtube_sync (TIMESTAMP) - currently NULL, will be updated
-- - alternative_names (TEXT) - currently messy, will be cleaned
```

---

## Appendix C: Example Title Parsing

### Before Fix
```
Input:  "Certified Zombie Pest Control Specialist - Zombie Army 4 (day7)"
Output: "Certified Zombie Pest Control Specialist" ❌
IGDB:   No match (confidence: 0.2)
Result: Bad database entry
```

### After Fix
```
Input:  "Certified Zombie Pest Control Specialist - Zombie Army 4 (day7)"
Step 1: Split on " - " → ["Certified...", "Zombie Army 4 (day7)"]
Step 2: Try "Zombie Army 4" (after cleaning)
Step 3: IGDB validation → confidence: 0.95 ✅
Output: "Zombie Army 4"
Result: Correct database entry with full metadata
```

---

## Document Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2025-12-06 | 1.0 | Initial comprehensive plan created |

---

**Next Steps:** Begin Phase 1 implementation with IGDB English filtering and Monday sync fixes.
