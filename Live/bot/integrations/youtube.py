"""
YouTube Integration Module

Handles all YouTube API interactions including:
- Fetching game data from channels
- Parsing video metadata
- Auto-posting functionality
- Playlist management
"""

import asyncio
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

# Database import
from ..database import DatabaseManager, db


async def fetch_youtube_games(channel_id: str) -> List[str]:
    """Fetch game titles from YouTube channel using YouTube Data API"""
    # This requires YouTube Data API v3 key
    youtube_api_key = os.getenv('YOUTUBE_API_KEY')
    if not youtube_api_key:
        raise Exception("YOUTUBE_API_KEY not configured")

    games = []
    max_videos = 200  # Reasonable limit
    video_count = 0

    async with aiohttp.ClientSession() as session:
        try:
            # Get channel uploads playlist
            url = f"https://www.googleapis.com/youtube/v3/channels"
            params = {
                "part": "contentDetails",
                "id": channel_id,
                "key": youtube_api_key
            }

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data['items']:
                        uploads_playlist_id = data['items'][0]['contentDetails']['relatedPlaylists']['uploads']

                        next_page_token = None
                        while video_count < max_videos:
                            url = f"https://www.googleapis.com/youtube/v3/playlistItems"
                            params = {
                                'part': 'snippet',
                                'playlistId': uploads_playlist_id,
                                'maxResults': min(
                                    50,
                                    max_videos - video_count),
                                'key': youtube_api_key}
                            if next_page_token:
                                params['pageToken'] = next_page_token

                            async with session.get(url, params=params) as response:
                                if response.status == 200:
                                    data = await response.json()
                                    for item in data['items']:
                                        title = item['snippet']['title']
                                        # Extract game name from title (basic
                                        # parsing)
                                        game_name = extract_game_name_from_title(
                                            title)
                                        if game_name and game_name not in games:
                                            games.append(game_name)

                                    video_count += len(data['items'])
                                    next_page_token = data.get('nextPageToken')
                                    if not next_page_token:
                                        break
                                else:
                                    break
                else:
                    raise Exception(f"YouTube API error: {response.status}")

        except Exception as e:
            raise Exception(f"Failed to fetch YouTube games: {str(e)}")

    return games


async def fetch_comprehensive_youtube_games(
        channel_id: str) -> List[Dict[str, Any]]:
    """Fetch comprehensive game data from YouTube channel using playlists as primary source"""
    youtube_api_key = os.getenv('YOUTUBE_API_KEY')
    if not youtube_api_key:
        raise Exception("YOUTUBE_API_KEY not configured")

    games_data = []

    async with aiohttp.ClientSession() as session:
        try:
            # STEP 1: Get all playlists from the channel (primary source)
            url = f"https://www.googleapis.com/youtube/v3/playlists"
            params = {
                'part': 'snippet,contentDetails',
                'channelId': channel_id,
                'maxResults': 50,
                'key': youtube_api_key
            }

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    for playlist in data['items']:
                        playlist_id = playlist['id']
                        playlist_title = playlist['snippet']['title']
                        video_count = playlist['contentDetails']['itemCount']

                        # Skip if not a game playlist or has very few videos
                        if video_count < 3:
                            continue

                        # Skip certain types of playlists
                        skip_patterns = [
                            'shorts', 'live', 'stream', 'highlight', 'clip']
                        if any(pattern in playlist_title.lower()
                               for pattern in skip_patterns):
                            continue

                        # Extract canonical game name from playlist title
                        canonical_name = extract_game_name_from_title(
                            playlist_title)
                        if not canonical_name:
                            continue

                        # Get playlist creation date (first video date)
                        first_video_date = None
                        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"

                        # Get total playtime from videos in playlist
                        total_playtime_seconds = 0
                        video_ids = []

                        # Get all videos from playlist with their durations
                        playlist_items_url = f"https://www.googleapis.com/youtube/v3/playlistItems"
                        playlist_params = {
                            'part': 'snippet',
                            'playlistId': playlist_id,
                            'maxResults': 50,
                            'key': youtube_api_key
                        }

                        async with session.get(playlist_items_url, params=playlist_params) as playlist_response:
                            if playlist_response.status == 200:
                                playlist_data = await playlist_response.json()
                                for item in playlist_data['items']:
                                    video_id = item['snippet']['resourceId']['videoId']
                                    video_ids.append(video_id)

                                    # Get first video date for series start
                                    # date
                                    if not first_video_date:
                                        first_video_date = item['snippet']['publishedAt']

                        # Get video durations
                        if video_ids:
                            videos_url = f"https://www.googleapis.com/youtube/v3/videos"
                            videos_params = {
                                'part': 'contentDetails',
                                'id': ','.join(video_ids[:50]),  # API limit
                                'key': youtube_api_key
                            }

                            async with session.get(videos_url, params=videos_params) as videos_response:
                                if videos_response.status == 200:
                                    videos_data = await videos_response.json()
                                    for video in videos_data['items']:
                                        duration = video["contentDetails"]["duration"]
                                        duration_minutes = parse_youtube_duration(
                                            duration) // 60
                                        total_playtime_seconds += duration_minutes * 60

                        total_playtime_minutes = total_playtime_seconds // 60

                        game_data = {
                            'canonical_name': canonical_name,
                            'series_name': playlist_title,
                            'total_playtime_minutes': total_playtime_minutes,
                            'youtube_playlist_url': playlist_url,
                            'twitch_vod_urls': [],
                            'notes': f"Auto-imported from YouTube playlist '{playlist_title}'. {video_count} episodes, {total_playtime_minutes//60}h {total_playtime_minutes%60}m total.",
                            'date_started': first_video_date,
                            'alternative_names': [
                                playlist_title,
                                canonical_name]}
                        games_data.append(game_data)

                # STEP 2: Fallback - check uploads playlist for games not in
                # dedicated playlists
                try:
                    # Get channel uploads playlist
                    url = f"https://www.googleapis.com/youtube/v3/channels"
                    params = {
                        "part": "contentDetails",
                        "id": channel_id,
                        "key": youtube_api_key
                    }

                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data['items']:
                                uploads_playlist_id = data['items'][0]['contentDetails']['relatedPlaylists']['uploads']

                                # Get videos from uploads playlist
                                fallback_games = await parse_videos_for_games(session, uploads_playlist_id, youtube_api_key)
                                games_data.extend(fallback_games)

                except Exception as e:
                    print(f"Warning: Could not fetch uploads playlist: {e}")

        except Exception as e:
            raise Exception(
                f"Failed to fetch comprehensive YouTube games: {str(e)}")

    return games_data


async def parse_videos_for_games(
        session, uploads_playlist_id: str, youtube_api_key: str) -> List[Dict[str, Any]]:
    """Parse individual videos to extract game data (fallback method)"""
    games_data = []
    max_videos = 200
    video_count = 0

    # Track series of videos for same games
    game_series = {}

    try:
        next_page_token = None
        while video_count < max_videos:
            url = f"https://www.googleapis.com/youtube/v3/playlistItems"
            params = {
                'part': 'snippet',
                'playlistId': uploads_playlist_id,
                'maxResults': min(50, max_videos - video_count),
                'key': youtube_api_key
            }
            if next_page_token:
                params['pageToken'] = next_page_token

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    for item in data['items']:
                        title = item['snippet']['title']
                        published_at = item['snippet']['publishedAt']

                        # Extract game name
                        game_name = extract_game_name_from_title(title)
                        if game_name:
                            if game_name not in game_series:
                                game_series[game_name] = {
                                    'canonical_name': game_name,
                                    'first_video_date': published_at,
                                    'total_episodes': 0,
                                    'video_titles': []
                                }

                            game_series[game_name]['total_episodes'] += 1
                            game_series[game_name]['video_titles'].append(
                                title)

                    video_count += len(data['items'])
                    next_page_token = data.get('nextPageToken')
                    if not next_page_token:
                        break
                else:
                    break

        # Convert series data to game data format
        for game_name, series_info in game_series.items():
            # Only include games with multiple episodes
            if series_info['total_episodes'] >= 3:
                # Estimate 30 min per episode
                estimated_playtime = series_info['total_episodes'] * 30

                game_data = {
                    'canonical_name': game_name,
                    'series_name': game_name,
                    'total_playtime_minutes': estimated_playtime,
                    'youtube_playlist_url': None,
                    'twitch_vod_urls': [],
                    'notes': f"Auto-imported from YouTube videos. {series_info['total_episodes']} episodes found.",
                    'date_started': series_info['first_video_date'],
                    'alternative_names': [game_name]}
                games_data.append(game_data)

    except Exception as e:
        print(f"Warning: Error parsing videos for games: {e}")

    return games_data


def parse_youtube_duration(duration: str) -> int:
    """Parse YouTube ISO 8601 duration format (PT1H23M45S) to seconds"""
    if not duration.startswith('PT'):
        return 0

    duration = duration[2:]  # Remove 'PT'
    total_seconds = 0

    # Parse hours
    if 'H' in duration:
        hours_match = re.search(r'(\d+)H', duration)
        if hours_match:
            total_seconds += int(hours_match.group(1)) * 3600

    # Parse minutes
    if 'M' in duration:
        minutes_match = re.search(r'(\d+)M', duration)
        if minutes_match:
            total_seconds += int(minutes_match.group(1)) * 60

    # Parse seconds
    if 'S' in duration:
        seconds_match = re.search(r'(\d+)S', duration)
        if seconds_match:
            total_seconds += int(seconds_match.group(1))

    return total_seconds


def extract_game_name_from_title(title: str) -> Optional[str]:
    """Extract game name from video/playlist title using various patterns"""
    # Remove common prefixes/suffixes
    cleaned_title = title.strip()

    # Remove episode numbers and common patterns
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
        'gaming']
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

    generic_terms = ['live', 'stream', 'gaming', 'playing', 'game']
    if cleaned_title.lower() in generic_terms:
        return None

    return cleaned_title


async def execute_youtube_auto_post(
        reminder: Dict[str, Any], auto_action_data: Dict[str, Any]) -> None:
    """Execute automatic YouTube post to youtube-uploads channel"""
    try:
        from ..main import bot  # Import here to avoid circular imports

        youtube_url = auto_action_data.get("youtube_url")
        custom_message = auto_action_data.get("custom_message", "")
        user_id = reminder.get("user_id")

        if not youtube_url:
            print(f"❌ No YouTube URL found in auto-action data")
            return

        # Find youtube-uploads channel
        youtube_channel = None
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.name == "youtube-uploads":
                    youtube_channel = channel
                    break
            if youtube_channel:
                break

        if youtube_channel:
            ash_auto_message = f"⚡ **Auto-Action Protocol Executed**\n\n{custom_message}\n\n"
            ash_auto_message += (
                f"{youtube_url}\n\n*Auto-posted by Science Officer Ash on behalf of <@{user_id}>. Efficiency maintained.*"
            )
            await youtube_channel.send(ash_auto_message)

            # Send notification to user
            if user_id:
                user = bot.get_user(int(user_id))
                if user:
                    notification = f"⚡ **Auto-action executed successfully.** Your YouTube link has been posted to the youtube-uploads channel as scheduled. Mission parameters fulfilled."
                    await user.send(notification)
                else:
                    print(
                        f"❌ Could not find user {user_id} to send notification")
        else:
            print(f"❌ Could not find youtube-uploads channel")

    except Exception as e:
        print(f"❌ Error executing YouTube auto-post: {e}")


async def update_youtube_playlist_data(
        games_data: List[Dict[str, Any]]) -> int:
    """Update YouTube playlist data for games that have playlist URLs"""
    try:
        if not db:
            return 0

        updated_count = 0
        youtube_api_key = os.getenv('YOUTUBE_API_KEY')

        if not youtube_api_key:
            return 0

        async with aiohttp.ClientSession() as session:
            for game in games_data:
                try:
                    playlist_url = game.get('youtube_playlist_url')
                    if not playlist_url:
                        continue

                    # Extract playlist ID
                    playlist_id_match = re.search(
                        r'list=([a-zA-Z0-9_-]+)', playlist_url)
                    if not playlist_id_match:
                        continue

                    playlist_id = playlist_id_match.group(1)

                    # Get current video count and playtime
                    playlist_url_api = f"https://www.googleapis.com/youtube/v3/playlists"
                    params = {
                        "part": "contentDetails",
                        "id": playlist_id,
                        "key": youtube_api_key
                    }

                    async with session.get(playlist_url_api, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data['items']:
                                current_video_count = data['items'][0]['contentDetails']['itemCount']

                                # Get video IDs from playlist
                                playlist_items_url = f"https://www.googleapis.com/youtube/v3/playlistItems"
                                playlist_params = {
                                    'part': 'snippet',
                                    'playlistId': playlist_id,
                                    'maxResults': 50,
                                    'key': youtube_api_key
                                }

                                video_ids = []
                                async with session.get(playlist_items_url, params=playlist_params) as playlist_response:
                                    if playlist_response.status == 200:
                                        playlist_data = await playlist_response.json()
                                        for item in playlist_data['items']:
                                            video_id = item['snippet']['resourceId']['videoId']
                                            video_ids.append(video_id)

                                # Get video durations
                                total_playtime_seconds = 0
                                if video_ids:
                                    videos_url = f"https://www.googleapis.com/youtube/v3/videos"
                                    videos_params = {
                                        'part': 'contentDetails',
                                        'id': ','.join(video_ids[:50]),
                                        'key': youtube_api_key
                                    }

                                    async with session.get(videos_url, params=videos_params) as videos_response:
                                        if videos_response.status == 200:
                                            videos_data = await videos_response.json()
                                            for video in videos_data['items']:
                                                duration = video["contentDetails"]["duration"]
                                                duration_minutes = parse_youtube_duration(
                                                    duration) // 60
                                                total_playtime_seconds += duration_minutes * 60

                                total_playtime_minutes = total_playtime_seconds // 60

                                # Update database with new data
                                canonical_name = game.get('canonical_name')
                                if canonical_name and total_playtime_minutes > 0:
                                    # Get the game by name first, then update
                                    # it
                                    existing_game = db.get_played_game(  # type: ignore
                                        canonical_name)  # type: ignore
                                    if existing_game:
                                        success = db.update_played_game(  # type: ignore
                                            existing_game['id'], total_playtime_minutes=total_playtime_minutes)  # type: ignore
                                        if success:
                                            updated_count += 1

                except Exception as e:
                    print(
                        f"Error updating YouTube data for {game.get('canonical_name', 'unknown')}: {e}")

        return updated_count

    except Exception as e:
        print(f"Error in update_youtube_playlist_data: {e}")
        return 0


def extract_youtube_urls(text: str) -> List[str]:
    """Extract YouTube URLs from text"""
    youtube_url_pattern = r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]+)'
    youtube_urls = re.findall(youtube_url_pattern, text, re.IGNORECASE)
    return [f"https://youtube.com/watch?v={url_id}" for url_id in youtube_urls]


def has_youtube_content(text: str) -> bool:
    """Check if text contains YouTube-related content"""
    youtube_urls = extract_youtube_urls(text)
    return len(youtube_urls) > 0 or "youtube" in text.lower()
