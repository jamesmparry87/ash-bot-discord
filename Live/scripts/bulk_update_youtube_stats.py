"""
Bulk Update YouTube Stats for All Games
Date: 2025-12-26
Purpose: Update view counts for all games with YouTube playlists
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.database_module import get_database
from bot.integrations.youtube import get_playlist_videos_with_views
import aiohttp


async def fetch_youtube_playlist_stats(playlist_id: str, youtube_api_key: str, session: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
    """
    Fetch current stats for a YouTube playlist.
    
    Returns:
        dict with total_views, total_videos, total_duration_minutes
    """
    try:
        videos = await get_playlist_videos_with_views(session, playlist_id, youtube_api_key)
        
        if not videos:
            return None
        
        total_views = sum(v.get('view_count', 0) for v in videos)
        total_videos = len(videos)
        total_duration_seconds = sum(v.get('duration_seconds', 0) for v in videos)
        total_duration_minutes = total_duration_seconds // 60
        
        return {
            'total_views': total_views,
            'total_videos': total_videos,
            'total_duration_minutes': total_duration_minutes
        }
    except Exception as e:
        print(f"  ❌ Error fetching playlist: {e}")
        return None


async def bulk_update_youtube_stats():
    """Main function to update all YouTube game stats"""
    print("=" * 80)
    print("📺 BULK YOUTUBE STATS UPDATE")
    print("=" * 80)
    
    # Check API credentials
    youtube_api_key = os.getenv('YOUTUBE_API_KEY')
    if not youtube_api_key:
        print("❌ YOUTUBE_API_KEY not configured")
        print("   Set environment variable: export YOUTUBE_API_KEY=...")
        return
    
    # Get database
    db = get_database()
    
    # Fetch all games with YouTube playlists
    print("\n🔍 Fetching games with YouTube playlists...")
    
    all_games = db.get_all_played_games()
    youtube_games = [g for g in all_games if g.get('youtube_playlist_url')]
    
    print(f"✅ Found {len(youtube_games)} games with YouTube playlists")
    
    if not youtube_games:
        print("ℹ️ No games with YouTube data to update")
        return
    
    # Extract playlist IDs
    import re
    
    updated_count = 0
    failed_count = 0
    skipped_count = 0
    
    async with aiohttp.ClientSession() as session:
        for i, game in enumerate(youtube_games, 1):
            game_name = game.get('canonical_name', 'Unknown')
            game_id = game.get('id')
            playlist_url = game.get('youtube_playlist_url', '')
            
            print(f"\n[{i}/{len(youtube_games)}] {game_name}")
            print(f"   Current views: {game.get('youtube_views', 0):,}")
            
            # Extract playlist ID from URL
            playlist_match = re.search(r'list=([a-zA-Z0-9_-]+)', playlist_url)
            
            if not playlist_match:
                print(f"   ⚠️ Could not extract playlist ID from URL")
                skipped_count += 1
                continue
            
            playlist_id = playlist_match.group(1)
            
            # Fetch current stats
            stats = await fetch_youtube_playlist_stats(playlist_id, youtube_api_key, session)
            
            if not stats:
                print(f"   ❌ Failed to fetch stats")
                failed_count += 1
                continue
            
            # Update database
            new_views = stats['total_views']
            old_views = game.get('youtube_views', 0) or 0
            view_change = new_views - old_views
            
            if not game_id:
                print(f"   ⚠️ No game ID found, skipping")
                skipped_count += 1
                continue
            
            success = db.update_played_game(
                game_id,
                youtube_views=new_views,
                total_episodes=stats['total_videos'],
                total_playtime_minutes=stats['total_duration_minutes']
            )
            
            if success:
                print(f"   ✅ Updated: {new_views:,} views (Δ{view_change:+,})")
                print(f"   Episodes: {stats['total_videos']}, Playtime: {stats['total_duration_minutes'] // 60}h {stats['total_duration_minutes'] % 60}m")
                updated_count += 1
            else:
                print(f"   ❌ Database update failed")
                failed_count += 1
            
            # Rate limiting (YouTube quota conservation)
            await asyncio.sleep(0.5)
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 UPDATE SUMMARY")
    print("=" * 80)
    print(f"✅ Successfully updated: {updated_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"⏭️ Skipped: {skipped_count}")
    print(f"📺 Total YouTube games: {len(youtube_games)}")
    print("\n✅ YouTube stats update complete!")


if __name__ == "__main__":
    asyncio.run(bulk_update_youtube_stats())
