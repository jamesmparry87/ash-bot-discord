"""
Bulk Update Twitch Stats for All Games
Date: 2025-12-26
Purpose: Update watch time and view stats for all Twitch-sourced games using game_id grouping
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.database_module import get_database
from bot.integrations.twitch import parse_twitch_duration
import aiohttp


async def fetch_all_channel_vods(username: str, session: aiohttp.ClientSession, headers: dict) -> List[Dict[str, Any]]:
    """
    Fetch ALL VODs from a Twitch channel with pagination.
    
    Returns list of VODs with game_id, game_name, duration, views, etc.
    """
    # Get user ID first
    user_url = f"https://api.twitch.tv/helix/users?login={username}"
    
    async with session.get(user_url, headers=headers) as response:
        if response.status != 200:
            error_text = await response.text()
            print(f"❌ Failed to get user ID: {response.status}")
            print(f"   Response: {error_text}")
            return []
        
        user_data = await response.json()
        if not user_data.get('data'):
            print(f"❌ User '{username}' not found")
            return []
        
        user_id = user_data['data'][0]['id']
        print(f"✅ Found user ID: {user_id}")
    
    # Fetch ALL VODs with pagination
    all_vods = []
    cursor = None
    page = 0
    
    while True:
        page += 1
        videos_url = "https://api.twitch.tv/helix/videos"
        params = {
            "user_id": user_id,
            "first": 100,  # Max per page
            "type": "archive"
        }
        
        if cursor:
            params['after'] = cursor
        
        print(f"📡 Fetching page {page}...", end=" ")
        
        async with session.get(videos_url, params=params, headers=headers) as response:
            if response.status != 200:
                error_text = await response.text()
                print(f"\n❌ Failed to fetch VODs: {response.status}")
                print(f"   Response: {error_text}")
                break
            
            videos_data = await response.json()
            vods = videos_data.get('data', [])
            
            if not vods:
                print("(no more VODs)")
                break
            
            print(f"({len(vods)} VODs)")
            all_vods.extend(vods)
            
            # Check for next page
            cursor = videos_data.get('pagination', {}).get('cursor')
            if not cursor:
                break
            
            # Rate limiting
            await asyncio.sleep(0.2)
    
    print(f"✅ Total VODs fetched: {len(all_vods)}")
    return all_vods


async def fetch_game_names_bulk(game_ids: List[str], session: aiohttp.ClientSession, headers: dict) -> Dict[str, str]:
    """
    Fetch game names for multiple game IDs in bulk (max 100 per request).
    
    Returns dict mapping game_id -> game_name
    """
    game_name_map = {}
    
    # Process in chunks of 100 (Twitch API limit)
    for i in range(0, len(game_ids), 100):
        chunk = game_ids[i:i+100]
        
        games_url = "https://api.twitch.tv/helix/games"
        params = {"id": chunk}
        
        async with session.get(games_url, params=params, headers=headers) as response:
            if response.status == 200:
                games_data = await response.json()
                for game in games_data.get('data', []):
                    game_name_map[game['id']] = game['name']
            else:
                print(f"  ⚠️ Failed to fetch game names for chunk")
        
        await asyncio.sleep(0.2)  # Rate limiting
    
    return game_name_map


async def bulk_update_twitch_stats():
    """Main function to update all Twitch game stats"""
    print("=" * 80)
    print("📺 BULK TWITCH STATS UPDATE")
    print("=" * 80)
    
    # Check API credentials
    twitch_client_id = os.getenv('TWITCH_CLIENT_ID', '').strip()
    twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET', '').strip()
    
    if not twitch_client_id or not twitch_client_secret:
        print("❌ TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET required")
        print("   Set environment variables")
        return
    
    # Twitch channel to sync
    twitch_username = "jonesyspacecat"  # Update if needed
    
    async with aiohttp.ClientSession() as session:
        # Get OAuth token
        print("\n🔑 Authenticating with Twitch...")
        token_url = "https://id.twitch.tv/oauth2/token"
        token_params = {
            'client_id': twitch_client_id,
            'client_secret': twitch_client_secret,
            'grant_type': 'client_credentials'
        }
        
        async with session.post(token_url, params=token_params) as response:
            if response.status != 200:
                error_text = await response.text()
                print(f"❌ Failed to get OAuth token: {response.status}")
                print(f"   Response: {error_text}")
                return
            
            token_info = await response.json()
            access_token = token_info['access_token']
        
        headers = {
            "Client-ID": twitch_client_id,
            "Authorization": f"Bearer {access_token}"
        }
        
        # Fetch all VODs
        print(f"\n📡 Fetching all VODs from '{twitch_username}'...")
        all_vods = await fetch_all_channel_vods(twitch_username, session, headers)
        
        if not all_vods:
            print("❌ No VODs found")
            return
        
        # DEBUG: Print RAW JSON for first VOD to see ALL fields
        print(f"\n🔍 DEBUG: RAW JSON for first VOD...")
        print("=" * 80)
        if all_vods:
            import json
            print(json.dumps(all_vods[0], indent=2))
        print("=" * 80)
        
        # DEBUG: Print first 3 VODs to see what fields are available
        print(f"\n🔍 DEBUG: Showing first 3 VOD structures...")
        for i, vod in enumerate(all_vods[:3], 1):
            print(f"\n  VOD {i}:")
            print(f"    Title: {vod.get('title', 'N/A')[:50]}")
            print(f"    game_id: '{vod.get('game_id', 'MISSING')}'")
            print(f"    game_name: '{vod.get('game_name', 'MISSING')}'")
            print(f"    type: {vod.get('type', 'N/A')}")
            print(f"    Available fields: {list(vod.keys())}")
        
        # Group VODs by game (using game_name as primary, game_id as fallback)
        print(f"\n🎮 Grouping VODs by game...")
        game_groups = defaultdict(list)
        no_game_info_count = 0
        
        for vod in all_vods:
            # Try game_name first (newer API field, more reliable)
            game_name = vod.get('game_name', '').strip()
            game_id = vod.get('game_id', '').strip()
            
            # Skip VODs without any game info
            if not game_name and (not game_id or game_id == '0'):
                no_game_info_count += 1
                print(f"    ⚠️ No game info: '{vod.get('title', 'Unknown')[:40]}'")
                continue
            
            # Use game_name as the grouping key (it's what we'll match against database)
            # If game_name is empty but game_id exists, we'll look it up later
            group_key = game_name if game_name else f"ID:{game_id}"
            game_groups[group_key].append(vod)
        
        print(f"✅ Found {len(game_groups)} unique games")
        print(f"⚠️ Skipped {no_game_info_count} VODs without game info")
        
        # Resolve any game_ids that we used as keys (format: "ID:12345")
        print(f"\n📝 Resolving game names for ID-only entries...")
        id_only_keys = [key for key in game_groups.keys() if key.startswith('ID:')]
        
        if id_only_keys:
            print(f"   Found {len(id_only_keys)} games with only ID")
            game_ids_to_lookup = [key.replace('ID:', '') for key in id_only_keys]
            game_name_map = await fetch_game_names_bulk(game_ids_to_lookup, session, headers)
            
            # Replace ID keys with actual game names
            for id_key in id_only_keys:
                game_id = id_key.replace('ID:', '')
                game_name = game_name_map.get(game_id, f"Unknown Game (ID: {game_id})")
                game_groups[game_name] = game_groups.pop(id_key)
            
            print(f"   ✅ Resolved {len(game_name_map)} game names")
        else:
            print(f"   ✅ All games already have names from API")
        
        # Calculate stats per game
        print(f"\n📊 Calculating stats per game...")
        game_stats = {}
        
        for game_name, vods in game_groups.items():
            total_watch_minutes = 0
            total_views = 0
            vod_urls = []
            
            for vod in vods:
                # Calculate duration
                duration_str = vod.get('duration', '0s')
                duration_seconds = parse_twitch_duration(duration_str)
                total_watch_minutes += duration_seconds // 60
                
                # Sum views
                total_views += int(vod.get('view_count', 0))
                
                # Collect VOD URLs (limit to 10 per game)
                if len(vod_urls) < 10:
                    vod_urls.append(vod['url'].split('?')[0])
            
            game_stats[game_name] = {
                'total_episodes': len(vods),
                'total_watch_minutes': total_watch_minutes,
                'total_views': total_views,
                'vod_urls': vod_urls
            }
        
        # Update database
        print(f"\n💾 Updating database...")
        db = get_database()
        
        # Get all games with Twitch VODs
        all_games = db.get_all_played_games()
        twitch_games = [g for g in all_games if g.get('twitch_vod_urls')]
        
        print(f"   Database has {len(twitch_games)} games with Twitch data")
        
        updated_count = 0
        not_found_count = 0
        
        # Match and update
        for game_name, stats in game_stats.items():
            # Try to find matching game in database
            db_game = db.get_played_game(game_name)
            
            if not db_game:
                print(f"   ⚠️ '{game_name}' not in database ({stats['total_episodes']} VODs, {stats['total_watch_minutes']//60}h)")
                not_found_count += 1
                continue
            
            game_id_db = db_game.get('id')
            
            if not game_id_db:
                print(f"   ⚠️ '{game_name}' has no ID, skipping")
                continue
            
            # Update with fresh stats
            success = db.update_played_game(
                game_id_db,
                total_episodes=stats['total_episodes'],
                total_playtime_minutes=stats['total_watch_minutes'],
                twitch_vod_urls=stats['vod_urls']
            )
            
            if success:
                print(f"   ✅ {game_name}: {stats['total_watch_minutes']//60}h {stats['total_watch_minutes']%60}m ({stats['total_episodes']} VODs)")
                updated_count += 1
            else:
                print(f"   ❌ Failed to update '{game_name}'")
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 UPDATE SUMMARY")
    print("=" * 80)
    print(f"✅ Successfully updated: {updated_count} games")
    print(f"⚠️ Not in database: {not_found_count} games")
    print(f"📺 Total VODs processed: {len(all_vods)}")
    print(f"🎮 Unique games found: {len(game_stats)}")
    print("\n✅ Twitch stats update complete!")


if __name__ == "__main__":
    asyncio.run(bulk_update_twitch_stats())
