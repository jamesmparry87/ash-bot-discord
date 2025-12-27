"""
Twitch Integration Module

Handles all Twitch API interactions including:
- Fetching game data from channels
- Parsing VOD metadata
- Duration calculations
- Game series detection
"""

import asyncio
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

# Database import
from ..database_module import get_database

# Text processing utilities
from ..utils.text_processing import cleanup_game_name, extract_game_name_from_title, is_generic_term

# IGDB integration
from . import igdb


async def smart_extract_with_validation(title: str) -> tuple[Optional[str], float]:
    """
    Intelligently extract game name with IGDB validation and fallback strategies.

    If initial extraction fails IGDB validation (low confidence), tries alternative
    extraction methods and returns the one with highest confidence.

    Args:
        title: Video/stream title to extract from

    Returns:
        Tuple of (extracted_name, confidence_score)
    """
    best_name = None
    best_confidence = 0.0

    # PRIORITY Strategy 1: Try extracting from dash-separated titles FIRST
    # This is most common format for Twitch: "Description - Game Name (dayX)"
    if ' - ' in title or ' | ' in title:
        separator = ' - ' if ' - ' in title else ' | '
        parts = title.split(separator)

        # Try the SECOND part FIRST (after separator) - most common location for game name
        if len(parts) > 1:
            after_dash = parts[1].strip()
            # Remove day/episode markers (both parentheses and standalone)
            after_dash = re.sub(r'\s*\((?:day|part|episode|ep)\s+\d+[^)]*\)', '', after_dash, flags=re.IGNORECASE)
            after_dash = re.sub(r'\s*\[(?:day|part|episode|ep)\s+\d+[^\]]*\]', '', after_dash, flags=re.IGNORECASE)
            # Remove "Part X" at start or end of string
            after_dash = re.sub(r'^(?:part|ep|episode)\s+\d+\s*[-:]?\s*', '', after_dash, flags=re.IGNORECASE)
            after_dash = re.sub(r'\s*[-:]?\s*(?:part|ep|episode)\s+\d+$', '', after_dash, flags=re.IGNORECASE)
            # Remove common suffixes like "Gameplay", "Playthrough", "Stream"
            after_dash = re.sub(
                r'\s+(gameplay|playthrough|stream|let\'s play|walkthrough)$',
                '',
                after_dash,
                flags=re.IGNORECASE)
            after_dash = cleanup_game_name(after_dash)

            # Reject if it's ONLY "Part X" or similar episode marker
            if re.match(r'^(?:part|ep|episode|day)\s+\d+$', after_dash, flags=re.IGNORECASE):
                after_dash = ''  # Mark as invalid

            if len(after_dash) >= 3 and not is_generic_term(after_dash):
                # Keep this extraction even if IGDB fails
                if best_name is None:
                    best_name = after_dash

                print(f"🔍 Validating '{after_dash}' (after dash) with IGDB...")
                igdb_result = await igdb.validate_and_enrich(after_dash)
                confidence = igdb_result.get('confidence', 0.0)
                print(f"  → confidence: {confidence:.2f}")

                if confidence > best_confidence:
                    best_name = after_dash
                    best_confidence = confidence

                    # High confidence threshold since this is the priority extraction
                    if confidence >= 0.8:
                        return best_name, best_confidence

        # Try the FIRST part (before separator) as backup
        if len(parts) > 1 and best_confidence < 0.8:
            before_dash = parts[0].strip()
            # Clean common prefixes
            before_dash = re.sub(
                r'^\*?(DROPS?|NEW|SPONSORED?|LIVE)\*?\s*[-:]?\s*',
                '',
                before_dash,
                flags=re.IGNORECASE)
            before_dash = cleanup_game_name(before_dash)

            if len(before_dash) >= 3 and not is_generic_term(before_dash):
                print(f"🔍 Validating '{before_dash}' (before dash) with IGDB...")
                igdb_result = await igdb.validate_and_enrich(before_dash)
                confidence = igdb_result.get('confidence', 0.0)
                print(f"  → confidence: {confidence:.2f}")

                if confidence > best_confidence:
                    best_name = before_dash
                    best_confidence = confidence

                    if confidence >= 0.8:
                        return best_name, best_confidence

    # Strategy 2: Try standard extraction as fallback
    if best_confidence < 0.8:
        extracted = extract_game_name_from_title(title)
        if extracted:
            # Clean episode markers before IGDB validation
            cleaned_extracted = re.sub(r'\s*\((?:day|part|episode|ep)\s+\d+[^)]*\)', '', extracted, flags=re.IGNORECASE)
            cleaned_extracted = re.sub(r'\s*\[(?:day|part|episode|ep)\s+\d+[^\]]*\]',
                                       '', cleaned_extracted, flags=re.IGNORECASE)
            cleaned_extracted = cleaned_extracted.strip()

            if cleaned_extracted != best_name:  # Avoid duplicate validation
                # Keep this extraction even if IGDB fails
                if best_name is None:
                    best_name = cleaned_extracted

                print(f"🔍 Validating '{cleaned_extracted}' (standard extraction) with IGDB...")
                igdb_result = await igdb.validate_and_enrich(cleaned_extracted)
                confidence = igdb_result.get('confidence', 0.0)
                print(f"  → confidence: {confidence:.2f}")

                if confidence > best_confidence:
                    best_name = cleaned_extracted
                    best_confidence = confidence

                    if best_confidence >= 0.8:
                        return best_name, best_confidence

    # Strategy 3: Try simple cleaning of full title
    if best_confidence < 0.8:
        simple_clean = title
        simple_clean = re.sub(r'^\*?(DROPS?|NEW|SPONSORED?|LIVE)\*?\s*[-:]?\s*', '', simple_clean, flags=re.IGNORECASE)
        simple_clean = re.sub(r'\s*\((?:day|part|episode|ep)\s+\d+[^)]*\)', '', simple_clean, flags=re.IGNORECASE)
        simple_clean = re.sub(r'\s*\[(?:day|part|episode|ep)\s+\d+[^\]]*\]', '', simple_clean, flags=re.IGNORECASE)
        simple_clean = re.sub(r'\s+(?:Thanks|Thx|@|#).*$', '', simple_clean, flags=re.IGNORECASE)
        simple_clean = cleanup_game_name(simple_clean)

        if len(simple_clean) >= 3 and not is_generic_term(simple_clean) and simple_clean != best_name:
            # Keep this extraction even if IGDB fails
            if best_name is None:
                best_name = simple_clean

            print(f"🔍 Validating '{simple_clean}' (simple clean) with IGDB...")
            igdb_result = await igdb.validate_and_enrich(simple_clean)
            confidence = igdb_result.get('confidence', 0.0)
            print(f"  → confidence: {confidence:.2f}")

            if confidence > best_confidence:
                best_name = simple_clean
                best_confidence = confidence

    return best_name, best_confidence


async def fetch_twitch_games(username: str) -> List[str]:
    """Fetch game titles from Twitch channel using Twitch API"""
    # This requires Twitch Client ID and Client Secret
    twitch_client_id = os.getenv('TWITCH_CLIENT_ID')
    twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET')

    if not twitch_client_id or not twitch_client_secret:
        raise Exception(
            "TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET environment variables are required")

    games = []

    async with aiohttp.ClientSession() as session:
        try:
            # Get OAuth token
            token_url = "https://id.twitch.tv/oauth2/token"
            token_data = {
                'client_id': twitch_client_id,
                'client_secret': twitch_client_secret,
                'grant_type': 'client_credentials'
            }

            async with session.post(token_url, data=token_data) as response:
                if response.status == 200:
                    token_info = await response.json()
                    access_token = token_info['access_token']
                else:
                    raise Exception(
                        f"Failed to get Twitch OAuth token: {response.status}")

            headers = {
                "Client-ID": twitch_client_id,
                "Authorization": f"Bearer {access_token}"
            }

            # Get user ID
            user_url = f"https://api.twitch.tv/helix/users?login={username}"
            async with session.get(user_url, headers=headers) as response:
                if response.status == 200:
                    user_data = await response.json()
                    if user_data['data']:
                        user_id = user_data['data'][0]['id']
                    else:
                        raise Exception(f"Twitch user '{username}' not found")
                else:
                    raise Exception(
                        f"Failed to get Twitch user info: {response.status}")

            # Get recent videos (last 100)
            videos_url = f"https://api.twitch.tv/helix/videos"
            params = {"user_id": user_id, "first": 100, "type": "all"}

            async with session.get(videos_url, params=params, headers=headers) as response:
                if response.status == 200:
                    videos_data = await response.json()
                    for video in videos_data['data']:
                        title = video['title']
                        # Extract game name from title (basic parsing)
                        game_name = extract_game_name_from_title(title)
                        if game_name and game_name not in games:
                            games.append(game_name)
                else:
                    raise Exception(
                        f"Failed to get Twitch videos: {response.status}")

        except Exception as e:
            raise Exception(f"Failed to fetch Twitch games: {str(e)}")

    return games


async def fetch_new_vods_since(username: str, start_timestamp: datetime) -> List[Dict[str, Any]]:
    """Fetch all new VODs from a Twitch channel since a given timestamp."""
    twitch_client_id, twitch_client_secret = get_twitch_api_credentials()
    if not twitch_client_id or not twitch_client_secret:
        print("⚠️ Twitch credentials not configured for fetching new VODs.")
        return []

    new_vods = []
    async with aiohttp.ClientSession() as session:
        try:
            # Get OAuth token
            token_url = "https://id.twitch.tv/oauth2/token"
            token_data = {
                'client_id': twitch_client_id,
                'client_secret': twitch_client_secret,
                'grant_type': 'client_credentials'}
            async with session.post(token_url, data=token_data) as response:
                if response.status != 200:
                    return []
                token_info = await response.json()
                access_token = token_info['access_token']

            headers = {"Client-ID": twitch_client_id, "Authorization": f"Bearer {access_token}"}

            # Get user ID
            user_url = f"https://api.twitch.tv/helix/users?login={username}"
            async with session.get(user_url, headers=headers) as response:
                if response.status != 200:
                    return []
                user_data = await response.json()
                user_id = user_data['data'][0]['id']

            # Get recent videos with pagination
            videos_url = f"https://api.twitch.tv/helix/videos"
            cursor = None
            more_videos = True

            while more_videos:
                params = {"user_id": user_id, "first": 100, "type": "archive"}
                if cursor:
                    params['after'] = cursor

                async with session.get(videos_url, params=params, headers=headers) as response:
                    if response.status != 200:
                        print(f"❌ Twitch API error: {response.status}")
                        break

                    videos_data = await response.json()
                    if not videos_data.get('data'):
                        break

                    for video in videos_data['data']:
                        created_at = datetime.fromisoformat(video['created_at'].replace('Z', '+00:00'))
                        if created_at < start_timestamp:
                            more_videos = False
                            break  # Stop processing this batch and the loop

                        title = video['title']

                        # PRIMARY METHOD: Use Twitch API's game field (most reliable)
                        extracted_name = None
                        data_confidence = 0.0
                        twitch_game_name = None

                        # Try to fetch game name from Twitch API's game_id
                        game_id = video.get('game_id')
                        if game_id and game_id != '0' and game_id != '':
                            try:
                                # Fetch the game name from Twitch API
                                game_url = f"https://api.twitch.tv/helix/games?id={game_id}"
                                async with session.get(game_url, headers=headers) as game_response:
                                    if game_response.status == 200:
                                        game_data = await game_response.json()
                                        if game_data.get('data') and len(game_data['data']) > 0:
                                            twitch_game_name = game_data['data'][0].get('name')
                                            if twitch_game_name:
                                                print(f"🎮 TWITCH API: VOD '{title}' → Game: '{twitch_game_name}'")
                                                extracted_name = twitch_game_name
                                                data_confidence = 1.0  # High confidence since it's from Twitch API
                            except Exception as game_fetch_error:
                                print(f"⚠️ Failed to fetch game name from Twitch API: {game_fetch_error}")

                        # FALLBACK METHOD: Parse title if no game_id available
                        if not extracted_name:
                            print(f"⚠️ No game_id for VOD '{title}', falling back to title parsing")
                            extracted_name, data_confidence = await smart_extract_with_validation(title)

                        # Null safety checks
                        if not extracted_name:
                            extracted_name = ''
                            data_confidence = 0.0

                        # Set defaults for low-confidence or no-match scenarios
                        canonical_name = extracted_name
                        igdb_id = None
                        igdb_genre = None
                        igdb_series = None
                        igdb_year = None
                        alternative_names = []

                        if extracted_name and data_confidence >= 0.8:
                            # Get full IGDB enrichment data
                            igdb_result = await igdb.validate_and_enrich(extracted_name)
                            canonical_name = igdb_result.get('canonical_name', extracted_name)
                            igdb_id = igdb_result.get('igdb_id')
                            igdb_genre = igdb_result.get('genre')
                            igdb_series = igdb_result.get('series_name')
                            igdb_year = igdb_result.get('release_year')

                            # Get alternative names ONLY from IGDB
                            if igdb_result.get('alternative_names'):
                                alternative_names = igdb_result['alternative_names'][:5]

                            # DATA QUALITY CHECK: Empty alternative names = likely bad match
                            if not alternative_names or len(alternative_names) == 0:
                                print(
                                    f"⚠️ DATA QUALITY WARNING: '{canonical_name}' has NO alternative names in IGDB - likely incorrect extraction")
                                print(f"   Original title: '{title}'")
                                # Lower confidence to trigger manual review
                                data_confidence = 0.5

                            print(
                                f"✅ IGDB validated: '{extracted_name}' → '{canonical_name}' (confidence: {data_confidence:.2f})")
                        elif extracted_name:
                            print(
                                f"⚠️ Low IGDB confidence for '{extracted_name}': {data_confidence:.2f} - flagging for review")
                            # For low confidence, only keep extracted name as alternative
                            if canonical_name != extracted_name:
                                alternative_names = [extracted_name]

                        # Fallback series name extraction if IGDB doesn't provide one
                        series_name = igdb_series
                        if not series_name and extracted_name:
                            # Try to extract series from game name
                            # For titles like "God of War 3", extract "God of War"
                            # For titles like "Uncharted: The Lost Legacy", extract "Uncharted"
                            if ':' in extracted_name or '–' in extracted_name or '—' in extracted_name:
                                parts = re.split(r'[:\–\—]', extracted_name)
                                if parts and len(parts[0].strip()) >= 3:
                                    series_name = parts[0].strip()
                            else:
                                # Remove numbers from end (e.g., "God of War 3" → "God of War")
                                series_name = re.sub(r'\s+\d+\s*$', '', extracted_name).strip()
                                # If we removed something, use that as series, otherwise use canonical
                                if series_name == extracted_name:
                                    series_name = canonical_name

                        # Capture view_count from Twitch API
                        view_count = video.get('view_count', 0)

                        new_vods.append({
                            'title': title,
                            'url': video['url'],
                            'duration_seconds': parse_twitch_duration(video.get('duration', '0s')),
                            'view_count': view_count,  # NEW: Capture Twitch views
                            'published_at': created_at,
                            'canonical_name': canonical_name,
                            'alternative_names': alternative_names,
                            'series_name': series_name or canonical_name,
                            'genre': igdb_genre,
                            'release_year': igdb_year,
                            'igdb_id': igdb_id,
                            'data_confidence': data_confidence
                        })

                    cursor = videos_data.get('pagination', {}).get('cursor')
                    if not cursor:
                        break

        except Exception as e:
            print(f"❌ Failed to fetch new Twitch VODs: {e}")

    return new_vods


async def fetch_comprehensive_twitch_games(
        username: str) -> List[Dict[str, Any]]:
    """Fetch comprehensive game data from Twitch channel with full metadata"""
    twitch_client_id = os.getenv('TWITCH_CLIENT_ID')
    twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET')

    if not twitch_client_id or not twitch_client_secret:
        raise Exception(
            "TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET environment variables are required")

    games_data = []

    async with aiohttp.ClientSession() as session:
        try:
            # Get OAuth token
            token_url = "https://id.twitch.tv/oauth2/token"
            token_data = {
                'client_id': twitch_client_id,
                'client_secret': twitch_client_secret,
                'grant_type': 'client_credentials'
            }

            async with session.post(token_url, data=token_data) as response:
                if response.status == 200:
                    token_info = await response.json()
                    access_token = token_info['access_token']
                else:
                    raise Exception(
                        f"Failed to get Twitch OAuth token: {response.status}")

            headers = {
                "Client-ID": twitch_client_id,
                "Authorization": f"Bearer {access_token}"
            }

            # Get user ID
            user_url = f"https://api.twitch.tv/helix/users?login={username}"
            async with session.get(user_url, headers=headers) as response:
                if response.status == 200:
                    user_data = await response.json()
                    if user_data['data']:
                        user_id = user_data['data'][0]['id']
                    else:
                        raise Exception(f"Twitch user '{username}' not found")
                else:
                    raise Exception(
                        f"Failed to get Twitch user info: {response.status}")

            # Get comprehensive video data
            all_videos = []
            cursor = None

            # Fetch multiple pages of videos (limit to prevent excessive API
            # calls)
            while len(all_videos) < 500:  # Limit to prevent excessive API calls
                videos_url = f"https://api.twitch.tv/helix/videos"
                params = {
                    "user_id": user_id,
                    "first": 100,  # Max per request
                    "type": "all"
                }
                if cursor:
                    params["after"] = cursor

                async with session.get(videos_url, params=params, headers=headers) as response:
                    if response.status == 200:
                        videos_data = await response.json()
                        if not videos_data['data']:
                            break

                        all_videos.extend(videos_data['data'])
                        cursor = videos_data.get(
                            'pagination', {}).get('cursor')
                        if not cursor:
                            break
                    else:
                        break

            # Process videos into game series
            game_series = {}

            for video in all_videos:
                title = video['title']
                created_at = video['created_at']
                url = video['url']

                # Parse duration
                duration_str = video.get('duration', '0s')
                duration_seconds = parse_twitch_duration(duration_str)

                # Extract game name
                game_name = extract_game_name_from_title(title)
                if game_name:
                    if game_name not in game_series:
                        game_series[game_name] = {
                            'canonical_name': game_name,
                            'first_stream_date': created_at,
                            'total_episodes': 0,
                            'total_duration_seconds': 0,
                            'vod_urls': [],
                            'video_titles': []
                        }

                    series_info = game_series[game_name]
                    series_info['total_episodes'] += 1
                    series_info['total_duration_seconds'] += duration_seconds
                    series_info['vod_urls'].append(url)
                    series_info['video_titles'].append(title)

                    # Update first stream date if earlier
                    if created_at < series_info['first_stream_date']:
                        series_info['first_stream_date'] = created_at

            # Convert series data to game data format
            for game_name, series_info in game_series.items():
                # Only include games with multiple episodes
                if series_info['total_episodes'] >= 2:
                    game_data = {
                        'canonical_name': game_name,
                        'series_name': game_name,
                        "total_playtime_minutes": series_info["total_duration_seconds"] // 60,
                        "youtube_playlist_url": None,
                        # Limit to first 10 VODs
                        "twitch_vod_urls": series_info["vod_urls"][:10],
                        "notes": f"Auto-imported from Twitch. {series_info['total_episodes']} VODs found.",
                        'date_started': series_info['first_stream_date'],
                        'alternative_names': [game_name]
                    }
                    games_data.append(game_data)

        except Exception as e:
            raise Exception(
                f"Failed to fetch comprehensive Twitch games: {str(e)}")

    return games_data


def detect_multiple_games_in_title(title: str) -> List[str]:
    """
    Detect if a stream title mentions multiple games.
    Returns list of potential game names found in the title.

    Common patterns:
    - "Game A + Game B"
    - "Game A & Game B"
    - "Game A and Game B"
    - "Game A, Game B, Game C"

    Args:
        title: Stream title to analyze

    Returns:
        List of potential game names, or empty list if single game
    """
    potential_games = []

    # Common multi-game separators
    separators = [' + ', ' & ', ' and ', ', ']

    for sep in separators:
        if sep in title.lower():
            # Split on the separator
            parts = title.split(sep)

            # Only consider valid if we have 2-4 parts (reasonable multi-game scenario)
            if 2 <= len(parts) <= 4:
                # Clean each part
                cleaned_parts = []
                for part in parts:
                    cleaned = part.strip()
                    # Remove common prefixes/suffixes
                    cleaned = re.sub(r'\s*\((?:day|part|episode|ep)\s+\d+[^)]*\)', '', cleaned, flags=re.IGNORECASE)
                    cleaned = re.sub(
                        r'^\*?(DROPS?|NEW|SPONSORED?|LIVE)\*?\s*[-:]?\s*',
                        '',
                        cleaned,
                        flags=re.IGNORECASE)
                    cleaned = cleanup_game_name(cleaned)

                    # Only include if it looks like a game name (3+ chars, not generic)
                    if len(cleaned) >= 3 and not is_generic_term(cleaned):
                        cleaned_parts.append(cleaned)

                # If we got valid parts, use them
                if len(cleaned_parts) >= 2:
                    potential_games = cleaned_parts
                    break

    return potential_games


def parse_twitch_duration(duration: str) -> int:
    """Parse Twitch duration format (1h23m45s) to seconds"""
    if not duration:
        return 0

    total_seconds = 0

    # Parse hours
    hours_match = re.search(r'(\d+)h', duration.lower())
    if hours_match:
        total_seconds += int(hours_match.group(1)) * 3600

    # Parse minutes
    minutes_match = re.search(r'(\d+)m', duration.lower())
    if minutes_match:
        total_seconds += int(minutes_match.group(1)) * 60

    # Parse seconds
    seconds_match = re.search(r'(\d+)s', duration.lower())
    if seconds_match:
        total_seconds += int(seconds_match.group(1))

    return total_seconds


def format_twitch_vod_urls(vod_urls: List[str], max_display: int = 5) -> str:
    """Format Twitch VOD URLs for display"""
    if not vod_urls:
        return "No VODs available"

    vod_count = len(vod_urls)
    display_urls = vod_urls[:max_display]

    if vod_count <= max_display:
        return f"🎮 **{vod_count} Twitch VODs**\n" + \
            "\n".join([f"• [VOD {i+1}]({url})" for i, url in enumerate(display_urls)])
    else:
        formatted = f"🎮 **{vod_count} Twitch VODs** (showing first {max_display})\n"
        formatted += "\n".join([f"• [VOD {i+1}]({url})" for i,
                               url in enumerate(display_urls)])
        formatted += f"\n• ... and {vod_count - max_display} more VODs"
        return formatted


def get_twitch_api_credentials() -> tuple[Optional[str], Optional[str]]:
    """Get Twitch API credentials from environment"""
    twitch_client_id = os.getenv('TWITCH_CLIENT_ID')
    twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET')
    return twitch_client_id, twitch_client_secret


def has_twitch_credentials() -> bool:
    """Check if Twitch API credentials are available"""
    client_id, client_secret = get_twitch_api_credentials()
    return client_id is not None and client_secret is not None


async def validate_twitch_username(username: str) -> bool:
    """Validate if a Twitch username exists"""
    if not has_twitch_credentials():
        return False

    twitch_client_id, twitch_client_secret = get_twitch_api_credentials()

    async with aiohttp.ClientSession() as session:
        try:
            # Get OAuth token
            token_url = "https://id.twitch.tv/oauth2/token"
            token_data = {
                'client_id': twitch_client_id,
                'client_secret': twitch_client_secret,
                'grant_type': 'client_credentials'
            }

            async with session.post(token_url, data=token_data) as response:
                if response.status != 200:
                    return False

                token_info = await response.json()
                access_token = token_info['access_token']

            headers = {
                "Client-ID": twitch_client_id,
                "Authorization": f"Bearer {access_token}"
            }

            # Check if user exists
            user_url = f"https://api.twitch.tv/helix/users?login={username}"
            async with session.get(user_url, headers=headers) as response:
                if response.status == 200:
                    user_data = await response.json()
                    return len(user_data['data']) > 0
                else:
                    return False

        except Exception:
            return False


def extract_twitch_username_from_url(url: str) -> Optional[str]:
    """Extract Twitch username from various Twitch URL formats"""
    # Handle different Twitch URL formats
    patterns = [
        r'twitch\.tv/([a-zA-Z0-9_]+)',  # Basic username
        r'twitch\.tv/videos/\d+',       # VOD URL (can't extract username)
        r'twitch\.tv/([a-zA-Z0-9_]+)/video/\d+',  # User VOD URL
    ]

    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match and not match.group(1) in ['videos', 'clips', 'directory']:
            return match.group(1)

    return None


def is_valid_twitch_username(username: str) -> bool:
    """Check if a string looks like a valid Twitch username"""
    if not username:
        return False

    # Twitch usernames are 4-25 characters, alphanumeric + underscore
    return bool(re.match(r'^[a-zA-Z0-9_]{4,25}$', username))
