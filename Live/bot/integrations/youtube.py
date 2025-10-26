"""
YouTube Integration Module

Handles all YouTube API interactions including:
- Fetching game data from channels
- Parsing video metadata
- Auto-posting functionality
- Playlist management
- IGDB validation for game names
"""

import asyncio
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

# Database import
from ..database import DatabaseManager, db

# Text processing utilities
from ..utils.text_processing import extract_game_name_from_title

# IGDB integration
from . import igdb


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


async def execute_youtube_auto_post(
        reminder: Dict[str, Any], auto_action_data: Dict[str, Any]) -> None:
    """Execute automatic YouTube post to youtube-uploads channel"""
    try:
        # Import the global bot instance from scheduled tasks
        from ..tasks.scheduled import _bot_instance

        if not _bot_instance:
            print("❌ Bot instance not available for YouTube auto-post")
            return

        youtube_url = auto_action_data.get("youtube_url")
        custom_message = auto_action_data.get("custom_message", "")
        user_id = reminder.get("user_id")

        if not youtube_url:
            print(f"❌ No YouTube URL found in auto-action data")
            return

        # Find youtube-uploads channel
        youtube_channel = None
        for guild in _bot_instance.guilds:
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
                user = _bot_instance.get_user(int(user_id))
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


async def fetch_new_videos_since(channel_id: str, start_timestamp: datetime) -> List[Dict[str, Any]]:
    """Fetch all new videos from a channel's uploads playlist since a given timestamp."""
    youtube_api_key = os.getenv('YOUTUBE_API_KEY')
    if not youtube_api_key:
        print("⚠️ YOUTUBE_API_KEY not configured for fetching new videos.")
        return []

    new_videos = []
    async with aiohttp.ClientSession() as session:
        try:
            # 1. Get the channel's uploads playlist ID
            url = "https://www.googleapis.com/youtube/v3/channels"
            params = {"part": "contentDetails", "id": channel_id, "key": youtube_api_key}
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return []
                data = await response.json()
                uploads_playlist_id = data['items'][0]['contentDetails']['relatedPlaylists']['uploads']

            # 2. Paginate through the playlist to find new videos
            next_page_token = None
            while True:
                url = "https://www.googleapis.com/youtube/v3/playlistItems"
                params = {
                    'part': 'snippet',
                    'playlistId': uploads_playlist_id,
                    'maxResults': 50,
                    'key': youtube_api_key
                }
                if next_page_token:
                    params['pageToken'] = next_page_token

                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        break
                    data = await response.json()

                    for item in data['items']:
                        published_at = datetime.fromisoformat(item['snippet']['publishedAt'].replace('Z', '+00:00'))
                        # If video is older than our start time, stop searching
                        if published_at < start_timestamp:
                            # Break the outer loop
                            return new_videos

                        video_details = {
                            'title': item['snippet']['title'],
                            'video_id': item['snippet']['resourceId']['videoId'],
                            'published_at': published_at
                        }
                        new_videos.append(video_details)

                    next_page_token = data.get('nextPageToken')
                    if not next_page_token:
                        break
        except Exception as e:
            print(f"❌ Failed to fetch new YouTube videos: {e}")

    # After fetching IDs, get their stats (duration, views) in a batch
    if new_videos:
        video_ids = [v['video_id'] for v in new_videos]
        async with aiohttp.ClientSession() as session:
            stats = await get_video_statistics(session, video_ids, youtube_api_key)
            for video in new_videos:
                if video['video_id'] in stats:
                    video.update(stats[video['video_id']])

    return new_videos


async def fetch_playlist_based_content_since(channel_id: str, start_timestamp: datetime) -> List[Dict[str, Any]]:
    """
    Fetch new content from YouTube playlists since a given timestamp.

    This function:
    - Groups videos by their playlists
    - Extracts game names from playlist titles (not individual video titles)
    - Detects [COMPLETED] status from playlist titles
    - Populates complete metadata: series_name, youtube_playlist_url, completion_status, etc.
    - Aggregates views, playtime, and episode count per playlist

    Returns a list of game data dictionaries with complete metadata.
    """
    youtube_api_key = os.getenv('YOUTUBE_API_KEY')
    if not youtube_api_key:
        print("⚠️ YOUTUBE_API_KEY not configured")
        return []

    games_data = []

    async with aiohttp.ClientSession() as session:
        try:
            # Step 1: Get all playlists from the channel
            print(f"🔄 Fetching playlists from channel {channel_id}")
            url = f"https://www.googleapis.com/youtube/v3/playlists"
            params = {
                'part': 'snippet,contentDetails',
                'channelId': channel_id,
                'maxResults': 50,
                'key': youtube_api_key
            }

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    print(f"❌ YouTube API error: {response.status}")
                    return []

                data = await response.json()

                # Step 2: Process each playlist
                for playlist in data['items']:
                    try:
                        playlist_id = playlist['id']
                        playlist_title = playlist['snippet']['title']
                        video_count = playlist['contentDetails']['itemCount']

                        # Skip non-game playlists
                        if video_count < 3:
                            continue

                        skip_patterns = ['shorts', 'live', 'stream', 'highlight', 'clip']
                        if any(pattern in playlist_title.lower() for pattern in skip_patterns):
                            continue

                        # Check if playlist has content since start_timestamp
                        has_new_content = await playlist_has_new_content(
                            session, playlist_id, start_timestamp, youtube_api_key
                        )

                        if not has_new_content:
                            continue

                        print(f"✅ Processing playlist: {playlist_title}")

                        # Detect completion status from playlist title
                        completion_status = 'completed' if '[COMPLETED]' in playlist_title.upper() else 'in_progress'

                        # Extract clean canonical name (remove [COMPLETED] and other markers)
                        clean_title = playlist_title.replace('[COMPLETED]', '').replace('[completed]', '').strip()
                        extracted_name = extract_game_name_from_title(clean_title)

                        if not extracted_name:
                            print(f"⚠️ Could not extract game name from: {playlist_title}")
                            continue

                        # Validate with IGDB for better accuracy
                        print(f"🔍 Validating '{extracted_name}' with IGDB...")
                        igdb_result = await igdb.validate_and_enrich(extracted_name)

                        # Set defaults for low-confidence or no-match scenarios
                        canonical_name = extracted_name
                        igdb_id = None
                        igdb_genre = None
                        igdb_series = None
                        igdb_year = None
                        data_confidence = igdb_result.get('confidence', 0.0)

                        # Use IGDB data if confidence is high enough
                        if data_confidence >= 0.8:
                            canonical_name = igdb_result.get('canonical_name', extracted_name)
                            igdb_id = igdb_result.get('igdb_id')
                            igdb_genre = igdb_result.get('genre')
                            igdb_series = igdb_result.get('series_name')
                            igdb_year = igdb_result.get('release_year')
                            print(
                                f"✅ IGDB validated: '{extracted_name}' → '{canonical_name}' (confidence: {data_confidence:.2f})")
                        else:
                            print(
                                f"⚠️ Low IGDB confidence for '{extracted_name}': {data_confidence:.2f} - flagging for review")

                        # Get all videos from this playlist with statistics
                        videos_data = await get_playlist_videos_with_views(session, playlist_id, youtube_api_key)

                        if not videos_data:
                            continue

                        # Calculate aggregated statistics
                        total_views = sum(v.get('view_count', 0) for v in videos_data)
                        total_playtime_seconds = sum(v.get('duration_seconds', 0) for v in videos_data)
                        total_playtime_minutes = total_playtime_seconds // 60
                        total_episodes = len(videos_data)

                        # Get first video date
                        first_video_date = None
                        if videos_data:
                            first_video_date = videos_data[0].get('published_at')

                        # Build alternative names from video titles
                        alternative_names = [playlist_title, canonical_name]
                        for video in videos_data[:5]:  # Sample first 5 video titles
                            alt_name = extract_game_name_from_title(video['title'])
                            if alt_name and alt_name not in alternative_names:
                                alternative_names.append(alt_name)

                        # Create complete game data entry with IGDB enrichment
                        game_data = {
                            'canonical_name': canonical_name,
                            'series_name': igdb_series or playlist_title,  # Use IGDB series if available
                            'genre': igdb_genre,  # From IGDB
                            'release_year': igdb_year,  # From IGDB
                            'total_playtime_minutes': total_playtime_minutes,
                            'total_episodes': total_episodes,
                            'youtube_playlist_url': f"https://youtube.com/playlist?list={playlist_id}",
                            'youtube_views': total_views,
                            'completion_status': completion_status,
                            'alternative_names': alternative_names,
                            'first_played_date': first_video_date,
                            'igdb_id': igdb_id,  # IGDB tracking
                            'data_confidence': data_confidence,  # Confidence score
                            'notes': f"Auto-synced from YouTube playlist. {total_episodes} episodes, {total_playtime_minutes//60}h {total_playtime_minutes%60}m total."
                        }

                        games_data.append(game_data)
                        print(
                            f"✅ Processed: {canonical_name} - {total_episodes} episodes, {total_views:,} views, status: {completion_status}")

                    except Exception as playlist_error:
                        print(
                            f"⚠️ Error processing playlist '{playlist.get('snippet', {}).get('title', 'Unknown')}': {playlist_error}")
                        continue

        except Exception as e:
            print(f"❌ Failed to fetch playlist-based content: {e}")
            return []

    print(f"✅ Fetched {len(games_data)} games from playlists")
    return games_data


async def playlist_has_new_content(session, playlist_id: str, start_timestamp: datetime, api_key: str) -> bool:
    """Check if a playlist has any videos published since the start timestamp."""
    try:
        url = f"https://www.googleapis.com/youtube/v3/playlistItems"
        params = {
            'part': 'snippet',
            'playlistId': playlist_id,
            'maxResults': 5,  # Just check the most recent videos
            'key': api_key
        }

        async with session.get(url, params=params) as response:
            if response.status != 200:
                return False

            data = await response.json()

            for item in data.get('items', []):
                published_at = datetime.fromisoformat(item['snippet']['publishedAt'].replace('Z', '+00:00'))
                if published_at >= start_timestamp:
                    return True

            return False

    except Exception as e:
        print(f"⚠️ Error checking playlist for new content: {e}")
        return False


def extract_youtube_urls(text: str) -> List[str]:
    """Extract YouTube URLs from text"""
    youtube_url_pattern = r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]+)'
    youtube_urls = re.findall(youtube_url_pattern, text, re.IGNORECASE)
    return [f"https://youtube.com/watch?v={url_id}" for url_id in youtube_urls]


async def get_most_viewed_game_overall(channel_id: str = "UCPoUxLHeTnE9SUDAkqfJzDQ") -> Optional[Dict[str, Any]]:
    """
    Query YouTube API to find the most viewed game across all of Jonesy's content.

    Returns:
        A dictionary containing the full ranked list of games: {'full_rankings': [...]}
    """
    try:
        youtube_api_key = os.getenv('YOUTUBE_API_KEY')
        if not youtube_api_key:
            print("⚠️ YouTube API key not configured for overall analytics")
            return None

        print(f"🔄 Fetching overall YouTube analytics for channel: {channel_id}")

        async with aiohttp.ClientSession() as session:
            # Step 1: Get all playlists from the channel
            url = f"https://www.googleapis.com/youtube/v3/playlists"
            params = {
                'part': 'snippet,contentDetails',
                'channelId': channel_id,
                'maxResults': 50,
                'key': youtube_api_key
            }

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    print(f"YouTube API error: {response.status}")
                    return None

                data = await response.json()

                game_analytics = []

                # Step 2: Process each playlist to calculate total views
                for playlist in data['items']:
                    try:
                        playlist_id = playlist['id']
                        playlist_title = playlist['snippet']['title']
                        video_count = playlist['contentDetails']['itemCount']

                        if video_count < 3:
                            continue

                        skip_patterns = ['shorts', 'live', 'stream', 'highlight', 'clip']
                        if any(pattern in playlist_title.lower() for pattern in skip_patterns):
                            continue

                        canonical_name = extract_game_name_from_title(playlist_title)
                        if not canonical_name:
                            continue

                        print(f"📊 Analyzing playlist: {playlist_title} ({video_count} videos)")

                        videos_data = await get_playlist_videos_with_views(session, playlist_id, youtube_api_key)

                        if videos_data:
                            total_views = sum(video.get('view_count', 0) for video in videos_data)

                            game_analytics.append({
                                'canonical_name': canonical_name,
                                'youtube_views': total_views,  # Use the key expected by the database/handler
                                'total_episodes': len(videos_data),
                            })

                    except Exception as playlist_error:
                        print(
                            f"⚠️ Error processing playlist {playlist.get('snippet', {}).get('title', 'Unknown')}: {playlist_error}")
                        continue

                if not game_analytics:
                    print("❌ No valid game playlists found for analysis")
                    return None

                # --- MODIFICATION START ---
                # Sort the full list by views
                game_analytics.sort(key=lambda x: x['youtube_views'], reverse=True)

                print(f"✅ Overall YouTube analytics complete. Found {len(game_analytics)} ranked games.")

                # Return the full list in the format expected by the message handler
                return {'full_rankings': game_analytics}
                # --- MODIFICATION END ---

    except Exception as e:
        print(f"❌ Error in get_most_viewed_game_overall: {e}")
        return None

    """
    Query YouTube API to find the most viewed game across all of Jonesy's content.

    Returns:
        Dict with most viewed game data or None if unavailable
    """
    try:
        youtube_api_key = os.getenv('YOUTUBE_API_KEY')
        if not youtube_api_key:
            print("⚠️ YouTube API key not configured for overall analytics")
            return None

        print(f"🔄 Fetching overall YouTube analytics for channel: {channel_id}")

        async with aiohttp.ClientSession() as session:
            # Step 1: Get all playlists from the channel
            url = f"https://www.googleapis.com/youtube/v3/playlists"
            params = {
                'part': 'snippet,contentDetails',
                'channelId': channel_id,
                'maxResults': 50,
                'key': youtube_api_key
            }

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    print(f"YouTube API error: {response.status}")
                    return None

                data = await response.json()

                game_analytics = []

                # Step 2: Process each playlist to calculate total views
                for playlist in data['items']:
                    try:
                        playlist_id = playlist['id']
                        playlist_title = playlist['snippet']['title']
                        video_count = playlist['contentDetails']['itemCount']

                        # Skip playlists with very few videos or non-game content
                        if video_count < 3:
                            continue

                        skip_patterns = ['shorts', 'live', 'stream', 'highlight', 'clip']
                        if any(pattern in playlist_title.lower() for pattern in skip_patterns):
                            continue

                        # Extract canonical game name
                        canonical_name = extract_game_name_from_title(playlist_title)
                        if not canonical_name:
                            continue

                        print(f"📊 Analyzing playlist: {playlist_title} ({video_count} videos)")

                        # Get all videos from this playlist with view counts
                        videos_data = await get_playlist_videos_with_views(session, playlist_id, youtube_api_key)

                        if videos_data:
                            total_views = sum(video.get('view_count', 0) for video in videos_data)
                            total_likes = sum(video.get('like_count', 0) for video in videos_data)
                            average_views = total_views / len(videos_data) if videos_data else 0

                            game_analytics.append({
                                'canonical_name': canonical_name,
                                'playlist_title': playlist_title,
                                'total_views': total_views,
                                'total_videos': len(videos_data),
                                'average_views_per_episode': round(average_views),
                                'total_likes': total_likes,
                                'playlist_id': playlist_id,
                                'videos_data': videos_data[:5]  # Keep top 5 videos for detailed analysis
                            })

                    except Exception as playlist_error:
                        print(
                            f"⚠️ Error processing playlist {playlist.get('snippet', {}).get('title', 'Unknown')}: {playlist_error}")
                        continue

                # Step 3: Find the most viewed game
                if not game_analytics:
                    print("❌ No valid game playlists found for analysis")
                    return None

                # Sort by total views
                game_analytics.sort(key=lambda x: x['total_views'], reverse=True)
                most_viewed = game_analytics[0]

                # Find most viewed individual episode
                most_viewed_episode = max(
                    most_viewed['videos_data'], key=lambda x: x.get(
                        'view_count', 0)) if most_viewed['videos_data'] else None

                result = {
                    'query_type': 'most_viewed_overall',
                    'most_viewed_game': {
                        'name': most_viewed['canonical_name'],
                        'playlist_title': most_viewed['playlist_title'],
                        'total_views': most_viewed['total_views'],
                        'total_episodes': most_viewed['total_videos'],
                        'average_views_per_episode': most_viewed['average_views_per_episode'],
                        'total_likes': most_viewed['total_likes']
                    },
                    'runner_up': {
                        'name': game_analytics[1]['canonical_name'],
                        'total_views': game_analytics[1]['total_views']
                    } if len(game_analytics) > 1 else None,
                    'total_games_analyzed': len(game_analytics),
                    'most_viewed_episode': {
                        'title': most_viewed_episode['title'],
                        'view_count': most_viewed_episode.get('view_count', 0),
                        'episode_number': most_viewed_episode.get('position', 0) + 1
                    } if most_viewed_episode else None
                }

                print(
                    f"✅ Overall YouTube analytics complete: '{most_viewed['canonical_name']}' with {most_viewed['total_views']:,} total views")
                print(f"📊 DEBUG - Result structure: {result}")
                print(f"📊 DEBUG - Most viewed game name: {result['most_viewed_game']['name']}")
                print(f"📊 DEBUG - Total views: {result['most_viewed_game']['total_views']}")
                return result

    except Exception as e:
        print(f"❌ Error in get_most_viewed_game_overall: {e}")
        return None


async def get_youtube_analytics_for_game(game_name: str, query_type: str = "general") -> Optional[Dict[str, Any]]:
    """
    Get YouTube analytics for a specific game with intelligent query handling.

    Args:
        game_name: Name of the game to analyze
        query_type: Type of analysis ('most_viewed_episode', 'least_viewed_episode',
                   'total_series_views', 'episode_breakdown', 'general')

    Returns:
        Dict with analytics data or None if unavailable
    """
    try:
        youtube_api_key = os.getenv('YOUTUBE_API_KEY')
        if not youtube_api_key:
            print("⚠️ YouTube API key not configured")
            return None

        # Jonesy's channel ID
        JONESY_CHANNEL_ID = "UCPoUxLHeTnE9SUDAkqfJzDQ"

        print(f"🔄 Fetching YouTube analytics for '{game_name}' (query type: {query_type})")

        async with aiohttp.ClientSession() as session:
            # Step 1: Find the playlist for this specific game
            playlist_data = await find_game_playlist(session, JONESY_CHANNEL_ID, game_name, youtube_api_key)

            if not playlist_data:
                print(f"⚠️ No YouTube playlist found for '{game_name}'")
                return None

            # Step 2: Get detailed video data with view counts
            videos_data = await get_playlist_videos_with_views(
                session, playlist_data['playlist_id'], youtube_api_key)

            if not videos_data:
                print(f"⚠️ No video data retrieved for '{game_name}'")
                return None

            # Step 3: Analyze based on query type
            analytics_result = analyze_video_analytics(videos_data, playlist_data, query_type)

            print(f"✅ YouTube analytics complete for '{game_name}': {query_type}")
            return analytics_result

    except Exception as e:
        print(f"❌ Error in YouTube analytics for '{game_name}': {e}")
        return None


async def find_game_playlist(session, channel_id: str, game_name: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Find the YouTube playlist that matches the given game name."""
    try:
        # Get all playlists from the channel
        url = f"https://www.googleapis.com/youtube/v3/playlists"
        params = {
            'part': 'snippet,contentDetails',
            'channelId': channel_id,
            'maxResults': 50,
            'key': api_key
        }

        async with session.get(url, params=params) as response:
            if response.status != 200:
                print(f"YouTube API error: {response.status}")
                return None

            data = await response.json()

            # Search for playlist matching the game name
            game_name_lower = game_name.lower()

            # Clean game name for better matching
            game_name_clean = clean_game_name_for_matching(game_name_lower)

            best_match = None
            best_score = 0

            for playlist in data['items']:
                playlist_title = playlist['snippet']['title'].lower()
                playlist_clean = clean_game_name_for_matching(playlist_title)

                # Calculate match score
                score = calculate_playlist_match_score(game_name_clean, playlist_clean, playlist_title)

                if score > best_score and score > 0.5:  # Minimum threshold
                    best_score = score
                    best_match = {
                        'playlist_id': playlist['id'],
                        'title': playlist['snippet']['title'],
                        'video_count': playlist['contentDetails']['itemCount'],
                        'match_score': score
                    }

            if best_match:
                print(f"✅ Found playlist: '{best_match['title']}' (score: {best_match['match_score']:.2f})")
                return best_match
            else:
                print(f"❌ No matching playlist found for '{game_name}'")
                return None

    except Exception as e:
        print(f"❌ Error finding game playlist: {e}")
        return None


def clean_game_name_for_matching(name: str) -> str:
    """Clean game name for better matching."""
    import re

    # Remove common patterns
    cleaned = re.sub(r'\s*-\s*(episode|part|ep)\s*\d+.*$', '', name)
    cleaned = re.sub(r'\s*\(\d{4}\)', '', cleaned)  # Remove year
    cleaned = re.sub(r'\s*[:\-\|].*$', '', cleaned)  # Remove subtitle after colon/dash
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def calculate_playlist_match_score(game_name: str, playlist_name: str, original_playlist: str) -> float:
    """Calculate how well a playlist matches a game name."""
    score = 0.0

    # Exact match bonus
    if game_name == playlist_name:
        score += 1.0
    elif game_name in playlist_name:
        score += 0.8
    elif playlist_name in game_name:
        score += 0.7

    # Word-by-word matching
    game_words = set(game_name.split())
    playlist_words = set(playlist_name.split())

    if game_words and playlist_words:
        common_words = game_words.intersection(playlist_words)
        word_score = len(common_words) / max(len(game_words), len(playlist_words))
        score += word_score * 0.6

    # Special game handling
    special_cases = {
        'god of war': ['gow', 'god of war'],
        'grand theft auto': ['gta', 'grand theft auto'],
        'call of duty': ['cod', 'call of duty'],
        'assassins creed': ['ac', 'assassin', 'creed']
    }

    for canonical, variants in special_cases.items():
        if canonical in game_name:
            for variant in variants:
                if variant in original_playlist.lower():
                    score += 0.5
                    break

    return min(score, 1.0)


async def get_playlist_videos_with_views(session, playlist_id: str, api_key: str) -> Optional[List[Dict[str, Any]]]:
    """Get all videos from a playlist with their view counts."""
    try:
        videos = []
        next_page_token = None

        while True:
            # Get playlist items
            url = f"https://www.googleapis.com/youtube/v3/playlistItems"
            params = {
                'part': 'snippet',
                'playlistId': playlist_id,
                'maxResults': 50,
                'key': api_key
            }
            if next_page_token:
                params['pageToken'] = next_page_token

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    print(f"YouTube API error: {response.status}")
                    return None

                data = await response.json()

                # Extract video IDs and basic info
                video_ids = []
                video_info = {}

                for item in data['items']:
                    video_id = item['snippet']['resourceId']['videoId']
                    video_ids.append(video_id)
                    video_info[video_id] = {
                        'title': item['snippet']['title'],
                        'published_at': item['snippet']['publishedAt'],
                        'position': item['snippet']['position']
                    }

                # Get detailed video statistics (including view counts)
                if video_ids:
                    stats_data = await get_video_statistics(session, video_ids, api_key)

                    # Combine info with stats
                    for video_id, stats in stats_data.items():
                        if video_id in video_info:
                            video_data = video_info[video_id]
                            video_data.update(stats)
                            video_data['video_id'] = video_id
                            videos.append(video_data)

                next_page_token = data.get('nextPageToken')
                if not next_page_token:
                    break

        print(f"✅ Retrieved {len(videos)} videos with view data")
        return videos

    except Exception as e:
        print(f"❌ Error getting playlist videos with views: {e}")
        return None


async def get_video_statistics(session, video_ids: List[str], api_key: str) -> Dict[str, Dict[str, Any]]:
    """Get detailed statistics for a list of video IDs."""
    try:
        stats_data = {}

        # Process in chunks of 50 (API limit)
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i + 50]

            url = f"https://www.googleapis.com/youtube/v3/videos"
            params = {
                'part': 'statistics,contentDetails',
                'id': ','.join(chunk),
                'key': api_key
            }

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    print(f"YouTube API error: {response.status}")
                    continue

                data = await response.json()

                for item in data['items']:
                    video_id = item['id']
                    stats = item['statistics']
                    content_details = item['contentDetails']

                    stats_data[video_id] = {
                        'view_count': int(stats.get('viewCount', 0)),
                        'like_count': int(stats.get('likeCount', 0)),
                        'comment_count': int(stats.get('commentCount', 0)),
                        'duration': content_details.get('duration', ''),
                        'duration_seconds': parse_youtube_duration(content_details.get('duration', ''))
                    }

        return stats_data

    except Exception as e:
        print(f"❌ Error getting video statistics: {e}")
        return {}


def analyze_video_analytics(videos: List[Dict[str, Any]],
                            playlist_data: Dict[str, Any], query_type: str) -> Dict[str, Any]:
    """Analyze video data based on query type."""
    try:
        if not videos:
            return {'error': 'No video data available'}

        # Sort videos by position/episode order
        videos.sort(key=lambda x: x.get('position', 0))

        result = {
            'game_name': playlist_data['title'],
            'total_videos': len(videos),
            'query_type': query_type,
            'total_views': sum(v.get('view_count', 0) for v in videos),
            'average_views': sum(v.get('view_count', 0) for v in videos) / len(videos) if videos else 0
        }

        if query_type == 'most_viewed_episode':
            most_viewed = max(videos, key=lambda x: x.get('view_count', 0))
            result.update({
                'most_viewed_video': {
                    'title': most_viewed['title'],
                    'view_count': most_viewed.get('view_count', 0),
                    'episode_number': most_viewed.get('position', 0) + 1,
                    'video_id': most_viewed['video_id']
                }
            })

        elif query_type == 'least_viewed_episode':
            least_viewed = min(videos, key=lambda x: x.get('view_count', 0))
            result.update({
                'least_viewed_video': {
                    'title': least_viewed['title'],
                    'view_count': least_viewed.get('view_count', 0),
                    'episode_number': least_viewed.get('position', 0) + 1,
                    'video_id': least_viewed['video_id']
                }
            })

        elif query_type == 'episode_breakdown':
            result['episodes'] = [
                {
                    'episode_number': video.get('position', 0) + 1,
                    'title': video['title'],
                    'view_count': video.get('view_count', 0),
                    'video_id': video['video_id']
                }
                for video in videos[:10]  # Limit to first 10 episodes
            ]

        elif query_type == 'general':
            # Provide general analytics
            if len(videos) >= 2:
                most_viewed = max(videos, key=lambda x: x.get('view_count', 0))
                result.update({
                    'most_viewed_episode': {
                        'title': most_viewed['title'],
                        'view_count': most_viewed.get('view_count', 0),
                        'episode_number': most_viewed.get('position', 0) + 1
                    }
                })

        return result

    except Exception as e:
        print(f"❌ Error analyzing video analytics: {e}")
        return {'error': f'Analysis failed: {e}'}


def has_youtube_content(text: str) -> bool:
    """Check if text contains YouTube-related content"""
    youtube_urls = extract_youtube_urls(text)
    return len(youtube_urls) > 0 or "youtube" in text.lower()
