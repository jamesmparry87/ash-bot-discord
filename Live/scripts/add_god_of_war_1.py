"""
Add Missing God of War 1 Entry from YouTube Playlist
Date: 2025-12-26
Purpose: Import God of War 1 data from YouTube playlist
"""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import aiohttp
    from bot.database_module import get_database
    from bot.integrations import igdb
    from bot.integrations.youtube import get_playlist_videos_with_views, parse_youtube_duration
except ImportError as e:
    print(f"❌ Import Error: {e}")
    sys.exit(1)


async def extract_playlist_id(playlist_url):
    """Extract playlist ID from YouTube URL"""
    import re
    match = re.search(r'[?&]list=([a-zA-Z0-9_-]+)', playlist_url)
    if match:
        return match.group(1)
    return None


async def fetch_playlist_data(playlist_url):
    """Fetch complete data for YouTube playlist"""
    youtube_api_key = os.getenv('YOUTUBE_API_KEY', '').strip()
    
    if not youtube_api_key:
        print("❌ YOUTUBE_API_KEY not configured")
        print("   Run with: export YOUTUBE_API_KEY=...")
        return None
    
    playlist_id = await extract_playlist_id(playlist_url)
    
    if not playlist_id:
        print("❌ Could not extract playlist ID from URL")
        return None
    
    print(f"📋 Playlist ID: {playlist_id}")
    
    async with aiohttp.ClientSession() as session:
        try:
            # Get playlist details
            print("🔄 Fetching playlist metadata...")
            playlist_info_url = f"https://www.googleapis.com/youtube/v3/playlists"
            params = {
                'part': 'snippet,contentDetails',
                'id': playlist_id,
                'key': youtube_api_key
            }
            
            async with session.get(playlist_info_url, params=params) as response:
                if response.status != 200:
                    print(f"❌ YouTube API error: {response.status}")
                    text = await response.text()
                    print(f"   Response: {text}")
                    return None
                
                playlist_data = await response.json()
                
                if not playlist_data.get('items'):
                    print("❌ Playlist not found")
                    return None
                
                playlist_info = playlist_data['items'][0]
                playlist_title = playlist_info['snippet']['title']
                video_count = playlist_info['contentDetails']['itemCount']
                
                print(f"✅ Playlist: {playlist_title}")
                print(f"   Videos: {video_count}")
            
            # Get videos with view data
            print("\n🔄 Fetching video data with views...")
            videos_data = await get_playlist_videos_with_views(session, playlist_id, youtube_api_key)
            
            if not videos_data:
                print("❌ Failed to fetch video data")
                return None
            
            # Calculate totals
            total_views = sum(v.get('view_count', 0) for v in videos_data)
            total_duration_seconds = sum(v.get('duration_seconds', 0) for v in videos_data)
            total_duration_minutes = total_duration_seconds // 60
            
            # Get first video date
            first_video_date = None
            if videos_data:
                first_video_date = videos_data[0].get('published_at')
                if first_video_date:
                    first_video_date = datetime.fromisoformat(first_video_date.replace('Z', '+00:00')).date()
            
            print(f"\n📊 Calculated Data:")
            print(f"   Total Episodes: {len(videos_data)}")
            print(f"   Total Views: {total_views:,}")
            print(f"   Total Duration: {total_duration_minutes // 60}h {total_duration_minutes % 60}m")
            print(f"   First Published: {first_video_date}")
            
            return {
                'playlist_id': playlist_id,
                'playlist_title': playlist_title,
                'playlist_url': f"https://youtube.com/playlist?list={playlist_id}",
                'total_episodes': len(videos_data),
                'total_views': total_views,
                'total_playtime_minutes': total_duration_minutes,
                'first_played_date': first_video_date,
                'videos': videos_data
            }
        
        except Exception as e:
            print(f"❌ Error fetching playlist data: {e}")
            return None


async def add_god_of_war_1():
    """Main function to add God of War 1 entry"""
    print("=" * 80)
    print("🎮 GOD OF WAR 1 - MISSING ENTRY IMPORT")
    print("=" * 80)
    
    # Playlist URL
    playlist_url = "https://www.youtube.com/watch?v=QRVOiw3Ct6k&list=PLxgSRpBG9HcKr1GCOBHWCFOWF_lqKK9tU&pp=0gcJCbEEOCosWNin"
    
    print(f"\n📋 Processing YouTube playlist...")
    
    # Fetch playlist data
    playlist_data = await fetch_playlist_data(playlist_url)
    
    if not playlist_data:
        print("❌ Failed to fetch playlist data. Exiting.")
        return
    
    # Manual Data (Because IGDB credentials might be missing)
    target_name = "God of War (2005)"
    series_name = "God of War"
    genre = "Hack and slash/Beat 'em up"
    release_year = 2005
    alternative_names = ["GoW 1", "God of War 1", "God of War I"]
    
    print("\n" + "=" * 80)
    print("📝 DATA PREPARATION")
    print("=" * 80)
    print(f"✅ Target Name: '{target_name}'")
    print(f"   Genre: {genre}")
    print(f"   Series: {series_name}")
    print(f"   Release Year: {release_year}")
    
    # Check if game already exists
    db = get_database()
    
    print("\n" + "=" * 80)
    print("🔧 DATABASE OPERATIONS")
    print("=" * 80)
    
    # Check for the NEW name
    print(f"Checking database for '{target_name}'...")
    existing = db.get_played_game(target_name)
    
    if existing:
        # STRICT CHECK: Only abort if the name is an EXACT match
        if existing.get('canonical_name', '').lower() == target_name.lower():
            print(f"⚠️ Game already exists: {existing.get('canonical_name')} (id: {existing.get('id')})")
            print("❌ Aborting to prevent duplicates.")
            return
        else:
            # Fuzzy match found (e.g., God of War II), but we want to ignore it
            print(f"ℹ️ Fuzzy match found: '{existing.get('canonical_name')}' (id: {existing.get('id')})")
            print(f"   ...but we are adding '{target_name}', so we will PROCEED.")
    
    # Prepare data
    notes = f"God of War (2005) - Original PS2 game. YouTube playthrough with {playlist_data['total_episodes']} episodes."
    
    # Add to database
    print(f"\nAdding '{target_name}' to database...")
    
    success = db.add_played_game(
        canonical_name=target_name,
        alternative_names=alternative_names,
        series_name=series_name,
        genre=genre,
        release_year=release_year,
        first_played_date=playlist_data['first_played_date'],
        completion_status='completed',
        total_episodes=playlist_data['total_episodes'],
        total_playtime_minutes=playlist_data['total_playtime_minutes'],
        youtube_playlist_url=playlist_data['playlist_url'],
        youtube_views=playlist_data['total_views'],
        notes=notes
    )
    
    if success:
        print(f"✅ Successfully added {target_name} to database")
        
        # Verify
        new_entry = db.get_played_game(target_name)
        # We need to filter again because get_played_game might still return the fuzzy match if we are unlucky,
        # but the INSERT should have worked.
        
        if new_entry:
            print(f"\n📋 Database Confirmation:")
            # If get_played_game returns the fuzzy match (GoW II), try to fetch the new one manually or just trust the success bool
            if new_entry.get('canonical_name') != target_name:
                 print(f"   (Note: 'get_played_game' returned '{new_entry.get('canonical_name')}' due to fuzzy search, but insert was successful.)")
            else:
                 print(f"   ID: {new_entry.get('id')}")
                 print(f"   Name: {new_entry.get('canonical_name')}")
                 print(f"   Views: {new_entry.get('youtube_views'):,}")
    else:
        print("❌ Failed to add entry to database (SQL Error)")
    
    print("\n" + "=" * 80)
    print("✅ GOD OF WAR 1 IMPORT COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(add_god_of_war_1())