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
    client_id = os.getenv('IGDB_CLIENT_ID') or os.getenv('TWITCH_CLIENT_ID')
    client_secret = os.getenv('IGDB_CLIENT_SECRET') or os.getenv('TWITCH_CLIENT_SECRET')

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
    
    client_id = os.getenv('IGDB_CLIENT_ID') or os.getenv('TWITCH_CLIENT_ID')
    
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

    # Take best match (first result)
    best_match = results[0]

    # Calculate confidence based on name similarity
    igdb_name = best_match.get('name', '')
    confidence = calculate_confidence(game_name, igdb_name)

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

    # Parse alternative names
    if 'alternative_names' in best_match:
        alt_names = [alt.get('name') for alt in best_match['alternative_names'] if alt.get('name')]
        enrichment['alternative_names'] = alt_names[:5]  # Limit to 5

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
    Calculate confidence score for name match.
    Returns 0.0-1.0 where:
    - 1.0 = exact match
    - 0.8+ = high confidence
    - 0.5-0.8 = medium confidence
    - <0.5 = low confidence
    """
    import difflib

    # Normalize for comparison
    extracted_lower = extracted_name.lower().strip()
    igdb_lower = igdb_name.lower().strip()

    # Exact match
    if extracted_lower == igdb_lower:
        return 1.0

    # Calculate similarity ratio
    similarity = difflib.SequenceMatcher(None, extracted_lower, igdb_lower).ratio()

    # Word-based matching for multi-word names
    if len(extracted_lower.split()) > 1:
        extracted_words = set(extracted_lower.split())
        igdb_words = set(igdb_lower.split())

        if len(igdb_words) > 0:
            word_overlap = len(extracted_words & igdb_words) / len(igdb_words)
            # Use the higher of the two scores
            similarity = max(similarity, word_overlap)

    return round(similarity, 2)


def should_use_igdb_data(confidence: float) -> bool:
    """Determine if IGDB data is trustworthy enough to use"""
    return confidence >= 0.8  # 80% threshold for auto-approval


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
