"""
Data Quality Utilities

Provides normalization, validation, and cleanup functions for maintaining
high-quality game data in the database.
"""

import difflib
from typing import Any, Dict, List, Optional, Tuple, Union

# Standard genre taxonomy
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
    'roguelite': 'Roguelite',
    'metroidvania': 'Metroidvania',
    'souls-like': 'Souls-Like',
    'battle-royale': 'Battle Royale',
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
    'beat-em-up': 'Action',
    'fighting': 'Action',
    'stealth': 'Action',
    'mmo': 'RPG',
    'mmorpg': 'RPG',
    'sandbox': 'Adventure',
    'open world': 'Adventure',
    'open-world': 'Adventure',
}

# Canonical series name mappings
SERIES_NAME_MAPPINGS = {
    'halo': 'Halo',
    'the last of us': 'The Last of Us',
    'tlou': 'The Last of Us',
    'god of war': 'God of War',
    'gow': 'God of War',
    'grand theft auto': 'Grand Theft Auto',
    'gta': 'Grand Theft Auto',
    'cod': 'Call of Duty',
    'call of duty': 'Call of Duty',
    'red dead redemption': 'Red Dead Redemption',
    'rdr': 'Red Dead Redemption',
    'dark souls': 'Dark Souls',
    'elder scrolls': 'The Elder Scrolls',
    'the elder scrolls': 'The Elder Scrolls',
    'fallout': 'Fallout',
    'witcher': 'The Witcher',
    'the witcher': 'The Witcher',
    'zelda': 'The Legend of Zelda',
    'legend of zelda': 'The Legend of Zelda',
    'the legend of zelda': 'The Legend of Zelda',
    'loz': 'The Legend of Zelda',
    'final fantasy': 'Final Fantasy',
    'ff': 'Final Fantasy',
    'metal gear': 'Metal Gear',
    'metal gear solid': 'Metal Gear Solid',
    'mgs': 'Metal Gear Solid',
    'resident evil': 'Resident Evil',
    're': 'Resident Evil',
    'silent hill': 'Silent Hill',
    'assassins creed': "Assassin's Creed",
    "assassin's creed": "Assassin's Creed",
    'ac': "Assassin's Creed",
    'tomb raider': 'Tomb Raider',
    'uncharted': 'Uncharted',
    'mass effect': 'Mass Effect',
    'dragon age': 'Dragon Age',
    'bioshock': 'BioShock',
    'borderlands': 'Borderlands',
    'gears of war': 'Gears of War',
    'dead space': 'Dead Space',
    'doom': 'DOOM',
    'wolfenstein': 'Wolfenstein',
    'dishonored': 'Dishonored',
    'prey': 'Prey',
    'deus ex': 'Deus Ex',
    'half life': 'Half-Life',
    'half-life': 'Half-Life',
    'portal': 'Portal',
    'left 4 dead': 'Left 4 Dead',
    'l4d': 'Left 4 Dead',
}


def normalize_genre(genre_input: Optional[str]) -> Optional[str]:
    """
    Normalize genre to standard format.

    Args:
        genre_input: Raw genre string from various sources

    Returns:
        Standardized genre string or None if invalid
    """
    if not genre_input or not isinstance(genre_input, str):
        return None

    clean = genre_input.strip().lower()

    if not clean:
        return None

    # Check direct match in standard genres
    if clean in STANDARD_GENRES:
        return STANDARD_GENRES[clean]

    # Check aliases
    if clean in GENRE_ALIASES:
        return GENRE_ALIASES[clean]

    # Fuzzy match against standard genres and aliases
    all_genre_keys = list(STANDARD_GENRES.keys()) + list(GENRE_ALIASES.keys())
    matches = difflib.get_close_matches(
        clean,
        all_genre_keys,
        n=1,
        cutoff=0.8
    )

    if matches:
        matched = matches[0]
        return GENRE_ALIASES.get(matched) or STANDARD_GENRES.get(matched)

    # If no match found, return title case
    return genre_input.strip().title()


def normalize_series_name(series_name: Optional[str]) -> Optional[str]:
    """
    Normalize series name to canonical form.

    Args:
        series_name: Raw series name from various sources

    Returns:
        Standardized series name or None if invalid
    """
    if not series_name or not isinstance(series_name, str):
        return None

    clean = series_name.strip().lower()

    if not clean:
        return None

    # Check direct mapping
    if clean in SERIES_NAME_MAPPINGS:
        return SERIES_NAME_MAPPINGS[clean]

    # Fuzzy match for typos
    matches = difflib.get_close_matches(
        clean,
        SERIES_NAME_MAPPINGS.keys(),
        n=1,
        cutoff=0.85
    )

    if matches:
        return SERIES_NAME_MAPPINGS[matches[0]]

    # Return title case if no mapping found
    return series_name.strip().title()


def get_series_genre(series_name: str, db) -> Optional[str]:
    """
    Get the canonical genre for a series based on existing games.

    Args:
        series_name: The series name to check
        db: Database instance

    Returns:
        Most common genre in the series, or None
    """
    if not db:
        return None

    try:
        games_in_series = db.get_games_by_franchise(series_name)

        if not games_in_series:
            return None

        # Count genres
        genre_counts = {}
        for game in games_in_series:
            if game.get('genre'):
                normalized = normalize_genre(game['genre'])
                if normalized:
                    genre_counts[normalized] = genre_counts.get(normalized, 0) + 1

        # Return most common
        if genre_counts:
            return max(genre_counts.items(), key=lambda x: x[1])[0]

        return None
    except Exception as e:
        print(f"Error getting series genre: {e}")
        return None


def apply_series_genre(series_name: str, genre: str, db) -> int:
    """
    Apply genre to all games in series that don't have one.

    Args:
        series_name: The series to update
        genre: The genre to apply
        db: Database instance

    Returns:
        Number of games updated
    """
    if not db:
        return 0

    try:
        normalized_genre = normalize_genre(genre)
        if not normalized_genre:
            return 0

        games = db.get_games_by_franchise(series_name)
        updated = 0

        for game in games:
            if not game.get('genre'):
                db.update_played_game(game['id'], genre=normalized_genre)
                updated += 1

        return updated
    except Exception as e:
        print(f"Error applying series genre: {e}")
        return 0


class GameDataValidator:
    """Validates game data for quality and consistency."""

    VALID_COMPLETION_STATUSES = ['unknown', 'in_progress', 'completed', 'dropped']

    @staticmethod
    def validate_game_data(game_data: Dict) -> Tuple[bool, List[str]]:
        """
        Validate game data quality.

        Args:
            game_data: Dictionary containing game information

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        warnings = []

        # Required fields
        if not game_data.get('canonical_name'):
            errors.append("Missing canonical_name")

        # Genre validation
        if game_data.get('genre'):
            normalized = normalize_genre(game_data['genre'])
            if normalized and normalized not in STANDARD_GENRES.values():
                warnings.append(f"Non-standard genre: {game_data['genre']} (normalized to {normalized})")

        # Completion status validation
        status = game_data.get('completion_status', 'unknown')
        if status not in GameDataValidator.VALID_COMPLETION_STATUSES:
            errors.append(f"Invalid completion_status: {status}")

        # Data consistency checks
        episodes = game_data.get('total_episodes', 0)
        playtime = game_data.get('total_playtime_minutes', 0)

        if episodes > 0 and playtime == 0:
            warnings.append("Has episodes but no playtime recorded")

        if playtime > 0 and episodes == 0:
            warnings.append("Has playtime but no episodes recorded")

        # Series name should match canonical for single games
        series = game_data.get('series_name')
        canonical = game_data.get('canonical_name')
        if series and canonical and series != canonical:
            # This is okay for games in a series, just noting it
            pass

        # Log warnings but don't fail validation
        if warnings:
            for warning in warnings:
                print(f"⚠️ Data quality warning: {warning}")

        return len(errors) == 0, errors

    @staticmethod
    def normalize_game_data(game_data: Dict) -> Dict:
        """
        Normalize game data in-place.

        Args:
            game_data: Dictionary containing game information

        Returns:
            Normalized game data dictionary
        """
        # Normalize genre
        if game_data.get('genre'):
            game_data['genre'] = normalize_genre(game_data['genre'])

        # Normalize series name
        if game_data.get('series_name'):
            game_data['series_name'] = normalize_series_name(game_data['series_name'])

        # Ensure completion_status is valid
        if game_data.get('completion_status') not in GameDataValidator.VALID_COMPLETION_STATUSES:
            game_data['completion_status'] = 'unknown'

        return game_data


def cleanup_all_genres(db) -> Dict[str, Union[int, str]]:
    """
    Normalize all genres in database.

    Args:
        db: Database instance

    Returns:
        Dictionary with cleanup statistics
    """
    if not db:
        return {'error': 'Database not available'}

    try:
        all_games = db.get_all_played_games()
        stats: Dict[str, Union[int, str]] = {
            'total_games': len(all_games),
            'updated': 0,
            'already_normalized': 0,
            'missing_genre': 0,
        }

        for game in all_games:
            if not game.get('genre'):
                stats['missing_genre'] = int(stats['missing_genre']) + 1
                continue

            normalized = normalize_genre(game['genre'])
            if normalized and normalized != game['genre']:
                db.update_played_game(game['id'], genre=normalized)
                print(f"✅ Updated {game['canonical_name']}: '{game['genre']}' → '{normalized}'")
                stats['updated'] = int(stats['updated']) + 1
            else:
                stats['already_normalized'] = int(stats['already_normalized']) + 1

        return stats
    except Exception as e:
        print(f"Error cleaning up genres: {e}")
        return {'error': str(e)}


def cleanup_series_names(db) -> Dict[str, Union[int, str]]:
    """
    Normalize all series names in database.

    Args:
        db: Database instance

    Returns:
        Dictionary with cleanup statistics
    """
    if not db:
        return {'error': 'Database not available'}

    try:
        all_games = db.get_all_played_games()
        stats: Dict[str, Union[int, str]] = {
            'total_games': len(all_games),
            'updated': 0,
            'already_normalized': 0,
            'missing_series': 0,
        }

        for game in all_games:
            if not game.get('series_name'):
                stats['missing_series'] = int(stats['missing_series']) + 1
                continue

            normalized = normalize_series_name(game['series_name'])
            if normalized and normalized != game['series_name']:
                db.update_played_game(game['id'], series_name=normalized)
                print(f"✅ Updated {game['canonical_name']}: '{game['series_name']}' → '{normalized}'")
                stats['updated'] = int(stats['updated']) + 1
            else:
                stats['already_normalized'] = int(stats['already_normalized']) + 1

        return stats
    except Exception as e:
        print(f"Error cleaning up series names: {e}")
        return {'error': str(e)}


def parse_complex_array_syntax(alt_names_str: str) -> List[str]:
    """
    Parse complex array syntax from database into simple list.

    Handles formats like:
    - '{"Name 1","Name 2","Name 3"}'
    - '["Name 1", "Name 2"]'
    - 'Name 1, Name 2, Name 3'

    Args:
        alt_names_str: String representation of alternative names

    Returns:
        List of parsed names
    """
    import json
    import re

    if not alt_names_str:
        return []

    # Try JSON parsing first
    try:
        parsed = json.loads(alt_names_str)
        if isinstance(parsed, list):
            return [str(name).strip() for name in parsed if name]
    except (json.JSONDecodeError, ValueError):
        pass

    # Try PostgreSQL array format: {"Name 1","Name 2"}
    if alt_names_str.startswith('{') and alt_names_str.endswith('}'):
        # Remove outer braces
        content = alt_names_str[1:-1]
        # Split by comma, handling quoted strings
        names = re.findall(r'"([^"]*)"', content)
        if names:
            return [name.strip() for name in names if name.strip()]
        # Fallback: simple comma split
        return [name.strip() for name in content.split(',') if name.strip()]

    # Fallback: treat as comma-separated string
    return [name.strip() for name in alt_names_str.split(',') if name.strip()]


def filter_english_names(names: List[str]) -> List[str]:
    """
    Filter alternative names to English-only (ASCII + common European characters).

    Removes:
    - CJK characters (Chinese, Japanese, Korean)
    - Cyrillic characters (Russian, etc.)
    - Arabic script
    - Other non-Latin scripts

    Keeps:
    - ASCII characters (a-z, A-Z, 0-9)
    - Latin Extended-A (accented characters: é, ñ, ö, etc.)
    - Common punctuation and symbols

    Args:
        names: List of alternative names in various languages

    Returns:
        Filtered list containing only English/Latin-based names
    """
    import re

    english_names = []

    for name in names:
        if not name or not isinstance(name, str):
            continue

        name = name.strip()
        if not name:
            continue

        # Check if name contains CJK characters
        if re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', name):
            print(f"  🚫 Filtering CJK name: '{name}'")
            continue

        # Check if name contains Cyrillic
        if re.search(r'[\u0400-\u04ff]', name):
            print(f"  🚫 Filtering Cyrillic name: '{name}'")
            continue

        # Check if name contains Arabic
        if re.search(r'[\u0600-\u06ff]', name):
            print(f"  🚫 Filtering Arabic name: '{name}'")
            continue

        # Allow ASCII + Latin Extended-A (covers most European languages)
        # Unicode ranges: 0000-007F (ASCII), 0080-00FF (Latin-1), 0100-017F (Latin Extended-A)
        if all(ord(c) < 592 for c in name):  # 592 = end of Latin Extended-A
            english_names.append(name)
        else:
            print(f"  🚫 Filtering non-Latin name: '{name}'")

    return english_names


def cleanup_alternative_names_format(db) -> Dict[str, Union[int, str, float]]:
    """
    Clean up alternative names to English-only, deduplicated, simple format.

    This function:
    1. Parses complex array syntax from database
    2. Filters to English-only names
    3. Deduplicates names
    4. Updates database with clean list

    Args:
        db: Database instance

    Returns:
        Dictionary with cleanup statistics
    """
    if not db:
        return {'error': 'Database not available'}

    try:
        all_games = db.get_all_played_games()
        stats: Dict[str, Union[int, str, float]] = {
            'total_games': len(all_games),
            'processed': 0,
            'cleaned': 0,
            'skipped_no_alt_names': 0,
            'total_names_before': 0,
            'total_names_after': 0,
        }

        for game in all_games:
            alt_names = game.get('alternative_names')

            if not alt_names:
                stats['skipped_no_alt_names'] = int(stats['skipped_no_alt_names']) + 1
                continue

            # Parse if string
            if isinstance(alt_names, str):
                alt_names = parse_complex_array_syntax(alt_names)
            elif not isinstance(alt_names, list):
                print(f"⚠️ Unknown alt_names format for {game['canonical_name']}: {type(alt_names)}")
                stats['skipped_no_alt_names'] = int(stats['skipped_no_alt_names']) + 1
                continue

            if not alt_names:
                stats['skipped_no_alt_names'] = int(stats['skipped_no_alt_names']) + 1
                continue

            original_count = len(alt_names)
            stats['total_names_before'] = int(stats['total_names_before']) + original_count

            print(f"\n🔍 Processing {game['canonical_name']}:")
            print(f"  Original names ({original_count}): {alt_names}")

            # Filter to English-only
            english_only = filter_english_names(alt_names)

            # Deduplicate while preserving order
            seen = set()
            unique_names = []
            for name in english_only:
                name_lower = name.lower()
                if name_lower not in seen:
                    seen.add(name_lower)
                    unique_names.append(name)

            final_count = len(unique_names)
            stats['total_names_after'] = int(stats['total_names_after']) + final_count

            # Only update if there were changes
            if unique_names != alt_names:
                db.update_played_game(game['id'], alternative_names=unique_names)
                print(f"  ✅ Cleaned: {original_count} → {final_count} names")
                print(f"  Final names: {unique_names}")
                stats['cleaned'] = int(stats['cleaned']) + 1
            else:
                print(f"  ✓ Already clean ({final_count} names)")

            stats['processed'] = int(stats['processed']) + 1

        # Calculate summary
        names_removed = int(stats['total_names_before']) - int(stats['total_names_after'])
        stats['names_removed'] = names_removed
        stats['removal_percentage'] = round(
            (names_removed / int(stats['total_names_before']) * 100) if int(stats['total_names_before']) > 0 else 0,
            1
        )

        print(f"\n📊 Cleanup Summary:")
        print(f"  Total games: {stats['total_games']}")
        print(f"  Processed: {stats['processed']}")
        print(f"  Cleaned: {stats['cleaned']}")
        print(f"  Skipped (no alt names): {stats['skipped_no_alt_names']}")
        print(f"  Names before: {stats['total_names_before']}")
        print(f"  Names after: {stats['total_names_after']}")
        print(f"  Names removed: {stats['names_removed']} ({stats['removal_percentage']}%)")

        return stats

    except Exception as e:
        print(f"❌ Error cleaning up alternative names: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}


def audit_data_quality(db) -> Dict[str, Any]:
    """
    Generate comprehensive data quality report.

    Args:
        db: Database instance

    Returns:
        Dictionary with audit results
    """
    if not db:
        return {'error': 'Database not available'}

    try:
        all_games = db.get_all_played_games()

        report = {
            'total_games': len(all_games),
            'missing_genre': 0,
            'missing_series': 0,
            'missing_completion_status': 0,
            'non_standard_genres': [],
            'non_standard_series': [],
            'duplicate_series_spellings': {},
            'games_with_episodes_no_playtime': 0,
            'games_with_playtime_no_episodes': 0,
        }

        series_variations = {}

        for game in all_games:
            # Check missing fields
            if not game.get('genre'):
                report['missing_genre'] += 1

            if not game.get('series_name'):
                report['missing_series'] += 1

            if not game.get('completion_status') or game['completion_status'] == 'unknown':
                report['missing_completion_status'] += 1

            # Check genre standardization
            if game.get('genre'):
                normalized = normalize_genre(game['genre'])
                if normalized and normalized != game['genre']:
                    report['non_standard_genres'].append({
                        'game': game['canonical_name'],
                        'current': game['genre'],
                        'should_be': normalized
                    })

            # Check series name standardization
            if game.get('series_name'):
                normalized = normalize_series_name(game['series_name'])
                if normalized and normalized != game['series_name']:
                    report['non_standard_series'].append({
                        'game': game['canonical_name'],
                        'current': game['series_name'],
                        'should_be': normalized
                    })

                # Track series variations
                lower_series = game['series_name'].lower()
                if lower_series not in series_variations:
                    series_variations[lower_series] = set()
                series_variations[lower_series].add(game['series_name'])

            # Check data consistency
            episodes = game.get('total_episodes', 0)
            playtime = game.get('total_playtime_minutes', 0)

            if episodes > 0 and playtime == 0:
                report['games_with_episodes_no_playtime'] += 1

            if playtime > 0 and episodes == 0:
                report['games_with_playtime_no_episodes'] += 1

        # Find duplicate series spellings
        for lower_series, variations in series_variations.items():
            if len(variations) > 1:
                report['duplicate_series_spellings'][lower_series] = list(variations)

        return report
    except Exception as e:
        print(f"Error auditing data quality: {e}")
        return {'error': str(e)}
