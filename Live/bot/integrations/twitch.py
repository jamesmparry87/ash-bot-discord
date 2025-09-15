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
    """Extract game name from video/stream title using various patterns"""
    # Remove common prefixes/suffixes
    cleaned_title = title.strip()

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
        'stream',
        'streaming',
        'gameplay',
        'playthrough',
        'let\'s play',
        'gaming',
        'live',
        'vod']
    for word in streaming_words:
        cleaned_title = re.sub(
            rf'\b{word}\b',
            '',
            cleaned_title,
            flags=re.IGNORECASE)

    # Clean up whitespace and punctuation
    cleaned_title = re.sub(r'\s+', ' ', cleaned_title).strip()
    cleaned_title = cleaned_title.strip(' -|:')

    # Return None if title is too short or generic
    if len(cleaned_title) < 2:
        return None

    generic_terms = [
        'live',
        'stream',
        'gaming',
        'playing',
        'game',
        'twitch',
        'vod']
    if cleaned_title.lower() in generic_terms:
        return None

    return cleaned_title


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
