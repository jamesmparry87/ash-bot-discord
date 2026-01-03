# Data Quality & Consistency Plan

## Current Issues Identified

### 1. Genre Inconsistency ⚠️
**Problem**: Games in same series can have different genres
- No standardized genre list
- Freeform text allows: "Action", "action", "Action RPG", "action-rpg"
- Genre not populated during sync
- No series-level genre inheritance

### 2. Missing Metadata Population
**Problem**: Sync doesn't populate these fields:
- `genre` - Always NULL after sync
- `release_year` - Not extracted from YouTube
- `platform` - Column exists but unused (should be removed)
- `alternative_names` - Not fully populated

### 3. Series Name Normalization
**Problem**: Same series can have multiple names
- "Halo" vs "halo" vs "HALO"
- "The Last of Us" vs "Last of Us"
- No canonical series name validation

### 4. No Data Validation
**Problem**: No quality checks during sync
- Duplicate series names with different spellings
- Invalid completion_status values
- Missing required fields

## Solutions

### Phase 1: Genre Standardization System

#### 1.1 Create Standard Genre List
```python
STANDARD_GENRES = {
    # Primary genres
    'action': 'Action',
    'rpg': 'RPG',
    'strategy': 'Strategy',
    'puzzle': 'Puzzle',
    'horror': 'Horror',
    'survival': 'Survival',
    'platformer': 'Platformer',
    'racing': 'Racing',
    'sports': 'Sports',
    'simulation': 'Simulation',
    'adventure': 'Adventure',
    'shooter': 'Shooter',
    
    # Compound genres (hyphenated)
    'action-rpg': 'Action-RPG',
    'action-adventure': 'Action-Adventure',
    'survival-horror': 'Survival-Horror',
    'turn-based-strategy': 'Turn-Based Strategy',
    'first-person-shooter': 'FPS',
    'third-person-shooter': 'TPS',
    'roguelike': 'Roguelike',
    'metroidvania': 'Metroidvania',
    'souls-like': 'Souls-Like',
}

# Aliases for fuzzy matching
GENRE_ALIASES = {
    'fps': 'FPS',
    'tps': 'TPS',
    'action rpg': 'Action-RPG',
    'actionrpg': 'Action-RPG',
    'arpg': 'Action-RPG',
    'jrpg': 'RPG',
    'western rpg': 'RPG',
    'crpg': 'RPG',
    'hack and slash': 'Action',
    'hack-and-slash': 'Action',
    'beat em up': 'Action',
    'fighting': 'Action',
}
```

#### 1.2 Genre Normalization Function
```python
def normalize_genre(genre_input: str) -> str:
    """Normalize genre to standard format"""
    if not genre_input:
        return None
    
    clean = genre_input.strip().lower()
    
    # Check direct match
    if clean in STANDARD_GENRES:
        return STANDARD_GENRES[clean]
    
    # Check aliases
    if clean in GENRE_ALIASES:
        return GENRE_ALIASES[clean]
    
    # Fuzzy match
    import difflib
    matches = difflib.get_close_matches(
        clean, 
        list(STANDARD_GENRES.keys()) + list(GENRE_ALIASES.keys()),
        n=1,
        cutoff=0.8
    )
    
    if matches:
        matched = matches[0]
        return GENRE_ALIASES.get(matched) or STANDARD_GENRES.get(matched)
    
    # Return capitalized if no match found
    return genre_input.title()
```

#### 1.3 Series-Level Genre Inheritance
```python
def get_series_genre(series_name: str) -> Optional[str]:
    """Get the canonical genre for a series"""
    # Query database for most common genre in series
    games_in_series = db.get_games_by_franchise(series_name)
    
    if not games_in_series:
        return None
    
    # Count genres
    genre_counts = {}
    for game in games_in_series:
        if game.get('genre'):
            normalized = normalize_genre(game['genre'])
            genre_counts[normalized] = genre_counts.get(normalized, 0) + 1
    
    # Return most common
    if genre_counts:
        return max(genre_counts.items(), key=lambda x: x[1])[0]
    
    return None

def apply_series_genre(series_name: str, genre: str):
    """Apply genre to all games in series"""
    normalized_genre = normalize_genre(genre)
    games = db.get_games_by_franchise(series_name)
    
    for game in games:
        if not game.get('genre'):
            db.update_played_game(game['id'], genre=normalized_genre)
```

### Phase 2: Metadata Enrichment During Sync

#### 2.1 Enhanced Playlist Metadata Extraction
```python
# In fetch_playlist_based_content_since():
# Extract genre from playlist description or video tags
# Use AI to infer genre if not available
# Add to game_data dictionary before database insert
```

#### 2.2 Series Name Normalization
```python
SERIES_NAME_MAPPINGS = {
    'halo': 'Halo',
    'the last of us': 'The Last of Us',
    'god of war': 'God of War',
    'grand theft auto': 'Grand Theft Auto',
    'gta': 'Grand Theft Auto',
    'cod': 'Call of Duty',
    'call of duty': 'Call of Duty',
}

def normalize_series_name(series_name: str) -> str:
    """Normalize series name to canonical form"""
    if not series_name:
        return None
    
    clean = series_name.strip().lower()
    
    # Check mappings
    if clean in SERIES_NAME_MAPPINGS:
        return SERIES_NAME_MAPPINGS[clean]
    
    # Title case
    return series_name.strip().title()
```

### Phase 3: Data Validation Framework

#### 3.1 Validation Rules
```python
class GameDataValidator:
    @staticmethod
    def validate_game_data(game_data: Dict) -> Tuple[bool, List[str]]:
        """Validate game data quality"""
        errors = []
        
        # Required fields
        if not game_data.get('canonical_name'):
            errors.append("Missing canonical_name")
        
        # Genre validation
        if game_data.get('genre'):
            normalized = normalize_genre(game_data['genre'])
            if normalized not in STANDARD_GENRES.values():
                errors.append(f"Non-standard genre: {game_data['genre']}")
        
        # Completion status validation
        valid_statuses = ['unknown', 'in_progress', 'completed', 'dropped']
        if game_data.get('completion_status') not in valid_statuses:
            errors.append(f"Invalid completion_status: {game_data['completion_status']}")
        
        # Data consistency
        if game_data.get('total_episodes', 0) > 0 and game_data.get('total_playtime_minutes', 0) == 0:
            errors.append("Has episodes but no playtime")
        
        return len(errors) == 0, errors
```

#### 3.2 Sync-Time Validation
```python
# In perform_full_content_sync():
for game_data in playlist_games:
    # Normalize before insert/update
    game_data['genre'] = normalize_genre(game_data.get('genre'))
    game_data['series_name'] = normalize_series_name(game_data.get('series_name'))
    
    # Validate
    is_valid, errors = GameDataValidator.validate_game_data(game_data)
    if not is_valid:
        print(f"⚠️ Data quality issues for {game_data['canonical_name']}: {errors}")
        # Continue but log issues
```

### Phase 4: Database Cleanup Utilities

#### 4.1 Remove Platform Column
```sql
ALTER TABLE played_games DROP COLUMN IF EXISTS platform;
```

#### 4.2 Genre Cleanup Script
```python
def cleanup_all_genres():
    """Normalize all genres in database"""
    all_games = db.get_all_played_games()
    updated = 0
    
    for game in all_games:
        if game.get('genre'):
            normalized = normalize_genre(game['genre'])
            if normalized != game['genre']:
                db.update_played_game(game['id'], genre=normalized)
                print(f"Updated {game['canonical_name']}: {game['genre']} → {normalized}")
                updated += 1
    
    return updated
```

#### 4.3 Series Name Cleanup
```python
def cleanup_series_names():
    """Normalize all series names"""
    all_games = db.get_all_played_games()
    updated = 0
    
    for game in all_games:
        if game.get('series_name'):
            normalized = normalize_series_name(game['series_name'])
            if normalized != game['series_name']:
                db.update_played_game(game['id'], series_name=normalized)
                updated += 1
    
    return updated
```

### Phase 5: Implementation Priority

1. **Immediate** (Critical):
   - Remove platform column
   - Add genre normalization function
   - Add series name normalization
   - Run cleanup scripts on existing data

2. **Short-term** (This Week):
   - Integrate normalization into sync process
   - Add validation framework
   - Create data quality report command

3. **Medium-term** (Next 2 Weeks):
   - AI-powered genre inference for missing data
   - Automated series detection and grouping
   - Release year extraction from external APIs

4. **Long-term** (Next Month):
   - Automated data enrichment from IGDB/RAWG APIs
   - Series-level metadata management
   - Data quality monitoring dashboard

## Testing Plan

### 1. Unit Tests
```python
def test_genre_normalization():
    assert normalize_genre('action') == 'Action'
    assert normalize_genre('ACTION') == 'Action'
    assert normalize_genre('action rpg') == 'Action-RPG'
    assert normalize_genre('arpg') == 'Action-RPG'
```

### 2. Integration Tests
```python
def test_sync_with_normalization():
    # Test that sync properly normalizes data
    # Test that duplicates are merged with consistent data
```

### 3. Data Quality Audit
```python
def audit_data_quality():
    """Generate data quality report"""
    all_games = db.get_all_played_games()
    
    report = {
        'total_games': len(all_games),
        'missing_genre': 0,
        'missing_series': 0,
        'non_standard_genres': [],
        'duplicate_series_names': [],
    }
    
    # Analyze and report
    return report
```

## Success Metrics

1. **Genre Consistency**: 100% of games in same series have same genre
2. **Data Completeness**: <5% of games missing genre
3. **Series Normalization**: 0 duplicate series with different spellings
4. **Validation Success**: 95%+ of synced games pass validation

## Maintenance

- Weekly data quality audit
- Monthly cleanup of non-standard values
- Quarterly review of genre taxonomy
- Annual review of series mappings
