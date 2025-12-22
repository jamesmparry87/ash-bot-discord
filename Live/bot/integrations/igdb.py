"""
IGDB (Internet Game Database) Integration Module

Provides lightweight game validation and metadata enrichment using the IGDB API.
Uses Twitch OAuth for authentication (IGDB is owned by Twitch).

Focus: Validate extracted game names and enrich existing database fields only.
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp

# Cache to avoid redundant API calls
_igdb_cache: Dict[str, Dict[str, Any]] = {}
_cache_expiry: Dict[str, datetime] = {}
CACHE_DURATION = timedelta(hours=24)

# Rate limiting: IGDB allows 4 requests per second
_last_request_time = datetime.now()
_request_interval = 0.25  # 250ms between requests = 4 req/sec


async def get_igdb_access_token() -> Optional[str]:
    """Get OAuth access token for IGDB API using Twitch credentials"""
    client_id = os.getenv('IGDB_CLIENT_ID') or os.getenv('IGDB_TWITCH_CLIENT_ID') or os.getenv('TWITCH_CLIENT_ID')
    client_secret = os.getenv('IGDB_CLIENT_SECRET') or os.getenv(
        'IGDB_TWITCH_SECRET') or os.getenv('TWITCH_CLIENT_SECRET')

    if not client_id or not client_secret:
        print("⚠️ IGDB credentials not configured")
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://id.twitch.tv/oauth2/token',
                params={
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'grant_type': 'client_credentials'
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('access_token')
                else:
                    print(f"❌ Failed to get IGDB token: {response.status}")
                    return None
    except Exception as e:
        print(f"❌ Error getting IGDB token: {e}")
        return None


async def _rate_limit():
    """Ensure we don't exceed IGDB rate limit (4 req/sec)"""
    global _last_request_time
    now = datetime.now()
    time_since_last = (now - _last_request_time).total_seconds()

    if time_since_last < _request_interval:
        await asyncio.sleep(_request_interval - time_since_last)

    _last_request_time = datetime.now()


async def search_igdb(game_name: str, access_token: str) -> List[Dict[str, Any]]:
    """Search IGDB for a game by name"""
    await _rate_limit()

    client_id = os.getenv('IGDB_CLIENT_ID') or os.getenv('IGDB_TWITCH_CLIENT_ID') or os.getenv('TWITCH_CLIENT_ID')

    if not client_id:
        print("⚠️ IGDB Client ID not configured")
        return []

    try:
        # Escape double quotes to prevent query injection
        game_name_escaped = game_name.replace('"', '\\"')

        async with aiohttp.ClientSession() as session:
            # IGDB uses Twitch API-like syntax with POST and body query
            async with session.post(
                'https://api.igdb.com/v4/games',
                headers={
                    'Client-ID': client_id,
                    'Authorization': f'Bearer {access_token}'
                },
                data=f'search "{game_name_escaped}"; fields name,alternative_names.name,franchises.name,genres.name,release_dates.y,cover.url; limit 5;'
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"⚠️ IGDB search failed: {response.status}")
                    return []
    except Exception as e:
        print(f"❌ Error searching IGDB: {e}")
        return []


async def validate_and_enrich(game_name: str) -> Dict[str, Any]:
    """
    Validate a game name against IGDB and return enrichment data.

    Returns:
        Dict with canonical_name, alternative_names, genre, series_name,
        release_year, igdb_id, and confidence score.
    """
    # Check cache first
    cache_key = game_name.lower().strip()
    if cache_key in _igdb_cache:
        if datetime.now() - _cache_expiry.get(cache_key, datetime.min) < CACHE_DURATION:
            print(f"💾 IGDB cache hit: {game_name}")
            return _igdb_cache[cache_key]

    # Get access token
    access_token = await get_igdb_access_token()
    if not access_token:
        return {
            'canonical_name': game_name,
            'confidence': 0.0,
            'error': 'No IGDB access token'
        }

    # Search IGDB
    results = await search_igdb(game_name, access_token)

    if not results:
        return {
            'canonical_name': game_name,
            'confidence': 0.0,
            'match_found': False
        }

    # Find best match from results (don't just take first)
    best_match = None
    best_confidence = 0.0

    for result in results[:5]:  # Check up to 5 results
        igdb_name = result.get('name', '')

        # Skip compound/bundle games (e.g., "Halo 3 + Halo Wars")
        if ' + ' in igdb_name or ' & ' in igdb_name:
            print(f"⚠️ Skipping compound game: '{igdb_name}'")
            continue

        confidence = calculate_confidence(game_name, igdb_name)

        if confidence > best_confidence:
            best_confidence = confidence
            best_match = result

    # If no decent match found, return no match
    if best_match is None or best_confidence < 0.3:
        print(f"⚠️ IGDB: No acceptable match for '{game_name}' (best confidence: {best_confidence:.2f})")
        return {
            'canonical_name': game_name,
            'confidence': best_confidence,
            'match_found': False
        }

    # Use best match
    igdb_name = best_match.get('name', '')
    confidence = best_confidence

    # Extract enrichment data
    enrichment = {
        'canonical_name': igdb_name,
        'alternative_names': [],
        'genre': None,
        'series_name': None,
        'release_year': None,
        'igdb_id': best_match.get('id'),
        'confidence': confidence,
        'match_found': True
    }

    # Parse alternative names and filter to English-only
    if 'alternative_names' in best_match:
        alt_names = [alt.get('name') for alt in best_match['alternative_names'] if alt.get('name')]
        # Apply English-only filter
        english_alt_names = filter_english_names(alt_names)
        enrichment['alternative_names'] = english_alt_names[:5]  # Limit to 5

        if len(english_alt_names) < len(alt_names):
            print(f"🔤 IGDB: Filtered {len(alt_names) - len(english_alt_names)} non-English names from '{igdb_name}'")

    # Parse genres (take first one for consistency)
    if 'genres' in best_match and best_match['genres']:
        genre_name = best_match['genres'][0].get('name')
        if genre_name:
            enrichment['genre'] = genre_name

    # Parse series/franchise
    if 'franchises' in best_match and best_match['franchises']:
        franchise_name = best_match['franchises'][0].get('name')
        if franchise_name:
            enrichment['series_name'] = franchise_name

    # Parse release year
    if 'release_dates' in best_match and best_match['release_dates']:
        year = best_match['release_dates'][0].get('y')
        if year:
            enrichment['release_year'] = year

    # Cache the result
    _igdb_cache[cache_key] = enrichment
    _cache_expiry[cache_key] = datetime.now()

    print(f"✅ IGDB: {game_name} → {igdb_name} (confidence: {confidence:.2f})")

    return enrichment


def calculate_confidence(extracted_name: str, igdb_name: str) -> float:
    """
    Calculate confidence score for name match with gaming-specific rules.
    Returns 0.0-1.0 where:
    - 1.0 = exact match
    - 0.8+ = high confidence
    - 0.5-0.8 = medium confidence
    - <0.5 = low confidence
    """
    import difflib
    import re

    # Normalize for comparison
    extracted_lower = extracted_name.lower().strip()
    igdb_lower = igdb_name.lower().strip()

    # Exact match
    if extracted_lower == igdb_lower:
        return 1.0

    # Function to remove articles for comparison
    def remove_articles(text):
        """Remove common articles (the, a, an) for comparison"""
        # Remove articles at the beginning
        text = re.sub(r'^\s*(the|a|an)\s+', '', text, flags=re.IGNORECASE)
        # Remove articles after colons (e.g., "Game: The Subtitle")
        text = re.sub(r':\s*(the|a|an)\s+', ': ', text, flags=re.IGNORECASE)
        return text.strip()

    # Check match without articles (handles "Cronos: A New Dawn" vs "Cronos: The New Dawn")
    extracted_no_articles = remove_articles(extracted_lower)
    igdb_no_articles = remove_articles(igdb_lower)

    if extracted_no_articles == igdb_no_articles:
        return 0.95  # Very high confidence - only difference is articles

    # Gaming abbreviation mapping
    abbreviations = {
        'gta': 'grand theft auto',
        'cod': 'call of duty',
        'tlou': 'the last of us',
        'rdr': 'red dead redemption',
        'mgs': 'metal gear solid',
        'ffvii': 'final fantasy vii',
        'ffxv': 'final fantasy xv',
        'rottr': 'rise of the tomb raider',
        'sottr': 'shadow of the tomb raider',
    }

    # Expand abbreviations in extracted name
    expanded_extracted = extracted_lower
    for abbr, full in abbreviations.items():
        # Match word boundaries to avoid partial matches
        pattern = r'\b' + re.escape(abbr) + r'\b'
        expanded_extracted = re.sub(pattern, full, expanded_extracted)

    # Roman numeral to Arabic number mapping
    roman_to_arabic = {
        'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5',
        'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10'
    }

    # Convert Roman numerals to Arabic in both names for comparison
    def normalize_numbers(text):
        # Replace Roman numerals at word boundaries
        for roman, arabic in roman_to_arabic.items():
            text = re.sub(r'\b' + roman + r'\b', arabic, text)
        return text

    # Apply article removal to expanded/normalized versions too
    normalized_extracted = remove_articles(normalize_numbers(expanded_extracted))
    normalized_igdb = remove_articles(normalize_numbers(igdb_lower))

    # Remove edition suffixes for comparison
    edition_suffixes = [
        'remake', 'remastered', 'definitive edition', 'goty edition',
        'game of the year', 'complete edition', 'enhanced edition',
        'special edition', 'deluxe edition', 'ultimate edition',
        'directors cut', "director's cut", 'redux'
    ]

    def remove_editions(text):
        for suffix in edition_suffixes:
            # Remove suffix if it appears at the end
            if text.endswith(suffix):
                text = text[:-len(suffix)].strip()
            # Also try with parentheses/brackets
            text = re.sub(r'\s*[\(\[]' + re.escape(suffix) + r'[\)\]]', '', text, flags=re.IGNORECASE)
        # Handle common typos
        text = text.replace('compleated', 'completed')
        return text.strip()

    cleaned_extracted = remove_editions(normalized_extracted)
    cleaned_igdb = remove_editions(normalized_igdb)

    # Check for match after all normalizations
    if cleaned_extracted == cleaned_igdb:
        return 0.92  # Very high confidence but not perfect since we did transformations

    # Calculate similarity ratio on normalized names
    similarity = difflib.SequenceMatcher(None, cleaned_extracted, cleaned_igdb).ratio()

    # Word-based matching for multi-word names
    if len(cleaned_extracted.split()) > 1:
        extracted_words = set(cleaned_extracted.split())
        igdb_words = set(cleaned_igdb.split())

        if len(igdb_words) > 0:
            word_overlap = len(extracted_words & igdb_words) / len(igdb_words)
            # Use the higher of the two scores
            similarity = max(similarity, word_overlap)

    # Bonus for partial number matches (e.g., "5" in both names)
    extracted_numbers = set(re.findall(r'\d+', cleaned_extracted))
    igdb_numbers = set(re.findall(r'\d+', cleaned_igdb))
    if extracted_numbers and igdb_numbers and extracted_numbers & igdb_numbers:
        similarity = min(1.0, similarity + 0.1)  # Small bonus for matching numbers

    return round(similarity, 2)


def filter_english_names(names: List[str]) -> List[str]:
    """
    Filter alternative names to English-only (removes non-Latin scripts and non-English languages).

    Args:
        names: List of game names in various languages

    Returns:
        List of names using only English/Latin characters
    """
    import re

    if not names:
        return []

    english_names = []

    # Common non-English keywords to detect and filter (case-insensitive)
    # Spanish/Portuguese indicators
    spanish_keywords = [
        r'\bel\b', r'\bla\b', r'\blos\b', r'\blas\b',  # Spanish articles
        r'\bdel\b', r'\bde\b', r'\bal\b',  # Spanish prepositions
        r'\bcombate\b', r'\bha\b', r'\bevolucionado\b',  # Combat/has evolved (Spanish)
        r'\by\b(?!\s*the\b)',  # 'y' (and in Spanish) - but not "y the"
    ]
    # French indicators
    french_keywords = [
        r'\ble\b', r'\bun\b', r'\bune\b', r'\bdes\b',
        r'\bdu\b', r'\bdans\b',
    ]
    # German indicators
    german_keywords = [
        r'\bder\b', r'\bdie\b', r'\bdas\b', r'\bden\b',
        r'\bein\b', r'\beine\b',
    ]

    # Combine all patterns
    non_english_patterns = spanish_keywords + french_keywords + german_keywords
    non_english_regex = re.compile('|'.join(non_english_patterns), re.IGNORECASE)

    for name in names:
        if not name or not isinstance(name, str):
            continue

        # Allow ASCII + Latin Extended-A (covers English + European accents like é, ñ, ö)
        # Unicode range: 0-591 covers Basic Latin + Latin Extended-A
        try:
            # First check: Must use Latin characters
            if not all(ord(c) < 592 for c in name):
                continue

            # Second check: Skip if contains only CJK characters
            # CJK ranges: Chinese (4e00-9fff), Hiragana (3040-309f), Katakana (30a0-30ff)
            if re.match(r'^[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+$', name):
                continue

            # Third check: Detect non-English keywords
            if non_english_regex.search(name):
                print(f"🔤 Filtered non-English name: '{name}'")
                continue

            # Passed all checks - add to English names
            english_names.append(name)

        except Exception as e:
            # If we can't process the name, skip it
            print(f"⚠️ IGDB: Error filtering name '{name[:20]}...': {e}")
            continue

    return english_names


def should_use_igdb_data(confidence: float) -> bool:
    """Determine if IGDB data is trustworthy enough to use"""
    return confidence >= 0.75  # 75% threshold for auto-approval (lowered to handle gaming abbreviations and variations)


async def bulk_validate_games(game_names: List[str]) -> List[Dict[str, Any]]:
    """Validate multiple games efficiently with rate limiting"""
    results = []

    for game_name in game_names:
        result = await validate_and_enrich(game_name)
        results.append(result)

        # Add small delay between requests for politeness
        await asyncio.sleep(0.1)

    return results


def clear_cache():
    """Clear the IGDB cache (for testing/debugging)"""
    global _igdb_cache, _cache_expiry
    _igdb_cache.clear()
    _cache_expiry.clear()
    print("🗑️ IGDB cache cleared")
