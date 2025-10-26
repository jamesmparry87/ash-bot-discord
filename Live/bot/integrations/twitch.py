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
from ..database import db

# IGDB integration
from . import igdb


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

            # Get recent videos
            videos_url = f"https://api.twitch.tv/helix/videos"
            params = {"user_id": user_id, "first": 100, "type": "archive"}  # 'archive' for past broadcasts

            async with session.get(videos_url, params=params, headers=headers) as response:
                if response.status != 200:
                    return []
                videos_data = await response.json()
                for video in videos_data['data']:
                    created_at = datetime.fromisoformat(video['created_at'].replace('Z', '+00:00'))
                    if created_at < start_timestamp:
                        break  # Stop when we find videos older than our sync time

                    title = video['title']
                    
                    # Extract game name from title
                    extracted_name = extract_game_name_from_title(title)
                    
                    if extracted_name:
                        # Validate with IGDB for better accuracy
                        print(f"🔍 Validating '{extracted_name}' with IGDB...")
                        igdb_result = await igdb.validate_and_enrich(extracted_name)
                        
                        # Use IGDB data if confidence is high enough
                        if igdb_result.get('confidence', 0) >= 0.8:
                            canonical_name = igdb_result.get('canonical_name', extracted_name)
                            igdb_id = igdb_result.get('igdb_id')
                            igdb_genre = igdb_result.get('genre')
                            igdb_series = igdb_result.get('series_name')
                            igdb_year = igdb_result.get('release_year')
                            data_confidence = igdb_result['confidence']
                            print(f"✅ IGDB validated: '{extracted_name}' → '{canonical_name}' (confidence: {data_confidence:.2f})")
                        else:
                            # Low confidence - use extracted name but flag for review
                            canonical_name = extracted_name
                            igdb_id = None
                            igdb_genre = None
                            igdb_series = None
                            igdb_year = None
                            data_confidence = igdb_result.get('confidence', 0.0)
                            print(f"⚠️ Low IGDB confidence for '{extracted_name}': {data_confidence:.2f} - flagging for review")
                    else:
                        # No game name extracted
                        canonical_name = None
                        igdb_id = None
                        igdb_genre = None
                        igdb_series = None
                        igdb_year = None
                        data_confidence = 0.0

                    new_vods.append({
                        'title': title,
                        'url': video['url'],
                        'duration_seconds': parse_twitch_duration(video.get('duration', '0s')),
                        'published_at': created_at,
                        'canonical_name': canonical_name,
                        'series_name': igdb_series,
                        'genre': igdb_genre,
                        'release_year': igdb_year,
                        'igdb_id': igdb_id,
                        'data_confidence': data_confidence
                    })
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


def extract_game_name_from_title(title: str) -> Optional[str]:
    """
    Extract game name from video/stream title using priority-based pattern matching.
    
    Handles common Twitch streaming title formats with focus on reliable indicators
    like "(day X)", "(part X)", "(episode X)" that typically precede the actual game name.
    
    Example: "Samurai School Dropout - Ghost of Yotei (day 9) Thanks @playstation #ad/gift"
             Would extract: "Ghost of Yotei"
    """
    if not title or len(title.strip()) < 2:
        return None
    
    cleaned_title = title.strip()
    
    # PRIORITY 1: Extract game name that appears before day/part/episode indicators
    # These are the most reliable patterns as they explicitly mark ongoing series
    priority_patterns = [
        # Matches: "- Game Name (day 9)" or "| Game Name (day 9)"
        r'[-|]\s*([^-|()\[\]]+?)\s*\((?:day|part|episode|ep)\s+\d+\)',
        # Matches: "- Game Name [day 9]" or "| Game Name [day 9]"
        r'[-|]\s*([^-|()\[\]]+?)\s*\[(?:day|part|episode|ep)\s+\d+\]',
        # Matches without separator: "Game Name (day 9)"
        r'^([^-|()\[\]]+?)\s*\((?:day|part|episode|ep)\s+\d+\)',
        # Matches: "Game Name - day 9" (less parentheses version)
        r'[-|]\s*([^-|]+?)\s*-\s*(?:day|part|episode|ep)\s+\d+',
    ]
    
    for pattern in priority_patterns:
        match = re.search(pattern, cleaned_title, re.IGNORECASE)
        if match:
            game_name = match.group(1).strip()
            
            # Clean up trailing metadata (Thanks, @mentions, #hashtags, etc.)
            game_name = re.sub(r'\s+(?:Thanks|Thx|@|#).*$', '', game_name, flags=re.IGNORECASE)
            game_name = re.sub(r'\s+(?:ft\.|feat\.|featuring).*$', '', game_name, flags=re.IGNORECASE)
            game_name = re.sub(r'\s*[|:]\s*$', '', game_name)  # Remove trailing separators
            
            # Final cleanup
            game_name = game_name.strip(' -|:')
            
            # Validate extracted name
            if len(game_name) >= 2 and not _is_generic_term(game_name):
                return game_name
    
    # PRIORITY 2: Look for clear game title before episode/part numbers
    # Handles formats like "Game Name - Episode 5" or "Game Name | Part 3"
    episode_patterns = [
        r'^([^-|]+?)\s*[-|]\s*(?:Episode|Part|Ep|Stream|VOD)\s*[#\d]',
        r'^([^-|]+?)\s*[-|]\s*S\d+E\d+',  # Season/Episode format
    ]
    
    for pattern in episode_patterns:
        match = re.search(pattern, cleaned_title, re.IGNORECASE)
        if match:
            game_name = match.group(1).strip()
            game_name = _cleanup_game_name(game_name)
            if len(game_name) >= 2 and not _is_generic_term(game_name):
                return game_name
    
    # PRIORITY 3: Fallback to general cleanup (existing logic)
    # Remove episode/part numbers and common patterns
    patterns_to_remove = [
        r'\s*-\s*Episode\s*\d+.*$',
        r'\s*-\s*Part\s*\d+.*$',
        r'\s*-\s*#\d+.*$',
        r'\s*\|\s*Episode\s*\d+.*$',
        r'\s*\|\s*Part\s*\d+.*$',
        r'\s*\[.*?\]',
        r'\s*\(.*?\)',
        r'\s*-\s*Ep\s*\d+.*$',
        r'\s*S\d+E\d+.*$',
        r'\s*-\s*Stream\s*\d+.*$',
        r'\s*-\s*VOD.*$',
    ]
    
    for pattern in patterns_to_remove:
        cleaned_title = re.sub(pattern, '', cleaned_title, flags=re.IGNORECASE)
    
    # Remove common streaming/gaming words
    streaming_words = [
        'stream', 'streaming', 'gameplay', 'playthrough',
        'let\'s play', 'gaming', 'live', 'vod'
    ]
    for word in streaming_words:
        cleaned_title = re.sub(rf'\b{word}\b', '', cleaned_title, flags=re.IGNORECASE)
    
    # Final cleanup
    cleaned_title = _cleanup_game_name(cleaned_title)
    
    # Validate final result
    if len(cleaned_title) < 2 or _is_generic_term(cleaned_title):
        return None
    
    return cleaned_title


def _cleanup_game_name(name: str) -> str:
    """Helper function to clean up extracted game name"""
    # Clean up whitespace and punctuation
    name = re.sub(r'\s+', ' ', name).strip()
    name = name.strip(' -|:')
    
    # Remove trailing metadata
    name = re.sub(r'\s+(?:Thanks|Thx|@|#).*$', '', name, flags=re.IGNORECASE)
    
    return name


def _is_generic_term(name: str) -> bool:
    """Helper function to check if extracted name is too generic"""
    generic_terms = [
        'live', 'stream', 'streaming', 'gaming', 'playing',
        'game', 'twitch', 'vod', 'gameplay', 'playthrough'
    ]
    return name.lower() in generic_terms


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
