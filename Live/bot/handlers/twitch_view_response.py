"""
Twitch View Query Response Handler
Date: 2025-12-26
Purpose: Handle queries about Twitch game views with appropriate metric explanations
"""

from typing import Any, Dict, Optional

from ..database_module import get_database

db = get_database()


def is_twitch_only_game(game_data: Dict[str, Any]) -> bool:
    """
    Check if a game was played exclusively on Twitch.
    
    Args:
        game_data: Game database record
        
    Returns:
        True if game has Twitch VODs but no YouTube playlist
    """
    has_twitch = bool(game_data.get('twitch_vod_urls')) and game_data.get('twitch_vod_urls') not in ['', '{}', '[]']
    has_youtube = bool(game_data.get('youtube_playlist_url'))
    
    return has_twitch and not has_youtube


def is_view_query(query: str) -> bool:
    """
    Check if user is asking about view counts/popularity.
    
    Args:
        query: User's message content (lowercase)
        
    Returns:
        True if query is about views
    """
    view_keywords = ['view', 'views', 'popular', 'popularity', 'watched', 'viewership']
    return any(keyword in query.lower() for keyword in view_keywords)


def format_twitch_view_response(game_name: str, game_data: Dict[str, Any]) -> str:
    """
    Format response for Twitch-only game view queries.
    
    Args:
        game_name: Name of the game
        game_data: Game database record
        
    Returns:
        Formatted response explaining watch time metrics
    """
    # Get watch time data
    total_playtime_minutes = game_data.get('total_playtime_minutes', 0) or 0
    total_episodes = game_data.get('total_episodes', 0) or 0
    
    # Convert to hours and minutes
    hours = total_playtime_minutes // 60
    minutes = total_playtime_minutes % 60
    
    # Build response in Ash's analytical style
    response = (
        f"📊 **Twitch Metric Analysis - {game_name}**\n\n"
        f"Captain, Twitch VOD view counts are an ineffective performance metric due to "
        f"platform volatility and data inconsistency. For Twitch content, I track **watch time** "
        f"as a more reliable indicator of engagement.\n\n"
        f"**Watch Time:** {hours}h {minutes}m ({total_playtime_minutes:,} minutes)\n"
        f"**Total VODs:** {total_episodes}\n"
    )
    
    # Add average if we have episodes
    if total_episodes > 0:
        avg_minutes = total_playtime_minutes // total_episodes
        avg_hours = avg_minutes // 60
        avg_mins = avg_minutes % 60
        response += f"**Average per VOD:** {avg_hours}h {avg_mins}m\n"
    
    response += (
        f"\n*This provides a more accurate assessment of content performance than "
        f"transient view counters. Watch time metrics are consistent and reliable across "
        f"all streaming platforms.*"
    )
    
    return response


def handle_game_view_query(game_name: str, query: str) -> Optional[str]:
    """
    Main handler for game view queries.
    
    Checks if user is asking about views for a Twitch-only game and returns
    appropriate response. Returns None if not applicable.
    
    Args:
        game_name: Name of the game being queried
        query: User's full query text
        
    Returns:
        Formatted response if this is a Twitch view query, None otherwise
    """
    # Check if this is a view-related query
    if not is_view_query(query):
        return None
    
    # Get game data
    game_data = db.get_played_game(game_name)
    
    if not game_data:
        return None
    
    # Check if this is a Twitch-only game
    if not is_twitch_only_game(game_data):
        return None
    
    # Format and return the Twitch view response
    return format_twitch_view_response(game_name, game_data)


def get_platform_info(game_name: str) -> Optional[Dict[str, Any]]:
    """
    Get platform information for a game.
    
    Args:
        game_name: Name of the game
        
    Returns:
        Dict with platform info: {
            'platform': 'youtube'|'twitch'|'both'|'unknown',
            'has_view_data': bool,
            'total_playtime_minutes': int,
            'total_episodes': int,
            'youtube_views': int (if applicable)
        }
    """
    game_data = db.get_played_game(game_name)
    
    if not game_data:
        return None
    
    has_youtube = bool(game_data.get('youtube_playlist_url'))
    has_twitch = bool(game_data.get('twitch_vod_urls')) and game_data.get('twitch_vod_urls') not in ['', '{}', '[]']
    
    # Determine platform
    if has_youtube and has_twitch:
        platform = 'both'
    elif has_youtube:
        platform = 'youtube'
    elif has_twitch:
        platform = 'twitch'
    else:
        platform = 'unknown'
    
    return {
        'platform': platform,
        'has_view_data': has_youtube,  # Only YouTube has reliable view data
        'total_playtime_minutes': game_data.get('total_playtime_minutes', 0) or 0,
        'total_episodes': game_data.get('total_episodes', 0) or 0,
        'youtube_views': game_data.get('youtube_views', 0) or 0 if has_youtube else None
    }
